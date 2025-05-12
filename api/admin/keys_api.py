from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse

# Импорты из корневой папки проекта (на один уровень выше)
from admin_router import get_current_username, \
    ServiceApiKeyPayload, AirouterApiKeyPayload

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
        key_manager.add_key(service_name, payload.api_key)
        return JSONResponse(content={"status": "success", "message": f"API key added for service '{service_name}'."})
    except Exception as e:
        print(f"Error adding service API key via API for {service_name}: {e}")
        if service_name not in key_manager.key_files:
            raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found.")
        raise HTTPException(status_code=500, detail=f"Could not add API key for service '{service_name}'.")

@router.delete("/service/{service_name}", name="ui_api_delete_service_key")
async def ui_api_delete_service_key(
    service_name: str,
    payload: ServiceApiKeyPayload, 
    request: Request,
    username: str = Depends(get_current_username)
):
    key_manager = request.app.state.key_manager
    try:
        if service_name not in key_manager.api_keys or payload.api_key not in key_manager.api_keys.get(service_name, []):
             pass 
        
        key_manager.remove_key(service_name, payload.api_key)
        return JSONResponse(content={"status": "success", "message": f"API key removed for service '{service_name}'."})
    except Exception as e:
        print(f"Error deleting service API key via API for {service_name}: {e}")
        if service_name not in key_manager.key_files: 
            raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found.")
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

@router.delete("/airouter", name="ui_api_delete_airouter_key")
async def ui_api_delete_airouter_key(
    payload: AirouterApiKeyPayload, 
    request: Request,
    username: str = Depends(get_current_username)
):
    airouter_key_manager = request.app.state.airouter_key_manager
    try:
        if not airouter_key_manager.key_exists(payload.api_key):
            pass
        
        airouter_key_manager.remove_key(payload.api_key)
        return JSONResponse(content={"status": "success", "message": f"AIRouter API key '{payload.api_key}' removed."})
    except Exception as e:
        print(f"Error deleting AIRouter API key via API: {e}")
        raise HTTPException(status_code=500, detail=f"Could not delete AIRouter API key '{payload.api_key}'.")
