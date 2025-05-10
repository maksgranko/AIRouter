import os
import secrets
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

# Убираем временные импорты, т.к. менеджеры будут браться из app.state
# from api_key_manager import ApiKeyManager 
# from proxy_manager import ProxyManager

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(lambda: get_current_username)] # Применяем ко всем роутам в этом APIRouter
)

security = HTTPBasic()
templates = Jinja2Templates(directory="templates")

ADMIN_USERNAME_ENV = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_ENV = os.getenv("ADMIN_PASSWORD", "supersecret") # В продакшене используйте более надежный пароль!

# Переносим get_current_username внутрь файла или импортируем, если он общий
async def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME_ENV)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD_ENV)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@router.get("/dashboard", name="admin_dashboard") # Добавляем name для url_for
async def admin_dashboard_view(request: Request, username: str = Depends(get_current_username)):
    key_manager = request.app.state.key_manager
    key_manager = request.app.state.key_manager
    proxy_manager = request.app.state.proxy_manager
    module_registry = request.app.state.module_registry # Получаем registry
    
    proxy_status_text = "Включено" if proxy_manager.active else "Выключено"
    
    context = {
        "request": request,
        "username": username,
        "proxy_manager_is_active": proxy_manager.active, 
        "proxy_manager_active_status": proxy_status_text,
        "current_proxy_rotation_mode": proxy_manager.proxy_rotation_mode_env, 
        "initial_use_proxies_env": str(proxy_manager.use_proxies_env).lower(), 
        "initial_proxy_rotation_mode_env": os.getenv("PROXY_ROTATION_MODE", "once").lower(), 
        "openai_keys_file": key_manager.key_files.get("openai", "N/A"),
        "openai_keys_count": len(key_manager.api_keys.get("openai", [])),
        "gemini_keys_file": key_manager.key_files.get("gemini", "N/A"),
        "gemini_keys_count": len(key_manager.api_keys.get("gemini", [])),
        "proxies_file": proxy_manager.proxy_file_path,
        "proxies_count": len(proxy_manager.proxies),
        "module_statuses": module_registry.get_all_module_statuses() # Передаем статусы модулей
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
        
    return RedirectResponse(url=router.url_path_for("admin_dashboard_view"), status_code=status.HTTP_303_SEE_OTHER)

@router.post("/dashboard/settings/module", name="update_module_status")
async def update_module_status_form(
    request: Request,
    module_name: str = Form(...),
    module_status_str: str = Form(..., alias="module_status")
):
    module_registry = request.app.state.module_registry
    module_status_bool = module_status_str.lower() == "true"
    
    module_registry.set_module_active(module_name, module_status_bool)
    
    return RedirectResponse(url=router.url_path_for("admin_dashboard_view"), status_code=status.HTTP_303_SEE_OTHER)
