import json
from typing import Union
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List

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
        # После изменения настройки, нужно перезагрузить конфигурацию в ModuleRegistry, если это влияет на загрузку модулей
        # или другие аспекты приложения. В данном случае, это может не требоваться немедленно.
        return JSONResponse(content={"status": "success", "message": f"AIRouter API key requirement set to {payload.require_api_key}."})
    except Exception as e:
        print(f"Error updating AIRouter API key requirement via API: {e}")
        raise HTTPException(status_code=500, detail="Could not update AIRouter API key requirement settings.")

# --- OpenAI Compatible Instances Management ---
OPENAI_INSTANCES_CONFIG_PATH = "configs/openai_instances.json" # Определим путь к файлу

def _load_openai_instances() -> list:
    try:
        with open(OPENAI_INSTANCES_CONFIG_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        # Если файл существует, но пуст или содержит невалидный JSON
        return []


def _save_openai_instances(instances: list):
    with open(OPENAI_INSTANCES_CONFIG_PATH, 'w') as f:
        json.dump(instances, f, indent=2)
    # TODO: После сохранения нужно уведомить ModuleRegistry о необходимости перезагрузки OpenAICompatModule
    # или динамически обновить его конфигурацию, если это поддерживается.

class OpenAIInstancePayload(BaseModel):
    name: str
    base_url: str
    api_keys: List[str]

class OpenAIInstanceKeyPayload(BaseModel):
    api_key: str


@router.get("/openai-instances", name="ui_api_get_openai_instances")
async def ui_api_get_openai_instances(username: str = Depends(get_current_username)):
    return _load_openai_instances()

@router.post("/openai-instances", name="ui_api_add_openai_instance")
async def ui_api_add_openai_instance(
    payload: OpenAIInstancePayload, 
    request: Request, 
    username: str = Depends(get_current_username)
):
    instances = _load_openai_instances()
    if any(instance['name'] == payload.name for instance in instances):
        raise HTTPException(status_code=400, detail=f"Instance with name '{payload.name}' already exists.")
    
    # Валидация URL (простая)
    if not payload.base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid base_url format. Must start with http:// or https://")

    new_instance = {
        "name": payload.name,
        "base_url": payload.base_url,
        "api_keys": list(set(payload.api_keys)) # Удаляем дубликаты ключей
    }
    instances.append(new_instance)
    _save_openai_instances(instances)
    
    # Уведомляем ModuleRegistry о необходимости перезагрузки конфигурации
    module_registry = request.app.state.module_registry
    if hasattr(module_registry, 'reload_module_config'):
        await module_registry.reload_module_config("OAIC", new_config=instances) # Предполагаем такой метод

    return JSONResponse(content={"status": "success", "message": f"OpenAI Compatible instance '{payload.name}' added."})

@router.delete("/openai-instances/{instance_name}", name="ui_api_delete_openai_instance")
async def ui_api_delete_openai_instance(
    instance_name: str, 
    request: Request, 
    username: str = Depends(get_current_username)
):
    instances = _load_openai_instances()
    initial_len = len(instances)
    instances = [instance for instance in instances if instance['name'] != instance_name]
    if len(instances) == initial_len:
        raise HTTPException(status_code=404, detail=f"Instance '{instance_name}' not found.")
    _save_openai_instances(instances)

    module_registry = request.app.state.module_registry
    if hasattr(module_registry, 'reload_module_config'):
        await module_registry.reload_module_config("OAIC", new_config=instances)

    return JSONResponse(content={"status": "success", "message": f"OpenAI Compatible instance '{instance_name}' deleted."})

@router.post("/openai-instances/{instance_name}/keys", name="ui_api_add_openai_instance_key")
async def ui_api_add_openai_instance_key(
    instance_name: str, 
    payload: OpenAIInstanceKeyPayload, 
    request: Request,
    username: str = Depends(get_current_username)
):
    instances = _load_openai_instances()
    instance_found = False
    for instance in instances:
        if instance['name'] == instance_name:
            instance_found = True
            if payload.api_key not in instance['api_keys']:
                instance['api_keys'].append(payload.api_key)
            else:
                raise HTTPException(status_code=400, detail=f"API key already exists for instance '{instance_name}'.")
            break
    if not instance_found:
        raise HTTPException(status_code=404, detail=f"Instance '{instance_name}' not found.")
    _save_openai_instances(instances)

    module_registry = request.app.state.module_registry
    if hasattr(module_registry, 'reload_module_config'):
        await module_registry.reload_module_config("OAIC", new_config=instances)
        
    return JSONResponse(content={"status": "success", "message": f"API key added to instance '{instance_name}'."})

@router.delete("/openai-instances/{instance_name}/keys", name="ui_api_delete_openai_instance_key")
async def ui_api_delete_openai_instance_key(
    instance_name: str, 
    payload: OpenAIInstanceKeyPayload, 
    request: Request,
    username: str = Depends(get_current_username)
):
    instances = _load_openai_instances()
    instance_found = False
    key_found_and_removed = False
    for instance in instances:
        if instance['name'] == instance_name:
            instance_found = True
            if payload.api_key in instance['api_keys']:
                instance['api_keys'].remove(payload.api_key)
                key_found_and_removed = True
            else:
                # Если ключ не найден, это не обязательно ошибка, можно просто вернуть успех
                pass 
            break
    if not instance_found:
        raise HTTPException(status_code=404, detail=f"Instance '{instance_name}' not found.")
    
    _save_openai_instances(instances)

    module_registry = request.app.state.module_registry
    if hasattr(module_registry, 'reload_module_config'):
        await module_registry.reload_module_config("OAIC", new_config=instances)

    message = f"API key removed from instance '{instance_name}'." if key_found_and_removed else f"API key not found in instance '{instance_name}', no changes made."
    return JSONResponse(content={"status": "success", "message": message})
