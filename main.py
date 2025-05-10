import os
from fastapi import FastAPI, Request, UploadFile, HTTPException
from registry import ModuleRegistry
from modules.openai_module import OpenAIChatModule
from modules.gemini_module import GeminiChatModule
from api_key_manager import ApiKeyManager
from proxy_manager import ProxyManager
import admin_router # Импортируем роутер админ-панели

app = FastAPI()
registry = ModuleRegistry()

# Инициализация менеджеров
key_manager = ApiKeyManager({
    "openai": "openai_keys.json",
    "gemini": "gemini_keys.json"
})
proxy_manager = ProxyManager(proxy_file_path="proxies.json")

# Сохраняем менеджеры в состоянии приложения для доступа из роутеров
app.state.key_manager = key_manager
app.state.proxy_manager = proxy_manager

# Регистрация модулей API
# Мы передаем менеджер ключей в модули, чтобы они могли запрашивать и ротировать ключи.
# Регистрация модулей с передачей ApiKeyManager и ProxyManager
if key_manager.get_key("openai"): 
    registry.register(OpenAIChatModule(
        api_key_manager=key_manager, 
        proxy_manager=proxy_manager, 
        service_name="openai"
    ))
else:
    print("Warning: No OpenAI API keys found. OpenAI module will not be registered.")

if key_manager.get_key("gemini"): 
    registry.register(GeminiChatModule(
        api_key_manager=key_manager, 
        proxy_manager=proxy_manager, 
        service_name="gemini"
    ))
else:
    print("Warning: No Gemini API keys found. Gemini module will not be registered.")

# Подключаем роутер админ-панели
app.include_router(admin_router.router)

def get_module(request_data: dict):
    """
    Получает модуль для обработки запроса.
    Логика выбора модуля по model_name или service_name.
    """
    # Сначала пытаемся получить по полному имени модели (например, "openai/gpt-4")
    # Если не найдено, пытаемся по имени сервиса (например, "openai")
    # Это позволяет регистрировать модули по имени сервиса, а в запросе указывать конкретную модель.
    model_identifier = request_data.get("model", "openai") # "openai" - сервис по умолчанию
    
    try:
        # Попытка 1: получить модуль по полному идентификатору модели из запроса
        module = registry.get(model_identifier)
        return module
    except KeyError:
        # Попытка 2: если не найдено, извлечь имя сервиса и попробовать по нему
        # Это полезно, если модуль зарегистрирован как "openai", а в запросе "openai/gpt-3.5-turbo"
        service_name = model_identifier.split('/')[0]
        try:
            module = registry.get(service_name)
            # TODO: В будущем модуль может сам решать, какую под-модель использовать, если service_name != model_identifier
            return module
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Module for model/service '{model_identifier}' not found or not registered.")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    module = get_module(body)
    return await module.chat_completion(body)

@app.post("/v1/completions")
async def completions(request: Request):
    body = await request.json()
    module = get_module(body)
    return await module.completion(body)

@app.post("/v1/embeddings")
async def embeddings(request: Request):
    body = await request.json()
    module = get_module(body)
    return await module.embeddings(body)

@app.get("/v1/models")
async def list_models():
    all_models = []
    for mod in registry.all():
        try:
            models = await mod.list_models()
            all_models.extend(models.get("data", []))
        except Exception:
            continue
    return {"object": "list", "data": all_models}

@app.get("/v1/models/{model_id}")
async def retrieve_model(model_id: str):
    for mod in registry.all():
        try:
            return await mod.retrieve_model(model_id)
        except NotImplementedError:
            continue
    return {"error": f"Model {model_id} not found."}

@app.post("/v1/moderations")
async def moderations(request: Request):
    body = await request.json()
    module = get_module(body)
    return await module.moderations(body)

@app.post("/v1/images/generations")
async def generate_image(request: Request):
    body = await request.json()
    module = get_module(body)
    return await module.generate_image(body)

@app.post("/v1/audio/transcriptions")
async def audio_transcription(request: Request, file: UploadFile):
    body = await request.form() # Аудио запросы обычно используют form-data
    model_name = body.get("model", "openai") # Получаем модель из формы или по умолчанию
    module = registry.get(model_name)
    file_bytes = await file.read()
    # Передаем параметры из формы в модуль, исключая сам файл, если он там есть
    request_params = {k: v for k, v in body.items() if k != 'file'}
    return await module.audio_transcription(request_params, file_bytes)

@app.post("/v1/audio/translations")
async def audio_translation(request: Request, file: UploadFile):
    body = await request.form() # Аудио запросы обычно используют form-data
    model_name = body.get("model", "openai") # Получаем модель из формы или по умолчанию
    module = registry.get(model_name)
    file_bytes = await file.read()
    # Передаем параметры из формы в модуль, исключая сам файл, если он там есть
    request_params = {k: v for k, v in body.items() if k != 'file'}
    return await module.audio_translation(request_params, file_bytes)
