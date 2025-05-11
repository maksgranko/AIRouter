import httpx # Используем httpx для запросов
from typing import Dict, Any, Optional, AsyncGenerator
from base_module import BaseModule
from api_key_manager import ApiKeyManager
from proxy_manager import ProxyManager, ProxyConfig # Импортируем ProxyManager
import logging
from fastapi import HTTPException
import json # Для обработки JSON ответов и тел запросов
import time # Для created timestamp
import random # Для генерации ID

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
            if proxy_config['type'] in ['http', 'https']:
                 return {
                    "http://": proxy_config['url'],
                    "https://": proxy_config['url'],
                }
            elif proxy_config['type'] in ['socks4', 'socks5']:
                return {"all://": proxy_config['url']}
        return None

    async def _execute_non_streaming_with_rotation(
        self,
        method: str,
        endpoint_path: str,
        payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        key_exhausted_message = f"All API keys for {self.service_name} are exhausted or failed."
        while True: # Key loop
            current_api_key = self.api_key_manager.get_key(self.service_name)
            if not current_api_key:
                logger.error(key_exhausted_message)
                raise HTTPException(status_code=503, detail=key_exhausted_message)
            self.proxy_manager.reset_proxies()
            while True: # Proxy loop
                current_proxy_config = None
                httpx_proxies = None
                if self.proxy_manager.active:
                    current_proxy_config = self.proxy_manager.get_proxy()
                    httpx_proxies = self._get_httpx_proxies(current_proxy_config)
                
                headers = {"Content-Type": "application/json", "x-goog-api-key": current_api_key}
                url = f"{GEMINI_API_BASE_URL}{endpoint_path}"
                proxy_url_for_log = current_proxy_config['url'] if current_proxy_config else "None (Direct)"
                logger.debug(f"Attempting Gemini API call: {method} {url} with key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}")
                try:
                    client_args = {"timeout": 30.0}
                    if httpx_proxies: client_args["proxies"] = httpx_proxies
                    async with httpx.AsyncClient(**client_args) as client:
                        response = None
                        if method.upper() == "POST":
                            response = await client.post(url, headers=headers, json=payload)
                        elif method.upper() == "GET":
                            response = await client.get(url, headers=headers)
                        else:
                            raise ValueError(f"Unsupported HTTP method: {method}")
                        response.raise_for_status()
                        response_data = response.json()
                        logger.info(f"Gemini API call successful for {self.service_name} with key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}.")
                        return response_data
                except httpx.HTTPStatusError as e:
                    error_response_data = {}
                    try: error_response_data = e.response.json()
                    except json.JSONDecodeError: pass
                    error_detail = error_response_data.get("error", {}).get("message", e.response.text or f"HTTP {e.response.status_code}")
                    status_code = e.response.status_code
                    if status_code in [401, 403]:
                        logger.warning(f"Key error for {self.service_name} (key ...{current_api_key[-4:]}): HTTP {status_code} - {error_detail}. Rotating key.")
                        if not self.api_key_manager.rotate_key(self.service_name): raise HTTPException(status_code=503, detail=key_exhausted_message)
                        break 
                    elif status_code == 429:
                        logger.warning(f"Rate limit for {self.service_name} (key ...{current_api_key[-4:]}): HTTP {status_code} - {error_detail}. Trying next proxy or key.")
                        if not self.proxy_manager.active or not self.proxy_manager.rotate_proxy():
                            if not self.api_key_manager.rotate_key(self.service_name): raise HTTPException(status_code=429, detail=key_exhausted_message + " (Rate limit)")
                            break
                    elif 400 <= status_code < 500:
                         logger.error(f"Client error for {self.service_name} (key ...{current_api_key[-4:]}): HTTP {status_code} - {error_detail}")
                         raise HTTPException(status_code=status_code, detail=f"Gemini API client error: {error_detail}")
                    else: 
                        logger.warning(f"Server/Connection error for {self.service_name} (key ...{current_api_key[-4:]}): HTTP {status_code} - {error_detail}. Trying next proxy or key.")
                        if not self.proxy_manager.active or not self.proxy_manager.rotate_proxy():
                            if not self.api_key_manager.rotate_key(self.service_name): raise HTTPException(status_code=502, detail=key_exhausted_message + f" (HTTP {status_code})")
                            break
                except httpx.RequestError as e:
                    logger.warning(f"httpx.RequestError for {self.service_name} (key ...{current_api_key[-4:]}): {type(e).__name__} - {str(e)}. Trying next proxy or key.")
                    if not self.proxy_manager.active or not self.proxy_manager.rotate_proxy():
                        if not self.api_key_manager.rotate_key(self.service_name): raise HTTPException(status_code=504, detail=key_exhausted_message + " (RequestError)")
                        break
                except Exception as e:
                    logger.error(f"Unexpected error during Gemini API call for {self.service_name} (key ...{current_api_key[-4:]}): {type(e).__name__} - {str(e)}")
                    raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
                if not self.proxy_manager.active:
                    if not self.api_key_manager.rotate_key(self.service_name): raise HTTPException(status_code=503, detail=key_exhausted_message)
                    break
                if current_proxy_config is None and self.proxy_manager.proxies:
                     if not self.api_key_manager.rotate_key(self.service_name): raise HTTPException(status_code=503, detail=key_exhausted_message)
                     break

    async def _execute_streaming_with_rotation(
        self,
        endpoint_path: str,
        payload: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        key_exhausted_message = f"All API keys for {self.service_name} are exhausted or failed."
        
        while True: # Key loop
            current_api_key = self.api_key_manager.get_key(self.service_name)
            if not current_api_key:
                logger.error(key_exhausted_message)
                # Вместо HTTPException, можно yield ошибку, если клиент это поддерживает
                raise HTTPException(status_code=503, detail=key_exhausted_message) 

            self.proxy_manager.reset_proxies()

            while True: # Proxy loop
                current_proxy_config = None
                httpx_proxies = None
                if self.proxy_manager.active:
                    current_proxy_config = self.proxy_manager.get_proxy()
                    httpx_proxies = self._get_httpx_proxies(current_proxy_config)
                
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": current_api_key,
                    "Accept": "text/event-stream" 
                }
                url = f"{GEMINI_API_BASE_URL}{endpoint_path}"
                proxy_url_for_log = current_proxy_config['url'] if current_proxy_config else "None (Direct)"
                logger.debug(f"Attempting Gemini API stream: POST {url} with key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}")

                try:
                    client_args = {"timeout": None} 
                    if httpx_proxies:
                        client_args["proxies"] = httpx_proxies
                    
                    async with httpx.AsyncClient(**client_args) as client:
                        async with client.stream("POST", url, headers=headers, json=payload) as response:
                            if response.status_code != 200: # Проверяем статус до чтения потока
                                error_content = await response.aread()
                                try:
                                    error_data = json.loads(error_content)
                                    error_detail = error_data.get("error", {}).get("message", error_content.decode(errors='ignore'))
                                except json.JSONDecodeError:
                                    error_detail = error_content.decode(errors='ignore')
                                
                                # Обработка ошибок HTTP для стриминга
                                status_code = response.status_code
                                if status_code in [401, 403]:
                                    logger.warning(f"Key error for {self.service_name} stream (key ...{current_api_key[-4:]}): HTTP {status_code} - {error_detail}. Rotating key.")
                                    if not self.api_key_manager.rotate_key(self.service_name):
                                        raise HTTPException(status_code=503, detail=key_exhausted_message)
                                    break # New key, retry proxy loop
                                elif status_code == 429:
                                    logger.warning(f"Rate limit for {self.service_name} stream (key ...{current_api_key[-4:]}): HTTP {status_code} - {error_detail}. Trying next proxy or key.")
                                    if not self.proxy_manager.active or not self.proxy_manager.rotate_proxy():
                                        if not self.api_key_manager.rotate_key(self.service_name):
                                            raise HTTPException(status_code=429, detail=key_exhausted_message + " (Rate limit on all proxies/keys)")
                                        break # New key, retry proxy loop
                                    continue # New proxy, retry with current key
                                elif 400 <= status_code < 500:
                                    raise HTTPException(status_code=status_code, detail=f"Gemini API client error (stream): {error_detail}")
                                else: # 5xx
                                    logger.warning(f"Server/Connection error for {self.service_name} stream (key ...{current_api_key[-4:]}): HTTP {status_code} - {error_detail}. Trying next proxy or key.")
                                    if not self.proxy_manager.active or not self.proxy_manager.rotate_proxy():
                                        if not self.api_key_manager.rotate_key(self.service_name):
                                            raise HTTPException(status_code=502, detail=key_exhausted_message + f" (HTTP {status_code} on all proxies/keys for stream)")
                                        break # New key, retry proxy loop
                                    continue # New proxy, retry with current key
                                # Если break/continue не сработал, значит нужно выйти из proxy loop
                                break # Выход из proxy loop для смены ключа или ошибки

                            # Если статус 200, начинаем читать поток
                            logger.debug(f"Gemini _execute_streaming_with_rotation: Status 200. Reading stream lines for key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}")
                            line_count = 0 # Считает количество текстовых чанков, полученных от httpx
                            data_chunk_count = 0 # Считает количество успешно распарсенных и выданных JSON-объектов
                            json_buffer = ""
                            
                            # Читаем весь поток как текст
                            async for text_chunk in response.aiter_text():
                                line_count += 1 
                                json_buffer += text_chunk
                                logger.debug(f"Gemini _execute_streaming_with_rotation: Appended text chunk #{line_count} (length {len(text_chunk)}). Current buffer size: {len(json_buffer)}")
                            
                            logger.info(f"Gemini _execute_streaming_with_rotation: Full response buffer received (length {len(json_buffer)}). Attempting to parse as JSON array.")
                            # logger.debug(f"Full buffer content: {json_buffer}") # Раскомментировать для очень детальной отладки всего буфера

                            if not json_buffer.strip():
                                logger.warning("Gemini _execute_streaming_with_rotation: Stream buffer is empty after reading.")
                                return

                            try:
                                # Gemini API возвращает массив JSON-объектов: [{obj1}, {obj2}, ..., {objN}]
                                full_response_array = json.loads(json_buffer)
                                
                                if isinstance(full_response_array, list):
                                    if not full_response_array:
                                        logger.warning("Gemini _execute_streaming_with_rotation: Parsed an empty list from stream.")
                                    for item in full_response_array:
                                        if isinstance(item, dict):
                                            data_chunk_count += 1
                                            logger.debug(f"Gemini _execute_streaming_with_rotation: Yielding item from parsed array: {item}")
                                            yield item
                                        else:
                                            logger.warning(f"Gemini _execute_streaming_with_rotation: Item in parsed array is not a dict: {type(item)}. Item: {str(item)[:200]}")
                                elif isinstance(full_response_array, dict): 
                                    logger.warning("Gemini _execute_streaming_with_rotation: Expected a list of objects from stream, but got a single dict. Yielding it.")
                                    data_chunk_count += 1
                                    yield full_response_array
                                else:
                                    logger.error(f"Gemini _execute_streaming_with_rotation: Parsed stream content is not a list or dict. Type: {type(full_response_array)}. Buffer (start): {json_buffer[:200]}")
                                    raise HTTPException(status_code=500, detail="Gemini API stream did not return a valid JSON array or object.")

                            except json.JSONDecodeError as e:
                                logger.error(f"Gemini _execute_streaming_with_rotation: Failed to parse JSON from Gemini stream buffer. Error: {e}. Buffer (start): '{json_buffer[:500]}...'")
                                raise HTTPException(status_code=500, detail=f"Failed to parse Gemini API response stream: {e}")
                            
                            logger.info(f"Gemini API stream processing finished for {self.service_name} with key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}. Text chunks read: {line_count}, data chunks processed: {data_chunk_count}.")
                            return

                except httpx.RequestError as e: # Ошибки соединения до получения ответа
                    logger.warning(f"httpx.RequestError for {self.service_name} stream (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {type(e).__name__} - {str(e)}. Trying next proxy or key.")
                    if not self.proxy_manager.active or not self.proxy_manager.rotate_proxy():
                        if not self.api_key_manager.rotate_key(self.service_name):
                            raise HTTPException(status_code=504, detail=key_exhausted_message + " (RequestError on all proxies/keys for stream - Gateway Timeout)")
                        break # New key, retry proxy loop
                    # continue to next proxy with current key
                except Exception as e:
                    logger.error(f"Unexpected error during Gemini API stream for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {type(e).__name__} - {str(e)}")
                    # Можно yield ошибку, если клиент это поддерживает, или re-raise
                    raise HTTPException(status_code=500, detail=f"Unexpected error in stream: {str(e)}")
                
                if not self.proxy_manager.active: 
                    if not self.api_key_manager.rotate_key(self.service_name):
                        raise HTTPException(status_code=503, detail=key_exhausted_message)
                    break 
                if current_proxy_config is None and self.proxy_manager.proxies: 
                     if not self.api_key_manager.rotate_key(self.service_name):
                         raise HTTPException(status_code=503, detail=key_exhausted_message)
                     break

    async def chat_completion(self, request: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        chat_id = f"gen-{int(time.time())}-{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789', k=10))}"
        created_time = int(time.time())
        
        model_name_from_request = request.get("model", self.default_model)
        if '/' in model_name_from_request:
            parts = model_name_from_request.split('/')
            if len(parts) == 2 and parts[0] == self.service_name:
                model_name_from_request = parts[1]
        
        model_to_use = f"models/{model_name_from_request}" if not model_name_from_request.startswith("models/") else model_name_from_request
        model_name_for_response = model_to_use.replace("models/", "")

        logger.debug(f"Gemini chat_completion ({chat_id}): Starting for model {model_name_for_response}. Request: {request}")
        
        gemini_contents = []
        for msg in request.get("messages", []):
            role = "user" if msg.get("role") == "user" else "model"
            content = msg.get("content")
            if not isinstance(content, str):
                content = str(content) if content is not None else ""
            gemini_contents.append({"role": role, "parts": [{"text": content}]})

        payload = {"contents": gemini_contents}
        
        generation_config = {}
        if "temperature" in request and request["temperature"] is not None:
            generation_config["temperature"] = request["temperature"]
        if "max_tokens" in request and request["max_tokens"] is not None:
            generation_config["maxOutputTokens"] = request["max_tokens"]
        if generation_config:
            payload["generationConfig"] = generation_config

        logger.debug(f"Gemini chat_completion ({chat_id}): Prepared payload: {payload}")

        yield {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": model_name_for_response,
            "provider": "google-gemini",
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "logprobs": None, "finish_reason": None, "native_finish_reason": None}]
        }
        logger.debug(f"Gemini chat_completion ({chat_id}): Yielded initial role chunk.")

        last_gemini_chunk_for_metadata = None
        accumulated_text = ""
        gemini_chunk_counter = 0

        logger.debug(f"Gemini chat_completion ({chat_id}): Entering stream processing loop with _execute_streaming_with_rotation.")
        try:
            async for gemini_chunk in self._execute_streaming_with_rotation(f"/{model_to_use}:streamGenerateContent", payload):
                gemini_chunk_counter += 1
                logger.debug(f"Gemini chat_completion ({chat_id}): Received Gemini chunk #{gemini_chunk_counter} from _execute_streaming_with_rotation: {gemini_chunk}")
                last_gemini_chunk_for_metadata = gemini_chunk 
                
                current_text_in_chunk = ""
                # gemini_chunk теперь это один из объектов массива, возвращаемого Gemini API
                if isinstance(gemini_chunk, dict) and gemini_chunk.get("candidates"):
                    candidate = gemini_chunk["candidates"][0] # Берем первого кандидата
                    if candidate.get("content") and candidate["content"].get("parts"):
                        # Собираем текст из всех parts, если их несколько (хотя обычно одна для текстовых моделей)
                        for part in candidate["content"]["parts"]:
                            current_text_in_chunk += part.get("text", "")
                
                text_delta = ""
                if current_text_in_chunk:
                    # Логика для извлечения дельты, если Gemini присылает нарастающий итог
                    if current_text_in_chunk.startswith(accumulated_text):
                        text_delta = current_text_in_chunk[len(accumulated_text):]
                    else:
                        # Если текст не начинается с накопленного, это может быть новый блок текста
                        # или Gemini присылает только фактические дельты.
                        # Для Gemini, который обычно присылает полные фрагменты в каждом чанке потока,
                        # эта ветка (else) означает, что пришел новый, не связанный с предыдущим, фрагмент,
                        # либо это самый первый фрагмент.
                        text_delta = current_text_in_chunk
                        # Сбрасываем accumulated_text, так как current_text_in_chunk не является его продолжением
                        # accumulated_text = "" # Это может быть неверно, если Gemini шлет только дельты.
                                            # Пока оставим так, чтобы увидеть, что приходит.
                                            # Если Gemini шлет только дельты, то accumulated_text не нужно сбрасывать,
                                            # а text_delta всегда будет равен current_text_in_chunk.

                    accumulated_text += text_delta # Обновляем накопленный текст, добавляя только реальную дельту
                
                if text_delta: # Отправляем чанк, только если есть реальное изменение текста
                    content_chunk_to_yield = {
                        "id": chat_id,
                        "object": "chat.completion.chunk",
                        "created": created_time,
                        "model": model_name_for_response,
                        "provider": "google-gemini",
                        "choices": [{"index": 0, "delta": {"content": text_delta}, "logprobs": None, "finish_reason": None, "native_finish_reason": None}]
                    }
                    yield content_chunk_to_yield
                    logger.debug(f"Gemini chat_completion ({chat_id}): Yielded content chunk: {content_chunk_to_yield}")
            logger.debug(f"Gemini chat_completion ({chat_id}): Exited stream processing loop. Processed {gemini_chunk_counter} Gemini chunks.")

        except Exception as e:
            logger.error(f"Gemini chat_completion ({chat_id}): Error during stream processing: {type(e).__name__} - {str(e)}", exc_info=True)
            # Consider yielding an error chunk if the client expects it
            # For now, just re-raise or let it propagate if it's an HTTPException
            if not isinstance(e, HTTPException):
                 raise HTTPException(status_code=500, detail=f"Error processing Gemini stream: {str(e)}")
            else:
                raise # Re-raise HTTPException
        
        openai_finish_reason = "stop"
        native_gemini_finish_reason = "FINISH_REASON_UNSPECIFIED"

        if last_gemini_chunk_for_metadata and last_gemini_chunk_for_metadata.get("candidates"):
            candidate = last_gemini_chunk_for_metadata["candidates"][0]
            gemini_reason = candidate.get("finishReason")
            if gemini_reason:
                native_gemini_finish_reason = gemini_reason
                finish_reason_map = {
                    "STOP": "stop", "MAX_TOKENS": "length", 
                    "SAFETY": "content_filter", "RECITATION": "content_filter",
                    "OTHER": "stop", "FINISH_REASON_UNSPECIFIED": "stop"
                }
                openai_finish_reason = finish_reason_map.get(gemini_reason, "stop")
        
        final_chunk_to_yield = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": model_name_for_response,
            "provider": "google-gemini",
            "choices": [{"index": 0, "delta": {}, "logprobs": None, 
                         "finish_reason": openai_finish_reason, 
                         "native_finish_reason": native_gemini_finish_reason}]
        }
        yield final_chunk_to_yield
        logger.debug(f"Gemini chat_completion ({chat_id}): Yielded final chunk with finish_reason: {openai_finish_reason}. Chunk: {final_chunk_to_yield}")

        include_usage = request.get("stream_options", {}).get("include_usage", False)
        if include_usage:
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            if last_gemini_chunk_for_metadata and "usageMetadata" in last_gemini_chunk_for_metadata:
                usage_meta = last_gemini_chunk_for_metadata["usageMetadata"]
                prompt_tokens = usage_meta.get("promptTokenCount", 0)
                total_tokens = usage_meta.get("totalTokenCount", 0)
                if total_tokens > 0 and prompt_tokens > 0:
                    completion_tokens = total_tokens - prompt_tokens
                elif "candidatesTokenCount" in usage_meta: 
                     completion_tokens = usage_meta.get("candidatesTokenCount", 0)
            elif last_gemini_chunk_for_metadata and "promptFeedback" in last_gemini_chunk_for_metadata and \
                 last_gemini_chunk_for_metadata["promptFeedback"].get("blockReason"):
                 pass

            usage_chunk_to_yield = {
                "id": chat_id, 
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": model_name_for_response,
                "provider": "google-gemini",
                "choices": [], 
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens if total_tokens > 0 else prompt_tokens + completion_tokens,
                    "prompt_tokens_details": None
                }
            }
            yield usage_chunk_to_yield
            logger.debug(f"Gemini chat_completion ({chat_id}): Yielded usage chunk: {usage_chunk_to_yield}")
        
        logger.debug(f"Gemini chat_completion ({chat_id}): Processing complete.")

    async def list_models(self) -> Dict[str, Any]:
        response_data = await self._execute_non_streaming_with_rotation("GET", "/models")
        openai_models = []
        if response_data and "models" in response_data:
            for gemini_model in response_data["models"]:
                if "generateContent" in gemini_model.get("supportedGenerationMethods", []):
                    openai_models.append({
                        "id": gemini_model.get("name", "").replace("models/", ""), 
                        "object": "model",
                        "owned_by": "google", 
                        "permission": [] 
                    })
        return {"object": "list", "data": openai_models}

    async def completion(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return {"error": {"message": "The Gemini module does not support the legacy completion operation.", "type": "invalid_request_error"}}
    async def embeddings(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return {"error": {"message": "The Gemini module does not support the embeddings operation.", "type": "invalid_request_error"}}
    async def moderations(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return {"error": {"message": "The Gemini module does not support the moderations operation.", "type": "invalid_request_error"}}
    async def generate_image(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return {"error": {"message": "The Gemini module does not support the image generation operation.", "type": "invalid_request_error"}}
    async def audio_transcription(self, request: Dict[str, Any], file_data: bytes) -> Dict[str, Any]:
        return {"error": {"message": "The Gemini module does not support the audio transcription operation.", "type": "invalid_request_error"}}
    async def audio_translation(self, request: Dict[str, Any], file_data: bytes) -> Dict[str, Any]:
        return {"error": {"message": "The Gemini module does not support the audio translation operation.", "type": "invalid_request_error"}}
