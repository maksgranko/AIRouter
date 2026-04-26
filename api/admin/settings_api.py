import json
from typing import Union, Dict, Any
import os
import logging
import re
import subprocess
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from typing import List
from utils.config_store import read_json, write_json, update_json

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

            def _mutate_force_rotation(settings_data):
                if not isinstance(settings_data, dict):
                    settings_data = {}
                settings_data.setdefault("proxy_settings", {})["force_proxy_rotation_after_request"] = payload.value
                return settings_data

            update_json(settings_file_path, {}, _mutate_force_rotation, ensure_ascii=False)
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
        logger.exception("Error updating proxy setting via API")
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
        def _mutate_module_proxy(settings_data):
            if not isinstance(settings_data, dict):
                settings_data = {}
            settings_data.setdefault("module_proxy_usage", {})
            settings_data["module_proxy_usage"][module_name] = payload.use_global_proxy
            return settings_data

        update_json(settings_file_path, {}, _mutate_module_proxy, ensure_ascii=False)
        return JSONResponse(content={"status": "success", "message": f"use_global_proxy for module '{module_name}' set to {payload.use_global_proxy}."})
    except Exception as e:
        logger.exception("Error updating module proxy setting via API for %s", module_name)
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
        logger.exception("Error updating module status via API for %s", module_name)
        raise HTTPException(status_code=500, detail=f"Could not update status for module '{module_name}'.")

@router.put("/airouter-security", name="ui_api_update_airouter_security") # Имя маршрута можно оставить
async def ui_api_update_airouter_security(
    payload: AirouterSecurityPayload,
    request: Request,
    username: str = Depends(get_current_username)
):
    settings_file_path = request.app.state.settings_file_path
    try:
        def _mutate_airouter_security(settings_data):
            if not isinstance(settings_data, dict):
                settings_data = {}
            settings_data["require_airouter_api_key"] = payload.require_api_key
            return settings_data

        update_json(settings_file_path, {}, _mutate_airouter_security, ensure_ascii=False)
        # После изменения настройки, нужно перезагрузить конфигурацию в ModuleRegistry, если это влияет на загрузку модулей
        # или другие аспекты приложения. В данном случае, это может не требоваться немедленно.
        return JSONResponse(content={"status": "success", "message": f"AIRouter API key requirement set to {payload.require_api_key}."})
    except Exception as e:
        logger.exception("Error updating AIRouter API key requirement via API")
        raise HTTPException(status_code=500, detail="Could not update AIRouter API key requirement settings.")

# --- OpenAI Compatible Instances Management ---
OPENAI_INSTANCES_CONFIG_PATH = "configs/openai_instances.json" # Определим путь к файлу

def _load_openai_instances() -> list:
    data = read_json(OPENAI_INSTANCES_CONFIG_PATH, [])
    return data if isinstance(data, list) else []


def _save_openai_instances(instances: list):
    write_json(OPENAI_INSTANCES_CONFIG_PATH, instances, ensure_ascii=False)
    # TODO: После сохранения нужно уведомить ModuleRegistry о необходимости перезагрузки OpenAICompatModule
    # или динамически обновить его конфигурацию, если это поддерживается.

class OpenAIInstanceMetaUpdatePayload(BaseModel):
    name: str = None
    base_url: str = None
    failsafe_providers: List[str] = None
    use_global_proxy: bool = None
    use_custom_tokenizer: bool = None
    model_aliases: Dict[str, Any] = None
    model_redirects: Dict[str, Any] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str):
        if value is None:
            return value
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", value):
            raise ValueError("Instance name may contain only A-Z, a-z, 0-9, dot, underscore, hyphen (1-64 chars).")
        return value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str):
        if value is None:
            return value
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return value

    @field_validator("failsafe_providers")
    @classmethod
    def validate_failsafe_providers(cls, value: List[str]):
        if value is None:
            return value
        if len(value) != len(set(value)):
            raise ValueError("failsafe_providers must not contain duplicates")
        for name in value:
            if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", name):
                raise ValueError("failsafe_providers contains invalid instance name")
        return value

    @field_validator("model_aliases", "model_redirects")
    @classmethod
    def validate_model_mappings(cls, value: Dict[str, Any]):
        if value is None:
            return value
        if not isinstance(value, dict):
            raise ValueError("Model mapping must be an object")
        cleaned = {}
        for k, v in value.items():
            key = str(k).strip()
            if not key:
                raise ValueError("Model mapping key must not be empty")
            if isinstance(v, str):
                target = v.strip()
                if not target:
                    raise ValueError("Model mapping value must not be empty")
                cleaned[key] = target
                continue
            if isinstance(v, list):
                normalized_targets = []
                for item in v:
                    if not isinstance(item, str) or not item.strip():
                        raise ValueError("Model mapping list values must be non-empty strings")
                    normalized_targets.append(item.strip())
                if not normalized_targets:
                    raise ValueError("Model mapping list must not be empty")
                cleaned[key] = normalized_targets
                continue
            raise ValueError("Model mapping value must be string or list of strings")
        return cleaned
