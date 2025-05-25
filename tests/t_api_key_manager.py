import json
import os
from api_key_manager import ApiKeyManager


def start():
    temp_openai_file = "temp_openai_keys.json"
    temp_gemini_file = "temp_gemini_keys.json"
    key_manager = ApiKeyManager({
        "openai": temp_openai_file,
        "gemini": temp_gemini_file
    })
    with open(temp_openai_file, "w") as f:
        json.dump(["openai_key_1", "openai_key_2"], f)
    with open(temp_gemini_file, "w") as f:
        json.dump(["gemini_key_1"], f)

    print("--- Initial Load ---")
    print(f"OpenAI Keys: {key_manager.api_keys.get('openai')}")
    print(f"Gemini Keys: {key_manager.api_keys.get('gemini')}")

    print("\n--- Adding Keys ---")
    key_manager.add_key("openai", "openai_key_3")
    key_manager.add_key("gemini", "gemini_key_2")
    key_manager.add_key("new_service", "new_service_key_1")
    print(f"OpenAI Keys after add: {key_manager.api_keys.get('openai')}")
    print(f"Gemini Keys after add: {key_manager.api_keys.get('gemini')}")
    print(f"New Service Keys: {key_manager.api_keys.get('new_service')}")


    print("\n--- Removing Keys ---")
    key_manager.remove_key("openai", "openai_key_1")
    key_manager.remove_key("gemini", "gemini_key_non_existent")
    print(f"OpenAI Keys after remove: {key_manager.api_keys.get('openai')}")
    
    # Проверка текущего ключа после удаления
    print(f"Current OpenAI Key: {key_manager.get_key('openai')}") # Должен быть openai_key_2 или openai_key_3
    key_manager.remove_key("openai", key_manager.get_key('openai'))
    print(f"Current OpenAI Key after removing current: {key_manager.get_key('openai')}")


    print("\n--- Reloading Keys ---")
    # Изменим файл openai ключей вручную для теста перезагрузки
    with open(temp_openai_file, "w") as f:
        json.dump(["openai_reloaded_1", "openai_reloaded_2"], f)
    key_manager.reload_keys_for_service("openai")
    print(f"OpenAI Keys after reload: {key_manager.api_keys.get('openai')}")
    print(f"Current OpenAI Key after reload: {key_manager.get_key('openai')}")


    # Удаляем временные файлы
    if os.path.exists(temp_openai_file):
        os.remove(temp_openai_file)
    if os.path.exists(temp_gemini_file):
        os.remove(temp_gemini_file)
    if os.path.exists("new_service_keys.json"): # Если создался файл для нового сервиса
        os.remove("new_service_keys.json")