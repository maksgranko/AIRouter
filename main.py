import os
import webbrowser
import json
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, Response, FileResponse
from fastapi.security.http import HTTPBearer, HTTPAuthorizationCredentials
from registry import ModuleRegistry
from modules.openai_module import OpenAIChatModule
from modules.gemini_module import GeminiChatModule
from modules.openai_compat_module import OpenAICompatModule
from api_key_manager import ApiKeyManager
from proxy_manager import ProxyManager 
from airouter_key_manager import AIRouterApiKeyManager
import admin_router
import logging

open_browser_on_save = False
logging_type = logging.INFO

logging.basicConfig(level=logging_type, format='%(levelname)s:%(name)s:%(asctime)s:%(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging_type)

# Дополнительно установим уровень для uvicorn логгеров, если они используются
uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.setLevel(logging_type)
uvicorn_error_logger = logging.getLogger("uvicorn.error")
uvicorn_error_logger.setLevel(logging_type)
gemini_module_logger = logging.getLogger("modules.gemini_module")
gemini_module_logger.setLevel(logging_type)
oaic_module_logger = logging.getLogger("modules.openai_compat_module")
oaic_module_logger.setLevel(logging_type)

output_oaic_module_logger = logging.getLogger("api.airouter.openai_compatible")
output_oaic_module_logger.setLevel(logging_type)

load_dotenv() 

APP_VERSION = "1.2.2"
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

bearer_scheme = HTTPBearer()


CONFIG_DIR = "configs"
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
OPENAI_KEYS_FILE = os.path.join(CONFIG_DIR, "openai_keys.json")
GEMINI_KEYS_FILE = os.path.join(CONFIG_DIR, "gemini_keys.json")
AIROUTER_KEYS_FILE = os.path.join(CONFIG_DIR, "airouter_api_keys.json")
PROXIES_FILE = os.path.join(CONFIG_DIR, "proxies.json")
OPENAI_INSTANCES_FILE = os.path.join(CONFIG_DIR, "openai_instances.json")

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
                "select_random_proxy_each_request": False
            },
            "module_statuses": {"openai": True, "gemini": True, "OAIC": True},
            "require_airouter_api_key": False 
        }
    }

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

ensure_config_files_exist()

registry = ModuleRegistry(settings_file_path=SETTINGS_FILE)

key_manager = ApiKeyManager({
    "openai": OPENAI_KEYS_FILE,
    "gemini": GEMINI_KEYS_FILE
})

proxy_manager = ProxyManager( 
    proxy_file_path=PROXIES_FILE,
    settings_file_path=SETTINGS_FILE
)
airouter_key_manager = AIRouterApiKeyManager()


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

app.state.key_manager = key_manager
app.state.proxy_manager = proxy_manager
app.state.module_registry = registry
app.state.airouter_key_manager = airouter_key_manager
app.state.settings_file_path = SETTINGS_FILE
app.state.app_version = APP_VERSION



@app.middleware("http")
async def check_airouter_api_key(request: Request, call_next):
    if request.url.path == "/favicon.ico" or \
       request.url.path.startswith("/static") or \
       request.url.path.startswith("/admin") or \
       request.url.path.startswith("/api/admin/"):
        response = await call_next(request)
        return response

    try:
        with open(app.state.settings_file_path, 'r') as f:
            settings = json.load(f)
        require_key = settings.get("require_airouter_api_key", False)
    except Exception:
        logger.error(f"Could not read settings file at {app.state.settings_file_path} for API key check. Denying access by default.")
        return JSONResponse(
            status_code=500,
            content={"detail": "Server configuration error, cannot verify API key requirement."}
        )

    if require_key:
        try:
            auth_header: Optional[HTTPAuthorizationCredentials] = await bearer_scheme(request)
        except HTTPException as e:
            logger.warning(f"Authorization header issue for {request.url.path}: {e.detail}")
            return JSONResponse(
                status_code=401,
                content={"Error": "Authorization header is missing or invalid. Use Bearer token."},
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not auth_header:
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

if key_manager.get_key("openai"): 
    registry.register(OpenAIChatModule(
        api_key_manager=key_manager, 
        proxy_manager=proxy_manager,
        settings_file_path=SETTINGS_FILE,
        service_name="openai"
    ))
else:
    print("Warning: No OpenAI API keys found. OpenAI module will not be registered.")

if key_manager.get_key("gemini"):
    registry.register(GeminiChatModule(
        api_key_manager=key_manager, 
        proxy_manager=proxy_manager,
        settings_file_path=SETTINGS_FILE,
        service_name="gemini"
    ))
else:
    print("Warning: No Gemini API keys found. Gemini module will not be registered.")

if openai_instances_config:
     registry.register(OpenAICompatModule(
         instances_config=openai_instances_config,
         proxy_manager=proxy_manager,
         settings_file_path=SETTINGS_FILE,
     ))
else:
    print("Warning: No OpenAI Compatible instances configured. OpenAI Compatible module will not be registered.")

try:
    if(open_browser_on_save): 
        webbrowser.open("http://localhost:8000/admin/dashboard")
except Exception as e:
    logger.warning(f"Could not open browser for admin dashboard: {e}")

app.include_router(admin_router.router)

from api.admin import dashboard_api, settings_api, keys_api, proxies_api, models_api
app.include_router(dashboard_api.router)
app.include_router(settings_api.router)
app.include_router(keys_api.router)
app.include_router(proxies_api.router)
app.include_router(models_api.router) 

from api.airouter import openai_compatible
app.include_router(openai_compatible.router)

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = os.path.join("static", "favicon.ico") # Изменен путь
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/vnd.microsoft.icon")
    else:
        return Response(status_code=204)