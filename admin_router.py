import os
import secrets
from typing import Optional, List, Dict, Any
import httpx # Добавляем httpx
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

# Убираем временные импорты, т.к. менеджеры будут браться из app.state
# from api_key_manager import ApiKeyManager
# from proxy_manager import ProxyManager

security = HTTPBasic() # Определяем экземпляр HTTPBasic на уровне модуля

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

# Закомментированные строки ниже не нужны, так как ADMIN_USERNAME_ENV и ADMIN_PASSWORD_ENV 
# теперь читаются внутри get_current_username, а security определен выше.
# # ADMIN_USERNAME_ENV и ADMIN_PASSWORD_ENV теперь читаются внутри get_current_username
# # security = HTTPBasic() # HTTPBasic() теперь вызывается внутри Depends в get_current_username
# # УДАЛЯЕМ ДУБЛИРУЮЩИЙСЯ БЛОК get_current_username, так как он уже определен выше.
# # Оставляем только один экземпляр функции.
# # Следующие строки были ошибочно оставлены и вызывали IndentationError:
# #    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME_ENV)
# #    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD_ENV)
# #    if not (correct_username and correct_password):
# #        raise HTTPException(
# #            status_code=status.HTTP_401_UNAUTHORIZED,
# #            detail="Incorrect username or password",
# #            headers={"WWW-Authenticate": "Basic"},
# #        )
# #    return credentials.username

@router.get("/dashboard", name="admin_dashboard") 
async def admin_dashboard_view(request: Request, username: str = Depends(get_current_username)):
    key_manager = request.app.state.key_manager # Исправлено дублирование
    proxy_manager = request.app.state.proxy_manager
    module_registry = request.app.state.module_registry
    
    proxy_status_text = "Включено" if proxy_manager.active else "Выключено"
    
    service_api_keys_info = {}
    for service_name_iter in key_manager.key_files.keys(): # Используем другое имя переменной
        service_api_keys_info[service_name_iter] = key_manager.api_keys.get(service_name_iter, [])

    context = {
        "request": request,
        "username": username,
        "proxy_manager_is_active": proxy_manager.active, 
        "proxy_manager_active_status": proxy_status_text,
        "current_proxy_rotation_mode": proxy_manager.current_rotation_mode, # Исправлено
        "initial_use_proxies_env": str(os.getenv("USE_PROXIES", "true")).lower(), # Читаем из env напрямую
        "initial_proxy_rotation_mode_env": os.getenv("PROXY_ROTATION_MODE", "once").lower(), # Читаем из env напрямую
        
        "openai_keys_file": key_manager.key_files.get("openai", "N/A"),
        "openai_keys_count": len(key_manager.api_keys.get("openai", [])),
        "gemini_keys_file": key_manager.key_files.get("gemini", "N/A"),
        "gemini_keys_count": len(key_manager.api_keys.get("gemini", [])),
        
        "service_api_keys": service_api_keys_info,

        "proxies_file": proxy_manager.proxy_file_path,
        "proxies_count": len(proxy_manager.proxies),
        "current_proxies_list": proxy_manager.proxies, # Передаем список прокси
        "module_statuses": module_registry.get_all_module_statuses()
    }
    return templates.TemplateResponse("admin_dashboard.html", context)

@router.post("/dashboard/settings/proxy", name="update_proxy_settings")
async def update_proxy_settings_form(
    request: Request,
    use_proxies_str: Optional[str] = Form(None, alias="use_proxies"), 
    rotation_mode: Optional[str] = Form(None, alias="rotation_mode"),
    action: str = Form(...) 
):
    proxy_manager = request.app.state.proxy_manager
    
    if action == "set_use_proxies" and use_proxies_str is not None:
        use_proxies_bool = use_proxies_str.lower() == "true"
        proxy_manager.set_use_proxies(use_proxies_bool)
    elif action == "set_rotation_mode" and rotation_mode is not None:
        proxy_manager.set_rotation_mode(rotation_mode)
        
    return RedirectResponse(url=router.url_path_for("admin_dashboard"), status_code=status.HTTP_303_SEE_OTHER)

@router.post("/dashboard/settings/module", name="update_module_status")
async def update_module_status_form(
    request: Request,
    module_name: str = Form(...),
    module_status_str: str = Form(..., alias="module_status")
):
    module_registry = request.app.state.module_registry
    module_status_bool = module_status_str.lower() == "true"
    
    module_registry.set_module_active(module_name, module_status_bool)
    
    return RedirectResponse(url=router.url_path_for("admin_dashboard"), status_code=status.HTTP_303_SEE_OTHER)

@router.post("/dashboard/keys", name="manage_api_key")
async def manage_api_key_form(
    request: Request,
    service_name: str = Form(...),
    api_key: str = Form(...), # Для add_key это новый ключ, для remove_key это ключ для удаления
    action: str = Form(...) 
):
    key_manager = request.app.state.key_manager
    
    if action == "add_key":
        if api_key and api_key.strip(): # Проверяем, что ключ не пустой
            key_manager.add_key(service_name, api_key.strip())
        # Можно добавить flash-сообщение об успехе/ошибке
    elif action == "remove_key":
        key_manager.remove_key(service_name, api_key) # api_key здесь - это ключ для удаления
        
    return RedirectResponse(url=router.url_path_for("admin_dashboard"), status_code=status.HTTP_303_SEE_OTHER)

@router.post("/dashboard/proxies", name="manage_proxy_list")
async def manage_proxy_list_form(
    request: Request,
    action: str = Form(...),
    new_proxy_type: Optional[str] = Form(None),
    new_proxy_url: Optional[str] = Form(None),
    proxy_url: Optional[str] = Form(None) # URL прокси для удаления
):
    proxy_manager = request.app.state.proxy_manager
    
    if action == "add_proxy":
        if new_proxy_type and new_proxy_url and new_proxy_url.strip():
            proxy_manager.add_proxy(new_proxy_type, new_proxy_url.strip())
        # Можно добавить flash-сообщение
    elif action == "remove_proxy" and proxy_url:
        proxy_manager.remove_proxy(proxy_url)
    elif action == "reload_proxies":
        proxy_manager.reload_proxies()
        
    return RedirectResponse(url=router.url_path_for("admin_dashboard"), status_code=status.HTTP_303_SEE_OTHER)

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
            try:
                models_response = await mod.list_models() # Это должно быть await, если list_models асинхронный
                if isinstance(models_response, dict) and "data" in models_response:
                    all_models.extend(models_response.get("data", []))
                else:
                    # Логируем, если модуль вернул что-то неожиданное
                    print(f"Warning: Module {mod.get_name()} returned unexpected format from list_models: {models_response}")
            except Exception as e:
                print(f"Error fetching models from module {mod.get_name()}: {e}")
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
        "error_message": _cached_models_error
    }
    return templates.TemplateResponse("admin_models.html", context)

@router.post("/models/refresh", name="admin_refresh_models")
async def admin_refresh_models_action(request: Request):
    # Принудительно обновляем кэш
    await _fetch_and_cache_all_models(request, force_refresh=True)
    # Перенаправляем на GET-эндпоинт, который использует обновленный кэш
    return RedirectResponse(url=router.url_path_for("admin_models_view"), status_code=status.HTTP_303_SEE_OTHER)
