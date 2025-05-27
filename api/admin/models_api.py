from fastapi import APIRouter, Depends, HTTPException, status, Request, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Импортируем модуль admin_router целиком, чтобы получить доступ к его глобальным переменным
import admin_router 
# Также импортируем необходимые функции напрямую, если они используются как зависимости и т.д.
from admin_router import (
    get_current_username,
    get_reformat_settings, set_reformat_setting, ReformatMessageSettingPayload,
    get_smart_context_zipper_settings, set_smart_context_zipper_setting, SmartContextZipperSettingPayload
)


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

@router.post("/set_reformat_status", name="ui_api_set_reformat_status", status_code=status.HTTP_200_OK)
async def ui_api_set_reformat_status(
    payload: ReformatMessageSettingPayload,
    username: str = Depends(get_current_username)
):
    try:
        set_reformat_setting(payload.module_name, payload.model_id, payload.is_reformat_enabled)
        return JSONResponse(content={
            "status": "success",
            "message": f"Reformat setting for model '{payload.model_id}' ({payload.module_name}) updated to {payload.is_reformat_enabled}."
        })
    except Exception as e:
        print(f"Error setting reformat status for model {payload.model_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Could not update reformat setting: {e}")

@router.post("/set_smart_context_zipper_status", name="ui_api_set_smart_context_zipper_status", status_code=status.HTTP_200_OK)
async def ui_api_set_smart_context_zipper_status(
    payload: SmartContextZipperSettingPayload,
    username: str = Depends(get_current_username)
):
    try:
        set_smart_context_zipper_setting(
            payload.module_name, payload.model_id, payload.is_smart_context_zipper_enabled
        )
        return JSONResponse(content={
            "status": "success",
            "message": f"SmartContextZipper setting for model '{payload.model_id}'"
                       f" ({payload.module_name}) updated to {payload.is_smart_context_zipper_enabled}."
        })
    except Exception as e:
        print(f"Error setting SmartContextZipper status for model {payload.model_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Could not update SmartContextZipper setting:{e}")

@router.get("/get_reformat_settings", name="ui_api_get_reformat_settings", status_code=status.HTTP_200_OK)
async def ui_api_get_reformat_settings(
    username: str = Depends(get_current_username)
):
    try:
        settings = get_reformat_settings()
        return JSONResponse(content={
            "status": "success",
            "settings": settings
        })
    except Exception as e:
        print(f"Error getting reformat settings: {e}")
        raise HTTPException(status_code=500, detail=f"Could not retrieve reformat settings: {e}")

@router.get("/get_smart_context_zipper_settings", name="ui_api_get_smart_context_zipper_settings", status_code=status.HTTP_200_OK)
async def ui_api_get_smart_context_zipper_settings(
    username: str = Depends(get_current_username)
):
    try:
        settings = get_smart_context_zipper_settings()
        return JSONResponse(content={
            "status": "success",
            "settings": settings
        })
    except Exception as e:
        print(f"Error getting SmartContextZipper settings: {e}")
        raise HTTPException(status_code=500, detail=f"Could not retrieve SmartContextZipper settings: {e}")
