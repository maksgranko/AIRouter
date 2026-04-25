import httpx
from httpx_socks import AsyncProxyTransport
import httpx
from httpx_socks import AsyncProxyTransport
from typing import Dict, Any, Optional, AsyncGenerator, List
from .base_module import BaseModule
from api_key_manager import ApiKeyManager
from proxy_manager import ProxyManager, ProxyConfig
import logging
from fastapi import HTTPException
import json
import time
import random

# Импортируем функцию reformat_messages
from handlers.misc.one_messager import reformat_messages
# Импортируем функцию для получения настроек reformat_messages
from admin_router import get_reformat_settings

logger = logging.getLogger(__name__)

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

class GeminiChatModule(BaseModule):
    def __init__(self, api_key_manager: ApiKeyManager, proxy_manager: ProxyManager, settings_file_path: str, service_name: str = "gemini", default_model: str = "gemini-pro"):
        self.api_key_manager = api_key_manager
        self.proxy_manager = proxy_manager
        self.settings_file_path = settings_file_path
        self.service_name = service_name
        self.default_model = default_model
        self.last_api_key_used_for_proxy_context: Optional[str] = None
        self.first_key_in_overall_cycle: Optional[str] = None
        self.key_loop_initial_run: bool = True

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
                return {
                    "http://": proxy_config['url'],
                    "https://": proxy_config['url'],
                }
        return None

    async def _execute_non_streaming_with_rotation(
        self,
        method: str,
        endpoint_path: str,
        payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        key_exhausted_message = f"All API keys for {self.service_name} are exhausted or failed."

        if self.key_loop_initial_run:
            self.first_key_in_overall_cycle = self.api_key_manager.get_key(self.service_name, peek=True)
            self.key_loop_initial_run = False

        key_was_rotated_in_current_api_call = False

        while True:
            current_api_key = self.api_key_manager.get_key(self.service_name)
            if not current_api_key:
                logger.error(key_exhausted_message + " (No keys available at start of key loop for Gemini non-streaming)")
                raise HTTPException(status_code=503, detail=key_exhausted_message + " (No keys available at start of key loop for Gemini non-streaming)")

            if self.last_api_key_used_for_proxy_context != current_api_key or key_was_rotated_in_current_api_call:
                logger.debug(f"API key changed or rotated for {self.service_name} (non-streaming). Old: {self.last_api_key_used_for_proxy_context}, New: {current_api_key}. Resetting proxies.")
                self.proxy_manager.reset_proxies()
                self.last_api_key_used_for_proxy_context = current_api_key
                if key_was_rotated_in_current_api_call:
                    key_was_rotated_in_current_api_call = False

            while True:
                current_proxy_config = None
                httpx_proxies = None
                # Индивидуальная настройка прокси
                use_global_proxy = True
                try:
                    with open(self.settings_file_path, 'r') as f:
                        settings_data = json.load(f)
                        use_global_proxy = settings_data.get("module_proxy_usage", {}).get(self.service_name, True)
                except Exception as e:
                    logger.error(f"Error reading module_proxy_usage for {self.service_name}: {e} (defaulting to True)")
                if use_global_proxy and self.proxy_manager.active:
                    current_proxy_config = self.proxy_manager.get_proxy()
                    httpx_proxies = self._get_httpx_proxies(current_proxy_config)

                headers = {"Content-Type": "application/json", "x-goog-api-key": current_api_key}
                url = f"{GEMINI_API_BASE_URL}{endpoint_path}"
                proxy_url_for_log = current_proxy_config['url'] if current_proxy_config else "None (Direct)"
                logger.debug(f"Attempting Gemini API call: {method} {url} with key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}")
                try:
                    client_args = {"timeout": 60.0}
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
                        logger.info(f"Gemini API call successful for {self.service_name} with key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}.")

                        force_rotation_enabled = False
                        try:
                            with open(self.settings_file_path, 'r') as f:
                                settings_data_json = json.load(f)
                                force_rotation_enabled = settings_data_json.get("proxy_settings", {}).get("force_proxy_rotation_after_request", False)
                        except Exception as e_settings:
                            logger.error(f"Could not read force_proxy_rotation_after_request from {self.settings_file_path} for Gemini (non-streaming): {e_settings}. Defaulting to False.")

                        if force_rotation_enabled and \
                           self.proxy_manager.current_rotation_mode != "failover_cycle" and \
                           not self.proxy_manager.select_random_proxy_each_request:
                           if self.proxy_manager.active and self.proxy_manager.proxies:
                               logger.debug("Force rotating proxy after successful call as per settings (Gemini non-streaming).")
                               self.proxy_manager.rotate_proxy()
                        return response_data
                except httpx.HTTPStatusError as e:
                    error_response_data = {}
                    try: error_response_data = e.response.json()
                    except json.JSONDecodeError: pass 
                    error_detail = error_response_data.get("error", {}).get("message", e.response.text or f"HTTP {e.response.status_code}")
                    status_code = e.response.status_code

                    if status_code in [401, 403]:
                        logger.warning(f"Key error for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}. Rotating key.")
                        previous_key_for_check = current_api_key
                        if not self.api_key_manager.rotate_key(self.service_name):
                            raise HTTPException(status_code=503, detail=key_exhausted_message + " (No keys to rotate to after auth error)")
                        key_was_rotated_in_current_api_call = True
                        current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                        if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                            logger.warning(f"Completed a full cycle of API keys for {self.service_name} (non-streaming) due to HTTP {status_code}. All keys failed. Raising final exception.")
                            raise HTTPException(status_code=status_code, detail=f"{key_exhausted_message} (Full key cycle for HTTP {status_code})")
                        break

                    elif 400 <= status_code < 500 and status_code != 429:
                        logger.error(f"Client error for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}")
                        raise HTTPException(status_code=status_code, detail=f"Gemini API client error: {error_detail}")

                    else:
                        logger.warning(f"HTTPStatusError (status {status_code}, type {type(e).__name__}) for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {error_detail}. Attempting proxy rotation.")
                        if self.proxy_manager.active and self.proxy_manager.rotate_proxy():
                            logger.info(f"Successfully rotated to next proxy for key ...{current_api_key[-4:]}. Retrying.")
                            continue
                        else:
                            logger.warning(f"Failed to rotate proxy or proxies exhausted for key ...{current_api_key[-4:]}. Attempting key rotation.")
                            previous_key_for_check = current_api_key
                            if not self.api_key_manager.rotate_key(self.service_name):
                                final_err_msg = f"{key_exhausted_message} (HTTPStatusError {status_code} on all proxies/keys, no keys to rotate to)"
                                logger.error(final_err_msg)
                                raise HTTPException(status_code=status_code if status_code in [429, 502, 503, 504] else 500, detail=final_err_msg)
                            key_was_rotated_in_current_api_call = True
                            current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                            if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                                logger.warning(f"Completed a full cycle of API keys for {self.service_name} (non-streaming) due to HTTPStatusError {status_code}. All keys failed. Raising final exception.")
                                raise HTTPException(status_code=status_code if status_code in [429, 502, 503, 504] else 500, detail=f"{key_exhausted_message} (Full key cycle for HTTPStatusError {status_code})")
                            break

                except (httpx.RequestError, Exception) as e:
                    error_type_name = type(e).__name__
                    logger.warning(f"{error_type_name} for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {str(e)}. Attempting proxy rotation.")
                    if self.proxy_manager.active and self.proxy_manager.rotate_proxy():
                        logger.info(f"Successfully rotated to next proxy for key ...{current_api_key[-4:]} after {error_type_name}. Retrying.")
                        continue
                    else:
                        logger.warning(f"Failed to rotate proxy or proxies exhausted for key ...{current_api_key[-4:]} after {error_type_name}. Attempting key rotation.")
                        previous_key_for_check = current_api_key
                        if not self.api_key_manager.rotate_key(self.service_name):
                            final_err_msg = f"{key_exhausted_message} ({error_type_name} on all proxies/keys, no keys to rotate to)"
                            logger.error(final_err_msg)
                            status_code_for_exc = 504 if isinstance(e, httpx.TimeoutException) else 502 if isinstance(e, (httpx.NetworkError, httpx.ConnectError, httpx.ProxyError)) else 500
                            raise HTTPException(status_code=status_code_for_exc, detail=final_err_msg)
                        key_was_rotated_in_current_api_call = True
                        current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                        if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                            logger.warning(f"Completed a full cycle of API keys for {self.service_name} (non-streaming) due to {error_type_name}. All keys failed. Raising final exception.")
                            raise HTTPException(status_code=status_code_for_exc, detail=f"{key_exhausted_message} (Full key cycle for {error_type_name})")
                        break

                if not self.proxy_manager.active:
                    logger.debug(f"Direct call failed for key ...{current_api_key[-4:]} (proxies inactive). Rotating key.")
                    previous_key_for_check = current_api_key
                    if not self.api_key_manager.rotate_key(self.service_name):
                        raise HTTPException(status_code=503, detail=key_exhausted_message + " (Direct call failed, no more keys)")
                    key_was_rotated_in_current_api_call = True
                    current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                    if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                        logger.warning(f"Completed a full cycle of API keys for {self.service_name} (non-streaming, direct call failed). All keys failed.")
                        raise HTTPException(status_code=503, detail=f"{key_exhausted_message} (Full key cycle, direct calls failed)")
                    break

                if current_proxy_config is None and self.proxy_manager.proxies:
                     logger.debug(f"All proxies tried for key ...{current_api_key[-4:]} (non-streaming). Rotating key.")
                     previous_key_for_check = current_api_key
                     if not self.api_key_manager.rotate_key(self.service_name):
                         raise HTTPException(status_code=503, detail=key_exhausted_message + " (All proxies tried, no more keys)")
                     key_was_rotated_in_current_api_call = True
                     current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                     if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                        logger.warning(f"Completed a full cycle of API keys for {self.service_name} (non-streaming, all proxies tried). All keys failed.")
                        raise HTTPException(status_code=503, detail=f"{key_exhausted_message} (Full key cycle, all proxies tried)")
                     break

    async def _execute_streaming_with_rotation(
        self,
        endpoint_path: str,
        payload: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        key_exhausted_message = f"All API keys for {self.service_name} are exhausted or failed."

        if self.key_loop_initial_run:
            self.first_key_in_overall_cycle = self.api_key_manager.get_key(self.service_name, peek=True)
            self.key_loop_initial_run = False

        key_was_rotated_in_current_api_call = False

        while True:
            current_api_key = self.api_key_manager.get_key(self.service_name)
            if not current_api_key:
                logger.error(key_exhausted_message + " (No keys available at start of key loop for Gemini streaming)")
                raise HTTPException(status_code=503, detail=key_exhausted_message + " (No keys available at start of key loop for Gemini streaming)")

            if self.last_api_key_used_for_proxy_context != current_api_key or key_was_rotated_in_current_api_call:
                logger.debug(f"API key changed or rotated for {self.service_name} (streaming). Old: {self.last_api_key_used_for_proxy_context}, New: {current_api_key}. Resetting proxies.")
                self.proxy_manager.reset_proxies()
                self.last_api_key_used_for_proxy_context = current_api_key
                if key_was_rotated_in_current_api_call:
                    key_was_rotated_in_current_api_call = False

            while True:
                current_proxy_config = None
                httpx_proxies = None
                # Индивидуальная настройка прокси
                use_global_proxy = True
                try:
                    with open(self.settings_file_path, 'r') as f:
                        settings_data = json.load(f)
                        use_global_proxy = settings_data.get("module_proxy_usage", {}).get(self.service_name, True)
                except Exception as e:
                    logger.error(f"Error reading module_proxy_usage for {self.service_name}: {e} (defaulting to True)")
                if use_global_proxy and self.proxy_manager.active:
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
                    client_args = {"timeout": 60.0}
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
                                    logger.warning(f"Key error for {self.service_name} stream (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}. Rotating key.")
                                    previous_key_for_check = current_api_key
                                    if not self.api_key_manager.rotate_key(self.service_name):
                                        raise HTTPException(status_code=503, detail=key_exhausted_message + " (No keys to rotate to after auth error for stream)")
                                    key_was_rotated_in_current_api_call = True
                                    current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                                    if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                                        logger.warning(f"Completed a full cycle of API keys for {self.service_name} (streaming) due to HTTP {status_code}. All keys failed. Raising final exception.")
                                        raise HTTPException(status_code=status_code, detail=f"{key_exhausted_message} (Full key cycle for HTTP {status_code} in stream)")
                                    break

                                elif 400 <= status_code < 500 and status_code != 429:
                                    logger.error(f"Client error for {self.service_name} stream (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}")
                                    raise HTTPException(status_code=status_code, detail=f"Gemini API client error (stream): {error_detail}")

                                else:
                                    logger.warning(f"HTTPStatusError (status {status_code}) for {self.service_name} stream (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {error_detail}. Attempting proxy rotation.")
                                    if self.proxy_manager.active and self.proxy_manager.rotate_proxy():
                                        logger.info(f"Successfully rotated to next proxy for key ...{current_api_key[-4:]} (stream). Retrying.")
                                        continue
                                    else:
                                        logger.warning(f"Failed to rotate proxy or proxies exhausted for key ...{current_api_key[-4:]} (stream). Attempting key rotation.")
                                        previous_key_for_check = current_api_key
                                        if not self.api_key_manager.rotate_key(self.service_name):
                                            final_err_msg = f"{key_exhausted_message} (HTTPStatusError {status_code} on all proxies/keys for stream, no keys to rotate to)"
                                            logger.error(final_err_msg)
                                            raise HTTPException(status_code=status_code if status_code in [429, 502, 503, 504] else 500, detail=final_err_msg)
                                        key_was_rotated_in_current_api_call = True
                                        current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                                        if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                                            logger.warning(f"Completed a full cycle of API keys for {self.service_name} (streaming) due to HTTPStatusError {status_code}. All keys failed. Raising final exception.")
                                            raise HTTPException(status_code=status_code if status_code in [429, 502, 503, 504] else 500, detail=f"{key_exhausted_message} (Full key cycle for HTTPStatusError {status_code} in stream)")
                                        break

                            logger.info(f"Gemini API stream successful (status 200) for key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}. Reading stream.")

                            buffer = ""
                            brace_level = 0
                            object_start_index = -1
                            array_started = False
                            yielded_data_chunk_count = 0

                            async for text_chunk in response.aiter_text():
                                logger.debug(f"Gemini stream: Received text_chunk (length {len(text_chunk)}): '{text_chunk[:100]}...'")
                                buffer += text_chunk

                                while True:
                                    if not array_started:
                                        stripped_buffer = buffer.lstrip()
                                        if not stripped_buffer:
                                            break
                                        if stripped_buffer.startswith('['):
                                            array_started = True
                                            buffer = stripped_buffer[1:]
                                            object_start_index = -1
                                            brace_level = 0
                                            logger.debug("Gemini stream: JSON array started.")
                                            continue
                                        else:
                                            if len(buffer) > 1024*5 and not buffer.isspace():
                                                logger.error(f"Gemini stream error: Expected '[' at start of JSON array, got '{buffer[:50]}...' after significant data.")
                                                raise HTTPException(status_code=500, detail="Gemini stream error: Invalid JSON array start.")
                                            break

                                    if object_start_index == -1:
                                        temp_buffer = buffer.lstrip()
                                        if temp_buffer.startswith(','):
                                            temp_buffer = temp_buffer[1:].lstrip()

                                        start_brace_idx = temp_buffer.find('{')
                                        if start_brace_idx != -1:
                                            object_start_index = len(buffer) - len(temp_buffer) + start_brace_idx
                                            brace_level = 0
                                            logger.debug(f"Gemini stream: Potential object start found at index {object_start_index} in buffer.")
                                        else:
                                            if buffer.strip() == ']':
                                                logger.debug("Gemini stream: End of JSON array ']' detected.")
                                                buffer = ""
                                            elif not buffer.strip() or buffer.strip() == ',':
                                                logger.debug(f"Gemini stream: Buffer contains only whitespace/comma ('{buffer[:50]}...'), waiting for more data.")
                                            break

                                    if object_start_index != -1:
                                        current_scan_idx = object_start_index
                                        temp_brace_level = 0
                                        found_end_brace = False

                                        while current_scan_idx < len(buffer):
                                            char = buffer[current_scan_idx]
                                            if char == '{':
                                                temp_brace_level += 1
                                            elif char == '}':
                                                temp_brace_level -= 1
                                                if temp_brace_level == 0 and buffer[object_start_index] == '{':
                                                    obj_str = buffer[object_start_index : current_scan_idx + 1]
                                                    logger.debug(f"Gemini stream: Complete object candidate: '{obj_str[:100]}...'")
                                                    try:
                                                        parsed_obj = json.loads(obj_str)
                                                        yield parsed_obj
                                                        yielded_data_chunk_count += 1
                                                        logger.debug(f"Gemini stream: Yielded object #{yielded_data_chunk_count}")
                                                        buffer = buffer[current_scan_idx + 1:]
                                                        object_start_index = -1
                                                        found_end_brace = True
                                                        break
                                                    except json.JSONDecodeError as e:
                                                        logger.error(f"Gemini stream: JSONDecodeError for object string '{obj_str[:200]}...': {e}. Discarding segment.")
                                                        buffer = buffer[current_scan_idx + 1:]
                                                        object_start_index = -1
                                                        found_end_brace = True
                                                        break
                                            current_scan_idx += 1

                                        if not found_end_brace:
                                            logger.debug(f"Gemini stream: Incomplete object in buffer (brace_level: {temp_brace_level}), waiting for more data. Buffer: '{buffer[object_start_index:object_start_index+100]}...'")
                                            break
                                    else:
                                        break

                            if array_started and buffer.strip() and buffer.strip() != ']':
                                logger.warning(f"Gemini stream: Incomplete data or trailing content left in buffer at end of stream: '{buffer[:200]}...'")
                            elif not array_started and buffer.strip():
                                logger.warning(f"Gemini stream: Data left in buffer but JSON array start '[' was never found: '{buffer[:200]}...'")

                            logger.info(f"Gemini API stream processing finished for {self.service_name} with key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}. Data chunks yielded: {yielded_data_chunk_count}.")

                            force_rotation_enabled_stream = False
                            try:
                                with open(self.settings_file_path, 'r') as f:
                                    settings_data_stream = json.load(f)
                                    force_rotation_enabled_stream = settings_data_stream.get("proxy_settings", {}).get("force_proxy_rotation_after_request", False)
                            except Exception as e_settings_stream:
                                logger.error(f"Could not read force_proxy_rotation_after_request from {self.settings_file_path} for Gemini (streaming): {e_settings_stream}. Defaulting to False.")

                            if force_rotation_enabled_stream and \
                               self.proxy_manager.current_rotation_mode != "failover_cycle" and \
                               not self.proxy_manager.select_random_proxy_each_request:
                               if self.proxy_manager.active and self.proxy_manager.proxies:
                                   logger.debug("Force rotating proxy after successful stream as per settings (Gemini streaming).")
                                   self.proxy_manager.rotate_proxy()
                            return

                except (httpx.RequestError, Exception) as e:
                    error_type_name = type(e).__name__
                    is_proxy_related_error = "proxy" in str(e).lower() or "proxies" in str(e).lower()
                    log_message = (
                        f"{error_type_name} for {self.service_name} stream (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {str(e)}. "
                        f"{'This might be a proxy configuration issue. ' if is_proxy_related_error else ''}Attempting proxy rotation."
                    )
                    logger.warning(log_message)

                    if self.proxy_manager.active and self.proxy_manager.rotate_proxy():
                        logger.info(f"Successfully rotated to next proxy for key ...{current_api_key[-4:]} after {error_type_name} (stream). Retrying.")
                        continue
                    else:
                        logger.warning(f"Failed to rotate proxy or proxies exhausted for key ...{current_api_key[-4:]} after {error_type_name} (stream). Attempting key rotation.")
                        previous_key_for_check = current_api_key
                        if not self.api_key_manager.rotate_key(self.service_name):
                            final_err_msg = f"{key_exhausted_message} ({error_type_name} on all proxies/keys for stream, no keys to rotate to)"
                            logger.error(final_err_msg)
                            status_code_for_exc = 504 if isinstance(e, httpx.TimeoutException) else 502 if isinstance(e, (httpx.NetworkError, httpx.ConnectError, httpx.ProxyError)) else 500
                            if is_proxy_related_error and status_code_for_exc == 500: status_code_for_exc = 503
                            raise HTTPException(status_code=status_code_for_exc, detail=final_err_msg)
                        key_was_rotated_in_current_api_call = True
                        current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                        if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                            logger.warning(f"Completed a full cycle of API keys for {self.service_name} (streaming) due to {error_type_name}. All keys failed. Raising final exception.")
                            raise HTTPException(status_code=status_code_for_exc, detail=f"{key_exhausted_message} (Full key cycle for {error_type_name} in stream)")
                        break

                if not self.proxy_manager.active:
                    logger.debug(f"Direct call failed for key ...{current_api_key[-4:]} (proxies inactive, stream). Rotating key.")
                    previous_key_for_check = current_api_key
                    if not self.api_key_manager.rotate_key(self.service_name):
                        raise HTTPException(status_code=503, detail=key_exhausted_message + " (Direct call failed for stream, no more keys)")
                    key_was_rotated_in_current_api_call = True
                    current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                    if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                        logger.warning(f"Completed a full cycle of API keys for {self.service_name} (streaming, direct call failed). All keys failed.")
                        raise HTTPException(status_code=503, detail=f"{key_exhausted_message} (Full key cycle, direct calls failed for stream)")
                    break

                if current_proxy_config is None and self.proxy_manager.proxies:
                     logger.debug(f"All proxies tried for key ...{current_api_key[-4:]} (streaming). Rotating key.")
                     previous_key_for_check = current_api_key
                     if not self.api_key_manager.rotate_key(self.service_name):
                         raise HTTPException(status_code=503, detail=key_exhausted_message + " (All proxies tried for stream, no more keys)")
                     key_was_rotated_in_current_api_call = True
                     current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                     if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                        logger.warning(f"Completed a full cycle of API keys for {self.service_name} (streaming, all proxies tried). All keys failed.")
                        raise HTTPException(status_code=503, detail=f"{key_exhausted_message} (Full key cycle, all proxies tried for stream)")
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

        # Проверяем настройку reformat_messages
        reformat_settings = get_reformat_settings()
        module_reformat_settings = reformat_settings.get(self.get_name(), {})
        
        # model_id в настройках хранится как "module_name/model_id"
        # Здесь model_name_for_response - это просто имя модели, например "gemini-pro"
        # Поэтому нужно проверять по model_name_for_response и self.get_name().
        
        messages_to_process = request.get("messages", [])
        if module_reformat_settings.get(model_name_for_response, False):
            logger.warning(f"Reformat messages enabled for model '{model_name_for_response}' in module '{self.get_name()}'. Applying reformat_messages.")
            if messages_to_process:
                payload_for_reformat = {
                    "messages": messages_to_process
                }
                reformatted_json = await reformat_messages(json.dumps(payload_for_reformat, ensure_ascii=False))
                reformatted_payload = json.loads(reformatted_json)
                messages_to_process = reformatted_payload.get("messages", messages_to_process)
            else:
                logger.warning(f"Reformat messages enabled for model '{model_name_for_response}', but no 'messages' found in payload.")

        gemini_contents = []
        for msg in messages_to_process: # Используем messages_to_process после возможного реформатирования
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
                if isinstance(gemini_chunk, dict) and gemini_chunk.get("candidates"):
                    candidate = gemini_chunk["candidates"][0]
                    if candidate.get("content") and candidate["content"].get("parts"):
                        for part in candidate["content"]["parts"]:
                            current_text_in_chunk += part.get("text", "")

                text_delta = ""
                if current_text_in_chunk:
                    if current_text_in_chunk.startswith(accumulated_text):
                        text_delta = current_text_in_chunk[len(accumulated_text):]
                    else:
                        text_delta = current_text_in_chunk

                    accumulated_text += text_delta

                if text_delta:
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
            if not isinstance(e, HTTPException):
                 raise HTTPException(status_code=500, detail=f"Error processing Gemini stream: {str(e)}")
            else:
                raise

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
