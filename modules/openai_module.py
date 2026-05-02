import openai
from typing import Dict, Any, Callable, Optional, AsyncGenerator
from .base_module import BaseModule
from api_key_manager import ApiKeyManager
from proxy_manager import ProxyManager, ProxyConfig
import asyncio
import logging
import io
from fastapi import HTTPException
import json

from handlers.misc.one_messager import reformat_messages
from admin_router import get_reformat_settings
from utils.config_store import read_json
from .key_cycle_utils import init_first_cycle_key, rotate_key_and_detect_full_cycle
from .retry_utils import map_openai_exception_to_status, advance_proxy_or_key, with_reason, raise_http_with_reason

logger = logging.getLogger(__name__)

class OpenAIChatModule(BaseModule):
    def __init__(self, api_key_manager: ApiKeyManager, proxy_manager: ProxyManager, settings_file_path: str, service_name: str = "openai"):
        self.api_key_manager = api_key_manager
        self.proxy_manager = proxy_manager
        self.settings_file_path = settings_file_path
        self.service_name = service_name
        self.openai_sdk_lock = asyncio.Lock()
        self.last_api_key_used_for_proxy_context: Optional[str] = None
        self.first_key_in_overall_cycle: Optional[str] = None
        self.key_loop_initial_run: bool = True

    def get_name(self) -> str:
        return self.service_name

    def _format_proxy_for_openai_sdk(self, proxy_config: Optional[ProxyConfig]) -> Optional[str]:
        if proxy_config:
            return proxy_config['url']
        return None

    def _load_settings_snapshot(self) -> Dict[str, Any]:
        settings = read_json(self.settings_file_path, {})
        return settings if isinstance(settings, dict) else {}

    def _use_global_proxy_for_module(self) -> bool:
        settings = self._load_settings_snapshot()
        return settings.get("module_proxy_usage", {}).get(self.service_name, True)

    def _is_force_proxy_rotation_enabled(self) -> bool:
        settings = self._load_settings_snapshot()
        return settings.get("proxy_settings", {}).get("force_proxy_rotation_after_request", False)

    def _maybe_force_rotate_proxy_after_success(self):
        if not self._is_force_proxy_rotation_enabled():
            return
        if self.proxy_manager.current_rotation_mode == "failover_cycle":
            return
        if self.proxy_manager.select_random_proxy_each_request:
            return
        if self.proxy_manager.active and self.proxy_manager.proxies:
            logger.debug("Force rotating proxy after successful call as per settings (OpenAI).")
            self.proxy_manager.rotate_proxy()

    async def _execute_with_rotation(self, sync_api_call_func: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        key_exhausted_message = f"All API keys for {self.service_name} are exhausted or failed."
        self.first_key_in_overall_cycle, self.key_loop_initial_run = init_first_cycle_key(
            self.api_key_manager,
            self.service_name,
            self.first_key_in_overall_cycle,
            self.key_loop_initial_run,
        )

        key_was_rotated_in_current_api_call = False
        while True:
            current_api_key = self.api_key_manager.get_key(self.service_name)
            if not current_api_key:
                raise_http_with_reason(503, key_exhausted_message, "No keys available at start of key loop", logger)

            if self.last_api_key_used_for_proxy_context != current_api_key or key_was_rotated_in_current_api_call:
                logger.debug(f"API key changed or rotated for {self.service_name}. Old: {self.last_api_key_used_for_proxy_context}, New: {current_api_key}. Resetting proxies.")
                self.proxy_manager.reset_proxies()
                self.last_api_key_used_for_proxy_context = current_api_key
                if key_was_rotated_in_current_api_call:
                    key_was_rotated_in_current_api_call = False
            else:
                logger.debug(f"API key ...{current_api_key[-4:]} is the same as last used. Proxy context preserved for {self.service_name}.")

            while True:
                current_proxy_config = None
                # INDIVIDUAL module proxy logic
                use_global_proxy = self._use_global_proxy_for_module()

                if use_global_proxy and self.proxy_manager.active:
                    current_proxy_config = self.proxy_manager.get_proxy()

                async with self.openai_sdk_lock:
                    openai.api_key = current_api_key
                    openai.proxy = self._format_proxy_for_openai_sdk(current_proxy_config)
                    proxy_url_for_log = current_proxy_config['url'] if current_proxy_config else "None (Direct)"
                    logger.debug(f"Attempting API call for {self.service_name} with key ...{current_api_key[-4:]} and proxy {proxy_url_for_log}")

                    try:
                        result = await asyncio.to_thread(sync_api_call_func)
                        logger.info(f"API call successful for {self.service_name} with key ...{current_api_key[-4:]} and proxy {proxy_url_for_log}.")
                        self._maybe_force_rotate_proxy_after_success()
                        return result
                    except (openai.error.AuthenticationError, openai.error.PermissionError) as e:
                        logger.warning(f"Key error for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {type(e).__name__}. Rotating key.")
                        previous_key_for_check = current_api_key
                        rotated, full_cycle_completed = rotate_key_and_detect_full_cycle(
                            self.api_key_manager,
                            self.service_name,
                            self.first_key_in_overall_cycle,
                            previous_key_for_check,
                        )
                        if not rotated:
                            raise_http_with_reason(503, key_exhausted_message, "No keys to rotate to after auth error", logger)
                        key_was_rotated_in_current_api_call = True
                        if full_cycle_completed:
                            logger.warning(f"Completed a full cycle of API keys for {self.service_name} due to {type(e).__name__}. All keys failed. Raising final exception.")
                            raise HTTPException(status_code=503, detail=with_reason(key_exhausted_message, f"Full key cycle for {type(e).__name__}"))
                        break
                    except openai.error.InvalidRequestError as e:
                        logger.error(f"Invalid request to OpenAI for {self.service_name}: {e}")
                        raise HTTPException(status_code=400, detail=f"Invalid request to OpenAI: {str(e)}")
                    except openai.error.OpenAIError as e:
                        logger.warning(f"OpenAI API Error for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {type(e).__name__} - {str(e)}. Attempting proxy rotation.")
                        status_code_val = map_openai_exception_to_status(e, openai)
                        rotation_outcome, full_cycle_completed = advance_proxy_or_key(
                            self.proxy_manager,
                            self.api_key_manager,
                            self.service_name,
                            self.first_key_in_overall_cycle,
                            current_api_key,
                        )
                        if rotation_outcome == "proxy_rotated":
                            logger.info(f"Successfully rotated to next proxy for key ...{current_api_key[-4:]}. Retrying.")
                            continue
                        logger.warning(f"Failed to rotate proxy or proxies exhausted for key ...{current_api_key[-4:]}. Attempting key rotation.")
                        if rotation_outcome == "key_exhausted":
                            raise_http_with_reason(
                                status_code_val,
                                key_exhausted_message,
                                f"Error type: {type(e).__name__} on all proxies/keys, no keys to rotate to",
                                logger,
                            )
                        key_was_rotated_in_current_api_call = True
                        if full_cycle_completed:
                            logger.warning(f"Completed a full cycle of API keys for {self.service_name} due to {type(e).__name__}. All keys failed. Raising final exception.")
                            final_error_message = with_reason(key_exhausted_message, f"Full key cycle for {type(e).__name__}")
                            raise HTTPException(status_code=status_code_val, detail=final_error_message)
                        break
                    except Exception as e:
                        logger.error(f"Unexpected non-OpenAI error during API call for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {type(e).__name__} - {str(e)}. Attempting proxy rotation first.")
                        rotation_outcome, full_cycle_completed = advance_proxy_or_key(
                            self.proxy_manager,
                            self.api_key_manager,
                            self.service_name,
                            self.first_key_in_overall_cycle,
                            current_api_key,
                        )
                        if rotation_outcome == "proxy_rotated":
                            logger.info(f"Successfully rotated to next proxy for key ...{current_api_key[-4:]} after unexpected error. Retrying.")
                            continue
                        logger.warning(f"Failed to rotate proxy or proxies exhausted for key ...{current_api_key[-4:]} after unexpected error. Attempting key rotation.")
                        if rotation_outcome == "key_exhausted":
                            raise_http_with_reason(
                                500,
                                key_exhausted_message,
                                f"Unexpected Error type: {type(e).__name__} on all proxies/keys, no keys to rotate to",
                                logger,
                            )
                        key_was_rotated_in_current_api_call = True
                        if full_cycle_completed:
                            logger.warning(f"Completed a full cycle of API keys for {self.service_name} due to unexpected {type(e).__name__}. All keys failed. Raising final exception.")
                            raise HTTPException(status_code=500, detail=with_reason(key_exhausted_message, f"Full key cycle for unexpected {type(e).__name__}"))
                        break

                if not self.proxy_manager.active:
                    logger.debug(f"Proxies disabled or not loaded. Attempted direct call for key ...{current_api_key[-4:]}. Rotating key if call failed and not already rotated.")
                    previous_key_for_check = current_api_key
                    rotated, full_cycle_completed = rotate_key_and_detect_full_cycle(
                        self.api_key_manager,
                        self.service_name,
                        self.first_key_in_overall_cycle,
                        previous_key_for_check,
                    )
                    if not rotated:
                        raise_http_with_reason(503, key_exhausted_message, "Direct call failed, no keys to rotate to", logger)
                    key_was_rotated_in_current_api_call = True
                    if full_cycle_completed:
                        logger.warning(f"Completed a full cycle of API keys for {self.service_name} (direct call failed for last key). All keys failed.")
                        raise HTTPException(status_code=503, detail=with_reason(key_exhausted_message, "Full key cycle, direct calls failed"))
                    break

                if current_proxy_config is None and self.proxy_manager.proxies:
                     logger.debug(f"All proxies tried for key ...{current_api_key[-4:]}. Rotating key.")
                     previous_key_for_check = current_api_key
                     rotated, full_cycle_completed = rotate_key_and_detect_full_cycle(
                         self.api_key_manager,
                         self.service_name,
                         self.first_key_in_overall_cycle,
                         previous_key_for_check,
                     )
                     if not rotated:
                         raise_http_with_reason(503, key_exhausted_message, "All proxies tried, no keys to rotate to", logger)
                     key_was_rotated_in_current_api_call = True
                     if full_cycle_completed:
                         logger.warning(f"Completed a full cycle of API keys for {self.service_name} (all proxies tried for last key). All keys failed.")
                         raise HTTPException(status_code=503, detail=with_reason(key_exhausted_message, "Full key cycle, all proxies tried"))
                     break

    async def chat_completion(self, request: Dict[str, Any]) -> Dict[str, Any]:
        payload_to_send = dict(request)
        
        reformat_settings = get_reformat_settings()
        module_reformat_settings = reformat_settings.get(self.get_name(), {})
        
        # model_id в настройках хранится как "module_name/model_id"
        # Здесь model_id - это просто имя модели, например "gpt-3.5-turbo"
        # Поэтому нужно проверять по payload_to_send.get("model") и self.get_name().
        
        if module_reformat_settings.get(payload_to_send.get("model", ""), False):
            logger.debug(f"Reformat messages enabled for model '{payload_to_send.get('model')}' in module '{self.get_name()}'. Applying reformat_messages.")
            if "messages" in payload_to_send:
                reformatted_json = await reformat_messages(json.dumps(payload_to_send, ensure_ascii=False))
                payload_to_send = json.loads(reformatted_json)
            else:
                logger.warning(f"Reformat messages enabled for model '{payload_to_send.get('model')}', but no 'messages' found in payload.")

        return await self._execute_with_rotation(lambda: openai.ChatCompletion.create(**payload_to_send))

    async def completion(self, request: Dict[str, Any]) -> Dict[str, Any]:
        payload_to_send = dict(request)

        reformat_settings = get_reformat_settings()
        module_reformat_settings = reformat_settings.get(self.get_name(), {})

        if module_reformat_settings.get(payload_to_send.get("model", ""), False):
            logger.debug(f"Reformat messages enabled for model '{payload_to_send.get('model')}' in module '{self.get_name()}'. Applying reformat_messages.")
            if "prompt" in payload_to_send:
                # Для completions, reformat_messages может быть применена к prompt
                # Однако, reformat_messages предназначена для списка сообщений.
                # Если prompt - это строка, то reformat_messages не применима напрямую.
                # Если prompt - это список строк, то можно объединить.
                # Предполагаем, что reformat_messages работает с форматом сообщений чата.
                # Для completions, если prompt - это строка, то reformat_messages не имеет смысла.
                # Если prompt - это список строк, то можно объединить.
                # Пока не буду применять reformat_messages к prompt в completions,
                # так как это может быть несовместимо с ожидаемым форматом.
                # Если пользователь явно хочет, чтобы reformat_messages работала с prompt,
                # нужно будет адаптировать reformat_messages или добавить отдельную логику.
                logger.warning(f"Reformat messages enabled for model '{payload_to_send.get('model')}' in completions, but 'reformat_messages' is designed for chat messages. Skipping reformatting for 'prompt'.")
            else:
                logger.warning(f"Reformat messages enabled for model '{payload_to_send.get('model')}' in completions, but no 'prompt' found in payload.")

        return await self._execute_with_rotation(lambda: openai.Completion.create(**payload_to_send))

    async def embeddings(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return await self._execute_with_rotation(lambda: openai.Embedding.create(**request))

    async def list_models(self) -> Dict[str, Any]:
        return await self._execute_with_rotation(lambda: openai.Model.list())

    async def retrieve_model(self, model_id: str) -> Dict[str, Any]:
        return await self._execute_with_rotation(lambda: openai.Model.retrieve(model_id))

    async def moderations(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return await self._execute_with_rotation(lambda: openai.Moderation.create(**request))

    async def generate_image(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return await self._execute_with_rotation(lambda: openai.Image.create(**request))

    async def generate_image_edit(
        self,
        request_params: Dict[str, Any],
        image_data: bytes,
        image_filename: str,
        mask_data: Optional[bytes] = None,
        mask_filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        req_copy = request_params.copy()
        with io.BytesIO(image_data) as image_file:
            image_file.name = image_filename or "image.png"
            if mask_data is not None:
                with io.BytesIO(mask_data) as mask_file:
                    mask_file.name = mask_filename or "mask.png"
                    return await self._execute_with_rotation(
                        lambda: openai.Image.create_edit(image=image_file, mask=mask_file, **req_copy)
                    )
            return await self._execute_with_rotation(
                lambda: openai.Image.create_edit(image=image_file, **req_copy)
            )

    async def generate_image_variation(
        self,
        request_params: Dict[str, Any],
        image_data: bytes,
        image_filename: str,
    ) -> Dict[str, Any]:
        req_copy = request_params.copy()
        with io.BytesIO(image_data) as image_file:
            image_file.name = image_filename or "image.png"
            return await self._execute_with_rotation(
                lambda: openai.Image.create_variation(image=image_file, **req_copy)
            )

    async def audio_transcription(self, request: Dict[str, Any], file_data: bytes, filename: Optional[str] = None) -> Dict[str, Any]:
        req_copy = request.copy()
        filename_to_use = filename or req_copy.pop("filename", "audio.mp3")
        with io.BytesIO(file_data) as audio_file:
            audio_file.name = filename_to_use
            return await self._execute_with_rotation(
                lambda: openai.Audio.transcribe(file=audio_file, **req_copy)
            )

    async def audio_translation(self, request: Dict[str, Any], file_data: bytes, filename: Optional[str] = None) -> Dict[str, Any]:
        req_copy = request.copy()
        filename_to_use = filename or req_copy.pop("filename", "audio.mp3")
        with io.BytesIO(file_data) as audio_file:
            audio_file.name = filename_to_use
            return await self._execute_with_rotation(
                lambda: openai.Audio.translate(file=audio_file, **req_copy)
            )

    async def audio_speech(self, request: Dict[str, Any]) -> Dict[str, Any]:
        raise HTTPException(
            status_code=501,
            detail="audio/speech is not supported by legacy openai<1 SDK module. Use OAIC provider.",
        )

    async def responses(self, request: Dict[str, Any]) -> Dict[str, Any]:
        if "messages" in request or "input" in request:
            mapped = dict(request)
            if "input" in mapped and "messages" not in mapped:
                mapped["messages"] = [{"role": "user", "content": str(mapped["input"])}]
            return await self.chat_completion(mapped)
        raise HTTPException(
            status_code=501,
            detail="responses endpoint needs messages/input for legacy openai module.",
        )
