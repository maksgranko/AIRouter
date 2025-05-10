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

class OpenAIChatModule(BaseModule):
    def __init__(self, api_key_manager: ApiKeyManager, proxy_manager: ProxyManager, service_name: str = "openai"):
        self.api_key_manager = api_key_manager
        self.proxy_manager = proxy_manager
        self.service_name = service_name
        self.openai_sdk_lock = asyncio.Lock() # Для синхронизации доступа к глобальным настройкам openai SDK

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
        
        while True: # Key loop
            current_api_key = self.api_key_manager.get_key(self.service_name)
            if not current_api_key:
                logger.error(key_exhausted_message)
                raise HTTPException(status_code=503, detail=key_exhausted_message)

            self.proxy_manager.reset_proxies() # Сбрасываем прокси для каждого нового ключа

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
                        return result # Успех
                    except (openai.error.AuthenticationError, openai.error.PermissionError) as e:
                        logger.warning(f"Key error for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {type(e).__name__}. Rotating key.")
                        if not self.api_key_manager.rotate_key(self.service_name): 
                            logger.error(key_exhausted_message)
                            raise HTTPException(status_code=503, detail=key_exhausted_message)
                        break 
                    except openai.error.RateLimitError as e:
                        logger.warning(f"Rate limit for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {type(e).__name__}. Trying next proxy or key.")
                        if not self.proxy_manager.active or not self.proxy_manager.rotate_proxy(): 
                            if not self.api_key_manager.rotate_key(self.service_name): 
                                logger.error(key_exhausted_message + " (Rate limit on all proxies/keys)")
                                raise HTTPException(status_code=429, detail=key_exhausted_message + " (Rate limit on all proxies/keys)")
                            break 
                    except openai.error.APIConnectionError as e: 
                        logger.warning(f"Connection error for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {type(e).__name__}. Trying next proxy or key.")
                        if not self.proxy_manager.active or not self.proxy_manager.rotate_proxy(): 
                            if not self.api_key_manager.rotate_key(self.service_name): 
                                logger.error(key_exhausted_message + " (Connection error on all proxies/keys)")
                                raise HTTPException(status_code=502, detail=key_exhausted_message + " (Connection error on all proxies/keys)")
                            break 
                    except openai.error.InvalidRequestError as e:
                        logger.error(f"Invalid request to OpenAI for {self.service_name}: {e}")
                        raise HTTPException(status_code=400, detail=f"Invalid request to OpenAI: {str(e)}")
                    except openai.error.OpenAIError as e: 
                        logger.error(f"OpenAI API error for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {e}")
                        raise HTTPException(status_code=500, detail=f"OpenAI API error: {str(e)}")
                    except Exception as e:
                        logger.error(f"Unexpected error during API call for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {e}")
                        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
                
                # Логика выхода из proxy_loop:
                # 1. Если прокси неактивны (USE_PROXIES=false или нет загруженных прокси), proxy_loop выполнится один раз.
                #    current_proxy_config будет None. Если ошибка, то rotate_proxy() не вызовется (т.к. self.proxy_manager.active=false).
                #    Тогда должна произойти ротация ключа.
                # 2. Если прокси активны, но все опробованы (current_proxy_config стал None после rotate_proxy()),
                #    тоже должна произойти ротация ключа.
                
                if not self.proxy_manager.active: # Прокси выключены или не загружены
                    logger.debug(f"Proxies disabled or not loaded. Attempted direct call for key ...{current_api_key[-4:]}. Rotating key if call failed and not already rotated.")
                    # Если мы здесь, значит, прямой вызов не удался (и ошибка не была AuthenticationError, иначе бы уже вышли из key_loop)
                    # Нужно сменить ключ, чтобы не зациклиться на нерабочем прямом соединении с этим ключом.
                    if not self.api_key_manager.rotate_key(self.service_name):
                        logger.error(key_exhausted_message)
                        raise HTTPException(status_code=503, detail=key_exhausted_message)
                    break # Выход из proxy_loop для нового ключа

                if current_proxy_config is None and self.proxy_manager.proxies: # Прокси активны, но все опробованы
                     logger.debug(f"All proxies tried for key ...{current_api_key[-4:]}. Rotating key.")
                     if not self.api_key_manager.rotate_key(self.service_name):
                         logger.error(key_exhausted_message)
                         raise HTTPException(status_code=503, detail=key_exhausted_message)
                     break # Выход из proxy_loop для нового ключа

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
