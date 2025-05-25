
from handlers.misc.libs.tokenizer.main import get_token_count
from handlers.misc.libs.tokenizer.model_autodetect import get_model_config, UNKNOWN_MODEL_MULTIPLIER, GLOBAL_MIN_MATCH_THRESHOLD
from handlers.misc.libs.tokenizer.base_calculator import calculate_tokens_with_tiktoken, _get_tiktoken_encoding

def start():

    texts_to_test = [
        "A long and complex sentence that could be tokenized differently by various models. This text is quite verbose, demonstrating various aspects of language processing.",
        "Привет, как дела? Я хочу узнать прогноз погоды. Это более сложный текст с различными символами и несколькими пробелами.",
        "Hello, Привет, как дела? This is a mixed message with some Russian words.",
        "It's a beautiful day. Солнце светит ярко.",
        "Краткий пример.",
        "Hello!",
        "     ",
        "",
        "🚀💫",
        "Нейросеть - это круто, но сложно.",
        "The quick brown fox jumps over the lazy dog.",
        "你好世界。这是一个中文句子。",
        "Тестовый короткий текст. Сл. аббревиатура. Т. е. другой пример.",
        "This is an example. E.g., for testing.",
        "The quick brown fox jumps over the lazy dog. Тестовый короткий текст. Сл. аббревиатура. Т. е. другой пример. This is an example. E.g., for testing. Mr. Smith visited London. Dr. Ivanov is a professor."
    ]

    models_to_test = [
        "gpt-4o-2024-05-13",
        "gpt-4-turbo-preview",
        "gpt-3.5-turbo-0123",
        "claude-3-opus-20240229",
        "claude-3-7",
        "claude-3-5",
        "gemini-1.5-pro-preview-0409",
        "phi-2-v1",
        "unknown-llm-model-v99",
        "ada-002-embeddings",
        "gpt-4-o-mini",
        "llama-2-7b-chat"
    ]

    print(f"--- Модульный Автоопределяющий Tiktoken Токенизатор ---")
    print(f"Базовая кодировка tiktoken для неизвестных/неспецифических моделей: '{_get_tiktoken_encoding('cl100k_base').name}'")
    print(f"Множитель по умолчанию для неизвестных моделей: {UNKNOWN_MODEL_MULTIPLIER}")
    print(f"Глобальный минимальный порог схожести для определения известной модели: {GLOBAL_MIN_MATCH_THRESHOLD}%")
    print("Внимание: Точность для не-OpenAI моделей зависит от калибровки MODEL_CONFIGS!\n")

    for text_idx, text in enumerate(texts_to_test):
        print(f"\n--- Текст [{text_idx+1}]: '{text}' (Длина символов: {len(text)}) ---")
        
        base_cl100k_tokens = calculate_tokens_with_tiktoken(text, "cl100k_base", 1.0)
        print(f"  Базовый Tiktoken (cl100k_base): {base_cl100k_tokens} токенов")

        for model in models_to_test:
            tiktoken_enc_name, multiplier_used, match_percentage = get_model_config(model)
            actual_encoding_name = _get_tiktoken_encoding(tiktoken_enc_name).name
            approx_tokens = get_token_count(text, model_name=model)
            
            print(f"  Для модели '{model}' (найден '{tiktoken_enc_name}', кодировка {actual_encoding_name}, множитель {multiplier_used:.2f}, совпадение {match_percentage:.2f}%): {approx_tokens} токенов")