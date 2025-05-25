import json
from typing import Union
import os
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List

from admin_router import get_current_username, \
    ProxySettingName, UpdateProxySettingPayload, ModuleStatusPayload, AirouterSecurityPayload

class UpdateModuleProxyUsagePayload(BaseModel):
    use_global_proxy: bool

router = APIRouter(
    prefix="/api/admin/ui/settings",
    tags=["settings_admin_ui_api"], 
    dependencies=[Depends(get_current_username)]
)

@router.put("/proxy", name="ui_api_update_proxy_settings")
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

@router.put("/module/{module_name}/proxy-settings", name="ui_api_update_module_proxy_settings")
async def ui_api_update_module_proxy_settings(
    module_name: str,
    payload: UpdateModuleProxyUsagePayload,
    request: Request,
    username: str = Depends(get_current_username)
):
    """
    Изменяет использование глобального прокси для модуля, кроме OAIC.
    """
    if module_name == "OAIC":
        raise HTTPException(status_code=400, detail="Individual proxy settings for OAIC are managed via instancе management, not per-module.")

    settings_file_path = request.app.state.settings_file_path
    try:
        with open(settings_file_path, "r+") as f:
            settings_data = json.load(f)
            settings_data.setdefault("module_proxy_usage", {})
            settings_data["module_proxy_usage"][module_name] = payload.use_global_proxy
            f.seek(0)
            json.dump(settings_data, f, indent=2)
            f.truncate()
        return JSONResponse(content={"status": "success", "message": f"use_global_proxy for module '{module_name}' set to {payload.use_global_proxy}."})
    except Exception as e:
        print(f"Error updating module proxy setting via API for {module_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Could not update use_global_proxy for module '{module_name}'.")


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

class UpdateOpenAIInstanceProxyPayload(BaseModel):
    use_global_proxy: bool

class UpdateOpenAIInstanceCustomTokenizerPayload(BaseModel):
    use_custom_tokenizer: bool = None

class OpenAIInstanceMetaUpdatePayload(BaseModel):
    name: str = None
    base_url: str = None

class OpenAIInstancePayload(BaseModel):
    name: str
    base_url: str
    api_keys: List[str]

class UpdateOpenAIInstanceKeyPayload(BaseModel):
    old_api_key: str
    new_api_key: str

class UpdateServiceKeyPayload(BaseModel):
    old_api_key: str
    new_api_key: str
class OpenAIInstanceKeyPayload(BaseModel):
    api_key: str

class UpdateOpenAIInstanceEnabledPayload(BaseModel):
    enabled: bool

@router.put("/openai-instances/{instance_name}/custom-tokenizer", name="ui_api_update_openai_instance_custom_tokenizer")
async def ui_api_update_openai_instance_custom_tokenizer(
    instance_name: str,
    payload: UpdateOpenAIInstanceCustomTokenizerPayload,
    request: Request,
    username: str = Depends(get_current_username)
):
    """
    Обновляет поле use_custom_tokenizer у конкретного OpenAI-compatible инстанса.
    """
    instances = _load_openai_instances()
    found = False
    for instance in instances:
        if instance["name"] == instance_name:
            instance["use_custom_tokenizer"] = payload.use_custom_tokenizer
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail=f"Instance '{instance_name}' not found.")

    _save_openai_instances(instances)
    # Чтобы настройки применились без перезагрузки:
    module_registry = request.app.state.module_registry
    if hasattr(module_registry, 'reload_module_config'):
        await module_registry.reload_module_config("OAIC", new_config=instances)
    return JSONResponse(content={
        "status": "success",
        "message": f"use_custom_tokenizer for instance '{instance_name}' set to {payload.use_custom_tokenizer}."
    })

@router.patch("/openai-instances/{instance_name}/enabled", name="ui_api_patch_openai_instance_enabled")
async def ui_api_patch_openai_instance_enabled(
    instance_name: str,
    payload: UpdateOpenAIInstanceEnabledPayload,
    request: Request,
    username: str = Depends(get_current_username)
):
    """
    Обновляет статус enabled для указанного инстанса.
    """
    instances = _load_openai_instances()
    found = False
    for instance in instances:
        if instance["name"] == instance_name:
            instance["enabled"] = payload.enabled
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail=f"Instance '{instance_name}' not found.")

    _save_openai_instances(instances)
    module_registry = request.app.state.module_registry
    if hasattr(module_registry, "reload_module_config"):
        await module_registry.reload_module_config("OAIC", new_config=instances)
    return JSONResponse(
        content={
            "status": "success",
            "message": f"Instance '{instance_name}' set to enabled={payload.enabled}."
        }
    )


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
        "api_keys": list(set(payload.api_keys)), # Удаляем дубликаты ключей
        "enabled": True,
        "use_global_proxy": True
    }
    instances.append(new_instance)
    _save_openai_instances(instances)
    
    # Уведомляем ModuleRegistry о необходимости перезагрузки конфигурации
    module_registry = request.app.state.module_registry
    if hasattr(module_registry, 'reload_module_config'):
        await module_registry.reload_module_config("OAIC", new_config=instances) # Предполагаем такой метод

    return JSONResponse(content={"status": "success", "message": f"OpenAI Compatible instance '{payload.name}' added."})

