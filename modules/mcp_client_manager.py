from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import json
import os
import shutil
import gzip
import traceback

import httpx

from utils.config_store import read_json, write_json


class MCPClientManager:
    def __init__(self, config_path: str, audit_log_path: Optional[str] = None, settings_file_path: Optional[str] = None):
        self.config_path = config_path
        self.audit_log_path = audit_log_path
        self.settings_file_path = settings_file_path

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

    def update_server(self, name: str, mutate_fn):
        servers = self.list_servers()
        for idx, server in enumerate(servers):
            if server.get("name") != name:
                continue
            updated = mutate_fn(dict(server))
            servers[idx] = updated
            self.save_servers(servers)
            return updated
        return None

    async def list_tools(self, server_name: str) -> List[Dict[str, Any]]:
        server = self.get_server(server_name)
        if not server or not server.get("enabled", True):
            return []
        payload = {"jsonrpc": "2.0", "id": "list-tools", "method": "tools/list", "params": {}}
        response = await self._post_jsonrpc(server, payload)
        result = response.get("result", {}) if isinstance(response, dict) else {}
        tools = result.get("tools", []) if isinstance(result, dict) else []
        tools = tools if isinstance(tools, list) else []
        return self._merge_tools_with_local_config(server, tools)

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

    async def list_all_resources(self) -> List[Dict[str, Any]]:
        resources: List[Dict[str, Any]] = []
        for server in self.list_servers():
            if not server.get("enabled", True):
                continue
            server_name = server.get("name")
            if not server_name:
                continue
            payload = {"jsonrpc": "2.0", "id": "list-resources", "method": "resources/list", "params": {}}
            try:
                response = await self._post_jsonrpc(server, payload)
                result = response.get("result", {}) if isinstance(response, dict) else {}
                rows = result.get("resources", []) if isinstance(result, dict) else []
                if isinstance(rows, list):
                    for item in rows:
                        if isinstance(item, dict):
                            merged = dict(item)
                            merged["mcp_server"] = server_name
                            resources.append(merged)
            except Exception:
                continue
        return resources

    async def list_all_prompts(self) -> List[Dict[str, Any]]:
        prompts: List[Dict[str, Any]] = []
        for server in self.list_servers():
            if not server.get("enabled", True):
                continue
            server_name = server.get("name")
            if not server_name:
                continue
            payload = {"jsonrpc": "2.0", "id": "list-prompts", "method": "prompts/list", "params": {}}
            try:
                response = await self._post_jsonrpc(server, payload)
                result = response.get("result", {}) if isinstance(response, dict) else {}
                rows = result.get("prompts", []) if isinstance(result, dict) else []
                if isinstance(rows, list):
                    for item in rows:
                        if isinstance(item, dict):
                            merged = dict(item)
                            merged["mcp_server"] = server_name
                            prompts.append(merged)
            except Exception:
                continue
        return prompts

    async def list_server_tools(self, server_name: str) -> List[Dict[str, Any]]:
        return await self.list_tools(server_name)

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        preferred_server: Optional[str] = None,
        audit_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        candidate_servers = []
        if preferred_server:
            srv = self.get_server(preferred_server)
            if srv and srv.get("enabled", True):
                candidate_servers.append(srv)
        if not candidate_servers:
            candidate_servers = [s for s in self.list_servers() if s.get("enabled", True)]

        last_error: Optional[str] = None
        for server in candidate_servers:
            if not self._is_tool_enabled_on_server(server, tool_name):
                continue
            custom_tool = self._get_custom_tool(server, tool_name)
            if custom_tool:
                result = self._execute_custom_tool(custom_tool, arguments or {})
                self._append_audit_event(
                    {
                        "tool": tool_name,
                        "server": server.get("name"),
                        "source": "custom",
                        "ok": True,
                        "context": audit_context or {},
                    }
                )
                return result
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
                    self._append_audit_event(
                        {
                            "tool": tool_name,
                            "server": server.get("name"),
                            "source": "remote",
                            "ok": True,
                            "context": audit_context or {},
                        }
                    )
                    return response["result"]
                if isinstance(response, dict) and "error" in response:
                    last_error = str(response["error"])
                    self._append_audit_event(
                        {
                            "tool": tool_name,
                            "server": server.get("name"),
                            "source": "remote",
                            "ok": False,
                            "error": last_error,
                            "context": audit_context or {},
                        }
                    )
                    continue
            except Exception as exc:
                last_error = str(exc)
                self._append_audit_event(
                    {
                        "tool": tool_name,
                        "server": server.get("name"),
                        "source": "remote",
                        "ok": False,
                        "error": last_error,
                        "traceback": traceback.format_exc(),
                        "context": audit_context or {},
                    }
                )
                continue
        self._append_audit_event(
            {
                "tool": tool_name,
                "server": preferred_server,
                "source": "unknown",
                "ok": False,
                "error": last_error,
                "context": audit_context or {},
            }
        )
        raise RuntimeError(last_error or f"MCP tool '{tool_name}' call failed on all servers")

    def set_tool_enabled(self, server_name: str, tool_name: str, enabled: bool) -> bool:
        def _mutate(server: Dict[str, Any]):
            disabled = list(server.get("disabled_tools", [])) if isinstance(server.get("disabled_tools", []), list) else []
            disabled_set = {str(x) for x in disabled}
            if enabled:
                disabled_set.discard(tool_name)
            else:
                disabled_set.add(tool_name)
            server["disabled_tools"] = sorted(disabled_set)
            return server

        updated = self.update_server(server_name, _mutate)
        return updated is not None

    def add_custom_tool(self, server_name: str, tool_payload: Dict[str, Any]) -> bool:
        def _mutate(server: Dict[str, Any]):
            custom = server.get("custom_tools", [])
            if not isinstance(custom, list):
                custom = []
            name = str(tool_payload.get("name", "")).strip()
            custom = [t for t in custom if isinstance(t, dict) and t.get("name") != name]
            custom.append(tool_payload)
            server["custom_tools"] = custom
            return server

        updated = self.update_server(server_name, _mutate)
        return updated is not None

    def delete_custom_tool(self, server_name: str, tool_name: str) -> bool:
        def _mutate(server: Dict[str, Any]):
            custom = server.get("custom_tools", [])
            if not isinstance(custom, list):
                custom = []
            server["custom_tools"] = [t for t in custom if not (isinstance(t, dict) and t.get("name") == tool_name)]
            return server

        updated = self.update_server(server_name, _mutate)
        return updated is not None

    def update_custom_tool(self, server_name: str, tool_name: str, patch: Dict[str, Any]) -> bool:
        found_ref = {"found": False}

        def _mutate(server: Dict[str, Any]):
            custom = server.get("custom_tools", [])
            if not isinstance(custom, list):
                custom = []
            updated = []
            for tool in custom:
                if not isinstance(tool, dict):
                    continue
                if tool.get("name") != tool_name:
                    updated.append(tool)
                    continue
                patched = dict(tool)
                patched.update(patch)
                patched["name"] = tool_name
                updated.append(patched)
                found_ref["found"] = True
            if not found_ref["found"]:
                return server
            server["custom_tools"] = updated
            return server

        updated = self.update_server(server_name, _mutate)
        return updated is not None and found_ref["found"]

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

    @staticmethod
    def _merge_tools_with_local_config(server: Dict[str, Any], remote_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        disabled = set(str(x) for x in server.get("disabled_tools", []) if isinstance(x, str))
        merged: List[Dict[str, Any]] = []
        for tool in remote_tools:
            if not isinstance(tool, dict):
                continue
            name = str(tool.get("name", "")).strip()
            if not name:
                continue
            item = dict(tool)
            item["enabled"] = name not in disabled
            item["source"] = "remote"
            merged.append(item)

        custom_tools = server.get("custom_tools", [])
        if isinstance(custom_tools, list):
            for tool in custom_tools:
                if not isinstance(tool, dict):
                    continue
                name = str(tool.get("name", "")).strip()
                if not name:
                    continue
                item = dict(tool)
                item.setdefault("description", "Custom tool")
                item.setdefault("input_schema", {"type": "object", "properties": {}})
                item["enabled"] = bool(item.get("enabled", True)) and name not in disabled
                item["source"] = "custom"
                merged.append(item)
        return merged

    @staticmethod
    def _is_tool_enabled_on_server(server: Dict[str, Any], tool_name: str) -> bool:
        disabled = set(str(x) for x in server.get("disabled_tools", []) if isinstance(x, str))
        if tool_name in disabled:
            return False
        custom = server.get("custom_tools", [])
        if isinstance(custom, list):
            for tool in custom:
                if isinstance(tool, dict) and tool.get("name") == tool_name:
                    return bool(tool.get("enabled", True))
        return True

    @staticmethod
    def _get_custom_tool(server: Dict[str, Any], tool_name: str) -> Optional[Dict[str, Any]]:
        custom = server.get("custom_tools", [])
        if not isinstance(custom, list):
            return None
        for tool in custom:
            if isinstance(tool, dict) and tool.get("name") == tool_name:
                return tool
        return None

    @staticmethod
    def _execute_custom_tool(tool: Dict[str, Any], arguments: Dict[str, Any]) -> Dict[str, Any]:
        behavior = str(tool.get("behavior", "echo"))
        if behavior == "static_json":
            output = tool.get("static_output", {})
            return output if isinstance(output, dict) else {"output": output}
        return {"echo": arguments}

    def _append_audit_event(self, payload: Dict[str, Any]) -> None:
        if not self.audit_log_path:
            return
        audit_cfg = self._get_audit_settings()
        if not audit_cfg.get("enabled", True):
            return

        retention_days = int(audit_cfg.get("retention_days", 7) or 0)
        gzip_enabled = bool(audit_cfg.get("gzip_enabled", True))

        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        try:
            base_dir = os.path.dirname(self.audit_log_path) or "."
            os.makedirs(base_dir, exist_ok=True)
            day_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            day_dir = os.path.join(base_dir, day_str)
            os.makedirs(day_dir, exist_ok=True)
            server_name = self._sanitize_module_name(str(payload.get("server") or "unknown")) or "unknown"
            daily_path = os.path.join(day_dir, f"mcp.{server_name}.log")
            with open(daily_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")

            self._maintain_audit_logs(base_dir, day_str, retention_days, gzip_enabled)
        except Exception:
            return

    def _get_audit_settings(self) -> Dict[str, Any]:
        defaults = {"enabled": True, "retention_days": 7, "gzip_enabled": True}
        if not self.settings_file_path:
            return defaults
        settings = read_json(self.settings_file_path, {})
        if not isinstance(settings, dict):
            return defaults
        cfg = settings if isinstance(settings, dict) else {}
        merged = dict(defaults)
        merged.update({k: cfg.get(k, merged[k]) for k in defaults.keys()})
        return merged

    @staticmethod
    def _maintain_audit_logs(base_dir: str, current_day: str, retention_days: int, gzip_enabled: bool) -> None:
        day_dirs: List[str] = []
        for name in os.listdir(base_dir):
            full = os.path.join(base_dir, name)
            if os.path.isdir(full) and MCPClientManager._is_day_string(name):
                day_dirs.append(name)

        if gzip_enabled:
            for day in day_dirs:
                if day == current_day:
                    continue
                day_path = os.path.join(base_dir, day)
                for filename in os.listdir(day_path):
                    if not filename.endswith(".log"):
                        continue
                    src = os.path.join(day_path, filename)
                    dst = src + ".gz"
                    if os.path.exists(dst):
                        continue
                    with open(src, "rb") as f_in, gzip.open(dst, "wb") as f_out:
                        f_out.writelines(f_in)
                    os.remove(src)

        # Retention policy
        if retention_days <= 0:
            for name in os.listdir(base_dir):
                full = os.path.join(base_dir, name)
                if os.path.isdir(full) and MCPClientManager._is_day_string(name):
                    shutil.rmtree(full, ignore_errors=True)
                elif name.endswith(".gzip") and MCPClientManager._is_day_string(name[:-5]):
                    try:
                        os.remove(full)
                    except Exception:
                        pass
            return

        keep_days = set(sorted(set(day_dirs), reverse=True)[:retention_days])
        for name in os.listdir(base_dir):
            full = os.path.join(base_dir, name)
            if os.path.isdir(full) and MCPClientManager._is_day_string(name) and name not in keep_days:
                shutil.rmtree(full, ignore_errors=True)

    @staticmethod
    def _is_day_string(value: str) -> bool:
        if len(value) != 10:
            return False
        if value[4] != "-" or value[7] != "-":
            return False
        y, m, d = value.split("-")
        return y.isdigit() and m.isdigit() and d.isdigit()

    @staticmethod
    def _sanitize_module_name(value: str) -> str:
        if not value:
            return ""
        safe = []
        for ch in value:
            if ch.isalnum() or ch in "._-":
                safe.append(ch)
            else:
                safe.append("_")
        normalized = "".join(safe).strip("._-")
        return normalized[:120]
