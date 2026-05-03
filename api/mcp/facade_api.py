from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response


router = APIRouter(tags=["mcp_facade"])


def _jsonrpc_ok(result: Dict[str, Any], request_id: Any):
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_err(code: int, message: str, request_id: Any):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message, "data": {}}}


@router.post("/mcp")
async def mcp_facade_endpoint(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        return _jsonrpc_err(-32600, "Invalid Request", None)

    method = body.get("method")
    request_id = body.get("id")
    is_notification = request_id is None
    params = body.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    mcp_manager = getattr(request.app.state, "mcp_manager", None)
    if mcp_manager is None:
        return _jsonrpc_err(-32000, "MCP manager unavailable", request_id)

    try:
        if method == "initialize":
            result = _jsonrpc_ok(
                {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "AIRouter MCP Facade", "version": request.app.state.app_version},
                    "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                },
                request_id,
            )
            return Response(status_code=204) if is_notification else result

        if method == "tools/list":
            tools = await mcp_manager.list_all_tools()
            public_tools = []
            for tool in tools:
                if not isinstance(tool, dict):
                    continue
                if not tool.get("enabled", True):
                    continue
                public_tools.append(
                    {
                        "name": tool.get("name"),
                        "description": tool.get("description", ""),
                        "inputSchema": tool.get("input_schema", {"type": "object", "properties": {}}),
                        "mcp_server": tool.get("mcp_server"),
                        "source": tool.get("source", "remote"),
                    }
                )
            result = _jsonrpc_ok({"tools": public_tools}, request_id)
            return Response(status_code=204) if is_notification else result

        if method == "resources/list":
            resources = await mcp_manager.list_all_resources()
            result = _jsonrpc_ok({"resources": resources}, request_id)
            return Response(status_code=204) if is_notification else result

        if method == "prompts/list":
            prompts = await mcp_manager.list_all_prompts()
            result = _jsonrpc_ok({"prompts": prompts}, request_id)
            return Response(status_code=204) if is_notification else result

        if method == "tools/call":
            tool_name = str(params.get("name", "")).strip()
            if not tool_name:
                return _jsonrpc_err(-32602, "Missing tool name", request_id)
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                arguments = {"raw": arguments}
            preferred_server = params.get("server")
            client_host = request.client.host if request.client else "unknown"
            result = await mcp_manager.call_tool(
                tool_name,
                arguments,
                preferred_server=preferred_server,
                audit_context={"origin": "mcp.facade", "client": client_host},
            )
            payload_result = _jsonrpc_ok(result if isinstance(result, dict) else {"output": result}, request_id)
            return Response(status_code=204) if is_notification else payload_result

        return _jsonrpc_err(-32601, f"Method not found: {method}", request_id)
    except HTTPException as e:
        return _jsonrpc_err(-32000, str(e.detail), request_id)
    except Exception as e:
        return _jsonrpc_err(-32000, str(e), request_id)
