from .model_autodetect import get_model_config
from .base_calculator import calculate_tokens_with_tiktoken

def get_token_count(text: str, model_name: str = "default") -> int:
    """
    Основной метод для получения количества токенов.
    Автоматически определяет модель и применяет соответствующие настройки.

    Args:
        text: Входной текст.
        model_name: Имя модели (например, "gpt-4o", "claude-3-opus", "gemini-pro").

    Returns:
        Приблизительное количество токенов (целое число).
    """
    tiktoken_encoding_name, multiplier, _ = get_model_config(model_name)
    tokens = calculate_tokens_with_tiktoken(text, tiktoken_encoding_name, multiplier)
    return tokens