# tokenizer/base_calculator.py
import math
import tiktoken # pip install tiktoken

# Кэш для ускорения загрузки кодировок tiktoken
_ENCODING_CACHE = {}

def _get_tiktoken_encoding(model_name: str):
    """
    Получает специфическую кодировку tiktoken для данной модели.
    Если специфическая не найдена, возвращает общую 'cl100k_base'.
    Использует кэширование.
    """
    if model_name in _ENCODING_CACHE:
        return _ENCODING_CACHE[model_name]

    try:
        # tiktoken.encoding_for_model ожидает имя модели в нижнем регистре
        encoding = tiktoken.encoding_for_model(model_name.lower())
    except KeyError:
        # Если модель не найдена в маппинге tiktoken, используем базовую для современных моделей
        encoding = tiktoken.get_encoding("cl100k_base")
    except Exception as e:
        # В случае других ошибок при получении кодировки (очень редко)
        print(f"Ошибка при загрузке tiktoken кодировки для '{model_name}': {e}. Откат к 'cl100k_base'.")
        encoding = tiktoken.get_encoding("cl100k_base")
    
    _ENCODING_CACHE[model_name] = encoding
    return encoding

def calculate_tokens_with_tiktoken(text: str, tiktoken_model_name: str, multiplier: float = 1.0) -> int:
    """
    Подсчитывает количество токенов в тексте, используя указанную кодировку tiktoken
    и применяя заданный множитель.

    Args:
        text: Входной текст.
        tiktoken_model_name: Имя модели для получения tiktoken кодировки (например, "gpt-4o", "cl100k_base").
        multiplier: Коэффициент, на который умножается базовое количество токенов tiktoken.

    Returns:
        Приблизительное количество токенов (целое число).
    """
    if not isinstance(text, str) or not text.strip():
        return 0

    encoding = _get_tiktoken_encoding(tiktoken_model_name)
    
    base_tiktoken_tokens = len(encoding.encode(text))
    adjusted_tokens = base_tiktoken_tokens * multiplier
    
    return int(math.ceil(adjusted_tokens))