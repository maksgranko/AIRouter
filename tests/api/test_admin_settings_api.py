import json
import sys


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


async def test_openai_instance_can_be_created_without_api_keys(async_client, admin_basic_auth_header):
    create_payload = {
        "name": "inst-empty-keys",
        "base_url": "https://provider.invalid/v1",
        "api_keys": [],
    }
    create_response = await async_client.post(
        "/api/admin/ui/settings/openai-instances",
        json=create_payload,
        headers=admin_basic_auth_header,
    )
    assert create_response.status_code == 200


async def test_openai_instance_accepts_aliases_and_redirects(async_client, admin_basic_auth_header):
    create_payload = {
        "name": "inst-mapping",
        "base_url": "https://provider.invalid/v1",
        "api_keys": [],
        "model_aliases": {"fast": "gpt-4o-mini"},
        "model_redirects": {"main": "inst-mapping/gpt-4.1"},
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
    found = next(item for item in list_response.json() if item["name"] == "inst-mapping")
    assert found["model_aliases"]["fast"] == "gpt-4o-mini"
    assert found["model_redirects"]["main"] == "inst-mapping/gpt-4.1"


async def test_openai_instance_accepts_redirect_list(async_client, admin_basic_auth_header):
    create_payload = {
        "name": "inst-route-list",
        "base_url": "https://provider.invalid/v1",
        "api_keys": [],
        "model_redirects": {
            "gemini-2.5": [
                "inst-route-list/google/gemini-2.5-exp",
                "backup-inst/google/gemini-2.5-pro",
            ]
        },
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
    found = next(item for item in list_response.json() if item["name"] == "inst-route-list")
    assert isinstance(found["model_redirects"]["gemini-2.5"], list)
    assert len(found["model_redirects"]["gemini-2.5"]) == 2


async def test_reload_modules_endpoint(async_client, admin_basic_auth_header):
    response = await async_client.post(
        "/api/admin/ui/settings/reload-modules",
        headers=admin_basic_auth_header,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert "details" in payload


async def test_https_renew_endpoint(async_client, admin_basic_auth_header, monkeypatch):
    settings_api = sys.modules["api.admin.settings_api"]

    class DummyResult:
        returncode = 0
        stdout = "No renewals were attempted."
        stderr = ""

    def fake_run(cmd, check, capture_output, text, timeout):
        assert cmd[:2] == ["certbot", "renew"]
        assert "--non-interactive" in cmd
        return DummyResult()

    monkeypatch.setattr(settings_api.subprocess, "run", fake_run)

    response = await async_client.post(
        "/api/admin/ui/settings/https/renew",
        json={"force_renewal": False},
        headers=admin_basic_auth_header,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
