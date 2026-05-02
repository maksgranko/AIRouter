async def test_mcp_server_crud(async_client, admin_basic_auth_header):
    create_payload = {
        "name": "mcp-a",
        "base_url": "https://mcp.example.com",
        "jsonrpc_path": "/mcp",
        "auth_token": "",
        "timeout_seconds": 10,
        "enabled": True,
        "expose_policy": "internal_only",
    }
    create = await async_client.post(
        "/api/admin/ui/mcp/servers",
        json=create_payload,
        headers=admin_basic_auth_header,
    )
    assert create.status_code == 200

    listed = await async_client.get("/api/admin/ui/mcp/servers", headers=admin_basic_auth_header)
    assert listed.status_code == 200
    assert any(s["name"] == "mcp-a" for s in listed.json())

    patched = await async_client.patch(
        "/api/admin/ui/mcp/servers/mcp-a",
        json={"enabled": False},
        headers=admin_basic_auth_header,
    )
    assert patched.status_code == 200

    deleted = await async_client.delete(
        "/api/admin/ui/mcp/servers/mcp-a",
        headers=admin_basic_auth_header,
    )
    assert deleted.status_code == 200


async def test_mcp_server_test_endpoint(async_client, admin_basic_auth_header, monkeypatch, app_module):
    mcp_manager = app_module.app.state.mcp_manager
    mcp_manager.save_servers([
        {
            "name": "mcp-test",
            "base_url": "https://mcp.example.com",
            "jsonrpc_path": "/mcp",
            "enabled": True,
        }
    ])

    async def fake_test(name):
        assert name == "mcp-test"
        return {"ok": True, "tools_count": 3}

    monkeypatch.setattr(mcp_manager, "test_server", fake_test)

    response = await async_client.post(
        "/api/admin/ui/mcp/servers/mcp-test/test",
        headers=admin_basic_auth_header,
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


async def test_mcp_tool_toggle_and_custom_tool(async_client, admin_basic_auth_header, app_module):
    mcp_manager = app_module.app.state.mcp_manager
    mcp_manager.save_servers([
        {
            "name": "mcp-tools",
            "base_url": "https://mcp.example.com",
            "jsonrpc_path": "/mcp",
            "enabled": True,
            "disabled_tools": [],
            "custom_tools": [],
        }
    ])

    toggle_resp = await async_client.patch(
        "/api/admin/ui/mcp/servers/mcp-tools/tools/weather.get",
        json={"enabled": False},
        headers=admin_basic_auth_header,
    )
    assert toggle_resp.status_code == 200

    add_custom = await async_client.post(
        "/api/admin/ui/mcp/servers/mcp-tools/custom-tools",
        json={
            "name": "custom.echo",
            "description": "echo",
            "behavior": "echo",
            "input_schema": {"type": "object", "properties": {}},
            "static_output": {},
            "enabled": True,
        },
        headers=admin_basic_auth_header,
    )
    assert add_custom.status_code == 200

    patch_custom = await async_client.patch(
        "/api/admin/ui/mcp/servers/mcp-tools/custom-tools/custom.echo",
        json={"description": "edited", "behavior": "static_json", "static_output": {"ok": True}},
        headers=admin_basic_auth_header,
    )
    assert patch_custom.status_code == 200

    delete_custom = await async_client.delete(
        "/api/admin/ui/mcp/servers/mcp-tools/custom-tools/custom.echo",
        headers=admin_basic_auth_header,
    )
    assert delete_custom.status_code == 200
