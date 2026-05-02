import json

import pytest

from modules.mcp_client_manager import MCPClientManager


@pytest.mark.asyncio
async def test_custom_tool_update_and_audit_log(tmp_path):
    config_path = tmp_path / "mcp_servers.json"
    audit_path = tmp_path / "mcp_audit.log"
    manager = MCPClientManager(str(config_path), audit_log_path=str(audit_path))

    manager.save_servers(
        [
            {
                "name": "srv",
                "base_url": "https://mcp.example.com",
                "jsonrpc_path": "/mcp",
                "enabled": True,
                "custom_tools": [
                    {"name": "custom.echo", "description": "d", "behavior": "echo", "enabled": True}
                ],
            }
        ]
    )

    assert manager.update_custom_tool("srv", "custom.echo", {"description": "edited"}) is True
    servers = manager.list_servers()
    assert servers[0]["custom_tools"][0]["description"] == "edited"

    result = await manager.call_tool("custom.echo", {"x": 1}, audit_context={"origin": "test"})
    assert result["echo"]["x"] == 1

    day_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert day_dirs
    mcp_log = day_dirs[0] / "mcp.log"
    assert mcp_log.exists()
    lines = mcp_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    event = json.loads(lines[-1])
    assert event["tool"] == "custom.echo"
    assert event["ok"] is True
    assert event["context"]["origin"] == "test"
