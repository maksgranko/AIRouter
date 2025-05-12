import inspect
import json
import logging
from typing import AsyncGenerator, Dict, Any, Optional

from fastapi import APIRouter, Form, Request, UploadFile, HTTPException
from fastapi.responses import StreamingResponse

# Получаем глобальный registry и logger из app.state, если они там есть,
# или импортируем напрямую, если это возможно и безопасно.
# Для этого эндпоинты должны принимать Request и получать доступ к app.state.
# logger можно инициализировать локально.

router = APIRouter(
    tags=["openai_compatible_v1"] # Тег для Swagger
)
logger = logging.getLogger(__name__)
# Уровень логирования будет унаследован или можно установить здесь.

# Вспомогательные функции, перенесенные из main.py
def get_module(request: Request, request_data: dict):
    """
    Получает модуль для обработки запроса.
    Логика выбора модуля по model_name или service_name.
    """
    registry = request.app.state.module_registry # Получаем registry из app.state
    model_identifier = request_data.get("model", "openai") 
    
    try:
        module = registry.get(model_identifier)
        return module
    except KeyError:
        pass 

    if '/' in model_identifier:
        service_name_from_slash = model_identifier.split('/')[0]
        try:
            module = registry.get(service_name_from_slash)
            return module
        except KeyError:
            pass 

    known_prefixes = ["gemini", "openai"] 
    for prefix in known_prefixes:
        if model_identifier.startswith(prefix):
            try:
                module = registry.get(prefix) 
                return module
            except KeyError:
                pass 
                
    logger.error(f"Failed to find module for model_identifier: '{model_identifier}'. Review request body or ensure module is registered and active.")
    raise HTTPException(status_code=400, detail=f"Module for model/service '{model_identifier}' not found or not registered.")


async def sse_event_formatter(generator: AsyncGenerator[Dict[str, Any], None]) -> AsyncGenerator[str, None]:
    """
    Форматирует словари из генератора в Server-Sent Events (SSE) строки.
    """
    try:
        async for chunk_data in generator:
            yield f"data: {json.dumps(chunk_data)}\n\n"
        yield f"data: [DONE]\n\n"
    except HTTPException as e:
        logger.error(f"HTTPException during SSE stream generation: {e.detail}", exc_info=False)
        error_payload = {
            "error": {"message": e.detail, "type": "api_error", "param": None, "code": str(e.status_code)}
        }
        yield f"data: {json.dumps(error_payload)}\n\n"
        yield f"data: [DONE]\n\n"
    except Exception as e:
        logger.error(f"Unexpected exception during SSE stream generation: {e}", exc_info=True)
        error_payload = {
            "error": {"message": "An unexpected error occurred during streaming.", "type": "internal_server_error", "param": None, "code": "500"}
        }
        yield f"data: {json.dumps(error_payload)}\n\n"
        yield f"data: [DONE]\n\n"


# OpenAI Compatible Endpoints
@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    module = get_module(request, body) # Передаем request

    if inspect.isasyncgenfunction(module.chat_completion):
        actual_generator = module.chat_completion(body)
        return StreamingResponse(sse_event_formatter(actual_generator), media_type="text/event-stream")
    else:
        return await module.chat_completion(body)

@router.post("/v1/completions")
async def completions(request: Request):
    body = await request.json()
    module = get_module(request, body) # Передаем request
    return await module.completion(body)

@router.post("/v1/embeddings")
async def embeddings(request: Request):
    body = await request.json()
    module = get_module(request, body) # Передаем request
    return await module.embeddings(body)

@router.get("/v1/models")
async def list_models(request: Request): # Добавляем request для доступа к app.state
    all_models = []
    registry = request.app.state.module_registry # Получаем registry из app.state
    for mod in registry.all_active_modules(): 
        try:
            models = await mod.list_models()
            all_models.extend(models.get("data", []))
        except Exception: 
            continue
    return {"object": "list", "data": all_models}

@router.get("/v1/models/{model_id}")
async def retrieve_model(model_id: str, request: Request): # Добавляем request
    registry = request.app.state.module_registry # Получаем registry из app.state
    parts = model_id.split('/')
    service_to_try = parts[0] if len(parts) > 1 else None

    try:
        module = registry.get(model_id)
        return await module.retrieve_model(model_id)
    except KeyError:
        if service_to_try:
            try:
                module = registry.get(service_to_try)
                return await module.retrieve_model(model_id)
            except KeyError:
                pass 
        
        for mod in registry.all_active_modules():
            try:
                retrieved = await mod.retrieve_model(model_id)
                if isinstance(retrieved, dict) and retrieved.get("object") == "model": 
                    return retrieved
            except NotImplementedError:
                continue
            except HTTPException as e: 
                if e.status_code == 404 or "not found" in str(e.detail).lower(): 
                    continue
                raise 
            except Exception: 
                continue
                
    raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found or its service is inactive.")


@router.post("/v1/moderations")
async def moderations(request: Request):
    body = await request.json()
    module = get_module(request, body) # Передаем request
    return await module.moderations(body)

@router.post("/v1/images/generations")
async def generate_image(request: Request):
    body = await request.json()
    module = get_module(request, body) # Передаем request
    return await module.generate_image(body)

@router.post("/v1/audio/transcriptions")
async def audio_transcription(
    request: Request,
    file: UploadFile,
    model: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
    prompt: Optional[str] = Form(None),
    response_format: Optional[str] = Form(None),
    temperature: Optional[float] = Form(None)
    # timestamp_granularities: Optional[List[str]] = Form(None) # Для поддержки этого нужно будет адаптировать BaseModule и OpenAIModule
):
    model_name_to_use = model if model else "openai" # Или другой дефолт, если модуль может его определить
    module = get_module(request, {"model": model_name_to_use})

    file_bytes = await file.read()
    
    request_params = {"model": model_name_to_use} # model передается для внутренней логики модуля, если нужно
    if language:
        request_params["language"] = language
    if prompt:
        request_params["prompt"] = prompt
    if response_format:
        request_params["response_format"] = response_format
    if temperature is not None:
        request_params["temperature"] = temperature
    # if timestamp_granularities:
    #     request_params["timestamp_granularities[]"] = timestamp_granularities

    # Передаем filename в модуль, он может быть нужен
    return await module.audio_transcription(request_params, file_bytes, file.filename)

@router.post("/v1/audio/translations")
async def audio_translation(
    request: Request,
    file: UploadFile,
    model: Optional[str] = Form(None),
    prompt: Optional[str] = Form(None),
    response_format: Optional[str] = Form(None),
    temperature: Optional[float] = Form(None)
):
    model_name_to_use = model if model else "openai"
    module = get_module(request, {"model": model_name_to_use})

    file_bytes = await file.read()
    
    request_params = {"model": model_name_to_use}
    if prompt:
        request_params["prompt"] = prompt
    if response_format:
        request_params["response_format"] = response_format
    if temperature is not None:
        request_params["temperature"] = temperature
        
    return await module.audio_translation(request_params, file_bytes, file.filename)
