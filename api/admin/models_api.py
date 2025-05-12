from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse

# Импортируем модуль admin_router целиком, чтобы получить доступ к его глобальным переменным
import admin_router 
# Также импортируем необходимые функции напрямую, если они используются как зависимости и т.д.
from admin_router import get_current_username 


router = APIRouter(
    prefix="/api/admin/ui/models",
    tags=["models_admin_ui_api"], 
    dependencies=[Depends(get_current_username)]
)

@router.post("/refresh", name="ui_api_refresh_models", status_code=status.HTTP_200_OK)
async def ui_api_refresh_models(
    request: Request,
    username: str = Depends(get_current_username)
):
    try:
        # Вызываем функцию _fetch_and_cache_all_models из модуля admin_router
        await admin_router._fetch_and_cache_all_models(request, force_refresh=True)
        
        # Получаем обновленные данные из глобальных переменных модуля admin_router
        response_content = {
            "status": "success",
            "message": "Model list cache refreshed.",
            "models": admin_router._cached_models_data, # Доступ через префикс модуля
            "error_message": admin_router._cached_models_error # Доступ через префикс модуля
        }
        return JSONResponse(content=response_content)
    except Exception as e:
        print(f"Error refreshing models cache via API: {e}")
        raise HTTPException(status_code=500, detail="Could not refresh models cache.")
