import os
import webbrowser
import json
from copy import deepcopy
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
from modules.mcp_client_manager import MCPClientManager
from modules.global_audit_logger import GlobalAuditLogger
import admin_router
import logging
import time

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
LOGS_DIR = "logs"
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
OPENAI_KEYS_FILE = os.path.join(CONFIG_DIR, "openai_keys.json")
GEMINI_KEYS_FILE = os.path.join(CONFIG_DIR, "gemini_keys.json")
AIROUTER_KEYS_FILE = os.path.join(CONFIG_DIR, "airouter_api_keys.json")
PROXIES_FILE = os.path.join(CONFIG_DIR, "proxies.json")
OPENAI_INSTANCES_FILE = os.path.join(CONFIG_DIR, "openai_instances.json")
MCP_SERVERS_FILE = os.path.join(CONFIG_DIR, "mcp_servers.json")
MCP_AUDIT_LOG_FILE = os.path.join(LOGS_DIR, "mcp_audit.log")
MCP_AUDIT_SETTINGS_FILE = os.path.join(CONFIG_DIR, "mcp_audit_settings.json")
GLOBAL_AUDIT_SETTINGS_FILE = os.path.join(CONFIG_DIR, "global_audit_settings.json")

def ensure_config_files_exist():
    """Проверяет/нормализует файлы конфигурации и заполняет отсутствующие значения по умолчанию."""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
        print(f"Created directory: {CONFIG_DIR}")
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR)
        print(f"Created directory: {LOGS_DIR}")

    default_settings = {
        "proxy_settings": {
            "use_proxies": True,
            "rotation_mode": "once",
            "force_proxy_rotation_after_request": False,
            "select_random_proxy_each_request": False
        },
        "module_statuses": {"openai": True, "gemini": True, "OAIC": True},
        "require_airouter_api_key": False,
        "module_proxy_usage": {"openai": True, "gemini": True},
        "reformat_messages_settings": {},
        "smart_context_zipper_settings": {}
    }

    default_files_content = {
        OPENAI_KEYS_FILE: [],
        GEMINI_KEYS_FILE: [],
        AIROUTER_KEYS_FILE: [],
        PROXIES_FILE: [],
        OPENAI_INSTANCES_FILE: [],
        MCP_SERVERS_FILE: [],
        SETTINGS_FILE: default_settings
    }

    mcp_audit_defaults = {
        "enabled": True,
        "retention_days": 7,
        "gzip_enabled": True,
    }
    global_audit_defaults = {
        "enabled": True,
        "retention_days": 7,
        "gzip_enabled": True,
    }

    def _save_json(file_path: str, payload) -> None:
        try:
            with open(file_path, 'w') as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            print(f"Error creating default config file {file_path}: {e}")

    def _merge_dict_defaults(current: dict, defaults: dict) -> tuple[dict, bool]:
        changed = False
        merged = deepcopy(current)
        for key, default_value in defaults.items():
            if key not in merged:
                merged[key] = deepcopy(default_value)
                changed = True
                continue
            if isinstance(default_value, dict) and isinstance(merged.get(key), dict):
                nested_merged, nested_changed = _merge_dict_defaults(merged[key], default_value)
                if nested_changed:
                    merged[key] = nested_merged
                    changed = True
        return merged, changed

    for file_path, default_content in default_files_content.items():
        if not os.path.exists(file_path):
            _save_json(file_path, default_content)
            print(f"Created default config file: {file_path}")
            continue

        try:
            with open(file_path, 'r') as f:
                loaded = json.load(f)
        except Exception:
            _save_json(file_path, default_content)
            logger.warning(f"Config file '{file_path}' is invalid. Recreated with defaults.")
            continue

        if isinstance(default_content, dict):
            if not isinstance(loaded, dict):
                _save_json(file_path, default_content)
                logger.warning(f"Config file '{file_path}' has invalid format. Recreated with defaults.")
                continue
            merged, changed = _merge_dict_defaults(loaded, default_content)
            if changed:
                _save_json(file_path, merged)
                logger.info(f"Config file '{file_path}' was normalized with missing defaults.")
        elif isinstance(default_content, list):
            if not isinstance(loaded, list):
                _save_json(file_path, default_content)
                logger.warning(f"Config file '{file_path}' has invalid format. Recreated with defaults.")

    if not os.path.exists(MCP_AUDIT_SETTINGS_FILE):
        _save_json(MCP_AUDIT_SETTINGS_FILE, mcp_audit_defaults)
    else:
        try:
            with open(MCP_AUDIT_SETTINGS_FILE, 'r') as f:
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                _save_json(MCP_AUDIT_SETTINGS_FILE, mcp_audit_defaults)
            else:
                merged, changed = _merge_dict_defaults(loaded, mcp_audit_defaults)
                if changed:
                    _save_json(MCP_AUDIT_SETTINGS_FILE, merged)
        except Exception:
            _save_json(MCP_AUDIT_SETTINGS_FILE, mcp_audit_defaults)

    if not os.path.exists(GLOBAL_AUDIT_SETTINGS_FILE):
        _save_json(GLOBAL_AUDIT_SETTINGS_FILE, global_audit_defaults)
    else:
        try:
            with open(GLOBAL_AUDIT_SETTINGS_FILE, 'r') as f:
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                _save_json(GLOBAL_AUDIT_SETTINGS_FILE, global_audit_defaults)
            else:
                merged, changed = _merge_dict_defaults(loaded, global_audit_defaults)
                if changed:
                    _save_json(GLOBAL_AUDIT_SETTINGS_FILE, merged)
        except Exception:
            _save_json(GLOBAL_AUDIT_SETTINGS_FILE, global_audit_defaults)

