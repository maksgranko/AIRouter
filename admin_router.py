import os
import json
import secrets
from typing import Optional, List, Dict, Any, Union
import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, Body
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, Field
from enum import Enum

security = HTTPBasic()

# Pydantic модели для API настроек
class ProxySettingName(str, Enum):
    USE_PROXIES = "use_proxies"
    ROTATION_MODE = "rotation_mode"
    FORCE_PROXY_ROTATION = "force_proxy_rotation_after_request"
    SELECT_RANDOM_PROXY = "select_random_proxy_each_request"

class UpdateProxySettingPayload(BaseModel):
    setting_name: ProxySettingName
    value: Union[bool, str]

class ModuleStatusPayload(BaseModel):
    active: bool

class ServiceApiKeyPayload(BaseModel):
    api_key: str = Field(..., min_length=1)

class AirouterApiKeyPayload(BaseModel):
    api_key: str = Field(..., min_length=1) # Для удаления

class AirouterSecurityPayload(BaseModel):
    require_api_key: bool

class NewProxyPayload(BaseModel):
    type: str # http, socks4, socks5
    url: str

class ExistingProxyPayload(BaseModel):
    url: str

async def get_current_username(credentials: HTTPBasicCredentials = Depends(security)): # Используем экземпляр security
    ADMIN_USERNAME_ENV = os.getenv("ADMIN_USERNAME", "admin") 
    ADMIN_PASSWORD_ENV = os.getenv("ADMIN_PASSWORD", "supersecret")

    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME_ENV)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD_ENV)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_username)] 
)

templates = Jinja2Templates(directory="templates")

async def get_dashboard_data(request: Request) -> Dict[str, Any]:
    key_manager = request.app.state.key_manager
    proxy_manager = request.app.state.proxy_manager
    module_registry = request.app.state.module_registry
    airouter_key_manager = request.app.state.airouter_key_manager
    settings_file_path = request.app.state.settings_file_path

    proxy_status_text = "Включено" if proxy_manager.active else "Выключено"
    
    service_api_keys_info = {}
    for service_name_iter in key_manager.key_files.keys():
        service_api_keys_info[service_name_iter] = key_manager.api_keys.get(service_name_iter, [])

    require_airouter_api_key = False
    force_proxy_rotation_after_request = False
    try:
        with open(settings_file_path, 'r') as f:
            settings_data = json.load(f)
            require_airouter_api_key = settings_data.get("require_airouter_api_key", False)
            force_proxy_rotation_after_request = settings_data.get("proxy_settings", {}).get("force_proxy_rotation_after_request", False)
    except Exception as e:
        print(f"Error reading settings for dashboard data: {e}") 

    return {
        "proxy_manager_is_active": proxy_manager.active,
        "proxy_manager_active_status": proxy_status_text,
        "current_proxy_rotation_mode": proxy_manager.current_rotation_mode,
        "force_proxy_rotation_after_request": force_proxy_rotation_after_request, 
        "select_random_proxy_each_request": proxy_manager.select_random_proxy_each_request,
        "initial_use_proxies_env": str(os.getenv("USE_PROXIES", "true")).lower(),
        "initial_proxy_rotation_mode_env": os.getenv("PROXY_ROTATION_MODE", "once").lower(),
        "openai_keys_file": key_manager.key_files.get("openai", "N/A"),
        "openai_keys_count": len(key_manager.api_keys.get("openai", [])),
        "gemini_keys_file": key_manager.key_files.get("gemini", "N/A"),
        "gemini_keys_count": len(key_manager.api_keys.get("gemini", [])),
        "service_api_keys": service_api_keys_info,
        "proxies_file": proxy_manager.proxy_file_path,
        "proxies_count": len(proxy_manager.proxies),
        "current_proxies_list": proxy_manager.proxies,
        "module_statuses": module_registry.get_all_module_statuses(),
        "airouter_api_keys": airouter_key_manager.get_all_keys(),
        "require_airouter_api_key": require_airouter_api_key,
        "airouter_keys_file": airouter_key_manager.keys_file_path,
        "openai_instances_file": "configs/openai_instances.json", # Путь к файлу инстансов
        "openai_instances": _load_openai_instances(), # Список инстансов
        "app_version": request.app.state.app_version
    }

# Импортируем функции для работы с инстансами из settings_api
from api.admin.settings_api import _load_openai_instances, OPENAI_INSTANCES_CONFIG_PATH

@router.get("/ui/api/dashboard-data", name="admin_ui_api_dashboard_data")
async def admin_ui_api_dashboard_data_view(request: Request, username: str = Depends(get_current_username)):
    data = await get_dashboard_data(request)
    return data

