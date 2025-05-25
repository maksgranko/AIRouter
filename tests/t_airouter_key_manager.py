import json
import os

from airouter_key_manager import AIRouterApiKeyManager


def start():
    # Убедимся, что тестовый файл создается в текущей директории, а не в configs
    test_keys_file = "temp_airouter_keys.json"
    
    # Удаляем старый тестовый файл, если он есть
    if os.path.exists(test_keys_file):
        os.remove(test_keys_file)

    manager = AIRouterApiKeyManager(keys_file_path=test_keys_file)
    
    print(f"Initial keys: {manager.get_all_keys()}")

    key1 = manager.generate_and_add_key()
    print(f"Generated key 1: {key1}")
    print(f"Keys after adding key1: {manager.get_all_keys()}")

    key2 = "manual_test_key_123"
    manager.add_key(key2)
    print(f"Keys after adding key2: {manager.get_all_keys()}")

    print(f"Key '{key1}' exists: {manager.key_exists(key1)}")
    print(f"Key 'non_existent_key' exists: {manager.key_exists('non_existent_key')}")

    manager.remove_key(key1)
    print(f"Keys after removing key1: {manager.get_all_keys()}")

    manager.remove_key("another_non_existent_key")

    # Проверка перезагрузки
    # Изменим файл вручную
    if os.path.exists(test_keys_file):
        with open(test_keys_file, 'w') as f:
            json.dump(["reloaded_key1", "reloaded_key2"], f)
        manager.reload_keys()
        print(f"Keys after reloading: {manager.get_all_keys()}")

    # Очистка
    if os.path.exists(test_keys_file):
        os.remove(test_keys_file)