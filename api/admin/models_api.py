from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse

# Относительные импорты из корневой папки проекта
from admin_router import get_current_username, _fetch_and_cache_all_models, \
                         _cached_models_data, _cached_models_error
# _fetch_and_cache_all_models - внутренняя функция admin_router, нужно убедиться, что она доступна
# или перенести ее логику сюда/в общее место. Пока предполагаем, что импорт сработает.
# Если _fetch_and_cache_all_models не предназначена для прямого импорта, 
# то нужно будет рефакторить admin_router.py, чтобы сделать ее или ее логику доступной.

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
        # _fetch_and_cache_all_models - это асинхронная функция, обновляющая глобальный кэш
        await _fetch_and_cache_all_models(request, force_refresh=True)
        
        # Возвращаем обновленные данные из кэша
        response_content = {
            "status": "success",
            "message": "Model list cache refreshed.",
            "models": _cached_models_data, # Данные из кэша
            "error_message": _cached_models_error # Ошибка из кэша, если есть
        }
        return JSONResponse(content=response_content)
    except Exception as e:
        print(f"Error refreshing models cache via API: {e}")
        raise HTTPException(status_code=500, detail="Could not refresh models cache.")
