import json
import os
import secrets
from typing import List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AIROUTER_KEYS_FILE = os.path.join("configs", "airouter_api_keys.json")

class AIRouterApiKeyManager:
    def __init__(self, keys_file_path: str = AIROUTER_KEYS_FILE):
        """
        Инициализирует менеджер API ключей для AIRouter.
        :param keys_file_path: Путь к JSON-файлу со списком ключей.
        """
        self.keys_file_path = keys_file_path
        self.api_keys: List[str] = []
        self._load_keys()

    def _ensure_keys_file_exists(self):
        """Убеждается, что файл ключей существует, и создает его с пустым списком, если нет."""
        if not os.path.exists(self.keys_file_path):
            try:
                # Убедимся, что директория существует
                os.makedirs(os.path.dirname(self.keys_file_path), exist_ok=True)
                with open(self.keys_file_path, 'w') as f:
                    json.dump([], f)
                logger.info(f"Created default empty keys file: {self.keys_file_path}")
            except Exception as e:
                logger.error(f"Error creating default keys file {self.keys_file_path}: {e}")


    def _load_keys(self):
        """Загружает API ключи из указанного файла."""
        self._ensure_keys_file_exists()
        try:
            if os.path.exists(self.keys_file_path):
                with open(self.keys_file_path, 'r') as f:
                    keys = json.load(f)
                    if isinstance(keys, list) and all(isinstance(key, str) for key in keys):
                        self.api_keys = keys
                        logger.info(f"Successfully loaded {len(keys)} AIRouter API keys from {self.keys_file_path}")
                    else:
                        logger.error(f"Invalid format in key file {self.keys_file_path}. Expected a list of strings.")
                        self.api_keys = []
            else:
                logger.warning(f"Key file {self.keys_file_path} not found. No keys loaded.")
                self.api_keys = []
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from key file {self.keys_file_path}.")
            self.api_keys = []
        except Exception as e:
            logger.error(f"An unexpected error occurred while loading keys from {self.keys_file_path}: {e}")
            self.api_keys = []

    def _save_keys_to_file(self) -> bool:
        """Сохраняет текущий список ключей в JSON-файл."""
        self._ensure_keys_file_exists()
        try:
            with open(self.keys_file_path, 'w') as f:
                json.dump(self.api_keys, f, indent=2)
            logger.info(f"Successfully saved {len(self.api_keys)} AIRouter API keys to {self.keys_file_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving keys to {self.keys_file_path}: {e}")
            return False

    def get_all_keys(self) -> List[str]:
        """Возвращает все загруженные API ключи."""
        return self.api_keys

    def key_exists(self, api_key: str) -> bool:
        """Проверяет, существует ли указанный API ключ."""
        return api_key in self.api_keys

    def generate_and_add_key(self, length: int = 32) -> Optional[str]:
        """
        Генерирует новый API ключ, добавляет его в список и сохраняет в файл.
        :param length: Длина генерируемого токена (количество байт для hex-представления).
        :return: Сгенерированный ключ или None в случае ошибки.
        """
        new_key = secrets.token_hex(length)
        if self.add_key(new_key):
            return new_key
        return None

    def add_key(self, api_key: str) -> bool:
        """Добавляет новый API ключ и сохраняет в файл."""
        if not api_key or not isinstance(api_key, str):
            logger.error("Invalid API key provided.")
            return False
            
        if api_key not in self.api_keys:
            self.api_keys.append(api_key)
            logger.info(f"Added AIRouter API key. Total keys: {len(self.api_keys)}")
            return self._save_keys_to_file()
        else:
            logger.warning("AIRouter API key already exists.")
            return False

    def remove_key(self, api_key_to_remove: str) -> bool:
        """Удаляет API ключ и сохраняет в файл."""
        if not self.api_keys:
            logger.warning("No keys to remove.")
            return False
        
        if api_key_to_remove in self.api_keys:
            self.api_keys.remove(api_key_to_remove)
            logger.info(f"Removed AIRouter API key. Remaining keys: {len(self.api_keys)}")
            return self._save_keys_to_file()
        else:
            logger.warning(f"AIRouter API key '{api_key_to_remove}' not found.")
            return False

    def reload_keys(self):
        """Перезагружает ключи из файла."""
        logger.info(f"Reloading AIRouter API keys from {self.keys_file_path}...")
        self._load_keys()