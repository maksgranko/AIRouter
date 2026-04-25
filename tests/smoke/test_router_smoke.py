async def test_core_endpoints_smoke(async_client, admin_basic_auth_header):
    admin = await async_client.get("/api/admin/ui/dashboard-data", headers=admin_basic_auth_header)
    assert admin.status_code == 200

    models = await async_client.get("/v1/models")
    assert models.status_code == 200
    assert models.json().get("object") == "list"
