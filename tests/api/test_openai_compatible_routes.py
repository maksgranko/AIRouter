class FakeModule:
    def __init__(self, name="openai"):
        self._name = name

    def get_name(self):
        return self._name

    async def chat_completion(self, request):
        return {"ok": True, "model": request.get("model")}

    async def completion(self, request):
        return {"object": "text_completion", "model": request.get("model")}

    async def embeddings(self, request):
        return {"object": "list", "data": []}

    async def list_models(self):
        return {"object": "list", "data": [{"id": "gpt-4", "object": "model"}]}

    async def retrieve_model(self, model_id):
        return {"object": "model", "id": model_id}

    async def moderations(self, request):
        return {"ok": True}

    async def generate_image(self, request):
        return {"data": []}

    async def generate_image_edit(self, request_params, image_data, image_filename, mask_data=None, mask_filename=None):
        return {
            "ok": True,
            "kind": "image_edit",
            "filename": image_filename,
            "has_mask": mask_data is not None,
        }

    async def generate_image_variation(self, request_params, image_data, image_filename):
        return {"ok": True, "kind": "image_variation", "filename": image_filename}

    async def audio_transcription(self, request, file_data, filename=None):
        return {"text": "ok", "filename": filename}

    async def audio_translation(self, request, file_data, filename=None):
        return {"text": "ok", "filename": filename}

    async def audio_speech(self, request):
        return {"ok": True, "audio": "base64-or-url"}

    async def responses(self, request):
        return {"id": "resp_123", "object": "response", "model": request.get("model")}


class FakeStreamingModule(FakeModule):
    async def chat_completion(self, request):
        yield {"id": "chunk-1", "choices": [{"delta": {"content": "hello"}}]}


class FakeRegistry:
    def __init__(self, module):
        self.module = module

    def get(self, name):
        return self.module

    def all_active_modules(self):
        return [self.module]


async def test_chat_completion_non_stream(async_client, app_module):
    app_module.app.state.module_registry = FakeRegistry(FakeModule())
    response = await async_client.post("/v1/chat/completions", json={"model": "openai"})
    assert response.status_code == 200
    assert response.json()["ok"] is True


async def test_chat_completion_streaming(async_client, app_module):
    app_module.app.state.module_registry = FakeRegistry(FakeStreamingModule())
    response = await async_client.post("/v1/chat/completions", json={"model": "openai"})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "data:" in response.text
    assert "[DONE]" in response.text


async def test_models_routes(async_client, app_module):
    app_module.app.state.module_registry = FakeRegistry(FakeModule())

    list_response = await async_client.get("/v1/models")
    assert list_response.status_code == 200
    ids = [m["id"] for m in list_response.json()["data"]]
    assert any(i.endswith("/gpt-4") for i in ids)

    model_response = await async_client.get("/v1/models/gpt-4")
    assert model_response.status_code == 200
    assert model_response.json()["id"] == "gpt-4"


async def test_image_edits_route(async_client, app_module):
    app_module.app.state.module_registry = FakeRegistry(FakeModule())
    files = {"image": ("pic.png", b"img", "image/png")}
    data = {"model": "openai"}
    response = await async_client.post("/v1/images/edits", data=data, files=files)
    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "image_edit"


async def test_image_variations_route(async_client, app_module):
    app_module.app.state.module_registry = FakeRegistry(FakeModule())
    files = {"image": ("pic.png", b"img", "image/png")}
    data = {"model": "openai"}
    response = await async_client.post("/v1/images/variations", data=data, files=files)
    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "image_variation"


async def test_audio_speech_route(async_client, app_module):
    app_module.app.state.module_registry = FakeRegistry(FakeModule())
    response = await async_client.post("/v1/audio/speech", json={"model": "openai", "input": "hello"})
    assert response.status_code == 200
    assert response.json()["ok"] is True


async def test_responses_route(async_client, app_module):
    app_module.app.state.module_registry = FakeRegistry(FakeModule())
    response = await async_client.post("/v1/responses", json={"model": "openai", "input": "hello"})
    assert response.status_code == 200
    assert response.json()["object"] == "response"
