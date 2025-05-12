from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse

# Импорты из корневой папки проекта (на один уровень выше)
from admin_router import get_current_username, NewProxyPayload, ExistingProxyPayload

router = APIRouter(
    prefix="/api/admin/ui/proxies", # Новый префикс
    tags=["proxies_admin_ui_api"], 
    dependencies=[Depends(get_current_username)]
)

@router.post("", name="ui_api_add_proxy", status_code=status.HTTP_201_CREATED)
async def ui_api_add_proxy(
    payload: NewProxyPayload,
    request: Request,
    username: str = Depends(get_current_username)
):
    proxy_manager = request.app.state.proxy_manager
    try:
        proxy_manager.add_proxy(payload.type, payload.url)
        return JSONResponse(content={"status": "success", "message": f"Proxy '{payload.url}' added."})
    except Exception as e:
        print(f"Error adding proxy via API: {e}")
        raise HTTPException(status_code=500, detail=f"Could not add proxy '{payload.url}'.")

@router.delete("", name="ui_api_delete_proxy") 
async def ui_api_delete_proxy(
    payload: ExistingProxyPayload, 
    request: Request,
    username: str = Depends(get_current_username)
):
    proxy_manager = request.app.state.proxy_manager
    try:
        proxy_manager.remove_proxy(payload.url) 
        return JSONResponse(content={"status": "success", "message": f"Proxy '{payload.url}' removed."})
    except Exception as e:
        print(f"Error deleting proxy via API: {e}")
        raise HTTPException(status_code=500, detail=f"Could not delete proxy '{payload.url}'.")

@router.post("/reload", name="ui_api_reload_proxies")
async def ui_api_reload_proxies(
    request: Request,
    username: str = Depends(get_current_username)
):
    proxy_manager = request.app.state.proxy_manager
    try:
        proxy_manager.reload_proxies()
        return JSONResponse(content={"status": "success", "message": "Proxy list reloaded from file."})
    except Exception as e:
        print(f"Error reloading proxies via API: {e}")
        raise HTTPException(status_code=500, detail="Could not reload proxies from file.")

@router.post("/shuffle", name="ui_api_shuffle_proxies")
async def ui_api_shuffle_proxies(
    request: Request,
    username: str = Depends(get_current_username)
):
    proxy_manager = request.app.state.proxy_manager
    try:
        proxy_manager.shuffle_proxies_in_memory_and_save()
        return JSONResponse(content={"status": "success", "message": "Proxy list shuffled and saved."})
    except Exception as e:
        print(f"Error shuffling proxies via API: {e}")
        raise HTTPException(status_code=500, detail="Could not shuffle proxies.")