@router.get("/dashboard", name="admin_dashboard") 
async def admin_dashboard_view(request: Request, username: str = Depends(get_current_username)):
    # Теперь эта функция просто рендерит шаблон. Данные будут загружены через JS.
    context = {
        "request": request,
        "username": username,
        "app_version": request.app.state.app_version 
        # Можно передать и другие базовые вещи, если они нужны до загрузки JS,
        # например, URL для API эндпоинта
    }
    return templates.TemplateResponse("admin_dashboard.html", context)

# --- JSON API эндпоинты были перенесены в папку /api ---
# Старые обработчики форм удалены, так как UI теперь использует JSON API.

@router.get("/help", name="admin_help")
async def admin_help_view(request: Request, username: str = Depends(get_current_username)):
    # Можно передать какие-либо динамические данные в справку, если нужно
    # Например, актуальные имена файлов конфигурации
    key_manager = request.app.state.key_manager
    proxy_manager = request.app.state.proxy_manager
    context = {
        "request": request,
        "username": username,
        "openai_keys_file": key_manager.key_files.get("openai", "openai_keys.json"),
        "gemini_keys_file": key_manager.key_files.get("gemini", "gemini_keys.json"),
        "proxies_file": proxy_manager.proxy_file_path,
        "app_version": request.app.state.app_version
    }
    return templates.TemplateResponse("admin_help.html", context)

# Глобальные переменные для кэширования моделей
_cached_models_data: Optional[List[Dict[str, Any]]] = None
_cached_models_error: Optional[str] = None

async def _fetch_and_cache_all_models(request: Request, force_refresh: bool = False):
    """
    Получает список моделей от всех активных модулей и кэширует его.
    """
    global _cached_models_data, _cached_models_error

    if not force_refresh and _cached_models_data is not None:
        # Если не принудительное обновление и кэш есть, ничего не делаем
        # Ошибка также будет из кэша
        return

    all_models = []
    current_error = None
    module_registry = request.app.state.module_registry
    
    try:
        for mod in module_registry.all_active_modules():
            module_name = mod.get_name()
            try:
                models_response = await mod.list_models() # Это должно быть await, если list_models асинхронный
                if isinstance(models_response, dict) and "data" in models_response:
                    module_models = models_response.get("data", [])
                    for model_data in module_models:
                        # Предполагаем, что model_data - это словарь и у него есть 'id'
                        if isinstance(model_data, dict) and 'id' in model_data:
                            # Создаем новый ID или добавляем поле module_name
                            # Для простоты отображения в шаблоне, можно сразу изменить 'id'
                            # или добавить новое поле, например, 'display_id' или 'full_id'
                            model_data['id'] = f"{module_name}/{model_data['id']}"
                            # Если нужно сохранить оригинальный id, можно сделать так:
                            # model_data['original_id'] = model_data['id']
                            # model_data['id'] = f"{module_name}/{model_data['original_id']}"
                            # model_data['module_name'] = module_name
                        all_models.append(model_data) # Добавляем измененную или оригинальную модель
                else:
                    # Логируем, если модуль вернул что-то неожиданное
                    print(f"Warning: Module {module_name} returned unexpected format from list_models: {models_response}")
            except Exception as e:
                print(f"Error fetching models from module {module_name}: {e}")
                # Сохраняем первую возникшую ошибку, чтобы показать пользователю
                if not current_error:
                    current_error = f"Ошибка при получении моделей от модуля {mod.get_name()}: {str(e)}"
        
        if not all_models and not current_error:
             # Если список пуст, но ошибок не было, это может быть нормально
             pass # _cached_models_error останется None или предыдущей ошибкой, если она была
        
        _cached_models_data = all_models
        _cached_models_error = current_error # Обновляем кэш ошибки

    except Exception as e:
        # Общая ошибка при итерации или доступе к registry
        _cached_models_data = [] # Сбрасываем данные моделей в случае общей ошибки
        _cached_models_error = f"Общая ошибка при получении списка моделей: {str(e)}"


@router.get("/models", name="admin_models_view")
async def admin_models_view_page(request: Request, username: str = Depends(get_current_username)):
    # При первом заходе или если кэш пуст, _fetch_and_cache_all_models его заполнит
    # force_refresh=False означает, что если кэш уже есть, он будет использован
    # Если кэш пуст (_cached_models_data is None), то он будет заполнен.
    if _cached_models_data is None: # Только если кэш абсолютно пуст, делаем первоначальную загрузку
        await _fetch_and_cache_all_models(request, force_refresh=True)

    context = {
        "request": request,
        "username": username,
        "models": _cached_models_data,
        "error_message": _cached_models_error,
        "app_version": request.app.state.app_version
    }
    return templates.TemplateResponse("admin_models.html", context)
