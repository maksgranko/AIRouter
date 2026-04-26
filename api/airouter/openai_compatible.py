import inspect
import json
import logging
from typing import AsyncGenerator, Dict, Any, Optional

from fastapi import APIRouter, Form, Request, UploadFile, HTTPException, File
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
        module = registry.get(model_identifier) # Попытка 1: точное совпадение model_identifier (например, "gemini", "openai" для старых модулей)
        return module
    except KeyError:
        pass

    # Попытка 2: обработка префикса для нового OpenAICompatModule (например, "openai_instance1/gpt-4")
    # Новый модуль будет зарегистрирован под именем "openai_compat" (или аналогичным)
    # Имя модели в запросе будет "openai_INSTANCENAME/ACTUAL_MODEL_NAME"
    if (model_identifier.startswith("openai_") and '/' in model_identifier) or model_identifier.startswith("OAIC/"):
        try:
            # Все запросы к openai_INSTANCENAME/... должны идти к одному модулю OpenAICompatModule
            module = registry.get("OAIC") # Предполагаемое имя регистрации нового модуля
            return module
        except KeyError:
            # Если модуль "OAIC" не найден, это проблема конфигурации
            logger.error(f"OpenAI Compatible module ('OAIC') not found in registry for identifier: '{model_identifier}'.")
            # Продолжаем поиск, возможно, это старый "openai" модуль или другой.
            pass

    # Попытка 3: по префиксу до / (например, "gemini/gemini-pro" -> "gemini")
    if '/' in model_identifier:
        service_name_from_slash = model_identifier.split('/')[0]
        try:
            module = registry.get(service_name_from_slash)
            return module
        except KeyError:
            pass 

    # Попытка 4: по известным префиксам (для случаев, когда model_identifier это просто "gemini-pro" или "gpt-3.5-turbo")
    # Это должно быть после проверки "openai_", чтобы "openai_..." не матчилось на старый "openai" модуль.
    known_prefixes = ["gemini", "openai"] # "openai" здесь для старого модуля, если он еще используется
    for prefix in known_prefixes:
        if model_identifier.startswith(prefix) and not model_identifier.startswith("openai_"): # Условие, чтобы не пересекаться с новым
            try:
                module = registry.get(prefix) 
                return module
            except KeyError:
                pass 
                
    logger.error(f"Failed to find module for model_identifier: '{model_identifier}'. Review request body or ensure module is registered and active.")
    raise HTTPException(status_code=400, detail=f"Module for model/service '{model_identifier}' not found or not registered.")


def _require_module_method(module: Any, method_name: str):
    method = getattr(module, method_name, None)
    if not callable(method):
        raise HTTPException(
            status_code=501,
            detail=f"Endpoint is not supported by module '{module.get_name()}'.",
        )
    return method


async def _call_optional_module_method(module: Any, method_name: str, *args, **kwargs):
    method = _require_module_method(module, method_name)
    try:
        return await method(*args, **kwargs)
    except NotImplementedError:
        raise HTTPException(
            status_code=501,
            detail=f"Endpoint is not supported by module '{module.get_name()}'.",
        )


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
    logger.debug("Received /v1/completions request body")
    module = get_module(request, body)
    return await module.completion(body)

@router.post("/v1/embeddings")
async def embeddings(request: Request):
    body = await request.json()
    logger.debug("Received /v1/embeddings request body")
    module = get_module(request, body)
    return await module.embeddings(body)

@router.get("/v1/models")
async def list_models(request: Request): # Добавляем request для доступа к app.state
    all_models = []
    registry = request.app.state.module_registry # Получаем registry из app.state
    for mod in registry.all_active_modules(): 
        module_name = mod.get_name() # Получаем имя модуля
        try:
            models_response = await mod.list_models()
            if models_response and "data" in models_response:
                for model_data in models_response["data"]:
                    if isinstance(model_data, dict) and 'id' in model_data:
                        # Добавляем префикс модуля, если его еще нет
                        if not model_data['id'].startswith(f"{module_name}/"):
                            model_data['id'] = f"{module_name}/{model_data['id']}"
                    all_models.append(model_data)
        except Exception as e: 
            logger.error(f"Error fetching models from module {module_name} for /v1/models: {e}")
            continue
    return {"object": "list", "data": all_models}

