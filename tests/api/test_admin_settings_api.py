import json


async def test_update_proxy_setting(async_client, admin_basic_auth_header, runtime_dir):
    payload = {"setting_name": "use_proxies", "value": False}
    response = await async_client.put(
        "/api/admin/ui/settings/proxy", json=payload, headers=admin_basic_auth_header
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"

    settings = json.loads((runtime_dir / "configs" / "settings.json").read_text(encoding="utf-8"))
    assert settings["proxy_settings"]["use_proxies"] is False


async def test_toggle_airouter_security(async_client, admin_basic_auth_header, runtime_dir):
    response = await async_client.put(
        "/api/admin/ui/settings/airouter-security",
        json={"require_api_key": True},
        headers=admin_basic_auth_header,
    )
    assert response.status_code == 200

    settings = json.loads((runtime_dir / "configs" / "settings.json").read_text(encoding="utf-8"))
    assert settings["require_airouter_api_key"] is True


async def test_openai_instance_create_and_delete(async_client, admin_basic_auth_header):
    create_payload = {
        "name": "inst2",
        "base_url": "https://provider.invalid/v1",
        "api_keys": ["k1", "k2"],
    }
    create_response = await async_client.post(
        "/api/admin/ui/settings/openai-instances",
        json=create_payload,
        headers=admin_basic_auth_header,
    )
    assert create_response.status_code == 200

    list_response = await async_client.get(
        "/api/admin/ui/settings/openai-instances", headers=admin_basic_auth_header
    )
    assert list_response.status_code == 200
    names = [item["name"] for item in list_response.json()]
    assert "inst2" in names

    delete_response = await async_client.delete(
        "/api/admin/ui/settings/openai-instances/inst2", headers=admin_basic_auth_header
    )
    assert delete_response.status_code == 200