ensure_config_files_exist()


def _build_key_manager() -> ApiKeyManager:
    return ApiKeyManager({
        "openai": OPENAI_KEYS_FILE,
        "gemini": GEMINI_KEYS_FILE
    })


def _build_proxy_manager() -> ProxyManager:
    return ProxyManager(
        proxy_file_path=PROXIES_FILE,
        settings_file_path=SETTINGS_FILE
    )


def _build_airouter_key_manager() -> AIRouterApiKeyManager:
    return AIRouterApiKeyManager()


def _register_available_modules(
    target_registry: ModuleRegistry,
    km: ApiKeyManager,
    pm: ProxyManager,
    oaic_instances: list,
):
    if km.get_key("openai"):
        target_registry.register(OpenAIChatModule(
            api_key_manager=km,
            proxy_manager=pm,
            settings_file_path=SETTINGS_FILE,
            service_name="openai"
        ))
    else:
        print("Warning: No OpenAI API keys found. OpenAI module will not be registered.")

    if km.get_key("gemini"):
        target_registry.register(GeminiChatModule(
            api_key_manager=km,
            proxy_manager=pm,
            settings_file_path=SETTINGS_FILE,
            service_name="gemini"
        ))
    else:
        print("Warning: No Gemini API keys found. Gemini module will not be registered.")

    if oaic_instances:
        oaic_module = OpenAICompatModule(
            instances_config=oaic_instances,
            proxy_manager=pm,
            settings_file_path=SETTINGS_FILE,
        )
        oaic_module.app_state = app.state
        target_registry.register(oaic_module)
    else:
        print("Warning: No OpenAI Compatible instances configured. OpenAI Compatible module will not be registered.")


registry = ModuleRegistry(settings_file_path=SETTINGS_FILE)
key_manager = _build_key_manager()
proxy_manager = _build_proxy_manager()
airouter_key_manager = _build_airouter_key_manager()


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


