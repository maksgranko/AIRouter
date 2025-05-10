import httpx # Используем httpx для запросов
from typing import Dict, Any, Optional
from base_module import BaseModule
from api_key_manager import ApiKeyManager
from proxy_manager import ProxyManager, ProxyConfig # Импортируем ProxyManager
import logging
from fastapi import HTTPException
import json # Для обработки JSON ответов и тел запросов
import time # Для created timestamp

logger = logging.getLogger(__name__)

# Базовый URL для Gemini API
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

class GeminiChatModule(BaseModule):
    def __init__(self, api_key_manager: ApiKeyManager, proxy_manager: ProxyManager, service_name: str = "gemini", default_model: str = "gemini-pro"):
        self.api_key_manager = api_key_manager
        self.proxy_manager = proxy_manager
        self.service_name = service_name
        self.default_model = default_model

    def get_name(self) -> str:
        return self.service_name

    def _get_httpx_proxies(self, proxy_config: Optional[ProxyConfig]) -> Optional[Dict[str, str]]:
        if proxy_config:
            # httpx ожидает словарь вида {"http://": "...", "https://": "..."}
            # или {"all://": "socks5://..."}
            if proxy_config['type'] in ['http', 'https']: # HTTP/HTTPS прокси
                 return {
                    "http://": proxy_config['url'],
                    "https://": proxy_config['url'],
                }
            elif proxy_config['type'] in ['socks4', 'socks5']: # SOCKS прокси
                return {"all://": proxy_config['url']}
        return None

    async def _execute_with_rotation(
        self,
        method: str, # "GET" или "POST"
        endpoint_path: str, # Например, "/models" или "/models/gemini-pro:generateContent"
        payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        key_exhausted_message = f"All API keys for {self.service_name} are exhausted or failed."
        
        while True: # Key loop
            current_api_key = self.api_key_manager.get_key(self.service_name)
            if not current_api_key:
                logger.error(key_exhausted_message)
                raise HTTPException(status_code=503, detail=key_exhausted_message)

            self.proxy_manager.reset_proxies() # Сбрасываем прокси для каждого нового ключа

            while True: # Proxy loop
                current_proxy_config = None
                httpx_proxies = None # Инициализируем httpx_proxies как None
                if self.proxy_manager.active: # Только если прокси включены глобально и загружены
                    current_proxy_config = self.proxy_manager.get_proxy()
                    httpx_proxies = self._get_httpx_proxies(current_proxy_config)
                
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": current_api_key
                }
                url = f"{GEMINI_API_BASE_URL}{endpoint_path}"
                
                proxy_url_for_log = current_proxy_config['url'] if current_proxy_config else "None (Direct)"
                logger.debug(f"Attempting Gemini API call: {method} {url} with key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}")

                try:
                    async with httpx.AsyncClient(proxies=httpx_proxies, timeout=30.0) as client:
                        response = None
                        if method.upper() == "POST":
                            response = await client.post(url, headers=headers, json=payload)
                        elif method.upper() == "GET":
                            response = await client.get(url, headers=headers)
                        else:
                            raise ValueError(f"Unsupported HTTP method: {method}")
                        
                        response.raise_for_status() 
                        
                        content_type = response.headers.get("content-type", "")
                        if "application/json" in content_type:
                            response_data = response.json()
                        elif response.status_code == 204: 
                            response_data = {} 
                        else: 
                            response_data = {"raw_content": response.text} 
                            
                        logger.info(f"Gemini API call successful for {self.service_name} with key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}.")
                        return response_data

                except httpx.HTTPStatusError as e: 
                    error_response_data = {}
                    try:
                        error_response_data = e.response.json()
                    except json.JSONDecodeError:
                        pass 

                    error_detail = error_response_data.get("error", {}).get("message", e.response.text or f"HTTP {e.response.status_code}")
                    status_code = e.response.status_code

                    if status_code == 401 or status_code == 403: 
                        logger.warning(f"Key error for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}. Rotating key.")
                        if not self.api_key_manager.rotate_key(self.service_name):
                            logger.error(key_exhausted_message)
                            raise HTTPException(status_code=503, detail=key_exhausted_message)
                        break 
                    elif status_code == 429: 
                        logger.warning(f"Rate limit for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}. Trying next proxy or key.")
                        if not self.proxy_manager.active or not self.proxy_manager.rotate_proxy():
                            if not self.api_key_manager.rotate_key(self.service_name):
                                logger.error(key_exhausted_message + " (Rate limit on all proxies/keys)")
                                raise HTTPException(status_code=429, detail=key_exhausted_message + " (Rate limit on all proxies/keys)")
                            break 
                    elif status_code >= 400 and status_code < 500: 
                         logger.error(f"Client error for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}")
                         raise HTTPException(status_code=status_code, detail=f"Gemini API client error: {error_detail}")
                    else: 
                        logger.warning(f"Server/Connection error for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}. Trying next proxy or key.")
                        if not self.proxy_manager.active or not self.proxy_manager.rotate_proxy():
                            if not self.api_key_manager.rotate_key(self.service_name):
                                logger.error(key_exhausted_message + f" (HTTP {status_code} on all proxies/keys)")
                                raise HTTPException(status_code=502, detail=key_exhausted_message + f" (HTTP {status_code} on all proxies/keys)")
                            break
                except httpx.RequestError as e: 
                    logger.warning(f"httpx.RequestError for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {type(e).__name__} - {str(e)}. Trying next proxy or key.")
                    if not self.proxy_manager.active or not self.proxy_manager.rotate_proxy():
                        if not self.api_key_manager.rotate_key(self.service_name):
                            logger.error(key_exhausted_message + " (RequestError on all proxies/keys)")
                            raise HTTPException(status_code=504, detail=key_exhausted_message + " (RequestError on all proxies/keys - Gateway Timeout)")
                        break 
                except Exception as e:
                    logger.error(f"Unexpected error during Gemini API call for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {type(e).__name__} - {str(e)}")
                    raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
                
                if not self.proxy_manager.active:
                    logger.debug(f"Proxies disabled or not loaded. Attempted direct call for key ...{current_api_key[-4:]}. Rotating key if call failed.")
                    if not self.api_key_manager.rotate_key(self.service_name):
                        logger.error(key_exhausted_message)
                        raise HTTPException(status_code=503, detail=key_exhausted_message)
                    break 

                if current_proxy_config is None and self.proxy_manager.proxies: # Прокси активны, но все опробованы
                     logger.debug(f"All proxies tried for key ...{current_api_key[-4:]}. Rotating key.")
                     if not self.api_key_manager.rotate_key(self.service_name):
                         logger.error(key_exhausted_message)
                         raise HTTPException(status_code=503, detail=key_exhausted_message)
                     break 

    async def chat_completion(self, request: Dict[str, Any]) -> Dict[str, Any]:
        # Адаптация OpenAI запроса к формату Gemini generateContent
        # https://ai.google.dev/docs/gemini_api_reference/rest/v1beta/models/generateContent
        gemini_contents = []
        for msg in request.get("messages", []):
            role = "user" if msg.get("role") == "user" else "model" # Gemini использует "user" и "model"
            gemini_contents.append({"role": role, "parts": [{"text": msg.get("content")}]})

        # TODO: Поддержка других параметров, таких как temperature, topP, topK, maxOutputTokens, stopSequences
        # generationConfig = { "temperature": request.get("temperature", 0.7) ... }
        
        model_to_use = request.get("model", self.default_model)
        if not model_to_use.startswith("models/"): # Gemini API ожидает "models/gemini-pro"
            model_to_use = f"models/{model_to_use}"


        payload = {"contents": gemini_contents}
        # if generationConfig: payload["generationConfig"] = generationConfig

        response_data = await self._execute_with_rotation("POST", f"/{model_to_use}:generateContent", payload)
        
        # Адаптация ответа Gemini к формату OpenAI
        # https://ai.google.dev/docs/gemini_api_reference/rest/v1beta/models/generateContent#response-body
        # (предполагаем, что не используем streaming здесь)
        
        choices = []
        if response_data and "candidates" in response_data and response_data["candidates"]:
            candidate = response_data["candidates"][0] # Берем первого кандидата
            content = ""
            if "content" in candidate and "parts" in candidate["content"] and candidate["content"]["parts"]:
                content = candidate["content"]["parts"][0].get("text", "")
            
            finish_reason_map = {
                "FINISH_REASON_UNSPECIFIED": "unknown",
                "STOP": "stop",
                "MAX_TOKENS": "length",
                "SAFETY": "content_filter", # или другое подходящее значение
                "RECITATION": "recitation_filter", # или другое подходящее значение
                "OTHER": "unknown",
            }
            finish_reason = finish_reason_map.get(candidate.get("finishReason"), "stop")

            choices.append({
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason
            })
        
        # Информация о токенах может отсутствовать или быть в другом формате
        # prompt_feedback.block_reason, prompt_feedback.safety_ratings
        # usage_metadata.prompt_token_count, usage_metadata.candidates_token_count, usage_metadata.total_token_count
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        if "usageMetadata" in response_data:
            usage["prompt_tokens"] = response_data["usageMetadata"].get("promptTokenCount", 0)
            usage["completion_tokens"] = response_data["usageMetadata"].get("candidatesTokenCount", 0) # Сумма по всем кандидатам, если их несколько
            usage["total_tokens"] = response_data["usageMetadata"].get("totalTokenCount", 0)
            
        return {
            "id": f"chatcmpl-gemini-{int(time.time())}", # Простое ID
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_to_use.replace("models/", ""), # Возвращаем чистое имя модели
            "choices": choices,
            "usage": usage
        }

    async def list_models(self) -> Dict[str, Any]:
        # https://ai.google.dev/docs/gemini_api_reference/rest/v1beta/models/list
        response_data = await self._execute_with_rotation("GET", "/models")
        
        openai_models = []
        if response_data and "models" in response_data:
            for gemini_model in response_data["models"]:
                # Gemini API возвращает модели вида "models/gemini-pro"
                # Отбираем только те, что поддерживают generateContent (аналог chat/completion)
                # и, возможно, другие нужные методы в будущем
                # if "generateContent" in gemini_model.get("supportedGenerationMethods", []):
                openai_models.append({
                    "id": gemini_model.get("name", "").replace("models/", ""), # "gemini-pro"
                    "object": "model",
                    "owned_by": "google", # Пример
                    "permission": [] # Пример
                })
        return {"object": "list", "data": openai_models}

    async def completion(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "error": {
                "message": "The Gemini module does not support the completion operation.",
                "type": "invalid_request_error",
                "param": None,
                "code": "operation_not_supported"
            }
        }

    async def embeddings(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "error": {
                "message": "The Gemini module does not support the embeddings operation.",
                "type": "invalid_request_error",
                "param": None,
                "code": "operation_not_supported"
            }
        }

    async def moderations(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "error": {
                "message": "The Gemini module does not support the moderations operation.",
                "type": "invalid_request_error",
                "param": None,
                "code": "operation_not_supported"
            }
        }

    async def generate_image(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "error": {
                "message": "The Gemini module does not support the image generation operation.",
                "type": "invalid_request_error",
                "param": None,
                "code": "operation_not_supported"
            }
        }

    async def audio_transcription(self, request: Dict[str, Any], file_data: bytes) -> Dict[str, Any]:
        return {
            "error": {
                "message": "The Gemini module does not support the audio transcription operation.",
                "type": "invalid_request_error",
                "param": None,
                "code": "operation_not_supported"
            }
        }

    async def audio_translation(self, request: Dict[str, Any], file_data: bytes) -> Dict[str, Any]:
        return {
            "error": {
                "message": "The Gemini module does not support the audio translation operation.",
                "type": "invalid_request_error",
                "param": None,
                "code": "operation_not_supported"
            }
        }
