import os
import json # Для создания пустых JSON файлов и для SSE
import inspect # Для проверки типа функции
from typing import AsyncGenerator, Dict, Any, Optional # Для sse_event_formatter
from dotenv import load_dotenv # Импортируем load_dotenv
from fastapi import FastAPI, Request, UploadFile, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse # Для потоковых ответов и JSON ответов
from fastapi.security.http import HTTPBearer, HTTPAuthorizationCredentials
from registry import ModuleRegistry
from modules.openai_module import OpenAIChatModule
from modules.gemini_module import GeminiChatModule
from api_key_manager import ApiKeyManager
from proxy_manager import ProxyManager
from airouter_key_manager import AIRouterApiKeyManager # <--- Добавлено
import admin_router
import logging # Добавляем импорт logging

# Настраиваем базовое логирование

logging_type = logging.ERROR
logging.basicConfig(level=logging_type, format='%(levelname)s:%(name)s:%(asctime)s:%(message)s') # Изменено на DEBUG и добавлен asctime
logger = logging.getLogger(__name__) # Создаем логгер для main.py
logger.setLevel(logging_type) # Убедимся, что и этот логгер на DEBUG

# Дополнительно установим уровень для uvicorn логгеров, если они используются
uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.setLevel(logging_type)
uvicorn_error_logger = logging.getLogger("uvicorn.error")
uvicorn_error_logger.setLevel(logging_type)
# И для модуля gemini, на всякий случай
gemini_module_logger = logging.getLogger("modules.gemini_module")
gemini_module_logger.setLevel(logging_type)


# Загружаем переменные окружения из .env файла (если он есть)
# Это должно быть сделано до того, как переменные окружения используются,
# например, в ProxyManager или admin_router.
load_dotenv() 

# app и registry создаются один раз здесь
app = FastAPI()

# Схема аутентификации Bearer
bearer_scheme = HTTPBearer()

# ModuleRegistry теперь инициализируется с путем к файлу настроек в ensure_config_files_exist или после него
# registry = ModuleRegistry() # Этот вызов будет ниже, после определения SETTINGS_FILE

# CONFIG_DIR и файлы уже определены выше, json импортирован

CONFIG_DIR = "configs"
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
OPENAI_KEYS_FILE = os.path.join(CONFIG_DIR, "openai_keys.json")
GEMINI_KEYS_FILE = os.path.join(CONFIG_DIR, "gemini_keys.json")
PROXIES_FILE = os.path.join(CONFIG_DIR, "proxies.json")

def ensure_config_files_exist():
    """Проверяет наличие папки configs и файлов конфигурации, создает их при необходимости."""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
        print(f"Created directory: {CONFIG_DIR}")

    default_files_content = {
        OPENAI_KEYS_FILE: [],
        GEMINI_KEYS_FILE: [],
        PROXIES_FILE: [],
        SETTINGS_FILE: {
            "proxy_settings": {"use_proxies": True, "rotation_mode": "once"},
            "module_statuses": {"openai": True, "gemini": True},
            "require_airouter_api_key": False # <--- Добавлено значение по умолчанию
        }
    }
    # Создаем файл для ключей AIRouter, если его нет
    airouter_keys_file_path = os.path.join(CONFIG_DIR, "airouter_api_keys.json")
    if not os.path.exists(airouter_keys_file_path):
        try:
            with open(airouter_keys_file_path, 'w') as f:
                json.dump([], f)
            print(f"Created default config file: {airouter_keys_file_path}")
        except Exception as e:
            print(f"Error creating default config file {airouter_keys_file_path}: {e}")

    for file_path, default_content in default_files_content.items():
        if not os.path.exists(file_path):
            try:
                with open(file_path, 'w') as f:
                    json.dump(default_content, f, indent=2)
                print(f"Created default config file: {file_path}")
            except Exception as e:
                print(f"Error creating default config file {file_path}: {e}")

# Вызываем функцию проверки/создания файлов перед инициализацией менеджеров
ensure_config_files_exist()

# Инициализация ModuleRegistry с путем к файлу настроек, ПОСЛЕ того как SETTINGS_FILE определен
registry = ModuleRegistry(settings_file_path=SETTINGS_FILE)

# Инициализация остальных менеджеров
key_manager = ApiKeyManager({
    "openai": OPENAI_KEYS_FILE,
    "gemini": GEMINI_KEYS_FILE
})
proxy_manager = ProxyManager(
    proxy_file_path=PROXIES_FILE,
    settings_file_path=SETTINGS_FILE
)
airouter_key_manager = AIRouterApiKeyManager() # <--- Добавлено

