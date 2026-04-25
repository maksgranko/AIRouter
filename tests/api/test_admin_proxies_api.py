import json


async def test_add_reload_shuffle_and_delete_proxy(
    async_client, admin_basic_auth_header, runtime_dir
):
    await async_client.put(
        "/api/admin/ui/settings/proxy",
        json={"setting_name": "use_proxies", "value": True},
        headers=admin_basic_auth_header,
    )

    add_response = await async_client.post(
        "/api/admin/ui/proxies",
        json={"type": "http", "url": "http://proxy.local:8080"},
        headers=admin_basic_auth_header,
    )
    assert add_response.status_code == 200

    reload_response = await async_client.post(
        "/api/admin/ui/proxies/reload", headers=admin_basic_auth_header
    )
    assert reload_response.status_code == 200

    shuffle_response = await async_client.post(
        "/api/admin/ui/proxies/shuffle", headers=admin_basic_auth_header
    )
    assert shuffle_response.status_code == 200

    delete_response = await async_client.request(
        "DELETE",
        "/api/admin/ui/proxies",
        json={"url": "http://proxy.local:8080"},
        headers=admin_basic_auth_header,
    )
    assert delete_response.status_code == 200

    proxies = json.loads((runtime_dir / "configs" / "proxies.json").read_text(encoding="utf-8"))
    assert proxies == []
