import json
from typing import Union
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse

# Импорты из корневой папки проекта (на один уровень выше)
from admin_router import get_current_username, \
    ProxySettingName, UpdateProxySettingPayload, ModuleStatusPayload, AirouterSecurityPayload

router = APIRouter(
    prefix="/api/admin/ui/settings", # Новый префикс
    tags=["settings_admin_ui_api"], 
    dependencies=[Depends(get_current_username)]
)

@router.put("/proxy", name="ui_api_update_proxy_settings") # Имя маршрута можно оставить
async def ui_api_update_proxy_settings(
    payload: UpdateProxySettingPayload,
    request: Request, 
    username: str = Depends(get_current_username)
):
    proxy_manager = request.app.state.proxy_manager
    settings_file_path = request.app.state.settings_file_path
    updated_setting = {}

    try:
        if payload.setting_name == ProxySettingName.USE_PROXIES:
            if not isinstance(payload.value, bool):
                raise HTTPException(status_code=400, detail="Invalid value type for use_proxies, boolean expected.")
            proxy_manager.set_use_proxies(payload.value)
            updated_setting = {"use_proxies": payload.value}
        elif payload.setting_name == ProxySettingName.ROTATION_MODE:
            if not isinstance(payload.value, str):
                raise HTTPException(status_code=400, detail="Invalid value type for rotation_mode, string expected.")
            proxy_manager.set_rotation_mode(payload.value)
            updated_setting = {"rotation_mode": payload.value}
        elif payload.setting_name == ProxySettingName.FORCE_PROXY_ROTATION:
            if not isinstance(payload.value, bool):
                raise HTTPException(status_code=400, detail="Invalid value type for force_proxy_rotation_after_request, boolean expected.")
            with open(settings_file_path, 'r+') as f:
                settings_data = json.load(f)
                settings_data.setdefault("proxy_settings", {})["force_proxy_rotation_after_request"] = payload.value
                f.seek(0)
                json.dump(settings_data, f, indent=2)
                f.truncate()
            updated_setting = {"force_proxy_rotation_after_request": payload.value}
        elif payload.setting_name == ProxySettingName.SELECT_RANDOM_PROXY:
            if not isinstance(payload.value, bool):
                raise HTTPException(status_code=400, detail="Invalid value type for select_random_proxy_each_request, boolean expected.")
            proxy_manager.set_select_random_proxy_each_request(payload.value)
            updated_setting = {"select_random_proxy_each_request": payload.value}
        else:
            raise HTTPException(status_code=400, detail="Invalid setting name for proxy.")
        
        return JSONResponse(content={"status": "success", "message": f"Proxy setting '{payload.setting_name.value}' updated.", "updated_setting": updated_setting})
    except HTTPException as e:
        raise e 
    except Exception as e:
        print(f"Error updating proxy setting via API: {e}")
        raise HTTPException(status_code=500, detail=f"Could not update proxy setting '{payload.setting_name.value}'.")

@router.put("/module/{module_name}", name="ui_api_update_module_status") # Имя маршрута можно оставить
async def ui_api_update_module_status(
    module_name: str,
    payload: ModuleStatusPayload,
    request: Request,
    username: str = Depends(get_current_username)
):
    module_registry = request.app.state.module_registry
    try:
        module_registry.set_module_active(module_name, payload.active)
        return JSONResponse(content={"status": "success", "message": f"Module '{module_name}' status updated to {payload.active}."})
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Module '{module_name}' not found.")
    except Exception as e:
        print(f"Error updating module status via API for {module_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Could not update status for module '{module_name}'.")

@router.put("/airouter-security", name="ui_api_update_airouter_security") # Имя маршрута можно оставить
async def ui_api_update_airouter_security(
    payload: AirouterSecurityPayload,
    request: Request,
    username: str = Depends(get_current_username)
):
    settings_file_path = request.app.state.settings_file_path
    try:
        with open(settings_file_path, 'r+') as f:
            settings_data = json.load(f)
            settings_data["require_airouter_api_key"] = payload.require_api_key
            f.seek(0)
            json.dump(settings_data, f, indent=2)
            f.truncate()
        return JSONResponse(content={"status": "success", "message": f"AIRouter API key requirement set to {payload.require_api_key}."})
    except Exception as e:
        print(f"Error updating AIRouter API key requirement via API: {e}")
        raise HTTPException(status_code=500, detail="Could not update AIRouter API key requirement settings.")
