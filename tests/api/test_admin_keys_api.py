import pytest


async def test_add_and_delete_service_key(async_client, admin_basic_auth_header):
    add_response = await async_client.post(
        "/api/admin/ui/keys/service/openai",
        json={"api_key": "sk-added"},
        headers=admin_basic_auth_header,
    )
    assert add_response.status_code == 200

    delete_response = await async_client.request(
        "DELETE",
        "/api/admin/ui/keys/service/openai",
        json={"api_key": "sk-added"},
        headers=admin_basic_auth_header,
    )
    assert delete_response.status_code == 200


async def test_generate_and_delete_airouter_key(async_client, admin_basic_auth_header):
    generate_response = await async_client.post(
        "/api/admin/ui/keys/airouter", headers=admin_basic_auth_header
    )
    assert generate_response.status_code == 200
    key = generate_response.json()["new_key"]
    assert key

    delete_response = await async_client.request(
        "DELETE",
        "/api/admin/ui/keys/airouter",
        json={"api_key": key},
        headers=admin_basic_auth_header,
    )
    assert delete_response.status_code == 200


@pytest.mark.xfail(reason="ApiKeyManager has no update_key method", strict=False)
async def test_patch_service_key(async_client, admin_basic_auth_header):
    await async_client.post(
        "/api/admin/ui/keys/service/openai",
        json={"api_key": "old-key"},
        headers=admin_basic_auth_header,
    )
    response = await async_client.patch(
        "/api/admin/ui/keys/service/openai/key",
        json={"old_api_key": "old-key", "new_api_key": "new-key"},
        headers=admin_basic_auth_header,
    )
    assert response.status_code == 200