@router.get("/v1/models/{model_id}")
async def retrieve_model(model_id: str, request: Request): # Добавляем request
    registry = request.app.state.module_registry
    
    # Логика для /v1/models/{model_id} должна быть совместима с новым форматом "openai_instance/model"
    # и старыми форматами.
    # model_id здесь это то, что приходит в URL, например "openai_instance1/gpt-4" или "gemini-pro"

    # Попытка 1: model_id - это имя зарегистрированного модуля (маловероятно для retrieve_model, но для полноты)
    try:
        module = registry.get(model_id)
        # Если модуль найден по полному model_id, значит model_id не содержит имя инстанса/сервиса как префикс.
        # Это может быть, если имя модели совпадает с именем сервиса (например, модуль "gpt4" для модели "gpt4").
        return await module.retrieve_model(model_id) # Модуль сам разберется с model_id
    except KeyError:
        pass

    # Попытка 2: model_id содержит префикс инстанса/сервиса (например, "openai_instance1/gpt-4" или "gemini/gemini-pro")
    if '/' in model_id:
        service_or_instance_prefix = model_id.split('/')[0]
        module_to_try_name = "OAIC" if service_or_instance_prefix.startswith("openai_") or service_or_instance_prefix == "OAIC" else service_or_instance_prefix
        
        try:
            module = registry.get(module_to_try_name)
            # Передаем полный model_id в модуль, он должен сам его распарсить, если нужно
            return await module.retrieve_model(model_id) 
        except KeyError:
            pass # Модуль по префиксу не найден, продолжаем

    # Попытка 3: model_id - это просто имя модели без префикса (например, "gpt-4").
    # В этом случае нужно перебрать все активные модули и спросить их.
    # Это особенно важно для OpenAICompatModule, который может содержать эту модель в одном из своих инстансов.
    for mod in registry.all_active_modules():
        try:
            # Передаем полный model_id. Модуль OpenAICompatModule должен проверить все свои инстансы.
            # Другие модули (gemini, старый openai) также должны уметь обрабатывать это.
            retrieved = await mod.retrieve_model(model_id) 
            if isinstance(retrieved, dict) and retrieved.get("object") == "model":
                # Важно: если это модель из OpenAICompatModule, ее id уже должен быть с префиксом инстанса.
                # Если model_id был без префикса, а модуль вернул с префиксом, это нормально.
                # Главное, чтобы клиент получил корректный объект модели.
                return retrieved
        except NotImplementedError:
            continue
        except HTTPException as e:
            # Если модуль явно говорит "не найдено" (404), пробуем следующий.
            # Другие HTTPException (например, 500 от инстанса) должны пробрасываться.
            if e.status_code == 404 or "not found" in str(e.detail).lower():
                continue
            raise # Пробрасываем другие ошибки HTTP
        except Exception: # Ловим другие неожиданные ошибки от модуля
            logger.warning(f"Unexpected error retrieving model '{model_id}' from module '{mod.get_name()}'. Skipping.", exc_info=True)
            continue
            
    raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found across all active modules or its service is inactive.")


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


@router.post("/v1/images/edits")
async def edit_image(
    request: Request,
    image: UploadFile = File(...),
    model: Optional[str] = Form(None),
    prompt: Optional[str] = Form(None),
    mask: Optional[UploadFile] = File(None),
    n: Optional[int] = Form(None),
    size: Optional[str] = Form(None),
    response_format: Optional[str] = Form(None),
    user: Optional[str] = Form(None),
):
    model_name_to_use = model if model else "openai"
    module = get_module(request, {"model": model_name_to_use})
    method_name = "generate_image_edit"

    image_bytes = await image.read()
    mask_bytes = await mask.read() if mask else None
    request_params = {"model": model_name_to_use}
    if prompt is not None:
        request_params["prompt"] = prompt
    if n is not None:
        request_params["n"] = n
    if size:
        request_params["size"] = size
    if response_format:
        request_params["response_format"] = response_format
    if user:
        request_params["user"] = user

    return await _call_optional_module_method(
        module,
        method_name,
        request_params,
        image_bytes,
        image.filename,
        mask_data=mask_bytes,
        mask_filename=mask.filename if mask else None,
    )


@router.post("/v1/images/variations")
async def image_variations(
    request: Request,
    image: UploadFile = File(...),
    model: Optional[str] = Form(None),
    n: Optional[int] = Form(None),
    size: Optional[str] = Form(None),
    response_format: Optional[str] = Form(None),
    user: Optional[str] = Form(None),
):
    model_name_to_use = model if model else "openai"
    module = get_module(request, {"model": model_name_to_use})
    method_name = "generate_image_variation"

    image_bytes = await image.read()
    request_params = {"model": model_name_to_use}
    if n is not None:
        request_params["n"] = n
    if size:
        request_params["size"] = size
    if response_format:
        request_params["response_format"] = response_format
    if user:
        request_params["user"] = user

    return await _call_optional_module_method(module, method_name, request_params, image_bytes, image.filename)

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


@router.post("/v1/audio/speech")
async def audio_speech(request: Request):
    body = await request.json()
    module = get_module(request, body)
    return await _call_optional_module_method(module, "audio_speech", body)


@router.post("/v1/responses")
async def responses(request: Request):
    body = await request.json()
    module = get_module(request, body)
    return await _call_optional_module_method(module, "responses", body)
