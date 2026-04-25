from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse

# Импорты из корневой папки проекта (на один уровень выше)
from admin_router import get_current_username, \
    ServiceApiKeyPayload, AirouterApiKeyPayload
from pydantic import BaseModel

class UpdateServiceApiKeyPayload(BaseModel):
    old_api_key: str
    new_api_key: str

class UpdateAirouterApiKeyPayload(BaseModel):
    old_api_key: str
    new_api_key: str

router = APIRouter(
    prefix="/api/admin/ui/keys", # Новый префикс
    tags=["keys_admin_ui_api"], 
    dependencies=[Depends(get_current_username)]
)

@router.post("/service/{service_name}", name="ui_api_add_service_key", status_code=status.HTTP_201_CREATED)
async def ui_api_add_service_key(
    service_name: str,
    payload: ServiceApiKeyPayload,
    request: Request,
    username: str = Depends(get_current_username)
):
    key_manager = request.app.state.key_manager
    try:
        if service_name not in key_manager.key_files:
            raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found.")
        if not key_manager.add_key(service_name, payload.api_key):
            raise HTTPException(status_code=400, detail="Could not add API key (already exists or invalid).")
        return JSONResponse(content={"status": "success", "message": f"API key added for service '{service_name}'."})
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error adding service API key via API for {service_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Could not add API key for service '{service_name}'.")

@router.patch("/service/{service_name}/key", name="ui_api_patch_service_key")
async def ui_api_patch_service_key(
    service_name: str,
    payload: UpdateServiceApiKeyPayload, 
    request: Request,
    username: str = Depends(get_current_username)
):
    key_manager = request.app.state.key_manager
    try:
        keys = key_manager.api_keys.get(service_name, [])
        if payload.old_api_key not in keys:
            raise HTTPException(status_code=404, detail="Old API key not found for this service.")
        if payload.new_api_key in keys:
            raise HTTPException(status_code=400, detail="New key already exists in this service.")
        if not key_manager.update_key(service_name, payload.old_api_key, payload.new_api_key):
            raise HTTPException(status_code=400, detail="Could not update API key for this service.")
        return JSONResponse(content={"status": "success", "message": f"API ключ обновлён для сервиса '{service_name}'."})
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating service API key via API for {service_name}: {e}")
        if service_name not in key_manager.key_files: 
            raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found.")
        raise HTTPException(status_code=500, detail=f"Could not update API key for service '{service_name}'.")

@router.delete("/service/{service_name}", name="ui_api_delete_service_key")
async def ui_api_delete_service_key(
    service_name: str,
    payload: ServiceApiKeyPayload, 
    request: Request,
    username: str = Depends(get_current_username)
):
    key_manager = request.app.state.key_manager
    try:
        if service_name not in key_manager.key_files:
            raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found.")
        if not key_manager.remove_key(service_name, payload.api_key):
            raise HTTPException(status_code=404, detail="API key not found for this service.")
        return JSONResponse(content={"status": "success", "message": f"API key removed for service '{service_name}'."})
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting service API key via API for {service_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Could not delete API key for service '{service_name}'.")

@router.post("/airouter", name="ui_api_generate_airouter_key", status_code=status.HTTP_201_CREATED)
async def ui_api_generate_airouter_key(
    request: Request,
    username: str = Depends(get_current_username)
):
    airouter_key_manager = request.app.state.airouter_key_manager
    try:
        new_key = airouter_key_manager.generate_and_add_key()
        return JSONResponse(content={"status": "success", "message": "New AIRouter API key generated and added.", "new_key": new_key})
    except Exception as e:
        print(f"Error generating AIRouter API key via API: {e}")
        raise HTTPException(status_code=500, detail="Could not generate AIRouter API key.")

@router.patch("/airouter/key", name="ui_api_patch_airouter_key")
async def ui_api_patch_airouter_key(
    payload: UpdateAirouterApiKeyPayload,
    request: Request,
    username: str = Depends(get_current_username)
):
    airouter_key_manager = request.app.state.airouter_key_manager
    try:
        all_keys = airouter_key_manager.get_all_keys()
        if payload.old_api_key not in all_keys:
            raise HTTPException(status_code=404, detail="Old AIRouter API key not found.")
        if payload.new_api_key in all_keys:
            raise HTTPException(status_code=400, detail="New AIRouter API key already exists.")
        # update_key реализация
        try:
            idx = all_keys.index(payload.old_api_key)
            airouter_key_manager.api_keys[idx] = payload.new_api_key
            airouter_key_manager._save_keys_to_file()
        except Exception as update_err:
            raise HTTPException(status_code=500, detail=f"Failed to update AIRouter API key: {update_err}")
        return JSONResponse(content={"status": "success", "message": "AIRouter API ключ обновлён."})
    except Exception as e:
        print(f"Error updating AIRouter API key via API: {e}")
        raise HTTPException(status_code=500, detail="Could not update AIRouter API key.")

@router.delete("/airouter", name="ui_api_delete_airouter_key")
async def ui_api_delete_airouter_key(
    payload: AirouterApiKeyPayload, 
    request: Request,
    username: str = Depends(get_current_username)
):
    airouter_key_manager = request.app.state.airouter_key_manager
    try:
        if not airouter_key_manager.remove_key(payload.api_key):
            raise HTTPException(status_code=404, detail=f"AIRouter API key '{payload.api_key}' not found.")
        return JSONResponse(content={"status": "success", "message": f"AIRouter API key '{payload.api_key}' removed."})
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting AIRouter API key via API: {e}")
        raise HTTPException(status_code=500, detail=f"Could not delete AIRouter API key '{payload.api_key}'.")
