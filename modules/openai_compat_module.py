import datetime
import httpx
from httpx_socks import AsyncProxyTransport
from typing import Dict, Any, Optional, AsyncGenerator, List

from .base_module import BaseModule
from api_key_manager import ApiKeyManager
from proxy_manager import ProxyManager, ProxyConfig
import logging
from fastapi import HTTPException
import json

# Импортируем функцию reformat_messages
from handlers.misc.one_messager import reformat_messages
# Импортируем функцию для получения настроек reformat_messages
from admin_router import get_reformat_settings

logger = logging.getLogger(__name__)

class OpenAICompatModule(BaseModule):

    @staticmethod
    def parse_instance_and_model_id(model_identifier: str):
        """
        Парсер для нового id вида OAIC/{instance}/{provider_path}.
        Возвращает: (instance_name: str, provider_model_path: str)
        """
        if not isinstance(model_identifier, str):
            return None, None
        if model_identifier.startswith("OAIC/"):
            parts = model_identifier.split("/", 2)
            if len(parts) < 3:
                return None, None
            instance = parts[1]
            provider_model_path = parts[2]
            return instance, provider_model_path
        return None, None

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

    def get_name(self) -> str:
        return "OAIC"

    def _get_httpx_proxies(self, proxy_config: Optional[ProxyConfig]) -> Optional[Dict[str, str]]:
        if proxy_config:
            if proxy_config['type'] in ['http', 'https']:
                 return {
                    "http://": proxy_config['url'],
                    "https://": proxy_config['url'],
                }
            elif proxy_config['type'] in ['socks4', 'socks5']:
                return {
                    "http://": proxy_config['url'],
                    "https://": proxy_config['url'],
                }
        return None

    def _get_instance_config(self, instance_name: str) -> Optional[Dict[str, Any]]:
        logger.info(self.instances_config)
        for conf in self.instances_config:
            if conf["name"] == instance_name:
                return conf
        return None

    # TODO: ApiKeyManager должен быть адаптирован для работы с ключами инстансов
    def _get_instance_api_key(self, instance_name: str) -> Optional[str]:
        instance_config = self._get_instance_config(instance_name)
        if instance_config and instance_config.get("api_keys"):
            return instance_config["api_keys"][0]
        return None

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
        # TODO: Реализовать полноценную ротацию ключей для инстанса
        current_api_key = self._get_instance_api_key(instance_name)
        if not current_api_key:
            raise HTTPException(status_code=503, detail=f"No API keys available for instance '{instance_name}'.")

        key_exhausted_message = f"All API keys for instance {instance_name} are exhausted or failed."

        current_proxy_config = None
        httpx_proxies = None
        # INDIVIDUAL PROXY LOGIC: учитываем флаг use_global_proxy
        use_global_proxy = instance_config.get("use_global_proxy", True)
        if use_global_proxy and self.proxy_manager.active:
            current_proxy_config = self.proxy_manager.get_proxy()
            httpx_proxies = self._get_httpx_proxies(current_proxy_config)

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {current_api_key}"}
        if extra_headers:
            headers.update(extra_headers)
            
        url = f"{base_url.rstrip('/')}{endpoint_path}"
        proxy_url_for_log = current_proxy_config['url'] if current_proxy_config else "None (Direct)"
        logger.debug(f"Attempting OpenAI Compatible API call for instance '{instance_name}': {method} {url} with key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}")
        try:
            client_args = {"timeout": 30.0}
            transport = None
            if httpx_proxies:
                proxy_url_for_transport = httpx_proxies.get("http://") 
                if proxy_url_for_transport and proxy_url_for_transport.startswith(("socks5://", "socks4://")):
                    logger.debug(f"Creating AsyncProxyTransport for SOCKS: {proxy_url_for_transport}")
                    transport = AsyncProxyTransport.from_url(proxy_url_for_transport)
                    client_args["transport"] = transport
                else:
                    client_args["proxies"] = httpx_proxies

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
                response_data = response.json()
                logger.info(f"OpenAI Compatible API call successful for instance {instance_name} with key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}.")

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
                logger.warning(f"Key error for instance {instance_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}. Rotating key.")
                # TODO: Implement key rotation for instance
                raise HTTPException(status_code=status_code, detail=f"Key error for instance {instance_name}: {error_detail}")
            
            elif 400 <= status_code < 500 and status_code != 429:
                logger.error(f"Client error for instance {instance_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}")
                raise HTTPException(status_code=status_code, detail=f"OpenAI Compatible API client error: {error_detail}")
            
            else:
                logger.warning(f"HTTPStatusError (status {status_code}, type {type(e).__name__}) for instance {instance_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {error_detail}. Attempting proxy rotation.")
                if self.proxy_manager.active and self.proxy_manager.rotate_proxy():
                    logger.info(f"Successfully rotated to next proxy for key ...{current_api_key[-4:]} of instance {instance_name}. Retrying.")
                    raise HTTPException(status_code=status_code, detail=f"Error after proxy rotation attempt: {error_detail}")
                else:
                    raise HTTPException(status_code=status_code, detail=f"Error, proxy rotation failed or exhausted: {error_detail}")

        except (httpx.RequestError, Exception) as e: 
            error_type_name = type(e).__name__
            logger.warning(f"{error_type_name} for instance {instance_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {str(e)}. Attempting proxy rotation.")
            if self.proxy_manager.active and self.proxy_manager.rotate_proxy():
                logger.info(f"Successfully rotated to next proxy for key ...{current_api_key[-4:]} of instance {instance_name} after {error_type_name}. Retrying.")
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
        if not current_api_key:
            logger.error(f"No API keys available for instance '{instance_name}' for streaming.")
            yield {"error": {"message": f"No API keys for instance '{instance_name}'.", "type": "server_error", "code": "no_api_keys"}}
            return

        current_proxy_config = None
        httpx_proxies = None
        # INDIVIDUAL PROXY LOGIC: учитываем флаг use_global_proxy
        use_global_proxy = instance_config.get("use_global_proxy", True)
        if use_global_proxy and self.proxy_manager.active:
            current_proxy_config = self.proxy_manager.get_proxy()
            httpx_proxies = self._get_httpx_proxies(current_proxy_config)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {current_api_key}",
            "Accept": "text/event-stream"
        }
        if extra_headers:
            headers.update(extra_headers)

        url = f"{base_url.rstrip('/')}{endpoint_path}"
        proxy_url_for_log = current_proxy_config['url'] if current_proxy_config else "None (Direct)"
        logger.debug(f"Attempting OpenAI Compatible API stream for instance '{instance_name}': POST {url} with key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}")
        try:
            client_args = {"timeout": None}
            transport_stream = None
            if httpx_proxies:
                proxy_url_for_transport_stream = httpx_proxies.get("http://")
                if proxy_url_for_transport_stream and proxy_url_for_transport_stream.startswith(("socks5://", "socks4://")):
                    logger.debug(f"Creating AsyncProxyTransport for SOCKS stream: {proxy_url_for_transport_stream}")
                    transport_stream = AsyncProxyTransport.from_url(proxy_url_for_transport_stream)
                    client_args["transport"] = transport_stream
                else:
                    client_args["proxies"] = httpx_proxies

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
                            logger.warning(f"Key error for instance {instance_name} stream (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}. Not retrying.")
                            yield {"error": {"message": f"Key error for instance {instance_name} stream: {error_detail}", "type": "authentication_error", "code": str(status_code)}}
                            return

                        elif 400 <= status_code < 500 and status_code != 429:
                            logger.error(f"Client error for instance {instance_name} stream (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}")
                            yield {"error": {"message": f"OpenAI Compatible API client error (stream): {error_detail}", "type": "invalid_request_error", "code": str(status_code)}}
                            return
                        else:
                            logger.warning(f"HTTPStatusError (status {status_code}) for instance {instance_name} stream (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {error_detail}. Attempting proxy rotation.")
                            if self.proxy_manager.active and self.proxy_manager.rotate_proxy():
                                logger.info(f"Successfully rotated to next proxy for key ...{current_api_key[-4:]} of instance {instance_name} (stream). Retrying.")
                                yield {"error": {"message": f"Error after proxy rotation attempt (stream): {error_detail}", "type": "server_error", "code": str(status_code)}}
                                return
                            else:
                                logger.warning(f"HTTP error {status_code} for instance {instance_name} stream, proxy rotation failed or exhausted. Not retrying.")
                                yield {"error": {"message": f"HTTP error {status_code}, proxy rotation failed/exhausted (stream): {error_detail}", "type": "server_error", "code": str(status_code)}}
                                return

                    logger.info(f"OpenAI Compatible API stream successful (status 200) for instance '{instance_name}' with key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}. Processing stream.")
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_content = line[len("data: "):].strip()
                            if data_content == "[DONE]":
                                logger.debug(f"Stream for instance '{instance_name}' ended with [DONE].")
                                break
                            logger.debug(f"Received stream message for instance '{instance_name}': {data_content}")
                            try:
                                chunk_obj = json.loads(data_content)
                                yield chunk_obj
                            except json.JSONDecodeError:
                                logger.error(f"JSONDecodeError in stream from instance '{instance_name}': {data_content}")

                    logger.info(f"OpenAI Compatible API stream processing finished for instance '{instance_name}'.")

                    # TODO: Force proxy rotation if enabled (similar to non-streaming)
                    return

        except (httpx.RequestError, Exception) as e:
            error_type_name = type(e).__name__
            logger.warning(f"{error_type_name} for instance {instance_name} stream (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {str(e)}. Not retrying with proxy/key rotation for now.")
            yield {"error": {"message": f"Error during stream connection or processing for instance '{instance_name}': {str(e)}", "type": "server_error", "code": "stream_error"}}
            return

    async def chat_completion(self, request: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        model_identifier = request.get("model", "")
        instance_name, actual_model_name = self.parse_instance_and_model_id(model_identifier)
        if not instance_name or not actual_model_name:
            logger.error(f"Invalid model identifier format for OpenAI Compatible module: {model_identifier}")
            yield {"error": {"message": f"Invalid model identifier format. Expected 'oai_compat_INSTANCE_NAME/model_name' or 'openai_INSTANCE_NAME/model_name', got '{model_identifier}'.", "type": "invalid_request_error"}}
            return
        
        payload_to_send = dict(request)
        payload_to_send["model"] = actual_model_name

        # Проверяем настройку reformat_messages
        reformat_settings = get_reformat_settings()
        print(self.get_name() + " " + instance_name)
        module_reformat_settings = reformat_settings.get(instance_name, {})
        
        # model_id в настройках хранится как "module_name/model_id", но здесь model_id уже без префикса модуля
        # Поэтому нужно использовать model_identifier, который включает префикс модуля
        # Или же, если model.id в admin_models.html уже содержит префикс, то model_id будет "OAIC/instance/model"
        # В данном случае model_identifier уже имеет формат "OAIC/instance/model",
        # а actual_model_name - это "instance/model".
        # Нам нужно проверить настройку для полного model_identifier, который приходит в запросе.
        # Или же, если model.id в admin_models.html уже содержит префикс, то model_id будет "OAIC/instance/model"
        # В admin_router.py set_reformat_setting принимает model_id и module_name.
        # model_id в admin_router.py будет "instance/model" (без OAIC), а module_name будет "OAIC".
        # Поэтому здесь нужно проверять по actual_model_name и self.get_name().
        
        if module_reformat_settings.get(model_identifier, False):
            logger.warning(f"Reformat messages enabled for model '{actual_model_name}' in module '{self.get_name()}'. Applying reformat_messages.")
            if "messages" in payload_to_send:
                messages_json_string = json.dumps(payload_to_send, ensure_ascii=False)
                reformatted_json_string = await reformat_messages(messages_json_string)
                reformatted_data = json.loads(reformatted_json_string)
                payload_to_send["messages"] = reformatted_data.get("messages", [])
            else:
                logger.warning(f"Reformat messages enabled for model '{actual_model_name}', but no 'messages' found in payload.")

        logger.debug(f"OpenAI Compatible chat_completion for instance '{instance_name}', model '{actual_model_name}'. Request: {payload_to_send}")

        async for chunk in self._execute_streaming_with_rotation(instance_name, "/chat/completions", payload_to_send):
            if isinstance(chunk, dict) and "id" in chunk:
                chunk["instance_name"] = instance_name
            yield chunk

    async def list_models(self) -> Dict[str, Any]:
        all_instance_models = []
        for instance_conf in self.instances_config:
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
        instance_name, actual_model_name = self.parse_instance_and_model_id(model_identifier)
        if not instance_name or not actual_model_name:
            raise HTTPException(status_code=400, detail=f"Invalid model format for completion. Expected 'oai_compat_INSTANCE_NAME/model_name' or 'openai_INSTANCE_NAME/model_name', got '{model_identifier}'.")

        payload_to_send = dict(request)
        payload_to_send["model"] = actual_model_name

        return await self._execute_non_streaming_with_rotation(instance_name, "POST", "/completions", payload_to_send)

    async def embeddings(self, request: Dict[str, Any]) -> Dict[str, Any]:
        model_identifier = request.get("model", "")
        instance_name, actual_model_name = self.parse_instance_and_model_id(model_identifier)
        if not instance_name:
            if self.instances_config:
                instance_name = self.instances_config[0]["name"]
                logger.warning(f"Embeddings call for model '{model_identifier}' without instance prefix, falling back to instance '{instance_name}'.")
            else:
                raise HTTPException(status_code=400, detail="No OpenAI Compatible instances configured for embeddings.")

        payload_to_send = request

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

        logger.info(f"Routing audio transcription to instance: {instance_name} for model {model_identifier}")

        files = {'file': (filename, file_data)}
        data_payload = {k: str(v) for k, v in request_params.items() if v is not None}

        instance_config = self._get_instance_config(instance_name)
        if not instance_config:
            raise HTTPException(status_code=400, detail=f"Instance '{instance_name}' not found.")
        base_url = instance_config["base_url"]
        api_key = self._get_instance_api_key(instance_name)
        if not api_key:
            raise HTTPException(status_code=503, detail=f"No API key for instance '{instance_name}'.")

        target_url = f"{base_url.rstrip('/')}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {api_key}"}

        httpx_proxies = None
        current_proxy_config = None
        if self.proxy_manager.active:
            current_proxy_config = self.proxy_manager.get_proxy()
            httpx_proxies = self._get_httpx_proxies(current_proxy_config)

        client_args = {"timeout": 60.0}
        if httpx_proxies:
            proxy_url_for_transport = httpx_proxies.get("http://")
            if proxy_url_for_transport and proxy_url_for_transport.startswith(("socks5://", "socks4://")):
                transport = AsyncProxyTransport.from_url(proxy_url_for_transport)
                client_args["transport"] = transport
            else:
                client_args["proxies"] = httpx_proxies

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

        logger.info(f"Routing audio translation to instance: {instance_name} for model {model_identifier}")

        files = {'file': (filename, file_data)}
        data_payload = {k: str(v) for k, v in request_params.items() if v is not None}

        instance_config = self._get_instance_config(instance_name)
        if not instance_config:
            raise HTTPException(status_code=400, detail=f"Instance '{instance_name}' not found.")
        base_url = instance_config["base_url"]
        api_key = self._get_instance_api_key(instance_name)
        if not api_key:
            raise HTTPException(status_code=503, detail=f"No API key for instance '{instance_name}'.")

        target_url = f"{base_url.rstrip('/')}/audio/translations"
        headers = {"Authorization": f"Bearer {api_key}"}

        httpx_proxies = None
        current_proxy_config = None
        if self.proxy_manager.active:
            current_proxy_config = self.proxy_manager.get_proxy()
            httpx_proxies = self._get_httpx_proxies(current_proxy_config)

        client_args = {"timeout": 60.0}
        if httpx_proxies:
            proxy_url_for_transport = httpx_proxies.get("http://")
            if proxy_url_for_transport and proxy_url_for_transport.startswith(("socks5://", "socks4://")):
                transport = AsyncProxyTransport.from_url(proxy_url_for_transport)
                client_args["transport"] = transport
            else:
                client_args["proxies"] = httpx_proxies

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
