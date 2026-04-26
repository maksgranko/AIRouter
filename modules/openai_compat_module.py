import httpx
from typing import Dict, Any, Optional, AsyncGenerator, List

from .base_module import BaseModule
from api_key_manager import ApiKeyManager
from proxy_manager import ProxyManager, ProxyConfig
import logging
from fastapi import HTTPException
import json

from handlers.misc.one_messager import reformat_messages
from admin_router import get_reformat_settings, get_smart_context_zipper_settings
from handlers.misc.libs.tokenizer.main import get_token_count
from handlers.misc.s200_handler import check_string_for_errors,FilteredStreamContentException
from .oaic_routing import (
    parse_instance_and_model_id as parse_oaic_instance_and_model_id,
    get_instance_config as get_oaic_instance_config,
    parse_target_reference as parse_oaic_target_reference,
    resolve_model_targets as resolve_oaic_model_targets,
    build_failsafe_chain as build_oaic_failsafe_chain,
)
from .httpx_client_utils import get_httpx_proxies, build_async_client_args

logger = logging.getLogger(__name__)


class OpenAICompatModule(BaseModule):

    @staticmethod
    def parse_instance_and_model_id(model_identifier: str):
        """Парсер для id вида OAIC/{instance}/{provider_path} или openai_{instance}/{provider_path}."""
        return parse_oaic_instance_and_model_id(model_identifier)

    def __init__(self, 
                 instances_config: List[Dict[str, Any]], 
                 proxy_manager: ProxyManager, 
                 settings_file_path: str,
                ):
        self.instances_config = instances_config
        self.proxy_manager = proxy_manager
        self.settings_file_path = settings_file_path
        self.instance_api_key_managers: Dict[str, ApiKeyManager] = {}
        for instance_conf in self.instances_config:
            instance_name = instance_conf["name"]
            # TODO: Интегрировать ApiKeyManager для управления ключами инстансов.
            pass

    def reload_module_config(self, new_config: list):
        """Перезагружает конфиг инстансов для модуля OAIC на лету."""
        self.instances_config = new_config
        logger.info("OpenAICompatModule: конфиг инстансов успешно перезагружен.")

    def get_name(self) -> str:
        return "OAIC"

    def _get_httpx_proxies(self, proxy_config: Optional[ProxyConfig]) -> Optional[Dict[str, str]]:
        return get_httpx_proxies(proxy_config)

    def _get_instance_config(self, instance_name: str) -> Optional[Dict[str, Any]]:
        return get_oaic_instance_config(self.instances_config, instance_name, include_disabled=False)

    def _get_instance_config_any_state(self, instance_name: str) -> Optional[Dict[str, Any]]:
        return get_oaic_instance_config(self.instances_config, instance_name, include_disabled=True)

    @staticmethod
    def _parse_target_reference(reference: Any, default_instance: str):
        return parse_oaic_target_reference(reference, default_instance)

    def _resolve_instance_and_model(self, instance_name: str, model_name: str):
        targets = self._resolve_model_targets(instance_name, model_name)
        return targets[0]

    def _resolve_model_targets(
        self,
        instance_name: str,
        model_name: str,
        path: Optional[List[tuple]] = None,
        depth: int = 0,
        max_depth: int = 16,
    ) -> List[tuple]:
        return resolve_oaic_model_targets(
            self.instances_config,
            instance_name,
            model_name,
            path=path,
            depth=depth,
            max_depth=max_depth,
        )

    def _build_failsafe_chain(self, primary_instance: str) -> List[str]:
        return build_oaic_failsafe_chain(self.instances_config, primary_instance)

    def _build_attempt_plan(self, resolved_targets: List[tuple]) -> List[tuple]:
        if not resolved_targets:
            return []
        if len(resolved_targets) > 1:
            return [
                (target_instance, [target_instance], target_model)
                for target_instance, target_model in resolved_targets
            ]

        instance_name, model_name = resolved_targets[0]
        return [(instance_name, self._build_failsafe_chain(instance_name), model_name)]

    @staticmethod
    def _iter_attempt_candidates(attempt_plan: List[tuple]):
        for target_instance, failsafe_chain, target_model in attempt_plan:
            for current_instance in failsafe_chain:
                yield target_instance, current_instance, target_model

    # TODO: ApiKeyManager должен быть адаптирован для работы с ключами инстансов
    def _get_instance_api_key(self, instance_name: str) -> Optional[str]:
        instance_config = self._get_instance_config(instance_name)
        if instance_config and instance_config.get("api_keys"):
            return instance_config["api_keys"][0]
        return None

    @staticmethod
    def _key_tail_for_log(api_key: Optional[str]) -> str:
        return f"...{api_key[-4:]}" if api_key else "<no-key>"

    async def _execute_non_streaming_with_rotation(
        self,
        instance_name: str,
        method: str,
        endpoint_path: str,
        payload: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        instance_config = self._get_instance_config(instance_name)
        if not instance_config:
            raise HTTPException(status_code=400, detail=f"Instance '{instance_name}' not found in configuration.")

        base_url = instance_config["base_url"]
        current_api_key = self._get_instance_api_key(instance_name)
        key_tail_for_log = self._key_tail_for_log(current_api_key)

        current_proxy_config = None
        httpx_proxies = None
        use_global_proxy = instance_config.get("use_global_proxy", True)
        if use_global_proxy and self.proxy_manager.active:
            current_proxy_config = self.proxy_manager.get_proxy()
            httpx_proxies = self._get_httpx_proxies(current_proxy_config)

        headers = {"Content-Type": "application/json"}
        if current_api_key:
            headers["Authorization"] = f"Bearer {current_api_key}"
        if extra_headers:
            headers.update(extra_headers)
            
        url = f"{base_url.rstrip('/')}{endpoint_path}"
        proxy_url_for_log = current_proxy_config['url'] if current_proxy_config else "None (Direct)"
        logger.debug(f"Attempting OpenAI Compatible API call for instance '{instance_name}': {method} {url} with key {key_tail_for_log}, proxy {proxy_url_for_log}")
        try:
            client_args = build_async_client_args(httpx_proxies, timeout=60.0)

            logger.debug(f"httpx version: {httpx.__version__}")
            logger.debug(f"AsyncClient arguments: {client_args}")
            
            async with httpx.AsyncClient(**client_args) as client:
                response = None
                if method.upper() == "POST":
                    response = await client.post(url, headers=headers, json=payload)
                elif method.upper() == "GET":
                    response = await client.get(url, headers=headers)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                response.raise_for_status()

                logger.debug(f"Тело ответа от {instance_name}: {response.text}")

                # Проверка на ошибки в ответе с кодом 200
                try:
                    check_string_for_errors(response.text)
                except Exception as e:
                    logger.warning(f"Found error in 200 response for instance {instance_name}: {e}. Raising HTTPException to trigger failsafe.")
                    # По формату Exception: 'Код 500: ...' — заберём код и текст, если по формату, иначе код 500.
                    exception_text = str(e)
                    if exception_text.startswith("Код ") and ":" in exception_text:
                        try:
                            code = int(exception_text.split(":", 1)[0].replace("Код", "").strip())
                            detail = exception_text.split(":", 1)[1].strip()
                        except Exception:
                            code = 500
                            detail = exception_text
                    else:
                        code = 500
                        detail = exception_text
                    raise HTTPException(status_code=code, detail=detail)

                response_data = response.json()
                logger.info(f"OpenAI Compatible API call successful for instance {instance_name} with key {key_tail_for_log}, proxy {proxy_url_for_log}.")

                force_rotation_enabled = False
                try:
                    with open(self.settings_file_path, 'r') as f:
                        settings_data_json = json.load(f)
                        force_rotation_enabled = settings_data_json.get("proxy_settings", {}).get("force_proxy_rotation_after_request", False)
                except Exception as e_settings:
                    logger.error(f"Could not read force_proxy_rotation_after_request from {self.settings_file_path} for instance {instance_name} (non-streaming): {e_settings}. Defaulting to False.")
                
                if force_rotation_enabled and \
                   self.proxy_manager.current_rotation_mode != "failover_cycle" and \
                   not self.proxy_manager.select_random_proxy_each_request:
                   if self.proxy_manager.active and self.proxy_manager.proxies:
                       logger.debug(f"Force rotating proxy after successful call as per settings for instance {instance_name} (non-streaming).")
                       self.proxy_manager.rotate_proxy()
                return response_data

        except httpx.HTTPStatusError as e:
            error_response_data = {}
            try: error_response_data = e.response.json()
            except json.JSONDecodeError: pass 
            error_detail = error_response_data.get("error", {}).get("message", e.response.text or f"HTTP {e.response.status_code}")
            status_code = e.response.status_code

            if status_code in [401, 403]:
                logger.warning(f"Key error for instance {instance_name} (key {key_tail_for_log}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}.")
                raise HTTPException(status_code=status_code, detail=f"Key error for instance {instance_name}: {error_detail}")
            
            elif 400 <= status_code < 500 and status_code != 429:
                logger.error(f"Client error for instance {instance_name} (key {key_tail_for_log}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}")
                raise HTTPException(status_code=status_code, detail=f"OpenAI Compatible API client error: {error_detail}")
            
            else:
                logger.warning(f"HTTPStatusError (status {status_code}, type {type(e).__name__}) for instance {instance_name} (key {key_tail_for_log}, proxy {proxy_url_for_log}): {error_detail}. Attempting proxy rotation.")
                if self.proxy_manager.active and self.proxy_manager.rotate_proxy():
                    logger.info(f"Successfully rotated to next proxy for key {key_tail_for_log} of instance {instance_name}. Retrying.")
                    raise HTTPException(status_code=status_code, detail=f"Error after proxy rotation attempt: {error_detail}")
                else:
                    raise HTTPException(status_code=status_code, detail=f"Error, proxy rotation failed or exhausted: {error_detail}")

        except (httpx.RequestError, Exception) as e: 
            error_type_name = type(e).__name__
            logger.warning(f"{error_type_name} for instance {instance_name} (key {key_tail_for_log}, proxy {proxy_url_for_log}): {str(e)}. Attempting proxy rotation.")
            if self.proxy_manager.active and self.proxy_manager.rotate_proxy():
                logger.info(f"Successfully rotated to next proxy for key {key_tail_for_log} of instance {instance_name} after {error_type_name}. Retrying.")
                raise HTTPException(status_code=500, detail=f"Error after proxy rotation attempt: {str(e)}")
            else:
                raise HTTPException(status_code=500, detail=f"Error, proxy rotation failed or exhausted: {str(e)}")

    async def _execute_streaming_with_rotation(
        self,
        instance_name: str,
        endpoint_path: str,
        payload: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        instance_config = self._get_instance_config(instance_name)
        if not instance_config:
            logger.error(f"Instance '{instance_name}' not found in configuration for streaming.")
            yield {"error": {"message": f"Instance '{instance_name}' not found.", "type": "invalid_request_error", "code": "instance_not_found"}}
            return

        base_url = instance_config["base_url"]
        current_api_key = self._get_instance_api_key(instance_name)
        key_tail_for_log = self._key_tail_for_log(current_api_key)

        current_proxy_config = None
        httpx_proxies = None
        use_global_proxy = instance_config.get("use_global_proxy", True)
        if use_global_proxy and self.proxy_manager.active:
            current_proxy_config = self.proxy_manager.get_proxy()
            httpx_proxies = self._get_httpx_proxies(current_proxy_config)
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream"
        }
        if current_api_key:
            headers["Authorization"] = f"Bearer {current_api_key}"
        if extra_headers:
            headers.update(extra_headers)

        url = f"{base_url.rstrip('/')}{endpoint_path}"
        proxy_url_for_log = current_proxy_config['url'] if current_proxy_config else "None (Direct)"
        logger.debug(f"Attempting OpenAI Compatible API stream for instance '{instance_name}': POST {url} with key {key_tail_for_log}, proxy {proxy_url_for_log}")
        try:
            client_args = build_async_client_args(httpx_proxies, timeout=60.0)

            logger.debug(f"httpx version for stream: {httpx.__version__}")
            logger.debug(f"AsyncClient arguments for stream: {client_args}")
            
            async with httpx.AsyncClient(**client_args) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        error_content = await response.aread()
                        try:
                            error_data = json.loads(error_content)
                            error_detail = error_data.get("error", {}).get("message", error_content.decode(errors='ignore'))
                        except json.JSONDecodeError:
                            error_detail = error_content.decode(errors='ignore')

                        status_code = response.status_code
                        if status_code in [401, 403]:
                            logger.warning(f"Key error for instance {instance_name} stream (key {key_tail_for_log}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}. Not retrying.")
                            yield {"error": {"message": f"Key error for instance {instance_name} stream: {error_detail}", "type": "authentication_error", "code": str(status_code)}}
                            return

                        elif 400 <= status_code < 500 and status_code != 429:
                            logger.error(f"Client error for instance {instance_name} stream (key {key_tail_for_log}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}")
                            yield {"error": {"message": f"OpenAI Compatible API client error (stream): {error_detail}", "type": "invalid_request_error", "code": str(status_code)}}
                            return
                        else:
                            logger.warning(f"HTTPStatusError (status {status_code}) for instance {instance_name} stream (key {key_tail_for_log}, proxy {proxy_url_for_log}): {error_detail}. Attempting proxy rotation.")
                            if self.proxy_manager.active and self.proxy_manager.rotate_proxy():
                                logger.info(f"Successfully rotated to next proxy for key {key_tail_for_log} of instance {instance_name} (stream). Retrying.")
                                yield {"error": {"message": f"Error after proxy rotation attempt (stream): {error_detail}", "type": "server_error", "code": str(status_code)}}
                                return
                            else:
                                logger.warning(f"HTTP error {status_code} for instance {instance_name} stream, proxy rotation failed or exhausted. Not retrying.")
                                yield {"error": {"message": f"HTTP error {status_code}, proxy rotation failed/exhausted (stream): {error_detail}", "type": "server_error", "code": str(status_code)}}
                                return

                    logger.info(f"OpenAI Compatible API stream successful (status 200) for instance '{instance_name}' with key {key_tail_for_log}, proxy {proxy_url_for_log}. Processing stream.")
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_content = line[len("data: "):].strip()
                            if data_content == "[DONE]":
                                logger.debug(f"Stream for instance '{instance_name}' ended with [DONE].")
                                break
                            logger.debug(f"Received stream message for instance '{instance_name}': {data_content}")
                            try:
                                chunk_obj = json.loads(data_content)
                                content = ""
                                try:
                                    content = chunk_obj["choices"][0].get("delta", {}).get("content", "")
                                except Exception:
                                    content = ""
                                if content:
                                    try:
                                        check_string_for_errors(content)
                                    except Exception as e:
                                        logger.warning(f"Filtered stream chunk (instance '{instance_name}') по фильтру: {str(e)}")
                                        raise FilteredStreamContentException(str(e))
                                yield chunk_obj
                            except json.JSONDecodeError:
                                logger.error(f"JSONDecodeError in stream from instance '{instance_name}': {data_content}")

                    logger.info(f"OpenAI Compatible API stream processing finished for instance '{instance_name}'.")

                    # TODO: Force proxy rotation if enabled (similar to non-streaming)
                    return

        except (httpx.RequestError, Exception) as e:
            if isinstance(e, FilteredStreamContentException):
                raise
            error_type_name = type(e).__name__
            logger.warning(f"{error_type_name} for instance {instance_name} stream (key {key_tail_for_log}, proxy {proxy_url_for_log}): {str(e)}. Not retrying with proxy/key rotation for now.")
            yield {"error": {"message": f"Error during stream connection or processing for instance '{instance_name}': {str(e)}", "type": "server_error", "code": "stream_error"}}
            return

    async def chat_completion(self, request: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        model_identifier = request.get("model", "")
        requested_instance, requested_model_name = self.parse_instance_and_model_id(model_identifier)
        if not requested_instance or not requested_model_name:
            logger.error(f"Invalid model identifier format for OpenAI Compatible module: {model_identifier}")
            yield {"error": {"message": f"Invalid model identifier format. Expected 'oai_compat_INSTANCE_NAME/model_name' or 'openai_INSTANCE_NAME/model_name', got '{model_identifier}'.", "type": "invalid_request_error"}}
            return

        resolved_targets = self._resolve_model_targets(requested_instance, requested_model_name)
        instance_name, actual_model_name = resolved_targets[0]

        payload_to_send = dict(request)
        payload_to_send["model"] = actual_model_name

        reformat_settings = get_reformat_settings()
        smart_context_settings = get_smart_context_zipper_settings()
        module_reformat_settings = reformat_settings.get(instance_name, {})
        module_scz_settings = smart_context_settings.get(instance_name, {})

        if module_reformat_settings.get(model_identifier, False):
            logger.warning(f"Reformat messages enabled for model '{actual_model_name}' in module '{self.get_name()}'. Applying reformat_messages.")
            if "messages" in payload_to_send:
                messages_json_string = json.dumps(payload_to_send, ensure_ascii=False)
                use_zipper = bool(module_scz_settings.get(model_identifier, False))
                reformatted_json_string = await reformat_messages(messages_json_string, smart_context_zipper=use_zipper)
                reformatted_data = json.loads(reformatted_json_string)
                payload_to_send["messages"] = reformatted_data.get("messages", [])
            else:
                logger.warning(f"Reformat messages enabled for model '{actual_model_name}', but no 'messages' found in payload.")

        logger.debug(f"OpenAI Compatible chat_completion for instance '{instance_name}', model '{actual_model_name}'. Request: {payload_to_send}")

        attempt_plan = self._build_attempt_plan(resolved_targets)

        last_exc = None
        repeat_count = 2
        for i in range(0,repeat_count):
            for target_instance, current_instance, target_model in self._iter_attempt_candidates(attempt_plan):
                    try:
                        payload_for_attempt = dict(payload_to_send)
                        payload_for_attempt["model"] = target_model
                        first_chunk = None
                        stream = self._execute_streaming_with_rotation(current_instance, "/chat/completions", payload_for_attempt)
                        # Попробовать взять первый чанк
                        async for chunk in stream:
                            first_chunk = chunk
                            break
                        if first_chunk is None:
                            raise Exception("Stream завершился без сообщений.")

                        content_candidate = ""
                        if isinstance(first_chunk, dict):
                            if "choices" in first_chunk and first_chunk["choices"]:
                                delta = first_chunk["choices"][0].get("delta", {})
                                content_candidate = delta.get("content", "")
                            elif "error" in first_chunk:
                                content_candidate = first_chunk["error"].get("message", "filtered")
                        if content_candidate:
                            try:
                                check_string_for_errors(content_candidate)
                            except Exception as e:
                                raise FilteredStreamContentException(str(e))

                        # Если всё хорошо — yield первый чанк, затем собирать usage (если нужно) и yield все остальные чанки
                        instance_config = self._get_instance_config(current_instance)
                        use_custom = instance_config and instance_config.get("use_custom_tokenizer")

                        collected_completion = ""
                        prompt_str = ""
                        if "messages" in payload_for_attempt:
                            prompt_str = "\n".join([msg.get("content", "") for msg in payload_for_attempt["messages"]])
                        elif "prompt" in payload_for_attempt:
                            if isinstance(payload_for_attempt["prompt"], list):
                                prompt_str = "\n".join(payload_for_attempt["prompt"])
                            else:
                                prompt_str = str(payload_for_attempt["prompt"])

                        # Выдать первый чанк
                        if use_custom and "choices" in first_chunk and first_chunk["choices"]:
                            delta = first_chunk["choices"][0].get("delta", {})
                            part = delta.get("content", "")
                            if part:
                                collected_completion += part
                        yield first_chunk

                        # Yield остальные чанки
                        finish_sent = False
                        async for chunk in stream:
                            # накапливаем текст для usage
                            if use_custom and "choices" in chunk and chunk["choices"]:
                                try:
                                    delta = chunk["choices"][0].get("delta", {})
                                    part = delta.get("content", "")
                                    if part:
                                        collected_completion += part
                                except Exception as e:
                                    logger.exception(f"Ошибка накопления completion части: {e}")

                                # определить финальный чанк — finish_reason == "stop" и есть usage
                                finish = False
                                if chunk["choices"][0].get("finish_reason") == "stop":
                                    finish = True

                                # добавить usage в финальный чанк
                                if finish and "usage" in chunk and not finish_sent:
                                    try:
                                        prompt_tokens = get_token_count(prompt_str, target_model)
                                        completion_tokens = get_token_count(collected_completion, target_model)
                                        chunk["usage"] = {
                                            "prompt_tokens": prompt_tokens,
                                            "completion_tokens": completion_tokens,
                                            "total_tokens": prompt_tokens + completion_tokens,
                                            "prompt_tokens_details": {"cached_tokens": 0}
                                        }
                                    except Exception as err:
                                        logger.exception(f"Ошибка пересчёта usage кастомным токенайзером в stream: {err}")
                                    finish_sent = True
                            yield chunk
                        return  # На первом успешном инстансе прекращаем
                    except FilteredStreamContentException as filtered_exc:
                        last_exc = filtered_exc
                        logger.warning(f"Failsafe: instance '{current_instance}' не ответил (reason: {filtered_exc}). Перехожу к следующему инстансу.")
                    except Exception as exc:
                        last_exc = exc
                        logger.warning(f"Failsafe: instance '{current_instance}' вернул ошибку: {exc}")

        log_level = logger.getEffectiveLevel()
        if log_level <= logging.DEBUG:
            msg = f"Все указанные провайдеры (failsafe chain) недоступны. Подробнее: {last_exc} Возможно, стоит попробовать ещё раз."
        else:
            msg = f"Инстанс '{instance_name}' временно недоступен или выдал отфильтрированный/ошибочный результат. Возможно, стоит попробовать ещё раз."
        raise HTTPException(status_code=503, detail=msg)
    async def list_models(self) -> Dict[str, Any]:
        all_instance_models = []
        for instance_conf in self.instances_config:
            if not instance_conf.get("enabled", True):
                continue
            instance_name = instance_conf["name"]
            logger.debug(f"Listing models for OpenAI Compatible instance: {instance_name}")
            try:
                instance_models_response = await self._execute_non_streaming_with_rotation(instance_name, "GET", "/models")

                if instance_models_response and "data" in instance_models_response:
                    for model_data in instance_models_response["data"]:
                        original_model_id = model_data.get("id", "unknown_model")
                        model_data["id"] = f"{instance_name}/{original_model_id}"
                        model_data["owned_by"] = instance_name
                        all_instance_models.append(model_data)
                else:
                    logger.warning(f"No 'data' field in list_models response from instance {instance_name}. Response: {instance_models_response}")

            except HTTPException as e:
                logger.error(f"HTTPException while listing models for instance {instance_name}: {e.detail}")
            except Exception as e:
                logger.error(f"Unexpected error while listing models for instance {instance_name}: {str(e)}")

        return {"object": "list", "data": all_instance_models}

    async def completion(self, request: Dict[str, Any]) -> Dict[str, Any]:
        model_identifier = request.get("model", "")
        requested_instance, requested_model_name = self.parse_instance_and_model_id(model_identifier)
        if not requested_instance or not requested_model_name:
            raise HTTPException(status_code=400, detail=f"Invalid model format for completion. Expected 'oai_compat_INSTANCE_NAME/model_name' or 'openai_INSTANCE_NAME/model_name', got '{model_identifier}'.")

        resolved_targets = self._resolve_model_targets(requested_instance, requested_model_name)
        instance_name, actual_model_name = resolved_targets[0]

        payload_to_send = dict(request)
        payload_to_send["model"] = actual_model_name

        attempt_plan = self._build_attempt_plan(resolved_targets)

        last_exc = None
        repeat_count = 2
        for i in range(0,repeat_count):
            for target_instance, current_instance, target_model in self._iter_attempt_candidates(attempt_plan):
                    try:
                        payload_for_attempt = dict(payload_to_send)
                        payload_for_attempt["model"] = target_model
                        result = await self._execute_non_streaming_with_rotation(current_instance, "POST", "/completions", payload_for_attempt)
                        # Успех — считаем usage если нужно и возвращаем
                        instance_config = self._get_instance_config(current_instance)
                        if instance_config and instance_config.get("use_custom_tokenizer"):
                            try:
                                raw_prompt = ""
                                # Для chat/completions это "messages", для completions "prompt"
                                if "messages" in payload_for_attempt:
                                    raw_prompt = "\n".join(
                                        [msg.get("content", "") for msg in payload_for_attempt["messages"]]
                                    )
                                elif "prompt" in payload_for_attempt:
                                    if isinstance(payload_for_attempt["prompt"], list):
                                        raw_prompt = "\n".join(payload_for_attempt["prompt"])
                                    else:
                                        raw_prompt = str(payload_for_attempt["prompt"])
                                completion_text = ""
                                if "choices" in result and result["choices"]:
                                    message = result["choices"][0]
                                    if "message" in message and isinstance(message["message"], dict) and "content" in message["message"]:
                                        completion_text = message["message"]["content"]
                                    elif "text" in message:
                                        completion_text = message["text"]

                                prompt_tokens = get_token_count(raw_prompt, target_model)
                                completion_tokens = get_token_count(completion_text, target_model)
                                usage_custom = {
                                    "prompt_tokens": prompt_tokens,
                                    "completion_tokens": completion_tokens,
                                    "total_tokens": prompt_tokens + completion_tokens,
                                    "prompt_tokens_details": {"cached_tokens": 0}
                                }
                                result["usage"] = usage_custom
                            except Exception as err:
                                logger.exception(f"Ошибка пересчёта usage кастомным токенайзером: {err}")
                        return result
                    except FilteredStreamContentException as filtered_exc:
                        last_exc = filtered_exc
                        logger.warning(f"Failsafe: instance '{current_instance}' не ответил (reason: {filtered_exc}). Перехожу к следующему инстансу.")
                    except Exception as exc:
                        last_exc = exc
                        logger.warning(f"Failsafe: instance '{current_instance}' не ответил.")

        # Ни один из цепочки не сработал – финальный фейл
        raise HTTPException(status_code=503, detail=f"Все указанные провайдеры (failsafe chain) недоступны. Подробнее: {last_exc} Возможно, стоит попробовать ещё раз.")

    async def embeddings(self, request: Dict[str, Any]) -> Dict[str, Any]:
        model_identifier = request.get("model", "")
        instance_name, actual_model_name = self.parse_instance_and_model_id(model_identifier)
        if not instance_name:
            if self.instances_config:
                instance_name = self.instances_config[0]["name"]
                logger.warning(f"Embeddings call for model '{model_identifier}' without instance prefix, falling back to instance '{instance_name}'.")
            else:
                raise HTTPException(status_code=400, detail="No OpenAI Compatible instances configured for embeddings.")

        if actual_model_name:
            instance_name, actual_model_name = self._resolve_instance_and_model(instance_name, actual_model_name)

        payload_to_send = dict(request)
        if actual_model_name:
            payload_to_send["model"] = actual_model_name

        return await self._execute_non_streaming_with_rotation(instance_name, "POST", "/embeddings", payload_to_send)

    async def moderations(self, request: Dict[str, Any]) -> Dict[str, Any]:
        instance_name = self.instances_config[0]["name"] if self.instances_config else None
        if not instance_name:
            raise HTTPException(status_code=500, detail="No OpenAI Compatible instances configured for moderations.")
        logger.info(f"Routing moderations request to instance: {instance_name}")
        return await self._execute_non_streaming_with_rotation(instance_name, "POST", "/moderations", request)

    async def generate_image(self, request: Dict[str, Any]) -> Dict[str, Any]:
        instance_name = self.instances_config[0]["name"] if self.instances_config else None
        if not instance_name:
            raise HTTPException(status_code=500, detail="No OpenAI Compatible instances configured for image generation.")
        logger.info(f"Routing image generation request to instance: {instance_name}")
        return await self._execute_non_streaming_with_rotation(instance_name, "POST", "/images/generations", request)

    async def audio_transcription(self, request_params: Dict[str, Any], file_data: bytes, filename: str) -> Dict[str, Any]:
        model_identifier = request_params.get("model", "")
        instance_name, actual_model_name = self.parse_instance_and_model_id(model_identifier)
        if not instance_name:
            if self.instances_config:
                instance_name = self.instances_config[0]["name"]
                logger.warning(f"Audio transcription for model '{model_identifier}' without instance prefix, fallback to instance '{instance_name}'.")
            else:
                raise HTTPException(status_code=500, detail="No OpenAI Compatible instances configured for audio transcription.")

        if actual_model_name:
            instance_name, actual_model_name = self._resolve_instance_and_model(instance_name, actual_model_name)

        logger.info(f"Routing audio transcription to instance: {instance_name} for model {model_identifier}")

        files = {'file': (filename, file_data)}
        rewritten_params = dict(request_params)
        if actual_model_name:
            rewritten_params["model"] = actual_model_name
        data_payload = {k: str(v) for k, v in rewritten_params.items() if v is not None}

        instance_config = self._get_instance_config(instance_name)
        if not instance_config:
            raise HTTPException(status_code=400, detail=f"Instance '{instance_name}' not found.")
        base_url = instance_config["base_url"]
        api_key = self._get_instance_api_key(instance_name)

        target_url = f"{base_url.rstrip('/')}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        httpx_proxies = None
        current_proxy_config = None
        if self.proxy_manager.active:
            current_proxy_config = self.proxy_manager.get_proxy()
            httpx_proxies = self._get_httpx_proxies(current_proxy_config)

        client_args = build_async_client_args(httpx_proxies, timeout=60.0)

        try:
            async with httpx.AsyncClient(**client_args) as client:
                response = await client.post(target_url, headers=headers, data=data_payload, files=files)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTPStatusError during audio transcription for instance {instance_name}: {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except Exception as e:
            logger.error(f"Error during audio transcription for instance {instance_name}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Audio transcription failed: {str(e)}")

    async def audio_translation(self, request_params: Dict[str, Any], file_data: bytes, filename: str) -> Dict[str, Any]:
        model_identifier = request_params.get("model", "")
        instance_name, actual_model_name = self.parse_instance_and_model_id(model_identifier)
        if not instance_name:
            if self.instances_config:
                instance_name = self.instances_config[0]["name"]
                logger.warning(f"Audio translation for model '{model_identifier}' without instance prefix, fallback to instance '{instance_name}'.")
            else:
                raise HTTPException(status_code=500, detail="No OpenAI Compatible instances configured for audio translation.")

        if actual_model_name:
            instance_name, actual_model_name = self._resolve_instance_and_model(instance_name, actual_model_name)

        logger.info(f"Routing audio translation to instance: {instance_name} for model {model_identifier}")

        files = {'file': (filename, file_data)}
        rewritten_params = dict(request_params)
        if actual_model_name:
            rewritten_params["model"] = actual_model_name
        data_payload = {k: str(v) for k, v in rewritten_params.items() if v is not None}

        instance_config = self._get_instance_config(instance_name)
        if not instance_config:
            raise HTTPException(status_code=400, detail=f"Instance '{instance_name}' not found.")
        base_url = instance_config["base_url"]
        api_key = self._get_instance_api_key(instance_name)

        target_url = f"{base_url.rstrip('/')}/audio/translations"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        httpx_proxies = None
        current_proxy_config = None
        if self.proxy_manager.active:
            current_proxy_config = self.proxy_manager.get_proxy()
            httpx_proxies = self._get_httpx_proxies(current_proxy_config)

        client_args = build_async_client_args(httpx_proxies, timeout=60.0)

        try:
            async with httpx.AsyncClient(**client_args) as client:
                response = await client.post(target_url, headers=headers, data=data_payload, files=files)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTPStatusError during audio translation for instance {instance_name}: {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except Exception as e:
            logger.error(f"Error during audio translation for instance {instance_name}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Audio translation failed: {str(e)}")

    async def _post_multipart_to_instance(
        self,
        instance_name: str,
        endpoint_path: str,
        data_payload: Dict[str, Any],
        files_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        instance_config = self._get_instance_config(instance_name)
        if not instance_config:
            raise HTTPException(status_code=400, detail=f"Instance '{instance_name}' not found.")

        base_url = instance_config["base_url"]
        api_key = self._get_instance_api_key(instance_name)
        target_url = f"{base_url.rstrip('/')}{endpoint_path}"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        httpx_proxies = None
        current_proxy_config = None
        if self.proxy_manager.active:
            current_proxy_config = self.proxy_manager.get_proxy()
            httpx_proxies = self._get_httpx_proxies(current_proxy_config)

        client_args = build_async_client_args(httpx_proxies, timeout=60.0)

        try:
            async with httpx.AsyncClient(**client_args) as client:
                response = await client.post(target_url, headers=headers, data=data_payload, files=files_payload)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTPStatusError during multipart request for instance {instance_name}: {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except Exception as e:
            logger.error(f"Error during multipart request for instance {instance_name}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Multipart request failed: {str(e)}")

    async def generate_image_edit(
        self,
        request_params: Dict[str, Any],
        image_data: bytes,
        image_filename: str,
        mask_data: Optional[bytes] = None,
        mask_filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        model_identifier = request_params.get("model", "")
        instance_name, actual_model_name = self.parse_instance_and_model_id(model_identifier)
        if not instance_name:
            if self.instances_config:
                instance_name = self.instances_config[0]["name"]
            else:
                raise HTTPException(status_code=500, detail="No OpenAI Compatible instances configured for image edits.")

        if actual_model_name:
            instance_name, actual_model_name = self._resolve_instance_and_model(instance_name, actual_model_name)

        rewritten = dict(request_params)
        if actual_model_name:
            rewritten["model"] = actual_model_name

        data_payload = {k: str(v) for k, v in rewritten.items() if v is not None}
        files_payload = {"image": (image_filename, image_data)}
        if mask_data is not None:
            files_payload["mask"] = (mask_filename or "mask.png", mask_data)

        return await self._post_multipart_to_instance(instance_name, "/images/edits", data_payload, files_payload)

    async def generate_image_variation(
        self,
        request_params: Dict[str, Any],
        image_data: bytes,
        image_filename: str,
    ) -> Dict[str, Any]:
        model_identifier = request_params.get("model", "")
        instance_name, actual_model_name = self.parse_instance_and_model_id(model_identifier)
        if not instance_name:
            if self.instances_config:
                instance_name = self.instances_config[0]["name"]
            else:
                raise HTTPException(status_code=500, detail="No OpenAI Compatible instances configured for image variations.")

        if actual_model_name:
            instance_name, actual_model_name = self._resolve_instance_and_model(instance_name, actual_model_name)

        rewritten = dict(request_params)
        if actual_model_name:
            rewritten["model"] = actual_model_name

        data_payload = {k: str(v) for k, v in rewritten.items() if v is not None}
        files_payload = {"image": (image_filename, image_data)}

        return await self._post_multipart_to_instance(instance_name, "/images/variations", data_payload, files_payload)

    async def audio_speech(self, request: Dict[str, Any]) -> Dict[str, Any]:
        model_identifier = request.get("model", "")
        instance_name, actual_model_name = self.parse_instance_and_model_id(model_identifier)
        if not instance_name:
            if self.instances_config:
                instance_name = self.instances_config[0]["name"]
            else:
                raise HTTPException(status_code=500, detail="No OpenAI Compatible instances configured for audio speech.")

        if actual_model_name:
            instance_name, actual_model_name = self._resolve_instance_and_model(instance_name, actual_model_name)

        payload_to_send = dict(request)
        if actual_model_name:
            payload_to_send["model"] = actual_model_name

        return await self._execute_non_streaming_with_rotation(instance_name, "POST", "/audio/speech", payload_to_send)

    async def responses(self, request: Dict[str, Any]) -> Dict[str, Any]:
        model_identifier = request.get("model", "")
        instance_name, actual_model_name = self.parse_instance_and_model_id(model_identifier)
        if not instance_name:
            if self.instances_config:
                instance_name = self.instances_config[0]["name"]
            else:
                raise HTTPException(status_code=500, detail="No OpenAI Compatible instances configured for responses.")

        if actual_model_name:
            resolved_targets = self._resolve_model_targets(instance_name, actual_model_name)
        else:
            resolved_targets = [(instance_name, actual_model_name)]

        attempt_plan = self._build_attempt_plan(resolved_targets)

        last_exc = None
        repeat_count = 2
        for _ in range(repeat_count):
            for target_instance, current_instance, target_model in self._iter_attempt_candidates(attempt_plan):
                payload_to_send = dict(request)
                if target_model:
                    payload_to_send["model"] = target_model
                try:
                    return await self._execute_non_streaming_with_rotation(current_instance, "POST", "/responses", payload_to_send)
                except Exception as exc:
                    last_exc = exc
                    logger.warning(f"Failsafe for responses: instance '{current_instance}' failed: {exc}")

        raise HTTPException(status_code=503, detail=f"All response providers are unavailable. Details: {last_exc}")
