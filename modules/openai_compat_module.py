import httpx
from httpx_socks import AsyncProxyTransport
from typing import Dict, Any, Optional, AsyncGenerator
from .base_module import BaseModule # Исправленный импорт, предполагает структуру проекта
from api_key_manager import ApiKeyManager
from proxy_manager import ProxyManager, ProxyConfig
import logging
from fastapi import HTTPException
import json
import time
import random

logger = logging.getLogger(__name__)

# Базовый URL для OpenAI API
OPENAI_API_BASE_URL = "https://api.openai.com/v1"

class OpenAIChatModule(BaseModule):
    def __init__(self, api_key_manager: ApiKeyManager, proxy_manager: ProxyManager, settings_file_path: str, service_name: str = "openai", default_model: str = "gpt-4o"):
        """
        Инициализирует модуль OpenAI Chat Compatible.

        Args:
            api_key_manager: Менеджер API ключей.
            proxy_manager: Менеджер прокси.
            settings_file_path: Путь к файлам настроек для чтения специфических параметров.
            service_name: Имя сервиса (по умолчанию "openai").
            default_model: Модель по умолчанию для использования (по умолчанию "gpt-4o").
        """
        self.api_key_manager = api_key_manager
        self.proxy_manager = proxy_manager
        self.settings_file_path = settings_file_path
        self.service_name = service_name
        self.default_model = default_model
        self.last_api_key_used_for_proxy_context: Optional[str] = None
        self.first_key_in_overall_cycle: Optional[str] = None
        self.key_loop_initial_run: bool = True

    def get_name(self) -> str:
        """Возвращает имя сервиса."""
        return self.service_name

    def _get_httpx_proxies(self, proxy_config: Optional[ProxyConfig]) -> Optional[Dict[str, str]]:
        """
        Преобразует конфигурацию прокси в формат, понятный httpx.
        Поддерживает http, https, socks4, socks5.
        """
        if proxy_config:
            if proxy_config['type'] in ['http', 'https']:
                 return {
                    "http://": proxy_config['url'],
                    "https://": proxy_config['url'],
                }
            elif proxy_config['type'] in ['socks4', 'socks5']:
                # Для SOCKS используем явные схемы http/https.
                # httpx-socks должен их корректно обработать через транспорт.
                # Здесь мы просто возвращаем URL, транспорт создается позже.
                 return {
                    "http://": proxy_config['url'], # e.g., "socks5://user:pass@host:port"
                    "https://": proxy_config['url'], # e.g., "socks5://user:pass@host:port"
                }
        return None

    async def _execute_non_streaming_with_rotation(
        self,
        method: str,
        endpoint_path: str, # Должен быть "/chat/completions"
        payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Выполняет не-стриминговый запрос к OpenAI API с автоматической
        ротацией ключей и прокси в случае ошибок.
        """
        key_exhausted_message = f"All API keys for {self.service_name} are exhausted or failed."

        if self.key_loop_initial_run:
            self.first_key_in_overall_cycle = self.api_key_manager.get_key(self.service_name, peek=True)
            self.key_loop_initial_run = False

        key_was_rotated_in_current_api_call = False

        while True: # Key loop
            current_api_key = self.api_key_manager.get_key(self.service_name)
            if not current_api_key:
                logger.error(key_exhausted_message + f" (No keys available at start of key loop for {self.service_name} non-streaming)")
                raise HTTPException(status_code=503, detail=key_exhausted_message + f" (No keys available at start of key loop for {self.service_name} non-streaming)")

            # Сброс контекста прокси при смене ключа или после ротации ключа внутри вызова
            if self.last_api_key_used_for_proxy_context != current_api_key or key_was_rotated_in_current_api_call:
                logger.debug(f"API key changed or rotated for {self.service_name} (non-streaming). Old: {self.last_api_key_used_for_proxy_context}, New: ...{current_api_key[-4:]}. Resetting proxies.")
                self.proxy_manager.reset_proxies()
                self.last_api_key_used_for_proxy_context = current_api_key
                if key_was_rotated_in_current_api_call:
                    key_was_rotated_in_current_api_call = False # Сбрасываем флаг после обработки
            else:
                logger.debug(f"API key ...{current_api_key[-4:]} is the same as last used. Proxy context preserved for {self.service_name} (non-streaming).")

            while True: # Proxy loop
                current_proxy_config = None
                httpx_proxies = None
                transport = None # Для явного SOCKS транспорта

                if self.proxy_manager.active:
                    current_proxy_config = self.proxy_manager.get_proxy()
                    httpx_proxies = self._get_httpx_proxies(current_proxy_config)

                # Заголовок авторизации для OpenAI
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {current_api_key}"
                }
                url = f"{OPENAI_API_BASE_URL}{endpoint_path}"
                proxy_url_for_log = current_proxy_config['url'] if current_proxy_config else "None (Direct)"
                logger.debug(f"Attempting {self.service_name} API call: {method} {url} with key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}")

                client_args = {"timeout": 30.0} # Таймаут для не-стриминговых запросов

                # Создание транспорта для SOCKS прокси, если используется
                if httpx_proxies:
                    proxy_url_for_transport = httpx_proxies.get("http://")
                    if proxy_url_for_transport and proxy_url_for_transport.startswith(("socks5://", "socks4://")):
                        logger.debug(f"Creating AsyncProxyTransport for SOCKS: {proxy_url_for_transport}")
                        try:
                            transport = AsyncProxyTransport.from_url(proxy_url_for_transport)
                            client_args["transport"] = transport
                        except Exception as e:
                            logger.error(f"Failed to create AsyncProxyTransport from URL {proxy_url_for_transport}: {e}. Treating as proxy failure.")
                            # Продолжаем, ошибка будет поймана далее как httpx.RequestError
                            transport = None # Ensure transport is None if creation failed
                            client_args.pop("transport", None) # Remove potentially invalid transport
                            if self.proxy_manager.rotate_proxy():
                                logger.info(f"Rotated to next proxy for key ...{current_api_key[-4:]} after SOCKS transport creation failure. Retrying.")
                                continue # Retry with next proxy
                            else:
                                logger.warning(f"Failed to rotate proxy or proxies exhausted after SOCKS transport creation failure for key ...{current_api_key[-4:]}. Attempting key rotation.")
                                previous_key_for_check = current_api_key
                                if not self.api_key_manager.rotate_key(self.service_name):
                                    final_err_msg = f"{key_exhausted_message} (SOCKS transport setup failed, no keys to rotate to)"
                                    logger.error(final_err_msg)
                                    raise HTTPException(status_code=500, detail=final_err_msg)
                                key_was_rotated_in_current_api_call = True
                                current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                                if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                                     logger.warning(f"Completed a full cycle of API keys for {self.service_name} (non-streaming) due to SOCKS transport setup failure. All keys failed. Raising final exception.")
                                     raise HTTPException(status_code=500, detail=f"{key_exhausted_message} (Full key cycle for SOCKS transport setup failure)")
                                break # Exit proxy loop to try new key
                    else:
                        # Для обычных HTTP/HTTPS прокси или если URL не SOCKS
                        client_args["proxies"] = httpx_proxies
                
                try:
                    async with httpx.AsyncClient(**client_args) as client:
                        response = None
                        if method.upper() == "POST":
                            response = await client.post(url, headers=headers, json=payload)
                        elif method.upper() == "GET": # Хотя для completions это маловероятно, сохраним структуру
                            response = await client.get(url, headers=headers)
                        else:
                            raise ValueError(f"Unsupported HTTP method: {method}")
                        response.raise_for_status() # Выбросит исключение для 4xx/5xx статусов
                        response_data = response.json()
                        logger.info(f"{self.service_name} API call successful with key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}.")

                        # Логика принудительной ротации прокси после успешного запроса
                        force_rotation_enabled = False
                        try:
                            with open(self.settings_file_path, 'r') as f:
                                settings_data_json = json.load(f)
                                # Читаем настройку force_proxy_rotation_after_request из файла
                                force_rotation_enabled = settings_data_json.get("proxy_settings", {}).get("force_proxy_rotation_after_request", False)
                        except Exception as e_settings:
                            logger.error(f"Could not read force_proxy_rotation_after_request from {self.settings_file_path} for {self.service_name} (non-streaming): {e_settings}. Defaulting to False.")

                        # Если принудительная ротация включена и мы не в режиме failover_cycle
                        if force_rotation_enabled and \
                           self.proxy_manager.current_rotation_mode != "failover_cycle" and \
                           not self.proxy_manager.select_random_proxy_each_request:
                           if self.proxy_manager.active and self.proxy_manager.proxies:
                               logger.debug(f"Force rotating proxy after successful call as per settings ({self.service_name} non-streaming).")
                               self.proxy_manager.rotate_proxy() # Принудительно переключаем на следующий прокси

                        return response_data # Успешный ответ, выходим из обоих циклов

                except httpx.HTTPStatusError as e:
                    error_response_data = {}
                    try: error_response_data = e.response.json()
                    except json.JSONDecodeError: pass # Может быть не JSON ответ
                    # Пытаемся получить сообщение об ошибке из ответа или используем статус/текст
                    error_detail = error_response_data.get("error", {}).get("message", e.response.text or f"HTTP {e.response.status_code}")
                    status_code = e.response.status_code

                    # Обработка ошибок, связанных с ключом API
                    # OpenAI использует 401 для невалидного ключа
                    if status_code in [401]:
                        logger.warning(f"Key error for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}. Rotating key.")
                        previous_key_for_check = current_api_key # Запоминаем ключ для детекции цикла
                        if not self.api_key_manager.rotate_key(self.service_name):
                            # Если нет ключей для ротации, значит все исчерпаны
                            raise HTTPException(status_code=503, detail=key_exhausted_message + " (No keys to rotate to after auth error)")
                        key_was_rotated_in_current_api_call = True # Устанавливаем флаг, что ключ был изменен
                        current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True) # Проверяем новый ключ
                        # Проверяем, завершился ли полный цикл ключей после ротации
                        if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                            logger.warning(f"Completed a full cycle of API keys for {self.service_name} (non-streaming) due to HTTP {status_code}. All keys failed. Raising final exception.")
                            raise HTTPException(status_code=status_code, detail=f"{key_exhausted_message} (Full key cycle for HTTP {status_code})")
                        break # Выходим из proxy loop, чтобы начать новую итерацию key loop с новым ключом

                    # Клиентские ошибки, которые не должны приводить к ротации (например, неверный формат запроса 400)
                    # За исключением 429 (Too Many Requests), которую обрабатываем как временную проблему
                    elif 400 <= status_code < 500 and status_code != 429:
                        logger.error(f"Client error for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}")
                        # Это, вероятно, ошибка в запросе пользователя, не в ключе/прокси. Пробрасываем ее.
                        raise HTTPException(status_code=status_code, detail=f"{self.service_name} API client error: {error_detail}")

                    # Все остальные ошибки (5xx, 429, таймауты и т.п.)
                    else:
                        logger.warning(f"HTTPStatusError (status {status_code}, type {type(e).__name__}) for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {error_detail}. Attempting proxy rotation.")
                        if self.proxy_manager.active and self.proxy_manager.rotate_proxy():
                            logger.info(f"Successfully rotated to next proxy for key ...{current_api_key[-4:]}. Retrying.")
                            continue # Продолжаем в proxy loop с новым прокси
                        else:
                            logger.warning(f"Failed to rotate proxy or proxies exhausted for key ...{current_api_key[-4:]} after HTTPStatusError {status_code}. Attempting key rotation.")
                            previous_key_for_check = current_api_key # Запоминаем ключ для детекции цикла
                            if not self.api_key_manager.rotate_key(self.service_name):
                                # Если нет ключей для ротации, значит все исчерпаны
                                final_err_msg = f"{key_exhausted_message} (HTTPStatusError {status_code} on all proxies/keys, no keys to rotate to)"
                                logger.error(final_err_msg)
                                # Выбираем статус код в зависимости от оригинальной ошибки или по умолчанию 500
                                status_code_for_exc = status_code if status_code in [429, 502, 503, 504] else 500
                                raise HTTPException(status_code=status_code_for_exc, detail=final_err_msg)
                            key_was_rotated_in_current_api_call = True # Устанавливаем флаг
                            current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True) # Проверяем новый ключ
                            # Проверяем, завершился ли полный цикл ключей после ротации
                            if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                                logger.warning(f"Completed a full cycle of API keys for {self.service_name} (non-streaming) due to HTTPStatusError {status_code}. All keys failed. Raising final exception.")
                                raise HTTPException(status_code=status_code_for_exc, detail=f"{key_exhausted_message} (Full key cycle for HTTPStatusError {status_code})")
                            break # Выходим из proxy loop, чтобы начать новую итерацию key loop с новым ключом

                except (httpx.RequestError, Exception) as e: # Ловим другие ошибки запроса (сеть, прокси, таймауты и т.п.)
                    error_type_name = type(e).__name__
                    logger.warning(f"{error_type_name} for {self.service_name} (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {str(e)}. Attempting proxy rotation.")
                    if self.proxy_manager.active and self.proxy_manager.rotate_proxy():
                        logger.info(f"Successfully rotated to next proxy for key ...{current_api_key[-4:]} after {error_type_name}. Retrying.")
                        continue # Продолжаем в proxy loop с новым прокси
                    else:
                        logger.warning(f"Failed to rotate proxy or proxies exhausted for key ...{current_api_key[-4:]} after {error_type_name}. Attempting key rotation.")
                        previous_key_for_check = current_api_key # Запоминаем ключ для детекции цикла
                        if not self.api_key_manager.rotate_key(self.service_name):
                            # Если нет ключей для ротации, значит все исчерпаны
                            final_err_msg = f"{key_exhausted_message} ({error_type_name} on all proxies/keys, no keys to rotate to)"
                            logger.error(final_err_msg)
                            # Выбираем статус код в зависимости от типа ошибки
                            status_code_for_exc = 504 if isinstance(e, httpx.TimeoutException) else 502 if isinstance(e, (httpx.NetworkError, httpx.ConnectError, httpx.ProxyError)) else 500
                            raise HTTPException(status_code=status_code_for_exc, detail=final_err_msg)
                        key_was_rotated_in_current_api_call = True # Устанавливаем флаг
                        current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True) # Проверяем новый ключ
                        # Проверяем, завершился ли полный цикл ключей после ротации
                        if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                            logger.warning(f"Completed a full cycle of API keys for {self.service_name} (non-streaming) due to {error_type_name}. All keys failed. Raising final exception.")
                            raise HTTPException(status_code=status_code_for_exc, detail=f"{key_exhausted_message} (Full key cycle for {error_type_name})")
                        break # Выходим из proxy loop, чтобы начать новую итерацию key loop с новым ключом

                # Если proxy loop завершился без успешного ответа (т.е., все прокси или прямой вызов для текущего ключа исчерпаны)
                # Этот блок выполняется, если внутренний while True (proxy loop) завершился без return или break с HTTPException
                # Это произойдет, если все прокси для текущего ключа исчерпаны, но rotate_proxy() вернул False
                # или если прокси не активны и прямой вызов не удался.

                # Если прокси не активны, и вызов не удался, ротируем ключ
                if not self.proxy_manager.active:
                    logger.debug(f"Direct call failed for key ...{current_api_key[-4:]} ({self.service_name}, proxies inactive). Rotating key.")
                    previous_key_for_check = current_api_key
                    if not self.api_key_manager.rotate_key(self.service_name):
                        raise HTTPException(status_code=503, detail=key_exhausted_message + f" (Direct call failed for {self.service_name}, no more keys)")
                    key_was_rotated_in_current_api_call = True
                    current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                    if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                        logger.warning(f"Completed a full cycle of API keys for {self.service_name} (non-streaming, direct call failed). All keys failed.")
                        raise HTTPException(status_code=503, detail=f"{key_exhausted_message} (Full key cycle for {self.service_name}, direct calls failed)")
                    break # Выходим из proxy loop, чтобы попробовать новый ключ

                # Если прокси активны, но все прокси для текущего ключа исчерпаны
                # (т.е. get_proxy() вернул None после того, как все были перебраны в failover_cycle или единожды в once), ротируем ключ.
                # Проверка `current_proxy_config is None` здесь не совсем точна, т.к. `get_proxy()` уже мог ротировать.
                # Лучше проверять, если proxy loop завершился без успеха.
                # Этот блок достигается только если внутренний `continue` или `return` не сработал,
                # и при этом `proxy_manager.active` был True, но все прокси для текущего ключа исчерпаны.
                # Логика ротации ключа уже есть в блоках except.
                # Добавим явную проверку, если прокси менеджер активен и вернул None (все прокси для ключа исчерпаны)
                if self.proxy_manager.active and current_proxy_config is None and self.proxy_manager.proxies:
                     logger.debug(f"All proxies tried for key ...{current_api_key[-4:]} ({self.service_name}, non-streaming). Rotating key.")
                     previous_key_for_check = current_api_key
                     if not self.api_key_manager.rotate_key(self.service_name):
                         raise HTTPException(status_code=503, detail=key_exhausted_message + f" (All proxies tried for {self.service_name}, no more keys)")
                     key_was_rotated_in_current_api_call = True
                     current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                     if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                        logger.warning(f"Completed a full cycle of API keys for {self.service_name} (non-streaming, all proxies tried). All keys failed.")
                        raise HTTPException(status_code=503, detail=f"{key_exhausted_message} (Full key cycle for {self.service_name}, all proxies tried)")
                     break # Выходим из proxy loop, чтобы попробовать новый ключ


    async def _execute_streaming_with_rotation(
        self,
        endpoint_path: str, # Должен быть "/chat/completions"
        payload: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Выполняет стриминговый запрос к OpenAI API с автоматической
        ротацией ключей и прокси в случае ошибок.
        """
        key_exhausted_message = f"All API keys for {self.service_name} are exhausted or failed."

        # self.first_key_in_overall_cycle и self.key_loop_initial_run используются общие для экземпляра
        if self.key_loop_initial_run:
            self.first_key_in_overall_cycle = self.api_key_manager.get_key(self.service_name, peek=True)
            self.key_loop_initial_run = False

        key_was_rotated_in_current_api_call = False

        while True: # Key loop
            current_api_key = self.api_key_manager.get_key(self.service_name)
            if not current_api_key:
                logger.error(key_exhausted_message + f" (No keys available at start of key loop for {self.service_name} streaming)")
                raise HTTPException(status_code=503, detail=key_exhausted_message + f" (No keys available at start of key loop for {self.service_name} streaming)")

            # Сброс контекста прокси при смене ключа или после ротации ключа внутри вызова
            if self.last_api_key_used_for_proxy_context != current_api_key or key_was_rotated_in_current_api_call:
                logger.debug(f"API key changed or rotated for {self.service_name} (streaming). Old: {self.last_api_key_used_for_proxy_context}, New: ...{current_api_key[-4:]}. Resetting proxies.")
                self.proxy_manager.reset_proxies()
                self.last_api_key_used_for_proxy_context = current_api_key
                if key_was_rotated_in_current_api_call:
                    key_was_rotated_in_current_api_call = False # Сбрасываем флаг
            else:
                logger.debug(f"API key ...{current_api_key[-4:]} is the same as last used. Proxy context preserved for {self.service_name} (streaming).")


            while True: # Proxy loop
                current_proxy_config = None
                httpx_proxies = None
                transport_stream = None # Для явного SOCKS транспорта

                if self.proxy_manager.active:
                    current_proxy_config = self.proxy_manager.get_proxy()
                    httpx_proxies = self._get_httpx_proxies(current_proxy_config)

                # Заголовки для стриминга OpenAI
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {current_api_key}",
                    "Accept": "text/event-stream" # Явно запрашиваем SSE
                }
                url = f"{OPENAI_API_BASE_URL}{endpoint_path}"
                proxy_url_for_log = current_proxy_config['url'] if current_proxy_config else "None (Direct)"
                logger.debug(f"Attempting {self.service_name} API stream: POST {url} with key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}")

                client_args = {"timeout": None} # Бесконечный таймаут для стриминга

                # Создание транспорта для SOCKS прокси, если используется
                if httpx_proxies:
                    proxy_url_for_transport_stream = httpx_proxies.get("http://")
                    if proxy_url_for_transport_stream and proxy_url_for_transport_stream.startswith(("socks5://", "socks4://")):
                        logger.debug(f"Creating AsyncProxyTransport for SOCKS stream: {proxy_url_for_transport_stream}")
                        try:
                            transport_stream = AsyncProxyTransport.from_url(proxy_url_for_transport_stream)
                            client_args["transport"] = transport_stream
                        except Exception as e:
                            logger.error(f"Failed to create AsyncProxyTransport from URL {proxy_url_for_transport_stream}: {e}. Treating as proxy failure for stream.")
                            transport_stream = None
                            client_args.pop("transport", None)
                            if self.proxy_manager.rotate_proxy():
                                logger.info(f"Rotated to next proxy for key ...{current_api_key[-4:]} after SOCKS transport creation failure (stream). Retrying.")
                                continue # Retry with next proxy
                            else:
                                logger.warning(f"Failed to rotate proxy or proxies exhausted after SOCKS transport creation failure (stream) for key ...{current_api_key[-4:]}. Attempting key rotation.")
                                previous_key_for_check = current_api_key
                                if not self.api_key_manager.rotate_key(self.service_name):
                                    final_err_msg = f"{key_exhausted_message} (SOCKS transport setup failed for stream, no keys to rotate to)"
                                    logger.error(final_err_msg)
                                    raise HTTPException(status_code=500, detail=final_err_msg)
                                key_was_rotated_in_current_api_call = True
                                current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                                if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                                     logger.warning(f"Completed a full cycle of API keys for {self.service_name} (streaming) due to SOCKS transport setup failure. All keys failed. Raising final exception.")
                                     raise HTTPException(status_code=500, detail=f"{key_exhausted_message} (Full key cycle for SOCKS transport setup failure in stream)")
                                break # Exit proxy loop

                    else:
                        # Для обычных HTTP/HTTPS прокси
                        client_args["proxies"] = httpx_proxies

                try:
                    async with httpx.AsyncClient(**client_args) as client:
                        async with client.stream("POST", url, headers=headers, json=payload) as response:
                            # Проверяем статус до чтения потока
                            if response.status_code != 200:
                                # Читаем содержимое ошибки
                                error_content = await response.aread()
                                error_detail = f"HTTP {response.status_code}"
                                try:
                                    # Пытаемся распарсить ошибку как JSON
                                    error_data = json.loads(error_content)
                                    error_detail = error_data.get("error", {}).get("message", error_detail + f" - {error_content.decode(errors='ignore')[:200]}...")
                                except json.JSONDecodeError:
                                    error_detail = error_detail + f" - {error_content.decode(errors='ignore')[:200]}..." # Используем сырой текст, если не JSON

                                status_code = response.status_code

                                # Обработка ошибок HTTP для стриминга (аналогично не-стримингу)
                                if status_code in [401]:
                                    logger.warning(f"Key error for {self.service_name} stream (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}. Rotating key.")
                                    previous_key_for_check = current_api_key
                                    if not self.api_key_manager.rotate_key(self.service_name):
                                        raise HTTPException(status_code=503, detail=key_exhausted_message + " (No keys to rotate to after auth error for stream)")
                                    key_was_rotated_in_current_api_call = True
                                    current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                                    if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                                        logger.warning(f"Completed a full cycle of API keys for {self.service_name} (streaming) due to HTTP {status_code}. All keys failed. Raising final exception.")
                                        raise HTTPException(status_code=status_code, detail=f"{key_exhausted_message} (Full key cycle for HTTP {status_code} in stream)")
                                    break # Выходим из proxy loop

                                elif 400 <= status_code < 500 and status_code != 429:
                                    logger.error(f"Client error for {self.service_name} stream (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): HTTP {status_code} - {error_detail}")
                                    raise HTTPException(status_code=status_code, detail=f"{self.service_name} API client error (stream): {error_detail}")

                                else:
                                    logger.warning(f"HTTPStatusError (status {status_code}) for {self.service_name} stream (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {error_detail}. Attempting proxy rotation.")
                                    if self.proxy_manager.active and self.proxy_manager.rotate_proxy():
                                        logger.info(f"Successfully rotated to next proxy for key ...{current_api_key[-4:]} (stream). Retrying.")
                                        continue # Продолжаем в proxy loop
                                    else:
                                        logger.warning(f"Failed to rotate proxy or proxies exhausted for key ...{current_api_key[-4:]} (stream) after HTTPStatusError {status_code}. Attempting key rotation.")
                                        previous_key_for_check = current_api_key
                                        if not self.api_key_manager.rotate_key(self.service_name):
                                            final_err_msg = f"{key_exhausted_message} (HTTPStatusError {status_code} on all proxies/keys for stream, no keys to rotate to)"
                                            logger.error(final_err_msg)
                                            status_code_for_exc = status_code if status_code in [429, 502, 503, 504] else 500
                                            raise HTTPException(status_code=status_code_for_exc, detail=final_err_msg)
                                        key_was_rotated_in_current_api_call = True
                                        current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                                        if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                                            logger.warning(f"Completed a full cycle of API keys for {self.service_name} (streaming) due to HTTPStatusError {status_code}. All keys failed. Raising final exception.")
                                            raise HTTPException(status_code=status_code_for_exc, detail=f"{key_exhausted_message} (Full key cycle for HTTPStatusError {status_code} in stream)")
                                        break # Выходим из proxy loop

                            # Если статус 200, начинаем читать поток SSE
                            logger.info(f"{self.service_name} API stream successful (status 200) for key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}. Reading stream.")
                            
                            # Обработка Server-Sent Events (SSE)
                            async for line in response.aiter_lines():
                                #logger.debug(f"Received raw stream line: '{line[:100]}...'")
                                if line.startswith("data:"):
                                    data = line[5:].strip() # Удаляем "data:" и пробелы по краям
                                    if data == "[DONE]":
                                        # Конец стрима по протоколу SSE OpenAI
                                        logger.debug(f"{self.service_name} stream: [DONE] received. Ending stream.")
                                        # Проверяем принудительную ротацию прокси после успешного стрима (если включена)
                                        force_rotation_enabled = False
                                        try:
                                            with open(self.settings_file_path, 'r') as f:
                                                settings_data_json = json.load(f)
                                                force_rotation_enabled = settings_data_json.get("proxy_settings", {}).get("force_proxy_rotation_after_request", False)
                                        except Exception as e_settings:
                                            logger.error(f"Could not read force_proxy_rotation_after_request from {self.settings_file_path} for {self.service_name} (streaming): {e_settings}. Defaulting to False.")

                                        if force_rotation_enabled and \
                                           self.proxy_manager.current_rotation_mode != "failover_cycle" and \
                                           not self.proxy_manager.select_random_proxy_each_request:
                                           if self.proxy_manager.active and self.proxy_manager.proxies:
                                               logger.debug(f"Force rotating proxy after successful stream as per settings ({self.service_name}).")
                                               self.proxy_manager.rotate_proxy()
                                        return # Успешное завершение стрима, выходим из функции

                                    if data: # Игнорируем пустые data поля
                                        try:
                                            # Парсим JSON из data поля
                                            json_chunk = json.loads(data)
                                            yield json_chunk # Выдаем распарсенный JSON объект
                                        except json.JSONDecodeError as e:
                                            # Если JSON некорректен, это может быть проблема с API или прокси
                                            logger.warning(f"JSONDecodeError in {self.service_name} stream (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {e} from data: '{data[:100]}...'. Attempting proxy/key rotation.")
                                            # В случае ошибки парсинга JSON в середине стрима,
                                            # прерываем текущий стрим и пытаемся ротировать прокси/ключ.
                                            # Сначала пробуем прокси
                                            if self.proxy_manager.active and self.proxy_manager.rotate_proxy():
                                                logger.info(f"Successfully rotated to next proxy for key ...{current_api_key[-4:]} after JSONDecodeError (stream). Retrying.")
                                                # Переходим к следующей итерации внешнего proxy loop
                                                raise StopAsyncIteration # Прерываем текущий aiter_lines и переходим к следующей итерации proxy loop
                                            else:
                                                logger.warning(f"Failed to rotate proxy or proxies exhausted for key ...{current_api_key[-4:]} (stream) after JSONDecodeError. Attempting key rotation.")
                                                previous_key_for_check = current_api_key
                                                if not self.api_key_manager.rotate_key(self.service_name):
                                                    final_err_msg = f"{key_exhausted_message} (JSONDecodeError on stream, all proxies/keys, no keys to rotate to)"
                                                    logger.error(final_err_msg)
                                                    raise HTTPException(status_code=500, detail=final_err_msg)
                                                key_was_rotated_in_current_api_call = True
                                                current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                                                if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                                                     logger.warning(f"Completed a full cycle of API keys for {self.service_name} (streaming) due to JSONDecodeError. All keys failed. Raising final exception.")
                                                     raise HTTPException(status_code=500, detail=f"{key_exhausted_message} (Full key cycle for JSONDecodeError in stream)")
                                                raise StopAsyncIteration # Прерываем текущий aiter_lines и переходим к следующей итерации key loop
                                # else: Игнорируем другие типы строк SSE (event:, id:)
                                # or lines starting with : (comments)
                
                    # Этот блок выполняется, если стрим завершился неожиданно (без [DONE])
                    logger.warning(f"{self.service_name} stream ended unexpectedly for key ...{current_api_key[-4:]}, proxy {proxy_url_for_log} (No [DONE]). Attempting proxy rotation.")
                    if self.proxy_manager.active and self.proxy_manager.rotate_proxy():
                        logger.info(f"Successfully rotated to next proxy for key ...{current_api_key[-4:]} after unexpected stream end. Retrying.")
                        continue # Продолжаем в proxy loop
                    else:
                        logger.warning(f"Failed to rotate proxy or proxies exhausted for key ...{current_api_key[-4:]} after unexpected stream end. Attempting key rotation.")
                        previous_key_for_check = current_api_key
                        if not self.api_key_manager.rotate_key(self.service_name):
                            final_err_msg = f"{key_exhausted_message} (Unexpected stream end on all proxies/keys, no keys to rotate to)"
                            logger.error(final_err_msg)
                            raise HTTPException(status_code=500, detail=final_err_msg)
                        key_was_rotated_in_current_api_call = True
                        current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                        if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                            logger.warning(f"Completed a full cycle of API keys for {self.service_name} (streaming) due to unexpected stream end. All keys failed. Raising final exception.")
                            raise HTTPException(status_code=500, detail=f"{key_exhausted_message} (Full key cycle for unexpected stream end)")
                        break # Выходим из proxy loop


                except (httpx.RequestError, Exception) as e: # Ловим другие ошибки запроса (сеть, прокси, таймауты и т.п.)
                    error_type_name = type(e).__name__
                    logger.warning(f"{error_type_name} for {self.service_name} stream (key ...{current_api_key[-4:]}, proxy {proxy_url_for_log}): {str(e)}. Attempting proxy rotation.")
                    if self.proxy_manager.active and self.proxy_manager.rotate_proxy():
                        logger.info(f"Successfully rotated to next proxy for key ...{current_api_key[-4:]} after {error_type_name} (stream). Retrying.")
                        continue # Продолжаем в proxy loop
                    else:
                        logger.warning(f"Failed to rotate proxy or proxies exhausted for key ...{current_api_key[-4:]} after {error_type_name} (stream). Attempting key rotation.")
                        previous_key_for_check = current_api_key
                        if not self.api_key_manager.rotate_key(self.service_name):
                            final_err_msg = f"{key_exhausted_message} ({error_type_name} on all proxies/keys for stream, no keys to rotate to)"
                            logger.error(final_err_msg)
                            status_code_for_exc = 504 if isinstance(e, httpx.TimeoutException) else 502 if isinstance(e, (httpx.NetworkError, httpx.ConnectError, httpx.ProxyError)) else 500
                            raise HTTPException(status_code=status_code_for_exc, detail=final_err_msg)
                        key_was_rotated_in_current_api_call = True
                        current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                        if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                            logger.warning(f"Completed a full cycle of API keys for {self.service_name} (streaming) due to {error_type_name}. All keys failed. Raising final exception.")
                            raise HTTPException(status_code=status_code_for_exc, detail=f"{key_exhausted_message} (Full key cycle for {error_type_name} in stream)")
                        break # Выходим из proxy loop

            # Если proxy loop завершился без успешного стрима (аналогично не-стримингу)
            if not self.proxy_manager.active:
                logger.debug(f"Direct call failed for key ...{current_api_key[-4:]} ({self.service_name}, streaming, proxies inactive). Rotating key.")
                previous_key_for_check = current_api_key
                if not self.api_key_manager.rotate_key(self.service_name):
                    raise HTTPException(status_code=503, detail=key_exhausted_message + f" (Direct call failed for {self.service_name} streaming, no more keys)")
                key_was_rotated_in_current_api_call = True
                current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                        logger.warning(f"Completed a full cycle of API keys for {self.service_name} (streaming, direct call failed). All keys failed.")
                        raise HTTPException(status_code=503, detail=f"{key_exhausted_message} (Full key cycle for {self.service_name}, direct calls failed)")
                break # Выходим из proxy loop

            if self.proxy_manager.active and current_proxy_config is None and self.proxy_manager.proxies:
                    logger.debug(f"All proxies tried for key ...{current_api_key[-4:]} ({self.service_name}, streaming). Rotating key.")
                    previous_key_for_check = current_api_key
                    if not self.api_key_manager.rotate_key(self.service_name):
                        raise HTTPException(status_code=503, detail=key_exhausted_message + f" (All proxies tried for {self.service_name} streaming, no more keys)")
                    key_was_rotated_in_current_api_call = True
                    current_api_key_after_rotation = self.api_key_manager.get_key(self.service_name, peek=True)
                    if current_api_key_after_rotation == self.first_key_in_overall_cycle and current_api_key_after_rotation != previous_key_for_check:
                        logger.warning(f"Completed a full cycle of API keys for {self.service_name} (streaming, all proxies tried). All keys failed.")
                        raise HTTPException(status_code=503, detail=f"{key_exhausted_message} (Full key cycle for {self.service_name}, all proxies tried)")
                        break # Выходим из proxy loop


    async def generate_chat_completion(
        self,
        payload: Dict[str, Any],
        is_stream: bool = False
    ) -> AsyncGenerator[Dict[str, Any], None] | Dict[str, Any]:
        """
        Обрабатывает запрос на завершение чата в формате OpenAI Compatible.

        Args:
            payload: Тело запроса в формате OpenAI Chat Completions API.
            is_stream: Флаг, указывающий, является ли запрос стриминговым.

        Returns:
            Словарь (для не-стриминга) или AsyncGenerator (для стриминга)
            с ответом в формате OpenAI Compatible API.

        Raises:
            HTTPException: Если запрос не удается после всех попыток ротации.
        """
        endpoint_path = "/chat/completions"

        if is_stream:
            # Убеждаемся, что в payload включен stream: true для стриминга
            payload["stream"] = True
            return self._execute_streaming_with_rotation(
                endpoint_path=endpoint_path,
                payload=payload
            )
        else:
            # Убеждаемся, что в payload включен stream: false или отсутствует для не-стриминга
            payload.pop("stream", None) # Удаляем, если присутствует
            return await self._execute_non_streaming_with_rotation(
                method="POST",
                endpoint_path=endpoint_path,
                payload=payload
            )

    # Может быть добавлены другие методы, если нужны для других типов запросов (например, /models)
    # def get_models(self) -> Dict[str, Any]:
    #     # Пример заглушки для метода models
    #     # Реальная логика должна также использовать _execute_non_streaming_with_rotation
    #     # с GET запросом к /models
    #     logger.info(f"Fetching models for {self.service_name}...")
    #     # Это упрощенная версия, без ротации ключей/прокси для GET /models
    #     # Для полной реализации нужно обернуть в _execute_non_streaming_with_rotation
    #     try:
    #         # WARNING: This does NOT handle key/proxy rotation!
    #         # Replace with _execute_non_streaming_with_rotation for production use.
    #         async def _fetch_models():
    #             current_api_key = self.api_key_manager.get_key(self.service_name, peek=True) # peek не ротирует
    #             if not current_api_key:
    #                  raise HTTPException(status_code=503, detail=f"No API keys available for {self.service_name} to fetch models.")
    #             headers = {"Authorization": f"Bearer {current_api_key}"}
    #             url = f"{OPENAI_API_BASE_URL}/models"
    #             async with httpx.AsyncClient() as client:
    #                 response = await client.get(url, headers=headers, timeout=10.0)
    #                 response.raise_for_status()
    #                 return response.json()
    #
    #         # В асинхронном контексте вам нужно будет вызвать это через await
    #         # await _fetch_models()
    #         # Или адаптировать _execute_non_streaming_with_rotation для GET запросов
    #         # На данный момент, для простоты, предполагается, что основной кейс - chat completions.
    #         # Если /models нужен с ротацией, измените эту часть.
    #         pass
    #     except Exception as e:
    #         logger.error(f"Failed to fetch models for {self.service_name}: {e}")
    #         # В реальной реализации тут должна быть обработка ошибок/ротация
    #         # raise HTTPException(status_code=500, detail=f"Failed to fetch models: {e}")
    #         pass # Заглушка