@router.patch("/openai-instances/{instance_name}/meta", name="ui_api_patch_openai_instance_meta")
async def ui_api_patch_openai_instance_meta(
    instance_name: str,
    payload: OpenAIInstanceMetaUpdatePayload,
    request: Request,
    username: str = Depends(get_current_username)
):
    """
    Изменяет название и/или base_url у конкретного инстанса.
    """
    instances = _load_openai_instances()
    idx = None
    for i, inst in enumerate(instances):
        if inst['name'] == instance_name:
            idx = i
            break
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Instance '{instance_name}' not found.")

    # Проверим на дубликаты имени при переименовании
    if payload.name is not None and payload.name != instance_name:
        for inst in instances:
            if inst['name'] == payload.name:
                raise HTTPException(status_code=400, detail=f"Instance with name '{payload.name}' already exists.")

    updated_fields = {}
    if payload.name is not None:
        instances[idx]['name'] = payload.name
        updated_fields['name'] = payload.name
    if payload.base_url is not None:
        instances[idx]['base_url'] = payload.base_url
        updated_fields['base_url'] = payload.base_url

    _save_openai_instances(instances)
    # чтобы не потерялись ключи и остальные поля, reload
    module_registry = request.app.state.module_registry
    if hasattr(module_registry, 'reload_module_config'):
        await module_registry.reload_module_config("OAIC", new_config=instances)
    return JSONResponse(content={
        "status": "success",
        "message": f"Instance '{instance_name}' updated.",
        "updated_fields": updated_fields
    })

@router.put("/openai-instances/{instance_name}/proxy-settings", name="ui_api_update_openai_instance_proxy_settings")
async def ui_api_update_openai_instance_proxy_settings(
    instance_name: str,
    payload: UpdateOpenAIInstanceProxyPayload,
    request: Request,
    username: str = Depends(get_current_username)
):
    """
    Обновить поле use_global_proxy у конкретного openai-compatible инстанса.
    """
    instances = _load_openai_instances()
    found = False
    for instance in instances:
        if instance['name'] == instance_name:
            instance['use_global_proxy'] = payload.use_global_proxy
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail=f"Instance '{instance_name}' not found.")

    _save_openai_instances(instances)
    # Чтобы настройки применились без перезагрузки:
    module_registry = request.app.state.module_registry
    if hasattr(module_registry, 'reload_module_config'):
        await module_registry.reload_module_config("OAIC", new_config=instances)
    return JSONResponse(content={
        "status": "success",
        "message": f"use_global_proxy for instance '{instance_name}' set to {payload.use_global_proxy}."
    })

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

@router.patch("/openai-instances/{instance_name}/keys", name="ui_api_patch_openai_instance_key")
async def ui_api_patch_openai_instance_key(
    instance_name: str, 
    payload: UpdateOpenAIInstanceKeyPayload, 
    request: Request,
    username: str = Depends(get_current_username)
):
    instances = _load_openai_instances()
    instance_found = False
    updated = False
    for instance in instances:
        if instance['name'] == instance_name:
            instance_found = True
            keys = instance['api_keys']
            try:
                idx = keys.index(payload.old_api_key)
            except ValueError:
                raise HTTPException(status_code=404, detail="Old API key not found.")
            if payload.new_api_key in keys:
                raise HTTPException(status_code=400, detail="Этот ключ уже существует.")
            keys[idx] = payload.new_api_key
            updated = True
            break
    if not instance_found:
        raise HTTPException(status_code=404, detail=f"Instance '{instance_name}' not found.")
    if not updated:
        raise HTTPException(status_code=404, detail="API key not found or update failed.")

    _save_openai_instances(instances)
    module_registry = request.app.state.module_registry
    if hasattr(module_registry, 'reload_module_config'):
        await module_registry.reload_module_config("OAIC", new_config=instances)

    return JSONResponse(content={"status": "success", "message": "API-ключ обновлён для инстанса."})

@router.patch("/service-keys/{service_name}", name="ui_api_patch_service_key")
async def ui_api_patch_service_key(
    service_name: str,
    payload: UpdateServiceKeyPayload,
    request: Request,
    username: str = Depends(get_current_username)
):
    # Определяем путь к файлу по имени сервиса
    config_dir = os.path.join("configs")
    file_map = {
        "openai": os.path.join(config_dir, "openai_keys.json"),
        "gemini": os.path.join(config_dir, "gemini_keys.json"),
        "airouter": os.path.join(config_dir, "airouter_api_keys.json"),
    }
    if service_name not in file_map:
        raise HTTPException(status_code=404, detail="Unknown service.")
    file_path = file_map[service_name]

    # Читаем и обновляем ключ
    try:
        with open(file_path, "r+", encoding="utf-8") as f:
            keys = json.load(f)
            if not isinstance(keys, list):
                raise HTTPException(status_code=400, detail="Key file format error.")
            try:
                idx = keys.index(payload.old_api_key)
            except ValueError:
                raise HTTPException(status_code=404, detail="Old API key not found.")
            if payload.new_api_key in keys:
                raise HTTPException(status_code=400, detail="Этот ключ уже существует.")
            keys[idx] = payload.new_api_key
            f.seek(0)
            json.dump(keys, f, indent=2)
            f.truncate()
        return JSONResponse(content={"status": "success", "message": "API ключ обновлён."})
    except Exception as e:
        raise HTTPException(status_code=500, detail="Ошибка обновления ключа: " + str(e))

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