# Сохраняем менеджеры и реестр модулей в состоянии приложения
app.state.key_manager = key_manager
app.state.proxy_manager = proxy_manager
app.state.module_registry = registry
app.state.airouter_key_manager = airouter_key_manager # <--- Добавлено
app.state.settings_file_path = SETTINGS_FILE # <--- Добавлено для доступа к настройкам


# Middleware для проверки API ключа AIRouter
@app.middleware("http")
async def check_airouter_api_key(request: Request, call_next):
    # Пропускаем проверку для админ-панели и статических файлов (если они есть)
    if request.url.path.startswith("/admin") or request.url.path.startswith("/static"):
        response = await call_next(request)
        return response

    # Проверяем, нужно ли требовать ключ
    try:
        with open(app.state.settings_file_path, 'r') as f:
            settings = json.load(f)
        require_key = settings.get("require_airouter_api_key", False)
    except Exception:
        # В случае ошибки чтения файла настроек, по умолчанию требуем ключ для безопасности
        # или можно логировать и пропускать, в зависимости от политики
        logger.error(f"Could not read settings file at {app.state.settings_file_path} for API key check. Denying access by default.")
        return JSONResponse(
            status_code=500,
            content={"detail": "Server configuration error, cannot verify API key requirement."}
        )

    if require_key:
        try:
            auth_header: Optional[HTTPAuthorizationCredentials] = await bearer_scheme(request)
        except HTTPException as e:
            # Если bearer_scheme вызвал ошибку (например, 403 "Not authenticated" из-за отсутствия/неверного формата заголовка)
            # мы вернем 401 с нашим сообщением.
            logger.warning(f"Authorization header issue for {request.url.path}: {e.detail}")
            return JSONResponse(
                status_code=401, # Стандартный код для проблем с аутентификацией
                content={"Error": "Authorization header is missing or invalid. Use Bearer token."},
                headers={"WWW-Authenticate": "Bearer"}, # Важно для 401
            )
        
        # Эта проверка может быть избыточной, так как bearer_scheme должен сам вызывать HTTPException
        # если заголовок отсутствует или схема не "bearer".
        # Однако, для явности и подстраховки можно оставить.
        if not auth_header: # auth_header будет None, если bearer_scheme не смог его извлечь и не вызвал исключение (маловероятно)
            logger.warning(f"Authorization header could not be processed for {request.url.path}")
            return JSONResponse(
                status_code=401,
                content={"Error": "Not authenticated. Bearer token could not be processed."},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header.credentials
        air_key_manager: AIRouterApiKeyManager = request.app.state.airouter_key_manager
        
        if not air_key_manager.key_exists(token):
            logger.warning(f"Invalid API Key received: '{token}' for {request.url.path}")
            return JSONResponse(
                status_code=403,
                content={"Error": "Auth data is not valid. Check API-Key on dashboard."}
            )
        logger.debug(f"Valid API Key received for {request.url.path}")

    response = await call_next(request)
    return response

# Регистрация модулей API
# ModuleRegistry теперь сам загрузит статусы активности из settings.json
# и применит их или active_by_default, если статус для модуля не найден в файле.
# Мы передаем менеджер ключей в модули, чтобы они могли запрашивать и ротировать ключи.
# Регистрация модулей с передачей ApiKeyManager и ProxyManager
if key_manager.get_key("openai"): 
    registry.register(OpenAIChatModule(
        api_key_manager=key_manager, 
        proxy_manager=proxy_manager, 
        service_name="openai"
    ))
else:
    print("Warning: No OpenAI API keys found. OpenAI module will not be registered.")

if key_manager.get_key("gemini"): 
    registry.register(GeminiChatModule(
        api_key_manager=key_manager, 
        proxy_manager=proxy_manager, 
        service_name="gemini"
    ))
else:
    print("Warning: No Gemini API keys found. Gemini module will not be registered.")

# Подключаем роутер админ-панели
app.include_router(admin_router.router)

def get_module(request_data: dict):
    """
    Получает модуль для обработки запроса.
    Логика выбора модуля по model_name или service_name.
    """
    # Сначала пытаемся получить по полному имени модели (например, "openai/gpt-4")
    # Если не найдено, пытаемся по имени сервиса (например, "openai")
    # Это позволяет регистрировать модули по имени сервиса, а в запросе указывать конкретную модель.
    model_identifier = request_data.get("model", "openai") # "openai" - сервис по умолчанию
    
    # Попытка 1: получить модуль по полному идентификатору модели из запроса
    try:
        module = registry.get(model_identifier)
        return module
    except KeyError:
        pass # Продолжаем, если не найдено

    # Попытка 2: если в идентификаторе есть '/', извлечь имя сервиса (часть до '/') и попробовать по нему
    if '/' in model_identifier:
        service_name_from_slash = model_identifier.split('/')[0]
        try:
            module = registry.get(service_name_from_slash)
            # TODO: В будущем модуль может сам решать, какую под-модель использовать,
            # если service_name_from_slash != model_identifier
            return module
        except KeyError:
            pass # Продолжаем, если не найдено

    # Попытка 3: проверить известные префиксы сервисов
    # Это полезно для моделей типа "gemini-pro", "gemini-1.5-flash", и т.д.
    # или если модуль зарегистрирован как "openai", а в запросе "gpt-4" (хотя это менее вероятно)
    known_prefixes = ["gemini", "openai"] # Можно расширить список
    for prefix in known_prefixes:
        if model_identifier.startswith(prefix):
            try:
                module = registry.get(prefix) # Пытаемся получить модуль по имени сервиса (префиксу)
                return module
            except KeyError:
                # Если модуль для этого префикса не зарегистрирован, это не ошибка,
                # просто этот префикс не подходит.
                pass 
                
    # Если ни одна из попыток не увенчалась успехом
    logger.error(f"Failed to find module for model_identifier: '{model_identifier}'. Review request body or ensure module is registered and active.")
    raise HTTPException(status_code=400, detail=f"Module for model/service '{model_identifier}' not found or not registered.")


async def sse_event_formatter(generator: AsyncGenerator[Dict[str, Any], None]) -> AsyncGenerator[str, None]:
    """
    Форматирует словари из генератора в Server-Sent Events (SSE) строки.
    Также обрабатывает исключения из генератора и отправляет ошибку в SSE формате.
    """
    try:
        async for chunk_data in generator:
            yield f"data: {json.dumps(chunk_data)}\n\n"
        yield f"data: [DONE]\n\n"
    except HTTPException as e:
        logger.error(f"HTTPException during SSE stream generation: {e.detail}", exc_info=False) # Не логгируем полный traceback для HTTPException
        error_payload = {
            "error": {
                "message": e.detail,
                "type": "api_error", # Можно уточнить тип ошибки
                "param": None, # Можно добавить, если известно
                "code": str(e.status_code) # Код ошибки как строка
            }
        }
        yield f"data: {json.dumps(error_payload)}\n\n"
        yield f"data: [DONE]\n\n" # Важно завершить поток корректно
    except Exception as e:
        logger.error(f"Unexpected exception during SSE stream generation: {e}", exc_info=True)
        error_payload = {
            "error": {
                "message": "An unexpected error occurred during streaming.",
                "type": "internal_server_error",
                "param": None,
                "code": "500"
            }
        }
        yield f"data: {json.dumps(error_payload)}\n\n"
        yield f"data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    module = get_module(body)

    # Проверяем, является ли метод chat_completion асинхронным генератором
    if inspect.isasyncgenfunction(module.chat_completion):
        # Если да, используем StreamingResponse
        # module.chat_completion(body) возвращает сам генератор
        actual_generator = module.chat_completion(body)
        return StreamingResponse(sse_event_formatter(actual_generator), media_type="text/event-stream")
    else:
        # Если это обычная async функция, вызываем ее через await
        return await module.chat_completion(body)

@app.post("/v1/completions")
async def completions(request: Request):
    body = await request.json()
    module = get_module(body)
    return await module.completion(body)

@app.post("/v1/embeddings")
async def embeddings(request: Request):
    body = await request.json()
    module = get_module(body)
    return await module.embeddings(body)

@app.get("/v1/models")
async def list_models():
    all_models = []
    # Используем all_active_modules, чтобы получать модели только от включенных сервисов
    for mod in registry.all_active_modules(): 
        try:
            models = await mod.list_models()
            all_models.extend(models.get("data", []))
        except Exception: # Общая обработка ошибок, чтобы один модуль не сломал весь эндпоинт
            continue
    return {"object": "list", "data": all_models}

@app.get("/v1/models/{model_id}")
async def retrieve_model(model_id: str):
    # При получении конкретной модели, мы должны проверить все зарегистрированные модули,
    # но registry.get() уже учитывает статус активности.
    # Однако, если модель запрашивается по ID, который может принадлежать неактивному модулю,
    # то get_module() не найдет его.
    # Логика здесь должна быть такой: найти модуль, которому принадлежит model_id,
    # и если этот модуль активен, то вызвать retrieve_model.
    # Это сложнее, т.к. model_id не содержит имени сервиса.
    # Пока оставим как есть, но это потенциальное место для улучшения:
    # возможно, retrieve_model должен перебирать all_registered_modules и проверять активность перед вызовом.
    # Или же, если модель запрашивается, она должна быть от активного модуля.
    # Текущая реализация get_module() в других эндпоинтах уже проверяет активность.
    # Для /v1/models/{model_id} нужно решить, как определять модуль.
    # Простой вариант: если модель запрашивают, она должна быть доступна через активный модуль.
    # Поэтому, если мы не можем получить модуль через registry.get(model_id) или registry.get(service_part_of_model_id),
    # то модель не найдена или ее сервис неактивен.

    # Попробуем извлечь имя сервиса из model_id, если оно там есть (например, "openai/gpt-4")
    parts = model_id.split('/')
    service_to_try = parts[0] if len(parts) > 1 else None

    # Сначала пытаемся по полному ID (если модуль зарегистрирован так)
    try:
        module = registry.get(model_id)
        return await module.retrieve_model(model_id)
    except KeyError:
        # Если не получилось, и есть сервисная часть, пробуем по ней
        if service_to_try:
            try:
                module = registry.get(service_to_try)
                # Убедимся, что запрашиваемая модель действительно принадлежит этому модулю
                # (это упрощенная проверка, в реальности может быть сложнее)
                # Например, модуль OpenAI может обслуживать много моделей.
                # Мы просто передаем model_id дальше, модуль сам разберется.
                return await module.retrieve_model(model_id)
            except KeyError:
                pass # Модуль сервиса не найден или неактивен
        
        # Если ничего не помогло, перебираем все активные модули (менее эффективно)
        # Это может быть нужно, если model_id не содержит префикса сервиса
        for mod in registry.all_active_modules():
            try:
                # Предполагаем, что retrieve_model вернет ошибку, если модель не его
                # или выбросит NotImplementedError, если не поддерживает метод
                retrieved = await mod.retrieve_model(model_id)
                # Проверим, что это не стандартный ответ "не реализовано" от BaseModule
                if isinstance(retrieved, dict) and retrieved.get("object") == "model": # Успешное получение
                    return retrieved
            except NotImplementedError:
                continue
            except HTTPException as e: # Если модуль вернул ошибку, что модель не найдена у него
                if e.status_code == 404 or "not found" in str(e.detail).lower(): # Примерная проверка
                    continue
                raise # Другая ошибка HTTPException
            except Exception: # Другие непредвиденные ошибки
                continue
                
    return HTTPException(status_code=404, detail=f"Model '{model_id}' not found or its service is inactive.")


@app.post("/v1/moderations")
async def moderations(request: Request):
    body = await request.json()
    module = get_module(body)
    return await module.moderations(body)

@app.post("/v1/images/generations")
async def generate_image(request: Request):
    body = await request.json()
    module = get_module(body)
    return await module.generate_image(body)

@app.post("/v1/audio/transcriptions")
async def audio_transcription(request: Request, file: UploadFile):
    body = await request.form() # Аудио запросы обычно используют form-data
    model_name = body.get("model", "openai") # Получаем модель из формы или по умолчанию
    module = registry.get(model_name)
    file_bytes = await file.read()
    # Передаем параметры из формы в модуль, исключая сам файл, если он там есть
    request_params = {k: v for k, v in body.items() if k != 'file'}
    return await module.audio_transcription(request_params, file_bytes)

@app.post("/v1/audio/translations")
async def audio_translation(request: Request, file: UploadFile):
    body = await request.form() # Аудио запросы обычно используют form-data
    model_name = body.get("model", "openai") # Получаем модель из формы или по умолчанию
    module = registry.get(model_name)
    file_bytes = await file.read()
    # Передаем параметры из формы в модуль, исключая сам файл, если он там есть
    request_params = {k: v for k, v in body.items() if k != 'file'}
    return await module.audio_translation(request_params, file_bytes)
