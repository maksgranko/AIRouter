import pytest
from fastapi import HTTPException

from modules.openai_compat_module import OpenAICompatModule


class DummyProxyManager:
    active = False
    proxies = []
    current_rotation_mode = "once"
    select_random_proxy_each_request = False

    def get_proxy(self):
        return None

    def rotate_proxy(self):
        return None


def make_module():
    return OpenAICompatModule(
        instances_config=[
            {
                "name": "inst1",
                "base_url": "https://provider.invalid/v1",
                "api_keys": ["k1"],
                "enabled": True,
                "use_global_proxy": False,
            }
        ],
        proxy_manager=DummyProxyManager(),
        settings_file_path="configs/settings.json",
    )


def test_parse_instance_and_model_id():
    instance, model = OpenAICompatModule.parse_instance_and_model_id("OAIC/inst1/gpt-4")
    assert instance == "inst1"
    assert model == "gpt-4"

    instance2, model2 = OpenAICompatModule.parse_instance_and_model_id("openai_inst1/gpt-4")
    assert instance2 == "inst1"
    assert model2 == "gpt-4"


def test_resolve_model_alias_same_instance():
    module = OpenAICompatModule(
        instances_config=[
            {
                "name": "inst1",
                "base_url": "https://provider.invalid/v1",
                "api_keys": ["k1"],
                "enabled": True,
                "use_global_proxy": False,
                "model_aliases": {"chat-fast": "gpt-4o-mini"},
            }
        ],
        proxy_manager=DummyProxyManager(),
        settings_file_path="configs/settings.json",
    )

    resolved_instance, resolved_model = module._resolve_instance_and_model("inst1", "chat-fast")
    assert resolved_instance == "inst1"
    assert resolved_model == "gpt-4o-mini"


def test_resolve_model_redirect_cross_instance():
    module = OpenAICompatModule(
        instances_config=[
            {
                "name": "inst1",
                "base_url": "https://provider.invalid/v1",
                "api_keys": ["k1"],
                "enabled": True,
                "use_global_proxy": False,
                "model_redirects": {"chat-main": "inst2/gpt-4.1"},
            },
            {
                "name": "inst2",
                "base_url": "https://provider-2.invalid/v1",
                "api_keys": ["k2"],
                "enabled": True,
                "use_global_proxy": False,
            },
        ],
        proxy_manager=DummyProxyManager(),
        settings_file_path="configs/settings.json",
    )

    resolved_instance, resolved_model = module._resolve_instance_and_model("inst1", "chat-main")
    assert resolved_instance == "inst2"
    assert resolved_model == "gpt-4.1"


def test_resolve_model_mapping_cycle_raises_http_exception():
    module = OpenAICompatModule(
        instances_config=[
            {
                "name": "inst1",
                "base_url": "https://provider.invalid/v1",
                "api_keys": ["k1"],
                "enabled": True,
                "use_global_proxy": False,
                "model_aliases": {"a": "b", "b": "a"},
            }
        ],
        proxy_manager=DummyProxyManager(),
        settings_file_path="configs/settings.json",
    )

    with pytest.raises(HTTPException) as exc:
        module._resolve_instance_and_model("inst1", "a")
    assert "cycle" in str(exc.value).lower()


def test_resolve_model_redirect_list_returns_ordered_targets():
    module = OpenAICompatModule(
        instances_config=[
            {
                "name": "inst1",
                "base_url": "https://provider.invalid/v1",
                "api_keys": ["k1"],
                "enabled": True,
                "use_global_proxy": False,
                "model_redirects": {
                    "gemini-2.5": [
                        "inst1/google/gemini-2.5-exp",
                        "inst2/white/gemini-2.5-flash-cool",
                    ]
                },
            },
            {
                "name": "inst2",
                "base_url": "https://provider-2.invalid/v1",
                "api_keys": ["k2"],
                "enabled": True,
                "use_global_proxy": False,
            },
        ],
        proxy_manager=DummyProxyManager(),
        settings_file_path="configs/settings.json",
    )

    resolved = module._resolve_model_targets("inst1", "gemini-2.5")
    assert resolved == [
        ("inst1", "google/gemini-2.5-exp"),
        ("inst2", "white/gemini-2.5-flash-cool"),
    ]


