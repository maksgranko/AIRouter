import openai
from typing import Dict, Any, Callable, Optional
from base_module import BaseModule
from api_key_manager import ApiKeyManager
from proxy_manager import ProxyManager, ProxyConfig
import asyncio
import logging
import io
from fastapi import HTTPException

logger = logging.getLogger(__name__)

import json # Добавлено для чтения settings.json

class OpenAIChatModule(BaseModule):
    def __init__(self, api_key_manager: ApiKeyManager, proxy_manager: ProxyManager, settings_file_path: str, service_name: str = "openai"):
        self.api_key_manager = api_key_manager
        self.proxy_manager = proxy_manager
        self.settings_file_path = settings_file_path 
        self.service_name = service_name
        self.openai_sdk_lock = asyncio.Lock() 
        self.last_api_key_used_for_proxy_context: Optional[str] = None # Для сохранения контекста прокси
        self.first_key_in_overall_cycle: Optional[str] = None # Для детекции полного цикла ключей
        self.key_loop_initial_run: bool = True # Чтобы установить first_key_in_overall_cycle один раз

    def get_name(self) -> str:
        return self.service_name

    def _format_proxy_for_openai_sdk(self, proxy_config: Optional[ProxyConfig]) -> Optional[str]:
        if proxy_config:
            # OpenAI SDK (использующий requests) должен понимать URL прокси напрямую,
            # включая socks5://user:pass@host:port если requests[socks] установлен.
            return proxy_config['url']
        return None

    async def _execute_with_rotation(self, sync_api_call_func: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        """
        Выполняет синхронный вызов OpenAI API с управлением API ключами, прокси и их ротацией.
        """
        key_exhausted_message = f"All API keys for {self.service_name} are exhausted or failed."
        
        if self.key_loop_initial_run:
            self.first_key_in_overall_cycle = self.api_key_manager.get_key(self.service_name, peek=True)
            self.key_loop_initial_run = False # Сбрасываем после первого вызова _execute_with_rotation для этого экземпляра

        # Этот флаг будет устанавливаться в True, если ключ был ротирован внутри этого вызова
        key_was_rotated_in_current_api_call = False

        while True: # Key loop
            current_api_key = self.api_key_manager.get_key(self.service_name)
            if not current_api_key:
                logger.error(key_exhausted_message + " (No keys available at start of key loop)")
                raise HTTPException(status_code=503, detail=key_exhausted_message + " (No keys available at start of key loop)")

            if self.last_api_key_used_for_proxy_context != current_api_key or key_was_rotated_in_current_api_call:
                logger.debug(f"API key changed or rotated for {self.service_name}. Old: {self.last_api_key_used_for_proxy_context}, New: {current_api_key}. Resetting proxies.")
                self.proxy_manager.reset_proxies()
                self.last_api_key_used_for_proxy_context = current_api_key
                if key_was_rotated_in_current_api_call: # Если ключ был ротирован, сбрасываем флаг
                    key_was_rotated_in_current_api_call = False
            else:
                logger.debug(f"API key ...{current_api_key[-4:]} is the same as last used. Proxy context preserved for {self.service_name}.")
            
            # Сброс first_key_in_overall_cycle, если мы начинаем новый "большой" цикл после того, как все ключи были опробованы
            # Это происходит, когда last_api_key_used_for_proxy_context сбрасывается (например, при ошибке и ротации)
            # и новый current_api_key становится первым в новом цикле.
            # Однако, first_key_in_overall_cycle должен быть более стабильным.
            # Он устанавливается один раз при первом вызове _execute_with_rotation для экземпляра.

            while True: # Proxy loop
                current_proxy_config = None
                if self.proxy_manager.active: # Только если прокси включены глобально и загружены
                    current_proxy_config = self.proxy_manager.get_proxy()
                
                # Если proxy_manager неактивен или get_proxy() вернул None (все прокси опробованы в режиме 'once' или список пуст)
                # current_proxy_config будет None, и openai.proxy установится в None.

                async with self.openai_sdk_lock:
                    openai.api_key = current_api_key
                    openai.proxy = self._format_proxy_for_openai_sdk(current_proxy_config) 
                    
                    proxy_url_for_log = current_proxy_config['url'] if current_proxy_config else "None (Direct)"
                    logger.debug(f"Attempting API call for {self.service_name} with key ...{current_api_key[-4:]} and proxy {proxy_url_for_log}")

                    try:
                        result = await asyncio.to_thread(sync_api_call_func)
                        logger.info(f"API call successful for {self.service_name} with key ...{current_api_key[-4:]} and proxy {proxy_url_for_log}.")
                        
                        # Чтение настройки принудительной ротации
                        force_rotation_enabled = False
                        try:
                            with open(self.settings_file_path, 'r') as f:
                                settings_data = json.load(f)
                                force_rotation_enabled = settings_data.get("proxy_settings", {}).get("force_proxy_rotation_after_request", False)
                        except Exception as e_settings:
                            logger.error(f"Could not read force_proxy_rotation_after_request from {self.settings_file_path}: {e_settings}. Defaulting to False.")
                            force_rotation_enabled = False

                        # Принудительная ротация после успеха, если включена и режим не failover_cycle и не случайный выбор
                        if force_rotation_enabled and \
                           self.proxy_manager.current_rotation_mode != "failover_cycle" and \
                           not self.proxy_manager.select_random_proxy_each_request:
                            if self.proxy_manager.active and self.proxy_manager.proxies:
                                logger.debug("Force rotating proxy after successful call as per settings (OpenAI).")
                                self.proxy_manager.rotate_proxy()
                        
                        return result # Успех
                    except (openai.error.AuthenticationError, openai.error.PermissionError) as e:
                        logger.warning(f"Key error for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {type(e).__name__}. Rotating key.")
                        # rotate_key теперь возвращает bool
                        previous_key_for_check = current_api_key
                        if not self.api_key_manager.rotate_key(self.service_name): 
                            logger.error(key_exhausted_message + " (No keys to rotate to after auth error)")
                            raise HTTPException(status_code=503, detail=key_exhausted_message + " (No keys to rotate to after auth error)")
                        
                        key_was_rotated_in_current_api_call = True 
                        current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True) # Смотрим на новый ключ
                        
                        if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                            logger.warning(f"Completed a full cycle of API keys for {self.service_name} due to {type(e).__name__}. All keys failed. Raising final exception.")
                            raise HTTPException(status_code=503, detail=f"{key_exhausted_message} (Full key cycle for {type(e).__name__})")
                        break 
                    
                    except openai.error.InvalidRequestError as e: 
                        logger.error(f"Invalid request to OpenAI for {self.service_name}: {e}")
                        raise HTTPException(status_code=400, detail=f"Invalid request to OpenAI: {str(e)}")

                    except openai.error.OpenAIError as e: # Все остальные ошибки OpenAI (RateLimit, APIConnection, Timeout, ServiceUnavailable etc.)
                        logger.warning(f"OpenAI API Error for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {type(e).__name__} - {str(e)}. Attempting proxy rotation.")
                        if self.proxy_manager.active and self.proxy_manager.rotate_proxy():
                            # Успешно сменили прокси, продолжаем proxy_loop со следующим прокси
                            logger.info(f"Successfully rotated to next proxy for key ...{current_api_key[-4:]}. Retrying.")
                            continue # к следующей итерации proxy_loop
                        else:
                            # Не удалось сменить прокси (неактивны, закончились в режиме 'once', или их нет)
                            # Пытаемся сменить ключ
                            logger.warning(f"Failed to rotate proxy or proxies exhausted for key ...{current_api_key[-4:]}. Attempting key rotation.")
                            previous_key_for_check = current_api_key
                            if not self.api_key_manager.rotate_key(self.service_name):
                                final_error_message = f"{key_exhausted_message} (Error type: {type(e).__name__} on all proxies/keys, no keys to rotate to)"
                                logger.error(final_error_message)
                                status_code_val = 500 # default
                                if isinstance(e, openai.error.RateLimitError): status_code_val = 429
                                elif isinstance(e, openai.error.APIConnectionError): status_code_val = 502
                                elif isinstance(e, openai.error.Timeout): status_code_val = 504
                                elif isinstance(e, openai.error.ServiceUnavailableError): status_code_val = 503
                                raise HTTPException(status_code=status_code_val, detail=final_error_message)
                            
                            key_was_rotated_in_current_api_call = True
                            current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                            if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                                logger.warning(f"Completed a full cycle of API keys for {self.service_name} due to {type(e).__name__}. All keys failed. Raising final exception.")
                                final_error_message = f"{key_exhausted_message} (Full key cycle for {type(e).__name__})"
                                raise HTTPException(status_code=status_code_val, detail=final_error_message) 
                            break 
                    
                    except Exception as e: 
                        logger.error(f"Unexpected non-OpenAI error during API call for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {type(e).__name__} - {str(e)}. Attempting proxy rotation first.")
                        # По аналогии с OpenAIError, сначала пробуем прокси
                        if self.proxy_manager.active and self.proxy_manager.rotate_proxy():
                            logger.info(f"Successfully rotated to next proxy for key ...{current_api_key[-4:]} after unexpected error. Retrying.")
                            continue
                        else:
                            logger.warning(f"Failed to rotate proxy or proxies exhausted for key ...{current_api_key[-4:]} after unexpected error. Attempting key rotation.")
                            previous_key_for_check = current_api_key
                            if not self.api_key_manager.rotate_key(self.service_name):
                                final_error_message = f"{key_exhausted_message} (Unexpected Error type: {type(e).__name__} on all proxies/keys, no keys to rotate to)"
                                logger.error(final_error_message)
                                raise HTTPException(status_code=500, detail=final_error_message)
                            key_was_rotated_in_current_api_call = True
                            current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                            if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                                logger.warning(f"Completed a full cycle of API keys for {self.service_name} due to unexpected {type(e).__name__}. All keys failed. Raising final exception.")
                                raise HTTPException(status_code=500, detail=f"{key_exhausted_message} (Full key cycle for unexpected {type(e).__name__})")
                            break
                
                # Логика выхода из proxy_loop:
                # 1. Если прокси неактивны (USE_PROXIES=false или нет загруженных прокси), proxy_loop выполнится один раз.
                #    current_proxy_config будет None. Если ошибка, то rotate_proxy() не вызовется (т.к. self.proxy_manager.active=false).
                #    Тогда должна произойти ротация ключа.
                # 2. Если прокси активны, но все опробованы (current_proxy_config стал None после rotate_proxy()),
                #    тоже должна произойти ротация ключа.
                
                if not self.proxy_manager.active: # Прокси выключены или не загружены
                    logger.debug(f"Proxies disabled or not loaded. Attempted direct call for key ...{current_api_key[-4:]}. Rotating key if call failed and not already rotated.")
                    # Если мы здесь, значит, прямой вызов не удался (и ошибка не была AuthenticationError, иначе бы уже вышли из key_loop)
                    previous_key_for_check = current_api_key
                    if not self.api_key_manager.rotate_key(self.service_name):
                        logger.error(key_exhausted_message + " (Direct call failed, no keys to rotate to)")
                        raise HTTPException(status_code=503, detail=key_exhausted_message + " (Direct call failed, no keys to rotate to)")
                    key_was_rotated_in_current_api_call = True 
                    current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                    if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                        logger.warning(f"Completed a full cycle of API keys for {self.service_name} (direct call failed for last key). All keys failed.")
                        raise HTTPException(status_code=503, detail=f"{key_exhausted_message} (Full key cycle, direct calls failed)")
                    break 

                if current_proxy_config is None and self.proxy_manager.proxies: 
                     logger.debug(f"All proxies tried for key ...{current_api_key[-4:]}. Rotating key.")
                     previous_key_for_check = current_api_key
                     if not self.api_key_manager.rotate_key(self.service_name):
                         logger.error(key_exhausted_message + " (All proxies tried, no keys to rotate to)")
                         raise HTTPException(status_code=503, detail=key_exhausted_message + " (All proxies tried, no keys to rotate to)")
                     key_was_rotated_in_current_api_call = True 
                     current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                     if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                        logger.warning(f"Completed a full cycle of API keys for {self.service_name} (all proxies tried for last key). All keys failed.")
                        raise HTTPException(status_code=503, detail=f"{key_exhausted_message} (Full key cycle, all proxies tried)")
                     break 

    async def chat_completion(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return await self._execute_with_rotation(lambda: openai.ChatCompletion.create(**request))

    async def completion(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return await self._execute_with_rotation(lambda: openai.Completion.create(**request))

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

    async def audio_transcription(self, request: Dict[str, Any], file_data: bytes) -> Dict[str, Any]:
        # Копируем request, чтобы не изменять оригинальный словарь при добавлении filename
        req_copy = request.copy()
        filename = req_copy.pop("filename", "audio.mp3") # Удаляем filename из параметров, если он там был для нашего удобства

        with io.BytesIO(file_data) as audio_file:
            audio_file.name = filename # OpenAI SDK требует атрибут name у file-like объекта
            return await self._execute_with_rotation(
                lambda: openai.Audio.transcribe(file=audio_file, **req_copy)
            )

    async def audio_translation(self, request: Dict[str, Any], file_data: bytes) -> Dict[str, Any]:
        req_copy = request.copy()
        filename = req_copy.pop("filename", "audio.mp3")

        with io.BytesIO(file_data) as audio_file:
            audio_file.name = filename
            return await self._execute_with_rotation(
                lambda: openai.Audio.translate(file=audio_file, **req_copy)
            )
