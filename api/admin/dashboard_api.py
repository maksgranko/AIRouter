from fastapi import APIRouter, Depends, Request
from typing import Dict, Any

# Импорты из корневой папки проекта (на один уровень выше)
from admin_router import get_current_username, get_dashboard_data

router = APIRouter(
    prefix="/api/admin/ui", # Новый префикс
    tags=["dashboard_admin_ui_api"], 
    dependencies=[Depends(get_current_username)]
)

@router.get("/dashboard-data", name="ui_api_dashboard_data") # Имя маршрута можно оставить прежним для совместимости с url_for
async def ui_api_dashboard_data_view(request: Request, username: str = Depends(get_current_username)):
    data = await get_dashboard_data(request)
    return data
