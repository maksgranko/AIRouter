from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from admin_router import get_current_username


router = APIRouter(
    prefix="/api/admin/ui/mcp",
    tags=["mcp_admin_ui_api"],
    dependencies=[Depends(get_current_username)],
)


class MCPServerPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    base_url: str = Field(..., min_length=1)
    jsonrpc_path: str = "/mcp"
    auth_token: Optional[str] = ""
    timeout_seconds: float = 20
    enabled: bool = True
    expose_policy: str = "internal_only"

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str):
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return value


class MCPServerPatchPayload(BaseModel):
    base_url: Optional[str] = None
    jsonrpc_path: Optional[str] = None
    auth_token: Optional[str] = None
    timeout_seconds: Optional[float] = None
    enabled: Optional[bool] = None
    expose_policy: Optional[str] = None


@router.get("/servers", name="ui_api_get_mcp_servers")
async def ui_api_get_mcp_servers(request: Request, username: str = Depends(get_current_username)):
    mcp_manager = request.app.state.mcp_manager
    return mcp_manager.list_servers()


@router.post("/servers", name="ui_api_add_mcp_server")
async def ui_api_add_mcp_server(payload: MCPServerPayload, request: Request, username: str = Depends(get_current_username)):
    mcp_manager = request.app.state.mcp_manager
    servers = mcp_manager.list_servers()
    if any(s.get("name") == payload.name for s in servers):
        raise HTTPException(status_code=409, detail=f"MCP server '{payload.name}' already exists")
    servers.append(payload.model_dump())
    mcp_manager.save_servers(servers)
    return {"status": "success", "message": f"MCP server '{payload.name}' added"}


@router.patch("/servers/{server_name}", name="ui_api_patch_mcp_server")
async def ui_api_patch_mcp_server(server_name: str, payload: MCPServerPatchPayload, request: Request, username: str = Depends(get_current_username)):
    mcp_manager = request.app.state.mcp_manager
    servers = mcp_manager.list_servers()
    for idx, server in enumerate(servers):
        if server.get("name") != server_name:
            continue
        patch = payload.model_dump(exclude_none=True)
        server.update(patch)
        servers[idx] = server
        mcp_manager.save_servers(servers)
        return {"status": "success", "message": f"MCP server '{server_name}' updated"}
    raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")


@router.delete("/servers/{server_name}", name="ui_api_delete_mcp_server")
async def ui_api_delete_mcp_server(server_name: str, request: Request, username: str = Depends(get_current_username)):
    mcp_manager = request.app.state.mcp_manager
    servers = mcp_manager.list_servers()
    kept = [s for s in servers if s.get("name") != server_name]
    if len(kept) == len(servers):
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")
    mcp_manager.save_servers(kept)
    return {"status": "success", "message": f"MCP server '{server_name}' deleted"}


@router.post("/servers/{server_name}/test", name="ui_api_test_mcp_server")
async def ui_api_test_mcp_server(server_name: str, request: Request, username: str = Depends(get_current_username)):
    mcp_manager = request.app.state.mcp_manager
    result = await mcp_manager.test_server(server_name)
    return result


@router.get("/tools", name="ui_api_list_mcp_tools")
async def ui_api_list_mcp_tools(request: Request, username: str = Depends(get_current_username)):
    mcp_manager = request.app.state.mcp_manager
    tools = await mcp_manager.list_all_tools()
    return {"tools": tools}
