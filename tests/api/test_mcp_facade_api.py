async def test_mcp_facade_initialize(async_client):
    response = await async_client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["serverInfo"]["name"] == "AIRouter MCP Facade"


async def test_mcp_facade_tools_list_and_call(async_client, monkeypatch, app_module):
    mcp_manager = app_module.app.state.mcp_manager

    async def fake_list_all_tools():
        return [
            {
                "name": "weather.get",
                "description": "weather",
                "input_schema": {"type": "object", "properties": {}},
                "enabled": True,
                "mcp_server": "srv1",
                "source": "remote",
            }
        ]

    async def fake_call_tool(tool_name, arguments, preferred_server=None, audit_context=None):
        assert tool_name == "weather.get"
        return {"city": arguments.get("city"), "temp": 20}

    monkeypatch.setattr(mcp_manager, "list_all_tools", fake_list_all_tools)
    monkeypatch.setattr(mcp_manager, "call_tool", fake_call_tool)

    list_resp = await async_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["result"]["tools"][0]["name"] == "weather.get"

    call_resp = await async_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "weather.get", "arguments": {"city": "Paris"}},
        },
    )
    assert call_resp.status_code == 200
    assert call_resp.json()["result"]["city"] == "Paris"