@pytest.mark.asyncio
async def test_list_models_prefixes_instance_name(monkeypatch):
    module = make_module()

    async def fake_call(instance_name, method, endpoint_path, payload=None, extra_headers=None):
        return {"data": [{"id": "gpt-4", "object": "model"}]}

    monkeypatch.setattr(module, "_execute_non_streaming_with_rotation", fake_call)
    response = await module.list_models()
    assert response["object"] == "list"
    assert response["data"][0]["id"] == "inst1/gpt-4"


@pytest.mark.asyncio
async def test_oaic_call_without_api_key_is_allowed(monkeypatch, tmp_path):
    captured_headers = {}

    class FakeResponse:
        status_code = 200
        text = '{"data": []}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": []}

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            captured_headers.update(headers or {})
            return FakeResponse()

        async def post(self, url, headers=None, json=None):
            captured_headers.update(headers or {})
            return FakeResponse()

    monkeypatch.setattr("modules.openai_compat_module.httpx.AsyncClient", FakeAsyncClient)

    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{}", encoding="utf-8")

    module = OpenAICompatModule(
        instances_config=[
            {
                "name": "inst1",
                "base_url": "https://provider.invalid/v1",
                "api_keys": [],
                "enabled": True,
                "use_global_proxy": False,
            }
        ],
        proxy_manager=DummyProxyManager(),
        settings_file_path=str(settings_file),
    )

    response = await module._execute_non_streaming_with_rotation("inst1", "GET", "/models")
    assert response == {"data": []}
    assert "Authorization" not in captured_headers


@pytest.mark.asyncio
async def test_completion_uses_redirected_instance_and_model(monkeypatch):
    module = OpenAICompatModule(
        instances_config=[
            {
                "name": "inst1",
                "base_url": "https://provider.invalid/v1",
                "api_keys": ["k1"],
                "enabled": True,
                "use_global_proxy": False,
                "model_redirects": {"chat-main": "inst2/gpt-4.1-mini"},
            },
            {
                "name": "inst2",
                "base_url": "https://provider-2.invalid/v1",
                "api_keys": ["k2"],
                "enabled": True,
                "use_global_proxy": False,
            },
        ],
        proxy_manager=DummyProxyManager(),
        settings_file_path="configs/settings.json",
    )

    captured = {}

    async def fake_call(instance_name, method, endpoint_path, payload=None, extra_headers=None):
        captured["instance_name"] = instance_name
        captured["payload_model"] = payload.get("model")
        return {"choices": [{"text": "ok"}]}

    monkeypatch.setattr(module, "_execute_non_streaming_with_rotation", fake_call)
    result = await module.completion({"model": "OAIC/inst1/chat-main", "prompt": "hello"})
    assert result["choices"][0]["text"] == "ok"
    assert captured["instance_name"] == "inst2"
    assert captured["payload_model"] == "gpt-4.1-mini"


@pytest.mark.asyncio
async def test_completion_uses_redirect_list_fallback(monkeypatch):
    module = OpenAICompatModule(
        instances_config=[
            {
                "name": "inst1",
                "base_url": "https://provider.invalid/v1",
                "api_keys": ["k1"],
                "enabled": True,
                "use_global_proxy": False,
                "model_redirects": {
                    "gemini-2.5": [
                        "inst1/google/gemini-2.5-exp",
                        "inst2/white/gemini-2.5-flash-cool",
                    ]
                },
            },
            {
                "name": "inst2",
                "base_url": "https://provider-2.invalid/v1",
                "api_keys": ["k2"],
                "enabled": True,
                "use_global_proxy": False,
            },
        ],
        proxy_manager=DummyProxyManager(),
        settings_file_path="configs/settings.json",
    )

    attempts = []

    async def fake_call(instance_name, method, endpoint_path, payload=None, extra_headers=None):
        attempts.append((instance_name, payload.get("model")))
        if len(attempts) == 1:
            raise HTTPException(status_code=503, detail="first provider down")
        return {"choices": [{"text": "ok-fallback"}]}

    monkeypatch.setattr(module, "_execute_non_streaming_with_rotation", fake_call)
    result = await module.completion({"model": "OAIC/inst1/gemini-2.5", "prompt": "hello"})

    assert result["choices"][0]["text"] == "ok-fallback"
    assert attempts[0] == ("inst1", "google/gemini-2.5-exp")
    assert attempts[1] == ("inst2", "white/gemini-2.5-flash-cool")
