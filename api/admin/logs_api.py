import os
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from admin_router import get_current_username
from utils.config_store import update_json, read_json


router = APIRouter(
    prefix="/api/admin/ui/logs",
    tags=["logs_admin_ui_api"],
    dependencies=[Depends(get_current_username)],
)


class MCPAuditSettingsPayload(BaseModel):
    enabled: bool = True
    retention_days: int = Field(default=7, ge=0, le=3650)
    gzip_enabled: bool = True


class GlobalAuditSettingsPayload(BaseModel):
    enabled: bool = True
    retention_days: int = Field(default=7, ge=0, le=3650)
    gzip_enabled: bool = True


@router.get("/mcp-audit", name="ui_api_get_mcp_audit_settings")
async def ui_api_get_mcp_audit_settings(request: Request, username: str = Depends(get_current_username)):
    settings_path = request.app.state.mcp_audit_settings_file_path
    cfg = read_json(settings_path, {})
    if not isinstance(cfg, dict):
        cfg = {}
    return {
        "enabled": bool(cfg.get("enabled", True)),
        "retention_days": int(cfg.get("retention_days", 7) or 0),
        "gzip_enabled": bool(cfg.get("gzip_enabled", True)),
    }


@router.put("/mcp-audit", name="ui_api_update_mcp_audit_settings")
async def ui_api_update_mcp_audit_settings(
    payload: MCPAuditSettingsPayload,
    request: Request,
    username: str = Depends(get_current_username),
):
    def _mutate(data):
        if not isinstance(data, dict):
            data = {}
        data = payload.model_dump()
        return data

    try:
        update_json(request.app.state.mcp_audit_settings_file_path, {}, _mutate, ensure_ascii=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not update MCP audit settings: {e}")

    return {"status": "success", "message": "MCP audit settings updated", "settings": payload.model_dump()}


@router.get("/global-audit", name="ui_api_get_global_audit_settings")
async def ui_api_get_global_audit_settings(request: Request, username: str = Depends(get_current_username)):
    settings_path = request.app.state.global_audit_settings_file_path
    cfg = read_json(settings_path, {})
    if not isinstance(cfg, dict):
        cfg = {}
    return {
        "enabled": bool(cfg.get("enabled", True)),
        "retention_days": int(cfg.get("retention_days", 7) or 0),
        "gzip_enabled": bool(cfg.get("gzip_enabled", True)),
    }


@router.put("/global-audit", name="ui_api_update_global_audit_settings")
async def ui_api_update_global_audit_settings(
    payload: GlobalAuditSettingsPayload,
    request: Request,
    username: str = Depends(get_current_username),
):
    def _mutate(data):
        if not isinstance(data, dict):
            data = {}
        data = payload.model_dump()
        return data

    try:
        update_json(request.app.state.global_audit_settings_file_path, {}, _mutate, ensure_ascii=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not update global audit settings: {e}")

    return {"status": "success", "message": "Global audit settings updated", "settings": payload.model_dump()}


@router.get("/files", name="ui_api_list_log_files")
async def ui_api_list_log_files(request: Request, username: str = Depends(get_current_username)):
    logs_dir = request.app.state.logs_dir
    os.makedirs(logs_dir, exist_ok=True)
    items = []
    for name in sorted(os.listdir(logs_dir), reverse=True):
        full = os.path.join(logs_dir, name)
        if not os.path.isdir(full):
            continue
        if not all(ch.isdigit() or ch == "-" for ch in name):
            continue
        files = []
        size = 0
        for child in sorted(os.listdir(full)):
            child_full = os.path.join(full, child)
            if not os.path.isfile(child_full):
                continue
            child_size = os.path.getsize(child_full)
            size += child_size
            files.append({"name": child, "size": child_size})
        items.append({"name": name, "is_dir": True, "size": size, "files": files})
    return {"logs": items}


@router.get("/files/{name}", name="ui_api_download_log_file")
async def ui_api_download_log_file(name: str, request: Request, username: str = Depends(get_current_username)):
    logs_dir = request.app.state.logs_dir
    safe_name = os.path.basename(name)
    full = os.path.join(logs_dir, safe_name)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="Log file not found")
    return FileResponse(full, filename=safe_name)


@router.get("/files/{day}/{filename}", name="ui_api_download_log_file_in_day")
async def ui_api_download_log_file_in_day(day: str, filename: str, request: Request, username: str = Depends(get_current_username)):
    logs_dir = request.app.state.logs_dir
    safe_day = os.path.basename(day)
    safe_filename = os.path.basename(filename)
    full = os.path.join(logs_dir, safe_day, safe_filename)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="Log file not found")
    return FileResponse(full, filename=f"{safe_day}-{safe_filename}")


@router.delete("/files/{name}", name="ui_api_delete_log_file")
async def ui_api_delete_log_file(name: str, request: Request, username: str = Depends(get_current_username)):
    logs_dir = request.app.state.logs_dir
    safe_name = os.path.basename(name)
    full = os.path.join(logs_dir, safe_name)
    if os.path.isdir(full):
        for child in os.listdir(full):
            child_full = os.path.join(full, child)
            if os.path.isfile(child_full):
                os.remove(child_full)
        os.rmdir(full)
        return {"status": "success", "message": f"Deleted directory '{safe_name}'"}
    if os.path.isfile(full):
        os.remove(full)
        return {"status": "success", "message": f"Deleted file '{safe_name}'"}
    raise HTTPException(status_code=404, detail="Log entry not found")


@router.delete("/files/{day}/{filename}", name="ui_api_delete_log_file_in_day")
async def ui_api_delete_log_file_in_day(day: str, filename: str, request: Request, username: str = Depends(get_current_username)):
    logs_dir = request.app.state.logs_dir
    safe_day = os.path.basename(day)
    safe_filename = os.path.basename(filename)
    full = os.path.join(logs_dir, safe_day, safe_filename)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="Log file not found")
    os.remove(full)
    return {"status": "success", "message": f"Deleted file '{safe_day}/{safe_filename}'"}
