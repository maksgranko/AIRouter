import importlib
import json
import os
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@pytest.fixture
def runtime_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "supersecret")
    monkeypatch.setenv("USE_PROXIES", "false")

    (tmp_path / "static").mkdir(parents=True, exist_ok=True)
    (tmp_path / "templates").mkdir(parents=True, exist_ok=True)

    (tmp_path / "templates" / "admin_dashboard.html").write_text("ok", encoding="utf-8")
    (tmp_path / "templates" / "admin_help.html").write_text("ok", encoding="utf-8")
    (tmp_path / "templates" / "admin_models.html").write_text("ok", encoding="utf-8")

    _write_json(
        tmp_path / "configs" / "settings.json",
        {
            "proxy_settings": {
                "use_proxies": False,
                "rotation_mode": "once",
                "force_proxy_rotation_after_request": False,
                "select_random_proxy_each_request": False,
            },
            "module_statuses": {"openai": True, "gemini": True, "OAIC": True},
            "require_airouter_api_key": False,
            "module_proxy_usage": {"openai": True, "gemini": True},
        },
    )
    _write_json(tmp_path / "configs" / "openai_keys.json", [])
    _write_json(tmp_path / "configs" / "gemini_keys.json", [])
    _write_json(tmp_path / "configs" / "airouter_api_keys.json", ["air-test-key"])
    _write_json(tmp_path / "configs" / "proxies.json", [])
    _write_json(
        tmp_path / "configs" / "openai_instances.json",
        [
            {
                "name": "inst1",
                "base_url": "https://example.invalid/v1",
                "api_keys": ["inst-key"],
                "use_global_proxy": False,
                "enabled": True,
                "failsafe_providers": [],
            }
        ],
    )

    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def app_module(runtime_dir):
    for module_name in ["main"]:
        if module_name in sys.modules:
            del sys.modules[module_name]

    main = importlib.import_module("main")
    return main


@pytest.fixture
async def async_client(app_module):
    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def admin_basic_auth_header():
    # admin:supersecret in base64
    return {"Authorization": "Basic YWRtaW46c3VwZXJzZWNyZXQ="}


@pytest.fixture
def settings_file(runtime_dir):
    return runtime_dir / "configs" / "settings.json"


@pytest.fixture
def update_settings(settings_file):
    def _update(mutator):
        current = json.loads(settings_file.read_text(encoding="utf-8"))
        mutator(current)
        settings_file.write_text(json.dumps(current, indent=2), encoding="utf-8")

    return _update
