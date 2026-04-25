async def test_refresh_models_cache(async_client, admin_basic_auth_header):
    response = await async_client.post(
        "/api/admin/ui/models/refresh", headers=admin_basic_auth_header
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert "models" in body


async def test_reformat_settings_roundtrip(async_client, admin_basic_auth_header):
    set_response = await async_client.post(
        "/api/admin/ui/models/set_reformat_status",
        json={
            "model_id": "OAIC/inst1/gpt-4",
            "module_name": "inst1",
            "is_reformat_enabled": True,
        },
        headers=admin_basic_auth_header,
    )
    assert set_response.status_code == 200

    get_response = await async_client.get(
        "/api/admin/ui/models/get_reformat_settings", headers=admin_basic_auth_header
    )
    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload["status"] == "success"
    assert payload["settings"]["inst1"]["OAIC/inst1/gpt-4"] is True
