import json
import os
from typing import List, Dict, Optional
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ApiKeyManager:
    def __init__(self, key_files: Dict[str, str]):
        """
        Инициализирует менеджер API ключей.
        :param key_files: Словарь, где ключ - это имя сервиса (например, "openai"),
                          а значение - путь к JSON-файлу со списком ключей.
        """
        self.key_files = key_files
        self.api_keys: Dict[str, List[str]] = {}
        self.current_key_indices: Dict[str, int] = {}
        self._load_keys()

    def _load_keys(self):
        """Загружает API ключи из указанных файлов."""
        for service_name, file_path in self.key_files.items():
            try:
                if os.path.exists(file_path):
                    with open(file_path, 'r') as f:
                        keys = json.load(f)
                        if isinstance(keys, list) and all(isinstance(key, str) for key in keys):
                            self.api_keys[service_name] = keys
                            self.current_key_indices[service_name] = 0
                            logger.info(f"Successfully loaded {len(keys)} API keys for service '{service_name}' from {file_path}")
                        else:
                            logger.error(f"Invalid format in key file {file_path} for service '{service_name}'. Expected a list of strings.")
                            self.api_keys[service_name] = []
                else:
                    logger.warning(f"Key file {file_path} not found for service '{service_name}'. No keys loaded for this service.")
                    self.api_keys[service_name] = []
            except json.JSONDecodeError:
                logger.error(f"Error decoding JSON from key file {file_path} for service '{service_name}'.")
                self.api_keys[service_name] = []
            except Exception as e:
                logger.error(f"An unexpected error occurred while loading keys for service '{service_name}' from {file_path}: {e}")
                self.api_keys[service_name] = []

    def get_key(self, service_name: str) -> Optional[str]:
        """
        Возвращает текущий активный API ключ для указанного сервиса.
        Если ключи закончились или не загружены, возвращает None.
        """
        if service_name not in self.api_keys or not self.api_keys[service_name]:
            logger.warning(f"No API keys available for service '{service_name}'.")
            return None
        
        idx = self.current_key_indices.get(service_name, 0)
        if idx < len(self.api_keys[service_name]):
            return self.api_keys[service_name][idx]
        else:
            logger.warning(f"All API keys for service '{service_name}' have been tried.")
            return None

    def rotate_key(self, service_name: str) -> Optional[str]:
        """
        Переключается на следующий API ключ для указанного сервиса.
        Возвращает новый ключ или None, если все ключи были использованы.
        """
        if service_name not in self.api_keys or not self.api_keys[service_name]:
            logger.warning(f"Cannot rotate keys for service '{service_name}': no keys loaded.")
            return None

        current_idx = self.current_key_indices.get(service_name, 0)
        next_idx = current_idx + 1

        if next_idx < len(self.api_keys[service_name]):
            self.current_key_indices[service_name] = next_idx
            new_key = self.api_keys[service_name][next_idx]
            logger.info(f"Rotated API key for service '{service_name}'. New key index: {next_idx}")
            return new_key
        else:
            # Все ключи были перебраны, можно либо остановиться, либо начать сначала (циклическая ротация)
            # Пока просто останавливаемся и сообщаем об этом
            logger.warning(f"All API keys for service '{service_name}' have been tried. Cannot rotate further.")
            # Устанавливаем индекс за пределы списка, чтобы get_key возвращал None
            self.current_key_indices[service_name] = len(self.api_keys[service_name]) 
            return None

    def reset_keys(self, service_name: str):
        """Сбрасывает индекс текущего ключа на начало списка для указанного сервиса."""
        if service_name in self.api_keys and self.api_keys[service_name]:
            self.current_key_indices[service_name] = 0
            logger.info(f"Reset API key index for service '{service_name}'.")

# Пример использования (для тестирования, будет удален или закомментирован)
if __name__ == '__main__':
    # Создаем временные файлы ключей для теста
    with open("temp_openai_keys.json", "w") as f:
        json.dump(["openai_key_1", "openai_key_2"], f)
    with open("temp_gemini_keys.json", "w") as f:
        json.dump(["gemini_key_1"], f)

    key_manager = ApiKeyManager({
        "openai": "temp_openai_keys.json",
        "gemini": "temp_gemini_keys.json",
        "nonexistent": "nonexistent_keys.json"
    })

    print(f"OpenAI Key 1: {key_manager.get_key('openai')}")
    key_manager.rotate_key('openai')
    print(f"OpenAI Key 2: {key_manager.get_key('openai')}")
    key_manager.rotate_key('openai')
    print(f"OpenAI Key 3 (should be None): {key_manager.get_key('openai')}")
    
    key_manager.reset_keys('openai')
    print(f"OpenAI Key after reset: {key_manager.get_key('openai')}")

    print(f"Gemini Key 1: {key_manager.get_key('gemini')}")
    key_manager.rotate_key('gemini')
    print(f"Gemini Key 2 (should be None): {key_manager.get_key('gemini')}")

    print(f"Nonexistent service key: {key_manager.get_key('nonexistent')}")
    print(f"Unknown service key: {key_manager.get_key('unknown')}")

    # Удаляем временные файлы
    os.remove("temp_openai_keys.json")
    os.remove("temp_gemini_keys.json")
