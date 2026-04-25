import pytest

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
    assert instance2 is None
    assert model2 is None


@pytest.mark.asyncio
async def test_list_models_prefixes_instance_name(monkeypatch):
    module = make_module()

    async def fake_call(instance_name, method, endpoint_path, payload=None, extra_headers=None):
        return {"data": [{"id": "gpt-4", "object": "model"}]}

    monkeypatch.setattr(module, "_execute_non_streaming_with_rotation", fake_call)
    response = await module.list_models()
    assert response["object"] == "list"
    assert response["data"][0]["id"] == "inst1/gpt-4"