def normalize_module_statuses_for_availability(registry_obj: ModuleRegistry):
    """Отключает в settings.json модули, которые недоступны по конфигу/ключам."""
    availability = {
        "openai": bool(key_manager.get_key("openai", peek=True)),
        "gemini": bool(key_manager.get_key("gemini", peek=True)),
        "OAIC": bool(openai_instances_config),
    }

    try:
        settings_data = {}
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings_data = json.load(f)

        statuses = settings_data.get("module_statuses", {})
        if not isinstance(statuses, dict):
            statuses = {}

        changed = False
        for module_name, is_available in availability.items():
            if module_name not in statuses:
                statuses[module_name] = is_available
                changed = True
            elif not is_available and statuses.get(module_name):
                statuses[module_name] = False
                changed = True

        settings_data["module_statuses"] = statuses
        if changed:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings_data, f, indent=2)
            logger.info("Module statuses normalized based on module availability.")

        registry_obj._module_active_status.update(statuses)
    except Exception as e:
        logger.warning(f"Could not normalize module statuses: {e}")

app.state.key_manager = key_manager
app.state.proxy_manager = proxy_manager
app.state.module_registry = registry
app.state.airouter_key_manager = airouter_key_manager
app.state.settings_file_path = SETTINGS_FILE
app.state.app_version = APP_VERSION
app.state.mcp_manager = MCPClientManager(MCP_SERVERS_FILE, audit_log_path=MCP_AUDIT_LOG_FILE, settings_file_path=MCP_AUDIT_SETTINGS_FILE)
app.state.mcp_audit_settings_file_path = MCP_AUDIT_SETTINGS_FILE
app.state.global_audit_settings_file_path = GLOBAL_AUDIT_SETTINGS_FILE
app.state.logs_dir = LOGS_DIR
app.state.global_audit_logger = GlobalAuditLogger(LOGS_DIR, GLOBAL_AUDIT_SETTINGS_FILE)

normalize_module_statuses_for_availability(registry)
_register_available_modules(registry, key_manager, proxy_manager, openai_instances_config)


def reload_runtime_modules() -> dict:
    """Полностью пересоздает runtime-состояние модулей без рестарта процесса."""
    global registry, key_manager, proxy_manager, airouter_key_manager, openai_instances_config

    ensure_config_files_exist()

    new_registry = ModuleRegistry(settings_file_path=SETTINGS_FILE)
    new_key_manager = _build_key_manager()
    new_proxy_manager = _build_proxy_manager()
    new_airouter_key_manager = _build_airouter_key_manager()
    new_openai_instances_config = load_openai_instances_config(OPENAI_INSTANCES_FILE)

    key_manager = new_key_manager
    proxy_manager = new_proxy_manager
    airouter_key_manager = new_airouter_key_manager
    openai_instances_config = new_openai_instances_config
    registry = new_registry

    normalize_module_statuses_for_availability(registry)
    _register_available_modules(registry, key_manager, proxy_manager, openai_instances_config)

    app.state.key_manager = key_manager
    app.state.proxy_manager = proxy_manager
    app.state.module_registry = registry
    app.state.airouter_key_manager = airouter_key_manager
    app.state.mcp_manager = MCPClientManager(MCP_SERVERS_FILE, audit_log_path=MCP_AUDIT_LOG_FILE, settings_file_path=MCP_AUDIT_SETTINGS_FILE)
    app.state.mcp_audit_settings_file_path = MCP_AUDIT_SETTINGS_FILE
    app.state.global_audit_settings_file_path = GLOBAL_AUDIT_SETTINGS_FILE
    app.state.logs_dir = LOGS_DIR
    app.state.global_audit_logger = GlobalAuditLogger(LOGS_DIR, GLOBAL_AUDIT_SETTINGS_FILE)

    return {
        "registered_modules": list(registry.get_all_module_statuses().keys()),
        "active_modules": [mod.get_name() for mod in registry.all_active_modules()],
        "openai_keys_count": len(key_manager.api_keys.get("openai", [])),
        "gemini_keys_count": len(key_manager.api_keys.get("gemini", [])),
        "oaic_instances_count": len(openai_instances_config),
        "proxies_count": len(proxy_manager.proxies),
    }


app.state.reload_runtime_modules = reload_runtime_modules



