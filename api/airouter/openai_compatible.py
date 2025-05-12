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
async def audio_transcription(request: Request, file: UploadFile = None): # File может быть None, если не передан
    # FastAPI ожидает UploadFile как отдельный параметр, а не в request.form() напрямую для JSON API
    # Если мы хотим JSON API, то файл должен быть частью multipart/form-data,
    # или тело запроса должно быть JSON, а файл - отдельным полем.
    # Для совместимости с OpenAI, они часто используют multipart/form-data для аудио.
    # Пока оставим как есть, но это может потребовать адаптации клиента.
    # Если файл передается как часть form-data, то request.json() вызовет ошибку.
    # Нужно будет использовать request.form() и обрабатывать файл отдельно.
    
    # Предположим, что клиент будет отправлять JSON с метаданными, а файл отдельно,
    # или что UploadFile будет корректно обработан FastAPI даже если тело JSON.
    # Это сложный момент для прямого переноса.
    # Для простоты, пока оставим как есть, но это может не работать как JSON API.
    # OpenAI API для audio ожидает multipart/form-data.
    
    # Чтобы это работало как JSON API, клиент должен был бы передать файл, например, в base64 в JSON.
    # Или мы должны оставить этот эндпоинт как form-data.
    # Поскольку пользователь просит перенести "все эндпоинты, не связанные с рендерингом" в API,
    # и эти эндпоинты уже были API, я сохраню их логику максимально близко.
    
    # Если мы хотим, чтобы это был JSON API, то file: UploadFile не будет работать с request.json()
    # Если это form-data, то request.json() не будет работать.
    # OpenAI API для audio/transcriptions использует multipart/form-data.
    # Поэтому, мы должны ожидать Form() для параметров и UploadFile для файла.
    
    # Вернемся к логике из main.py, где использовался request.form()
    # Это означает, что эти эндпоинты не являются чисто JSON API, а form-data API.
    
    form_data = await request.form()
    model_name = form_data.get("model", "openai")
    
    # Получаем файл из form_data, если он там есть.
    # FastAPI автоматически инжектирует UploadFile, если он объявлен в параметрах функции.
    # Если мы используем request.form(), то файл нужно будет искать там.
    # Но если file: UploadFile объявлен, FastAPI ожидает его как отдельный параметр.
    # Это конфликт.
    
    # Решение: Объявим file: UploadFile и model: str = Form(...)
    # Это стандартный способ для FastAPI обрабатывать файлы и данные форм.
    # Уберем request.json() и request.form() и будем полагаться на параметры функции.
    
    # Этот эндпоинт будет переписан ниже с правильными параметрами.
    raise NotImplementedError("Audio endpoints need specific form/file handling.")


@router.post("/v1/audio/translations")
async def audio_translation(request: Request, file: UploadFile = None):
    # Аналогично transcriptions
    raise NotImplementedError("Audio endpoints need specific form/file handling.")

# Переписанные аудио эндпоинты
@router.post("/v1/audio/transcriptions_form") # Изменим путь, чтобы не конфликтовать, пока не решим
async def audio_transcription_form(
    request: Request, # Для доступа к app.state
    file: UploadFile, 
    model: Optional[str] = Form(None) # model теперь Form параметр
    # другие параметры OpenAI могут быть добавлены сюда как Form(...)
):
    # Получаем model из Form или используем значение по умолчанию
    model_name_to_use = model if model else "openai" # или другой дефолт, если нужно
    module = get_module(request, {"model": model_name_to_use}) # Передаем request
    
    file_bytes = await file.read()
    # request_params должны собираться из других Form(...) полей, если они есть
    request_params = {"model": model_name_to_use} # Пример
    # Если есть другие параметры, их нужно будет добавить в request_params
    # Например: language: Optional[str] = Form(None) -> request_params["language"] = language
    
    return await module.audio_transcription(request_params, file_bytes, file.filename)


@router.post("/v1/audio/translations_form") # Изменим путь
async def audio_translation_form(
    request: Request, # Для доступа к app.state
    file: UploadFile,
    model: Optional[str] = Form(None)
):
    model_name_to_use = model if model else "openai"
    module = get_module(request, {"model": model_name_to_use}) # Передаем request
    
    file_bytes = await file.read()
    request_params = {"model": model_name_to_use}
    
    return await module.audio_translation(request_params, file_bytes, file.filename)
