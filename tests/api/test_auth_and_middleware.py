import json


async def test_admin_requires_basic_auth(async_client):
    response = await async_client.get("/admin/dashboard")
    assert response.status_code == 401


async def test_admin_works_with_basic_auth(async_client, admin_basic_auth_header):
    response = await async_client.get("/api/admin/ui/dashboard-data", headers=admin_basic_auth_header)
    assert response.status_code == 200


async def test_v1_requires_bearer_when_enabled(async_client, update_settings):
    def mutator(data):
        data["require_airouter_api_key"] = True

    update_settings(mutator)

    response = await async_client.get("/v1/models")
    assert response.status_code == 401


async def test_v1_accepts_valid_bearer(async_client, update_settings):
    def mutator(data):
        data["require_airouter_api_key"] = True

    update_settings(mutator)

    response = await async_client.get(
        "/v1/models", headers={"Authorization": "Bearer air-test-key"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
