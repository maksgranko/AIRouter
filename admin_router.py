import os
import secrets
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

# Предполагаем, что key_manager и proxy_manager будут доступны (например, импортированы из main или переданы)
# Для простоты пока сделаем их глобальными здесь, но лучше передавать через Depends или состояние приложения.
# Это временное решение для демонстрации.
from api_key_manager import ApiKeyManager
from proxy_manager import ProxyManager

# Эти экземпляры должны быть теми же, что используются в main.py
# В реальном приложении их нужно будет передавать более корректно.
# Сейчас мы их пересоздадим здесь для примера, но это неверно для реального состояния.
# Правильный способ - получить их из app.state или через Depends(get_key_manager) и т.д.
# ПОКА ОСТАВИМ ТАК, НО ЭТО НУЖНО БУДЕТ ИСПРАВИТЬ В main.py ПРИ ИНТЕГРАЦИИ
# key_manager_admin = ApiKeyManager({"openai": "openai_keys.json", "gemini": "gemini_keys.json"})
# proxy_manager_admin = ProxyManager(proxy_file_path="proxies.json")


router = APIRouter(
    prefix="/admin",
    tags=["admin"]
)

security = HTTPBasic()
templates = Jinja2Templates(directory="templates")

ADMIN_USERNAME_ENV = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_ENV = os.getenv("ADMIN_PASSWORD", "supersecret")

def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME_ENV)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD_ENV)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@router.get("/dashboard")
async def admin_dashboard(request: Request, username: str = Depends(get_current_username)):
    # Получаем key_manager и proxy_manager из состояния приложения (будет настроено в main.py)
    key_manager = request.app.state.key_manager
    proxy_manager = request.app.state.proxy_manager
    
    proxy_status = "Включено" if proxy_manager.active else "Выключено (USE_PROXIES=false или нет загруженных прокси)"
    
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "username": username,
        "proxy_manager_active_status": proxy_status,
        "proxy_rotation_mode": proxy_manager.proxy_rotation_mode_env if proxy_manager.active else "N/A (прокси выключены)",
        "openai_keys_file": key_manager.key_files.get("openai", "N/A"),
        "openai_keys_count": len(key_manager.api_keys.get("openai", [])),
        "gemini_keys_file": key_manager.key_files.get("gemini", "N/A"),
        "gemini_keys_count": len(key_manager.api_keys.get("gemini", [])),
        "proxies_file": proxy_manager.proxy_file_path if proxy_manager.active else "N/A (прокси выключены)",
        "proxies_count": len(proxy_manager.proxies) if proxy_manager.active else 0,
    })
