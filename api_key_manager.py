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
            
    def _save_keys_to_file(self, service_name: str) -> bool:
        """Сохраняет текущий список ключей для сервиса в его JSON-файл."""
        if service_name not in self.key_files:
            logger.error(f"Cannot save keys for service '{service_name}': no file path defined.")
            return False
        if service_name not in self.api_keys:
            logger.warning(f"Cannot save keys for service '{service_name}': no keys loaded in memory.")
            # Если ключей нет, сохраняем пустой список
            keys_to_save = []
        else:
            keys_to_save = self.api_keys[service_name]

        file_path = self.key_files[service_name]
        try:
            # Убедимся, что директория существует
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w') as f:
                json.dump(keys_to_save, f, indent=2) # Сохраняем с отступом для читаемости
            logger.info(f"Successfully saved {len(keys_to_save)} API keys for service '{service_name}' to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving keys for service '{service_name}' to {file_path}: {e}")
            return False

    def add_key(self, service_name: str, api_key: str) -> bool:
        """Добавляет новый API ключ для сервиса и сохраняет в файл."""
        if not api_key or not isinstance(api_key, str):
            logger.error(f"Invalid API key provided for service '{service_name}'.")
            return False
            
        if service_name not in self.api_keys:
            self.api_keys[service_name] = []
            self.current_key_indices[service_name] = 0 # Инициализируем, если сервис новый
            if service_name not in self.key_files: # Если для сервиса нет файла, создаем запись (но это редкий случай)
                 self.key_files[service_name] = f"{service_name}_keys.json" # Имя файла по умолчанию
                 logger.warning(f"No key file was defined for service '{service_name}', defaulting to '{self.key_files[service_name]}'.")


        if api_key not in self.api_keys[service_name]:
            self.api_keys[service_name].append(api_key)
            logger.info(f"Added API key for service '{service_name}'. Total keys: {len(self.api_keys[service_name])}")
            return self._save_keys_to_file(service_name)
        else:
            logger.warning(f"API key already exists for service '{service_name}'.")
            return False # Ключ уже существует

    def remove_key(self, service_name: str, api_key_to_remove: str) -> bool:
        """Удаляет API ключ для сервиса и сохраняет в файл."""
        if service_name not in self.api_keys or not self.api_keys[service_name]:
            logger.warning(f"No keys to remove for service '{service_name}'.")
            return False
        
        if api_key_to_remove in self.api_keys[service_name]:
            # Перед удалением, если удаляемый ключ был текущим и единственным, или текущий индекс станет невалидным
            current_key_val = self.get_key(service_name)

            self.api_keys[service_name].remove(api_key_to_remove)
            logger.info(f"Removed API key for service '{service_name}'. Remaining keys: {len(self.api_keys[service_name])}")
            
            # Скорректировать current_key_index если необходимо
            if not self.api_keys[service_name]: # Если ключей не осталось
                self.current_key_indices[service_name] = 0 # или -1, чтобы get_key вернул None
            elif current_key_val == api_key_to_remove or self.current_key_indices[service_name] >= len(self.api_keys[service_name]):
                # Если удалили текущий ключ, или индекс стал невалидным (например, удалили ключ перед текущим)
                self.current_key_indices[service_name] = 0 # Сбрасываем на первый
            
            return self._save_keys_to_file(service_name)
        else:
            logger.warning(f"API key '{api_key_to_remove}' not found for service '{service_name}'.")
            return False

    def reload_keys_for_service(self, service_name: str):
        """Перезагружает ключи для указанного сервиса из его файла."""
        if service_name not in self.key_files:
            logger.error(f"Cannot reload keys for service '{service_name}': no file path defined.")
            return

        logger.info(f"Reloading keys for service '{service_name}' from {self.key_files[service_name]}...")
        # Удаляем старые данные для сервиса перед загрузкой
        if service_name in self.api_keys:
            del self.api_keys[service_name]
        if service_name in self.current_key_indices:
            del self.current_key_indices[service_name]
        
        # Используем часть логики из _load_keys, но только для одного сервиса
        file_path = self.key_files[service_name]
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    keys = json.load(f)
                    if isinstance(keys, list) and all(isinstance(key, str) for key in keys):
                        self.api_keys[service_name] = keys
                        self.current_key_indices[service_name] = 0
                        logger.info(f"Successfully reloaded {len(keys)} API keys for service '{service_name}'.")
                    else:
                        logger.error(f"Invalid format in key file {file_path} for service '{service_name}'. Expected a list of strings.")
                        self.api_keys[service_name] = []
            else:
                logger.warning(f"Key file {file_path} not found for service '{service_name}'. No keys reloaded.")
                self.api_keys[service_name] = []
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from key file {file_path} for service '{service_name}'.")
            self.api_keys[service_name] = []
        except Exception as e:
            logger.error(f"An unexpected error occurred while reloading keys for service '{service_name}': {e}")
            self.api_keys[service_name] = []


# Пример использования (для тестирования, будет удален или закомментирован)
if __name__ == '__main__':
    # Создаем временные файлы ключей для теста
    temp_openai_file = "temp_openai_keys.json"
    temp_gemini_file = "temp_gemini_keys.json"

    with open(temp_openai_file, "w") as f:
        json.dump(["openai_key_1", "openai_key_2"], f)
    with open(temp_gemini_file, "w") as f:
        json.dump(["gemini_key_1"], f)

    key_manager = ApiKeyManager({
        "openai": temp_openai_file,
        "gemini": temp_gemini_file
    })

    print("--- Initial Load ---")
    print(f"OpenAI Keys: {key_manager.api_keys.get('openai')}")
    print(f"Gemini Keys: {key_manager.api_keys.get('gemini')}")

    print("\n--- Adding Keys ---")
    key_manager.add_key("openai", "openai_key_3")
    key_manager.add_key("gemini", "gemini_key_2")
    key_manager.add_key("new_service", "new_service_key_1") # Тест добавления для нового сервиса
    print(f"OpenAI Keys after add: {key_manager.api_keys.get('openai')}")
    print(f"Gemini Keys after add: {key_manager.api_keys.get('gemini')}")
    print(f"New Service Keys: {key_manager.api_keys.get('new_service')}")


    print("\n--- Removing Keys ---")
    key_manager.remove_key("openai", "openai_key_1")
    key_manager.remove_key("gemini", "gemini_key_non_existent") # Тест удаления несуществующего
    print(f"OpenAI Keys after remove: {key_manager.api_keys.get('openai')}")
    
    # Проверка текущего ключа после удаления
    print(f"Current OpenAI Key: {key_manager.get_key('openai')}") # Должен быть openai_key_2 или openai_key_3
    key_manager.remove_key("openai", key_manager.get_key('openai')) # Удаляем текущий
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
