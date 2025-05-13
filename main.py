import os
import webbrowser # Для открытия URL в браузере
import json # Для создания пустых JSON файлов и для SSE
import inspect # Для проверки типа функции
from typing import AsyncGenerator, Dict, Any, Optional # Для sse_event_formatter
from dotenv import load_dotenv # Импортируем load_dotenv
from fastapi import FastAPI, Request, UploadFile, HTTPException, Depends
from fastapi.staticfiles import StaticFiles # <--- Добавлено для статических файлов
from fastapi.responses import StreamingResponse, JSONResponse, Response, FileResponse # Добавлен FileResponse
from fastapi.security.http import HTTPBearer, HTTPAuthorizationCredentials
from registry import ModuleRegistry
from modules.openai_module import OpenAIChatModule # Старый модуль OpenAI
from modules.gemini_module import GeminiChatModule
from modules.openai_compat_module import OpenAICompatModule # Импортируем новый модуль
from api_key_manager import ApiKeyManager
from proxy_manager import ProxyManager 
from airouter_key_manager import AIRouterApiKeyManager # <--- Добавлено
import admin_router
import logging # Добавляем импорт logging
# Не импортируем _load_openai_instances здесь, он будет использоваться ниже при регистрации модуля
# from api.admin.settings_api import _load_openai_instances 

# Настраиваем базовое логирование
open_browser_on_save = False
logging_type = logging.INFO

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
APP_VERSION = "1.1.0a" # Версия приложения
app = FastAPI()

# Монтирование статических файлов
app.mount("/static", StaticFiles(directory="static"), name="static")

# Схема аутентификации Bearer
bearer_scheme = HTTPBearer()

# ModuleRegistry теперь инициализируется с путем к файлу настроек в ensure_config_files_exist или после него
# registry = ModuleRegistry() # Этот вызов будет ниже, после определения SETTINGS_FILE

# CONFIG_DIR и файлы уже определены выше, json импортирован

CONFIG_DIR = "configs"
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
OPENAI_KEYS_FILE = os.path.join(CONFIG_DIR, "openai_keys.json")
GEMINI_KEYS_FILE = os.path.join(CONFIG_DIR, "gemini_keys.json")
AIROUTER_KEYS_FILE = os.path.join(CONFIG_DIR, "airouter_api_keys.json")
PROXIES_FILE = os.path.join(CONFIG_DIR, "proxies.json")
OPENAI_INSTANCES_FILE = os.path.join(CONFIG_DIR, "openai_instances.json") # Добавлен файл инстансов

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
            "proxy_settings": {
                "use_proxies": True, 
                "rotation_mode": "once",
                "force_proxy_rotation_after_request": False, 
                "select_random_proxy_each_request": False # Переименованная настройка
            },
            "module_statuses": {"openai": True, "gemini": True, "OAIC": True}, # Добавлен статус для нового модуля
            "require_airouter_api_key": False 
        }
    }
    # Создаем файл для ключей AIRouter, если его нет
    if not os.path.exists(AIROUTER_KEYS_FILE):
        try:
            with open(AIROUTER_KEYS_FILE, 'w') as f:
                json.dump([], f)
            print(f"Created default config file: {AIROUTER_KEYS_FILE}")
        except Exception as e:
            print(f"Error creating default config file {AIROUTER_KEYS_FILE}: {e}")

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
# randomize_on_load убран из конструктора, будет читаться из settings.json внутри ProxyManager
proxy_manager = ProxyManager( 
    proxy_file_path=PROXIES_FILE,
    settings_file_path=SETTINGS_FILE
)
airouter_key_manager = AIRouterApiKeyManager() # <--- Добавлено

# Загружаем конфигурацию инстансов OpenAI Compatible
# Для этого нужна функция _load_openai_instances, определенная в api.admin.settings_api
# Чтобы избежать циклического импорта, можно либо перенести функцию, либо загружать здесь напрямую
def load_openai_instances_config(path: str) -> list:
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"OpenAI instances config file not found at {path}. Module will not load instances.")
        return []
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from OpenAI instances config file at {path}. Module will not load instances.")
        return []

openai_instances_config = load_openai_instances_config(OPENAI_INSTANCES_FILE)

# Сохраняем менеджеры и реестр модулей в состоянии приложения
app.state.key_manager = key_manager
app.state.proxy_manager = proxy_manager
app.state.module_registry = registry
app.state.airouter_key_manager = airouter_key_manager # <--- Добавлено
app.state.settings_file_path = SETTINGS_FILE # <--- Добавлено для доступа к настройкам
app.state.app_version = APP_VERSION # <--- Добавлено для версии


# Middleware для проверки API ключа AIRouter
@app.middleware("http")
async def check_airouter_api_key(request: Request, call_next):
    # Пропускаем проверку для админ-панели, ее API, статических файлов и favicon.ico
    if request.url.path == "/favicon.ico" or \
       request.url.path.startswith("/static") or \
       request.url.path.startswith("/admin") or \
       request.url.path.startswith("/api/admin/"): # Уточненное условие
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
        settings_file_path=SETTINGS_FILE, # Добавлено
        service_name="openai"
    ))
else:
    print("Warning: No OpenAI API keys found. OpenAI module will not be registered.")

if key_manager.get_key("gemini"): 
    # Предполагаем, что GeminiChatModule также будет обновлен для приема settings_file_path
    # Если нет, эту строку нужно будет адаптировать или временно закомментировать settings_file_path
    registry.register(GeminiChatModule(
        api_key_manager=key_manager, 
        proxy_manager=proxy_manager,
        settings_file_path=SETTINGS_FILE, # Добавлено (потребует изменений в GeminiChatModule)
        service_name="gemini"
    ))
else:
    print("Warning: No Gemini API keys found. Gemini module will not be registered.")

# Регистрация нового модуля OpenAI Compatible
if openai_instances_config: # Регистрируем модуль только если есть настроенные инстансы
     registry.register(OpenAICompatModule(
         instances_config=openai_instances_config,
         proxy_manager=proxy_manager,
         settings_file_path=SETTINGS_FILE,
         # api_key_manager не передается напрямую, ключи в instances_config
     )) # Регистрируем под именем "OAIC"
else:
    print("Warning: No OpenAI Compatible instances configured. OpenAI Compatible module will not be registered.")


# Открываем админ-панель в браузере при запуске
try:
    if(open_browser_on_save): 
        webbrowser.open("http://localhost:8000/admin/dashboard")
except Exception as e:
    logger.warning(f"Could not open browser for admin dashboard: {e}")

# Подключаем роутер админ-панели
app.include_router(admin_router.router)

# Подключаем новые UI API роутеры из папки api/admin
from api.admin import dashboard_api, settings_api, keys_api, proxies_api, models_api
app.include_router(dashboard_api.router)
app.include_router(settings_api.router)
app.include_router(keys_api.router)
app.include_router(proxies_api.router)
app.include_router(models_api.router) 

# Подключаем OpenAI-совместимый роутер
from api.airouter import openai_compatible
app.include_router(openai_compatible.router)

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = os.path.join("static", "favicon.ico") # Изменен путь
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/vnd.microsoft.icon")
    else:
        # Если файла нет по какой-то причине, возвращаем 204, чтобы не было ошибки 404 в логах браузера
        return Response(status_code=204)

# Вспомогательные функции get_module и sse_event_formatter, а также эндпоинты /v1/...
# были перенесены в api/airouter/openai_compatible.py