@app.middleware("http")
async def check_airouter_api_key(request: Request, call_next):
    start = time.perf_counter()
    body_model_name = None
    try:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            raw_body = await request.body()
            if raw_body:
                parsed_body = json.loads(raw_body)
                if isinstance(parsed_body, dict):
                    model_val = parsed_body.get("model")
                    if isinstance(model_val, str):
                        body_model_name = model_val
    except Exception:
        body_model_name = None

    def _resolve_module_name() -> str:
        if body_model_name:
            if "/" in body_model_name:
                prefix = body_model_name.split("/", 1)[0]
                if prefix == "OAIC":
                    remainder = body_model_name.split("/", 2)
                    if len(remainder) >= 2 and remainder[1]:
                        return remainder[1]
                if prefix.startswith("openai_"):
                    return prefix.replace("openai_", "", 1)
                return prefix
            if body_model_name.startswith("openai_"):
                return body_model_name.replace("openai_", "", 1)
            return body_model_name

        path = request.url.path
        if path.startswith("/api/admin") or path.startswith("/admin"):
            return "admin"
        if path.startswith("/v1/"):
            return "api"
        return "system"

    def _audit(status_code: int):
        logger_obj = getattr(app.state, "global_audit_logger", None)
        if not logger_obj:
            return
        latency_ms = int((time.perf_counter() - start) * 1000)
        logger_obj.log_event(
            {
                "path": request.url.path,
                "method": request.method,
                "status_code": status_code,
                "latency_ms": latency_ms,
                "client": request.client.host if request.client else "unknown",
                "module_name": _resolve_module_name(),
            }
        )

    if request.url.path == "/favicon.ico" or \
       request.url.path.startswith("/static") or \
       request.url.path.startswith("/admin") or \
       request.url.path.startswith("/api/admin/"):
        response = await call_next(request)
        _audit(response.status_code)
        return response

    try:
        with open(app.state.settings_file_path, 'r') as f:
            settings = json.load(f)
        require_key = settings.get("require_airouter_api_key", False)
    except Exception:
        logger.error(f"Could not read settings file at {app.state.settings_file_path} for API key check. Denying access by default.")
        _audit(500)
        return JSONResponse(
            status_code=500,
            content={"detail": "Server configuration error, cannot verify API key requirement."}
        )

    if require_key:
        try:
            auth_header: Optional[HTTPAuthorizationCredentials] = await bearer_scheme(request)
        except HTTPException as e:
            logger.warning(f"Authorization header issue for {request.url.path}: {e.detail}")
            _audit(401)
            return JSONResponse(
                status_code=401,
                content={"Error": "Authorization header is missing or invalid. Use Bearer token."},
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not auth_header:
            logger.warning(f"Authorization header could not be processed for {request.url.path}")
            _audit(401)
            return JSONResponse(
                status_code=401,
                content={"Error": "Not authenticated. Bearer token could not be processed."},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header.credentials
        air_key_manager: AIRouterApiKeyManager = request.app.state.airouter_key_manager
        
        if not air_key_manager.key_exists(token):
            logger.warning(f"Invalid API Key received: '{token}' for {request.url.path}")
            _audit(403)
            return JSONResponse(
                status_code=403,
                content={"Error": "Auth data is not valid. Check API-Key on dashboard."}
            )
        logger.debug(f"Valid API Key received for {request.url.path}")

    response = await call_next(request)
    _audit(response.status_code)
    return response

try:
    if(open_browser_on_save): 
        webbrowser.open("http://localhost:8000/admin/dashboard")
except Exception as e:
    logger.warning(f"Could not open browser for admin dashboard: {e}")

app.include_router(admin_router.router)

from api.admin import dashboard_api, settings_api, keys_api, proxies_api, models_api, logs_api
app.include_router(dashboard_api.router)
app.include_router(settings_api.router)
app.include_router(keys_api.router)
app.include_router(proxies_api.router)
app.include_router(models_api.router) 
app.include_router(logs_api.router)
from api.admin import mcp_api
app.include_router(mcp_api.router)

from api.airouter import openai_compatible
app.include_router(openai_compatible.router)
from api.mcp import facade_api
app.include_router(facade_api.router)

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = os.path.join("static", "favicon.ico") # Изменен путь
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/vnd.microsoft.icon")
    else:
        return Response(status_code=204)