class OpenAIInstanceKeyPayload(BaseModel):
    api_key: str

class UpdateOpenAIInstanceKeyPayload(BaseModel):
    old_api_key: str
    new_api_key: str
class OpenAIInstancePayload(BaseModel):
    name: str
    base_url: str
    api_keys: List[str] = Field(default_factory=list)
    model_aliases: Dict[str, Any] = Field(default_factory=dict)
    model_redirects: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str):
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", value):
            raise ValueError("Instance name may contain only A-Z, a-z, 0-9, dot, underscore, hyphen (1-64 chars).")
        return value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str):
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return value

    @field_validator("model_aliases", "model_redirects")
    @classmethod
    def validate_model_mappings(cls, value: Dict[str, Any]):
        if not isinstance(value, dict):
            raise ValueError("Model mapping must be an object")
        cleaned = {}
        for k, v in value.items():
            key = str(k).strip()
            if not key:
                raise ValueError("Model mapping key must not be empty")
            if isinstance(v, str):
                target = v.strip()
                if not target:
                    raise ValueError("Model mapping value must not be empty")
                cleaned[key] = target
                continue
            if isinstance(v, list):
                normalized_targets = []
                for item in v:
                    if not isinstance(item, str) or not item.strip():
                        raise ValueError("Model mapping list values must be non-empty strings")
                    normalized_targets.append(item.strip())
                if not normalized_targets:
                    raise ValueError("Model mapping list must not be empty")
                cleaned[key] = normalized_targets
                continue
            raise ValueError("Model mapping value must be string or list of strings")
        return cleaned


class UpdateServiceKeyPayload(BaseModel):
    old_api_key: str
    new_api_key: str
class UpdateOpenAIInstanceEnabledPayload(BaseModel):
    enabled: bool


class HTTPSRenewPayload(BaseModel):
    force_renewal: bool = False


logger = logging.getLogger(__name__)


def _is_valid_instance_name(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9._-]{1,64}", value or ""))


def _validate_instance_name_or_400(instance_name: str):
    if not _is_valid_instance_name(instance_name):
        raise HTTPException(
            status_code=400,
            detail="Invalid instance name. Use only A-Z, a-z, 0-9, dot, underscore, hyphen (1-64 chars).",
        )


async def _reload_oaic_module_if_available(request: Request, instances: list):
    module_registry = request.app.state.module_registry
    if not hasattr(module_registry, "reload_module_config"):
        return False
    try:
        await module_registry.reload_module_config("OAIC", new_config=instances)
        return True
    except KeyError:
        logger.warning("OAIC module is not registered yet; skipping live reload.")
        return False
    except Exception as e:
        logger.warning(f"Could not reload OAIC module config: {e}")
        return False


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
    _validate_instance_name_or_400(instance_name)
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
    await _reload_oaic_module_if_available(request, instances)
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
    
    new_instance = {
        "name": payload.name,
        "base_url": payload.base_url,
        "api_keys": list({k for k in payload.api_keys if isinstance(k, str) and k.strip()}),
        "enabled": True,
        "use_global_proxy": True,
        "model_aliases": payload.model_aliases,
        "model_redirects": payload.model_redirects,
    }
    instances.append(new_instance)
    _save_openai_instances(instances)
    
    # Уведомляем ModuleRegistry о необходимости перезагрузки конфигурации
    await _reload_oaic_module_if_available(request, instances)

    return JSONResponse(content={"status": "success", "message": f"OpenAI Compatible instance '{payload.name}' added."})


@router.post("/reload-modules", name="ui_api_reload_modules")
async def ui_api_reload_modules(
    request: Request,
    username: str = Depends(get_current_username)
):
    reload_cb = getattr(request.app.state, "reload_runtime_modules", None)
    if not callable(reload_cb):
        raise HTTPException(status_code=500, detail="Runtime module reload is not available.")
    try:
        result = reload_cb()
        return JSONResponse(content={
            "status": "success",
            "message": "Modules were fully reloaded without process restart.",
            "details": result,
        })
    except Exception as e:
        logger.exception("Failed to reload runtime modules")
        raise HTTPException(status_code=500, detail=f"Failed to reload modules: {e}")


