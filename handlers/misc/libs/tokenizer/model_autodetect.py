# tokenizer/model_autodetect.py
from typing import Dict, Tuple
from string_comparer.StringComparer import StringComparer

MODEL_CONFIGS: Dict[str, float] = {
    "gpt-4o": 1.0,
    "gpt-4-o": 1.0,
    "gpt-4": 1.0,
    "gpt-3.5-turbo": 1.0,
    "gpt-2": 1.3,
    "text-embedding-ada-002": 1.0,

    "claude-3.7": 1.08,
    "claude-3-7": 1.08,
    "claude-3.5": 1.03,
    "claude-3-5": 1.03,
    "claude-3": 1.03,
    "claude-3": 1.03,

    "gemini-pro": 1.0,
    "gemini-1.5-pro": 1.0,

    "phi-2": 1.25,
    "llama-2-7b": 1.3,
    "mixtral-8x7b": 1.2,
}

UNKNOWN_MODEL_MULTIPLIER: float = 1.2
GLOBAL_MIN_MATCH_THRESHOLD: float = 50.0

string_comparer = StringComparer()

def get_model_config(provided_model_name: str) -> Tuple[str, float, float]:
    """
    Определяет наиболее подходящую конфигурацию модели на основе предоставленного имени.
    Выбирает модель с наивысшим процентом схожести.

    Args:
        provided_model_name: Имя модели, предоставленное пользователем (например, "gpt-4o-2024-05-13").

    Returns:
        Кортеж: (имя_модели_tiktoken, множитель_токенов, процент_совпадения).
        имя_модели_tiktoken: Используется для получения tiktoken кодировки.
        множитель_токенов: Коэффициент из MODEL_CONFIGS или UNKNOWN_MODEL_MULTIPLIER.
        процент_совпадения: Процент схожести между предоставленным и каноническим именем модели.
    """
    provided_model_name_lower = provided_model_name.lower()

    best_match_name: str = "unknown"
    best_match_percentage: float = 0.0
    
    if provided_model_name_lower in MODEL_CONFIGS:
        best_match_name = provided_model_name_lower
        best_match_percentage = 100.0
    else:
        for canonical_name in MODEL_CONFIGS.keys():
            current_percentage = string_comparer.partial_match(provided_model_name_lower, canonical_name)
            
            if current_percentage > best_match_percentage:
                best_match_percentage = current_percentage
                best_match_name = canonical_name
    
    tiktoken_encoding_name: str = "cl100k_base"
    final_multiplier: float = UNKNOWN_MODEL_MULTIPLIER

    if best_match_name != "unknown" and best_match_percentage >= GLOBAL_MIN_MATCH_THRESHOLD:
        final_multiplier = MODEL_CONFIGS[best_match_name]
        
        if "gpt" in best_match_name or "text-embedding" in best_match_name:
            tiktoken_encoding_name = best_match_name
    
    return tiktoken_encoding_name, final_multiplier, best_match_percentage