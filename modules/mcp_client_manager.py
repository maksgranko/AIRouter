from typing import Any, Dict, List, Optional

import httpx

from utils.config_store import read_json, write_json


class MCPClientManager:
    def __init__(self, config_path: str):
        self.config_path = config_path

    def list_servers(self) -> List[Dict[str, Any]]:
        data = read_json(self.config_path, [])
        return data if isinstance(data, list) else []

    def save_servers(self, servers: List[Dict[str, Any]]) -> None:
        write_json(self.config_path, servers, ensure_ascii=False)

    def get_server(self, name: str) -> Optional[Dict[str, Any]]:
        for server in self.list_servers():
            if server.get("name") == name:
                return server
        return None

    async def list_tools(self, server_name: str) -> List[Dict[str, Any]]:
        server = self.get_server(server_name)
        if not server or not server.get("enabled", True):
            return []
        payload = {"jsonrpc": "2.0", "id": "list-tools", "method": "tools/list", "params": {}}
        response = await self._post_jsonrpc(server, payload)
        result = response.get("result", {}) if isinstance(response, dict) else {}
        tools = result.get("tools", []) if isinstance(result, dict) else []
        return tools if isinstance(tools, list) else []

    async def list_all_tools(self) -> List[Dict[str, Any]]:
        all_tools: List[Dict[str, Any]] = []
        for server in self.list_servers():
            if not server.get("enabled", True):
                continue
            name = server.get("name")
            if not name:
                continue
            tools = await self.list_tools(name)
            for tool in tools:
                if isinstance(tool, dict):
                    merged = dict(tool)
                    merged.setdefault("name", "unknown_tool")
                    merged["mcp_server"] = name
                    all_tools.append(merged)
        return all_tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], preferred_server: Optional[str] = None) -> Dict[str, Any]:
        candidate_servers = []
        if preferred_server:
            srv = self.get_server(preferred_server)
            if srv and srv.get("enabled", True):
                candidate_servers.append(srv)
        if not candidate_servers:
            candidate_servers = [s for s in self.list_servers() if s.get("enabled", True)]

        last_error: Optional[str] = None
        for server in candidate_servers:
            payload = {
                "jsonrpc": "2.0",
                "id": f"call-{tool_name}",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments or {},
                },
            }
            try:
                response = await self._post_jsonrpc(server, payload)
                if isinstance(response, dict) and "result" in response:
                    return response["result"]
                if isinstance(response, dict) and "error" in response:
                    last_error = str(response["error"])
                    continue
            except Exception as exc:
                last_error = str(exc)
                continue
        raise RuntimeError(last_error or f"MCP tool '{tool_name}' call failed on all servers")

    async def test_server(self, server_name: str) -> Dict[str, Any]:
        server = self.get_server(server_name)
        if not server:
            return {"ok": False, "error": "Server not found"}
        try:
            tools = await self.list_tools(server_name)
            return {"ok": True, "tools_count": len(tools)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def _post_jsonrpc(self, server: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        base_url = str(server.get("base_url", "")).rstrip("/")
        endpoint = str(server.get("jsonrpc_path", "/mcp")).strip()
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        target = f"{base_url}{endpoint}"
        timeout = float(server.get("timeout_seconds", 20))
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        token = (server.get("auth_token") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(target, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
