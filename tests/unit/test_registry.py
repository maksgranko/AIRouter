import json

import pytest

from modules.base_module import BaseModule
from registry import ModuleRegistry


class DummyModule(BaseModule):
    def __init__(self, name):
        self._name = name
        self.reloaded = None

    def get_name(self) -> str:
        return self._name

    def _get_httpx_proxies(self, proxy_config):
        return None

    async def _execute_non_streaming_with_rotation(self, *args, **kwargs):
        return {}

    async def _execute_streaming_with_rotation(self, *args, **kwargs):
        if False:
            yield {}

    async def chat_completion(self, request):
        return {}

    async def list_models(self):
        return {"object": "list", "data": []}

    async def completion(self, request):
        return {}

    async def embeddings(self, request):
        return {}

    async def moderations(self, request):
        return {}

    async def generate_image(self, request):
        return {}

    async def audio_transcription(self, request, file_data, filename=None):
        return {}

    async def audio_translation(self, request, file_data, filename=None):
        return {}

    def reload_module_config(self, payload):
        self.reloaded = payload


def test_registry_respects_statuses_and_persists(tmp_path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps({"module_statuses": {"m1": True, "m2": False}}, indent=2),
        encoding="utf-8",
    )

    reg = ModuleRegistry(str(settings_file))
    m1 = DummyModule("m1")
    m2 = DummyModule("m2")
    reg.register(m1)
    reg.register(m2)

    assert reg.get("m1") is m1
    with pytest.raises(KeyError):
        reg.get("m2")

    reg.set_module_active("m2", True)
    assert reg.get("m2") is m2

    saved = json.loads(settings_file.read_text(encoding="utf-8"))
    assert saved["module_statuses"]["m2"] is True


@pytest.mark.asyncio
async def test_reload_module_config_delegates(tmp_path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{}", encoding="utf-8")
    reg = ModuleRegistry(str(settings_file))
    mod = DummyModule("oaic")
    reg.register(mod)

    await reg.reload_module_config("oaic", [{"name": "x"}])
    assert mod.reloaded == [{"name": "x"}]
