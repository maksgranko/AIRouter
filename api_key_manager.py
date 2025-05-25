import json
import os
from typing import List, Dict, Optional
import logging

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
            
            if not self.api_keys.get(service_name):
                 self.current_key_indices[service_name] = -1


    def get_key(self, service_name: str, peek: bool = False) -> Optional[str]:
        """
        Возвращает текущий активный API ключ для указанного сервиса.
        Если peek=True, не изменяет текущий индекс.
        Если ключи не загружены, возвращает None.
        При первом вызове (если индекс -1) для сервиса с ключами, устанавливает индекс на 0 (если не peek).
        """
        if service_name not in self.api_keys or not self.api_keys[service_name]:
            return None
        
        keys_for_service = self.api_keys[service_name]
        current_idx = self.current_key_indices.get(service_name, -1)

        if current_idx == -1:
            if not keys_for_service:
                return None
            if not peek:
                self.current_key_indices[service_name] = 0
                logger.info(f"Initialized key index for service '{service_name}' to 0.")
                return keys_for_service[0]
            else:
                return keys_for_service[0]
        
        if 0 <= current_idx < len(keys_for_service):
            return keys_for_service[current_idx]
        else:
            # Этого не должно происходить, если rotate_key и reset_keys работают правильно
            logger.error(f"Invalid key index {current_idx} for service '{service_name}' with {len(keys_for_service)} keys. Resetting to 0.")
            if not peek:
                self.current_key_indices[service_name] = 0
                return keys_for_service[0] if keys_for_service else None
            else:
                return keys_for_service[0] if keys_for_service else None


    def rotate_key(self, service_name: str) -> bool:
        """
        Переключается на следующий API ключ для указанного сервиса циклически.
        Возвращает True, если ключи существуют и ротация произошла (даже если вернулись к первому).
        Возвращает False, если ключей для сервиса нет.
        """
        if service_name not in self.api_keys or not self.api_keys[service_name]:
            logger.warning(f"Cannot rotate keys for service '{service_name}': no keys loaded.")
            return False

        keys_for_service = self.api_keys[service_name]
        current_idx = self.current_key_indices.get(service_name, -1)
        
        next_idx = current_idx + 1
        
        if next_idx >= len(keys_for_service):
            logger.info(f"Reached end of API key list for service '{service_name}'. Cycling back to the first key.")
            next_idx = 0 # Циклическая ротация
        
        self.current_key_indices[service_name] = next_idx
        logger.info(f"Rotated API key for service '{service_name}'. New key index: {next_idx}")
        return True

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
            keys_to_save = []
        else:
            keys_to_save = self.api_keys[service_name]

        file_path = self.key_files[service_name]
        try:
            # Убедимся, что директория существует
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w') as f:
                json.dump(keys_to_save, f, indent=2)
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
            self.current_key_indices[service_name] = 0
            if service_name not in self.key_files:
                 self.key_files[service_name] = f"{service_name}_keys.json"
                 logger.warning(f"No key file was defined for service '{service_name}', defaulting to '{self.key_files[service_name]}'.")


        if api_key not in self.api_keys[service_name]:
            self.api_keys[service_name].append(api_key)
            logger.info(f"Added API key for service '{service_name}'. Total keys: {len(self.api_keys[service_name])}")
            return self._save_keys_to_file(service_name)
        else:
            logger.warning(f"API key already exists for service '{service_name}'.")
            return False

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
            
            if not self.api_keys[service_name]:
                self.current_key_indices[service_name] = 0
            elif current_key_val == api_key_to_remove or self.current_key_indices[service_name] >= len(self.api_keys[service_name]):
                self.current_key_indices[service_name] = 0
            
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
        if service_name in self.api_keys:
            del self.api_keys[service_name]
        if service_name in self.current_key_indices:
            del self.current_key_indices[service_name]
        
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