@router.post("/https/renew", name="ui_api_renew_https")
async def ui_api_renew_https(
    payload: HTTPSRenewPayload,
    username: str = Depends(get_current_username),
):
    certbot_cmd = ["certbot", "renew", "--non-interactive"]
    if payload.force_renewal:
        certbot_cmd.append("--force-renewal")

    try:
        result = subprocess.run(
            certbot_cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="certbot not found on server. Install certbot first.",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail="HTTPS renewal timed out. Check certbot and server logs.",
        )
    except Exception as e:
        logger.exception("Unexpected HTTPS renewal error")
        raise HTTPException(status_code=500, detail=f"HTTPS renewal failed: {e}")

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    if result.returncode != 0:
        detail = stderr or stdout or f"certbot exited with code {result.returncode}"
        raise HTTPException(status_code=500, detail=f"HTTPS renewal failed: {detail}")

    message = "HTTPS certificates checked/renewed successfully."
    if payload.force_renewal:
        message = "HTTPS certificates force-renewed successfully."

    return JSONResponse(
        content={
            "status": "success",
            "message": message,
            "stdout": stdout,
        }
    )

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
    _validate_instance_name_or_400(instance_name)
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
    if payload.failsafe_providers is not None:
        known_instances = {inst.get('name') for inst in instances}
        for prov in payload.failsafe_providers:
            if prov == instances[idx]['name']:
                raise HTTPException(status_code=400, detail="Instance cannot reference itself in failsafe_providers.")
            if prov not in known_instances:
                raise HTTPException(status_code=400, detail=f"Unknown failsafe provider '{prov}'.")
        instances[idx]['failsafe_providers'] = payload.failsafe_providers
        updated_fields['failsafe_providers'] = payload.failsafe_providers
    if payload.use_global_proxy is not None:
        instances[idx]['use_global_proxy'] = payload.use_global_proxy
        updated_fields['use_global_proxy'] = payload.use_global_proxy
    if payload.use_custom_tokenizer is not None:
        instances[idx]['use_custom_tokenizer'] = payload.use_custom_tokenizer
        updated_fields['use_custom_tokenizer'] = payload.use_custom_tokenizer
    if payload.model_aliases is not None:
        instances[idx]['model_aliases'] = payload.model_aliases
        updated_fields['model_aliases'] = payload.model_aliases
    if payload.model_redirects is not None:
        instances[idx]['model_redirects'] = payload.model_redirects
        updated_fields['model_redirects'] = payload.model_redirects

    _save_openai_instances(instances)
    # чтобы не потерялись ключи и остальные поля, reload
    await _reload_oaic_module_if_available(request, instances)
    return JSONResponse(content={
        "status": "success",
        "message": f"Instance '{instance_name}' updated.",
        "updated_fields": updated_fields
    })


@router.delete("/openai-instances/{instance_name}", name="ui_api_delete_openai_instance")
async def ui_api_delete_openai_instance(
    instance_name: str, 
    request: Request, 
    username: str = Depends(get_current_username)
):
    _validate_instance_name_or_400(instance_name)
    instances = _load_openai_instances()
    initial_len = len(instances)
    instances = [instance for instance in instances if instance['name'] != instance_name]
    if len(instances) == initial_len:
        raise HTTPException(status_code=404, detail=f"Instance '{instance_name}' not found.")
    _save_openai_instances(instances)

    await _reload_oaic_module_if_available(request, instances)

    return JSONResponse(content={"status": "success", "message": f"OpenAI Compatible instance '{instance_name}' deleted."})

@router.post("/openai-instances/{instance_name}/keys", name="ui_api_add_openai_instance_key")
async def ui_api_add_openai_instance_key(
    instance_name: str, 
    payload: OpenAIInstanceKeyPayload, 
    request: Request,
    username: str = Depends(get_current_username)
):
    _validate_instance_name_or_400(instance_name)
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

    await _reload_oaic_module_if_available(request, instances)
        
    return JSONResponse(content={"status": "success", "message": f"API key added to instance '{instance_name}'."})

@router.patch("/openai-instances/{instance_name}/keys", name="ui_api_patch_openai_instance_key")
async def ui_api_patch_openai_instance_key(
    instance_name: str, 
    payload: UpdateOpenAIInstanceKeyPayload, 
    request: Request,
    username: str = Depends(get_current_username)
):
    _validate_instance_name_or_400(instance_name)
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
    await _reload_oaic_module_if_available(request, instances)

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
    _validate_instance_name_or_400(instance_name)
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

    await _reload_oaic_module_if_available(request, instances)

    message = f"API key removed from instance '{instance_name}'." if key_found_and_removed else f"API key not found in instance '{instance_name}', no changes made."
    return JSONResponse(content={"status": "success", "message": message})
