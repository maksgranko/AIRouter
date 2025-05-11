import json
import os
from typing import List, Dict, Optional, TypedDict
import logging
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProxyConfig(TypedDict):
    type: str # "http", "socks4", "socks5"
    url: str

class ProxyManager:
    def __init__(self, 
                 proxy_file_path: str, 
                 settings_file_path: str, # Новый параметр
                 randomize_on_load: bool = True):
        """
        Инициализирует менеджер прокси.
        :param proxy_file_path: Путь к JSON-файлу со списком прокси.
        :param settings_file_path: Путь к JSON-файлу с общими настройками.
        :param randomize_on_load: Перемешивать ли список прокси при загрузке.
        """
        self.proxy_file_path = proxy_file_path
        self.settings_file_path = settings_file_path # Сохраняем путь
        self.proxies: List[ProxyConfig] = []
        self.current_proxy_index: int = -1 
        self.randomize_on_load = randomize_on_load

        # Начальные значения, которые могут быть переопределены
        self.current_use_proxies: bool = True 
        self.current_rotation_mode: str = "once"

        self._load_runtime_settings() # Загружаем настройки из settings.json

        # Переменные окружения имеют приоритет для начальной конфигурации
        env_use_proxies_val = os.getenv("USE_PROXIES")
        if env_use_proxies_val is not None:
            self.current_use_proxies = env_use_proxies_val.lower() == "true"
        
        env_proxy_rotation_mode_val = os.getenv("PROXY_ROTATION_MODE")
        if env_proxy_rotation_mode_val is not None:
            if env_proxy_rotation_mode_val.lower() in ["once", "cycle"]:
                self.current_rotation_mode = env_proxy_rotation_mode_val.lower()
            else:
                logger.warning(f"Invalid PROXY_ROTATION_MODE from env: '{env_proxy_rotation_mode_val}'. Using '{self.current_rotation_mode}'.")
        
        self.active = False 

        if self.current_use_proxies:
            self._load_proxies_from_file() # Используем новое имя метода
            if self.proxies:
                self.active = True
                logger.info(f"ProxyManager is active. Rotation mode: {self.current_rotation_mode}.")
            else:
                logger.warning("ProxyManager is set to use proxies, but no proxies were loaded. Will operate without proxies.")
        else:
            logger.info("ProxyManager is disabled by configuration (USE_PROXIES=false or settings.json). Operating without proxies.")

    def _load_runtime_settings(self):
        """Загружает настройки use_proxies и rotation_mode из settings.json."""
        try:
            if os.path.exists(self.settings_file_path):
                with open(self.settings_file_path, 'r') as f:
                    settings = json.load(f)
                    proxy_settings = settings.get("proxy_settings", {})
                    
                    if "use_proxies" in proxy_settings: # Загружаем, только если ключ существует
                        self.current_use_proxies = bool(proxy_settings["use_proxies"])
                    if "rotation_mode" in proxy_settings and proxy_settings["rotation_mode"] in ["once", "cycle"]:
                         self.current_rotation_mode = proxy_settings["rotation_mode"]
                    logger.info(f"Loaded proxy settings from {self.settings_file_path}: use_proxies={self.current_use_proxies}, rotation_mode={self.current_rotation_mode}")
            else:
                logger.info(f"{self.settings_file_path} not found. Using defaults or environment variables for proxy settings.")
                # Если файл не найден, сохраняем текущие (дефолтные/из env) настройки, чтобы файл создался
                self._save_runtime_settings() 
        except Exception as e:
            logger.error(f"Error loading runtime proxy settings from {self.settings_file_path}: {e}. Using defaults or environment variables.")

    def _save_runtime_settings(self):
        """Сохраняет текущие proxy_settings (use_proxies, rotation_mode) в settings.json."""
        try:
            all_settings = {}
            if os.path.exists(self.settings_file_path):
                try:
                    with open(self.settings_file_path, 'r') as f:
                        all_settings = json.load(f)
                except json.JSONDecodeError: # Если файл пуст или испорчен
                    logger.warning(f"Could not decode JSON from {self.settings_file_path}, will overwrite with new settings.")
                    all_settings = {} # Начинаем с чистого листа
            
            all_settings["proxy_settings"] = {
                "use_proxies": self.current_use_proxies,
                "rotation_mode": self.current_rotation_mode
            }
            
            # Убедимся, что директория существует
            os.makedirs(os.path.dirname(self.settings_file_path), exist_ok=True)

            with open(self.settings_file_path, 'w') as f:
                json.dump(all_settings, f, indent=2)
            logger.info(f"Saved proxy settings to {self.settings_file_path}: use_proxies={self.current_use_proxies}, rotation_mode={self.current_rotation_mode}")
        except Exception as e:
            logger.error(f"Error saving runtime proxy settings to {self.settings_file_path}: {e}")

    def _load_proxies_from_file(self): # Переименован
        """Загружает прокси из указанного файла."""
        try:
            if os.path.exists(self.proxy_file_path):
                with open(self.proxy_file_path, 'r') as f:
                    loaded_proxies = json.load(f)
                    if isinstance(loaded_proxies, list):
                        self.proxies = []
                        for proxy_data in loaded_proxies:
                            if isinstance(proxy_data, dict) and "type" in proxy_data and "url" in proxy_data:
                                self.proxies.append(ProxyConfig(type=proxy_data["type"], url=proxy_data["url"]))
                            else:
                                logger.warning(f"Invalid proxy entry format in {self.proxy_file_path}: {proxy_data}. Skipping.")
                        
                        if self.proxies:
                            if self.randomize_on_load:
                                random.shuffle(self.proxies)
                                logger.info(f"Successfully loaded and randomized {len(self.proxies)} proxies from {self.proxy_file_path}.")
                            else:
                                logger.info(f"Successfully loaded {len(self.proxies)} proxies from {self.proxy_file_path}.")
                            self.current_proxy_index = 0 
                        else:
                            logger.warning(f"No valid proxies found in {self.proxy_file_path}.")
                            self.current_proxy_index = -1
                    else:
                        logger.error(f"Invalid format in proxy file {self.proxy_file_path}. Expected a list of proxy objects.")
                        self.current_proxy_index = -1
            else:
                logger.warning(f"Proxy file {self.proxy_file_path} not found. No proxies loaded.")
                self.current_proxy_index = -1
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from proxy file {self.proxy_file_path}.")
            self.current_proxy_index = -1
        except Exception as e:
            logger.error(f"An unexpected error occurred while loading proxies from {self.proxy_file_path}: {e}")
            self.current_proxy_index = -1

    def get_proxy(self) -> Optional[ProxyConfig]:
        """
        Возвращает текущий активный прокси, если менеджер активен и прокси доступны.
        """
        if not self.active or not self.proxies or self.current_proxy_index < 0 or self.current_proxy_index >= len(self.proxies):
            logger.debug("ProxyManager inactive or no proxies available / all tried (in 'once' mode).")
            return None
        return self.proxies[self.current_proxy_index]

    def rotate_proxy(self) -> Optional[ProxyConfig]:
        """
        Переключается на следующий прокси. Учитывает PROXY_ROTATION_MODE.
        Возвращает новый прокси или None, если ротация невозможна или не включена.
        """
        if not self.active or not self.proxies or self.current_proxy_index < 0 :
            logger.warning("Cannot rotate proxy: ProxyManager inactive or no proxies loaded.")
            return None

        self.current_proxy_index += 1
        if self.current_proxy_index < len(self.proxies):
            new_proxy = self.proxies[self.current_proxy_index]
            logger.info(f"Rotated to next proxy: {new_proxy['url']} (Index: {self.current_proxy_index})")
            return new_proxy
        else: # Индекс вышел за пределы списка
            if self.current_rotation_mode == "cycle": # Исправлено на current_rotation_mode
                logger.info("Reached end of proxy list. Cycling back to the first proxy.")
                self.current_proxy_index = 0
                return self.proxies[self.current_proxy_index]
            else: # Режим "once" (по умолчанию)
                logger.warning("All proxies have been tried (mode 'once'). Cannot rotate further for the current cycle.")
                # current_proxy_index остается >= len(self.proxies), get_proxy() вернет None
                return None
            
    def reset_proxies(self):
        """
        Сбрасывает индекс текущего прокси на начало списка.
        Перемешивает список, если randomize_on_load=True.
        Эта функция вызывается, например, при смене API ключа.
        """
        if not self.active or not self.proxies:
            logger.debug("ProxyManager inactive or no proxies to reset.")
            return

        if self.randomize_on_load:
            random.shuffle(self.proxies)
            logger.info("Proxies have been re-shuffled during reset.")
        self.current_proxy_index = 0
        current_proxy_url = self.get_proxy()['url'] if self.get_proxy() else 'None'
        logger.info(f"Proxy index reset. Current proxy: {current_proxy_url}")

    def set_use_proxies(self, use_proxies: bool):
        """Включает или выключает использование прокси во время выполнения."""
        # 1. Обновить желаемое состояние
        self.current_use_proxies = use_proxies

        # 2. Попытаться актуализировать активное состояние на основе желаемого
        if use_proxies: # Желаем включить
            if not self.proxies: # Если прокси не загружены
                self._load_proxies_from_file() # Попытаться загрузить
            
            if self.proxies: # Если прокси есть (после попытки загрузки)
                self.active = True
                logger.info(f"Proxy usage set to enabled. Proxies available: {len(self.proxies)}. Active: {self.active}.")
            else:
                self.active = False # Не удалось загрузить/нет прокси
                logger.warning("Proxy usage set to enabled, but no proxies are loaded. ProxyManager remains inactive.")
        else: # Желаем выключить
            self.active = False
            logger.info("Proxy usage set to disabled. ProxyManager is inactive.")
        
        # 3. Сохранить желаемое состояние в файл
        self._save_runtime_settings()

    def set_rotation_mode(self, mode: str):
        """Устанавливает режим ротации прокси во время выполнения и сохраняет в settings.json."""
        if mode in ["once", "cycle"]:
            self.current_rotation_mode = mode # Обновляем текущее состояние
            logger.info(f"Proxy rotation mode set to: {self.current_rotation_mode}")
            self._save_runtime_settings() # Сохраняем в settings.json
            # При смене режима, имеет смысл сбросить текущий индекс, чтобы начать с начала списка
            self.reset_proxies() 
        else:
            logger.warning(f"Invalid proxy rotation mode: {mode}. Mode not changed. Allowed: 'once', 'cycle'.")

    def _save_proxies_to_file(self) -> bool:
        """Сохраняет текущий список прокси в JSON-файл."""
        if not self.proxy_file_path: # На случай, если путь не задан (хотя он задается в __init__)
            logger.error("Cannot save proxies: proxy_file_path is not defined.")
            return False
        
        # Мы сохраняем self.proxies, который является List[ProxyConfig]
        # ProxyConfig - это TypedDict, который при сериализации в JSON станет обычным dict.
        try:
            # Убедимся, что директория существует
            os.makedirs(os.path.dirname(self.proxy_file_path), exist_ok=True)
            with open(self.proxy_file_path, 'w') as f:
                json.dump(self.proxies, f, indent=2)
            logger.info(f"Successfully saved {len(self.proxies)} proxies to {self.proxy_file_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving proxies to {self.proxy_file_path}: {e}")
            return False

    def add_proxy(self, proxy_type: str, proxy_url: str) -> bool:
        """Добавляет новый прокси в список и сохраняет в файл."""
        if not proxy_type or not proxy_url:
            logger.error("Invalid proxy type or URL provided.")
            return False
        
        new_proxy = ProxyConfig(type=proxy_type.lower(), url=proxy_url.strip())

        # Проверка на дубликаты (по URL)
        if any(p['url'] == new_proxy['url'] for p in self.proxies):
            logger.warning(f"Proxy with URL '{new_proxy['url']}' already exists. Not adding.")
            return False

        self.proxies.append(new_proxy)
        logger.info(f"Added proxy: {new_proxy}. Total proxies: {len(self.proxies)}")
        
        # Если менеджер не был активен из-за отсутствия прокси, но теперь прокси есть и self.current_use_proxies=True
        if not self.active and self.current_use_proxies and self.proxies: 
            self.active = True
            if self.current_proxy_index == -1 : # Если это первый добавленный прокси
                 self.current_proxy_index = 0
            logger.info("ProxyManager became active after adding a proxy.")
        # Если менеджер был активен, но список прокси был пуст (например, все удалили), и мы добавляем первый
        elif self.active and self.current_proxy_index == -1 and len(self.proxies) == 1: 
            self.current_proxy_index = 0


        return self._save_proxies_to_file()

    def remove_proxy(self, proxy_url_to_remove: str) -> bool:
        """Удаляет прокси по URL из списка и сохраняет в файл."""
        if not self.proxies:
            logger.warning("No proxies to remove.")
            return False

        initial_len = len(self.proxies)
        # Сохраняем текущий выбранный прокси, если он есть
        current_selected_proxy_obj = self.get_proxy()

        self.proxies = [p for p in self.proxies if p['url'] != proxy_url_to_remove]

        if len(self.proxies) < initial_len:
            logger.info(f"Removed proxy with URL '{proxy_url_to_remove}'. Remaining proxies: {len(self.proxies)}")
            
            if not self.proxies: # Если все прокси удалены
                self.current_proxy_index = -1
                # self.active остается True, если use_proxies_env=True, но get_proxy() вернет None
                logger.info("All proxies removed.")
            elif current_selected_proxy_obj and current_selected_proxy_obj['url'] == proxy_url_to_remove:
                # Если удалили текущий выбранный прокси, сбрасываем индекс на начало
                self.reset_proxies() # reset_proxies установит current_proxy_index = 0
            elif self.current_proxy_index >= len(self.proxies):
                 # Если удалили прокси перед текущим, и индекс стал невалидным
                 self.current_proxy_index = 0 if self.proxies else -1


            return self._save_proxies_to_file()
        else:
            logger.warning(f"Proxy with URL '{proxy_url_to_remove}' not found.")
            return False
            
    def reload_proxies(self):
        """Перезагружает список прокси из файла."""
        logger.info(f"Reloading proxies from {self.proxy_file_path}...")
        self.proxies = []
        self.current_proxy_index = -1
        self.active = False # Временно деактивируем перед загрузкой

        # Используем self.current_use_proxies, которое отражает актуальную настройку
        if self.current_use_proxies:
            self._load_proxies_from_file() 
            if self.proxies: # Если после загрузки прокси есть
                self.active = True
                logger.info(f"Proxies reloaded. Active: {self.active}, Count: {len(self.proxies)}, Mode: {self.current_rotation_mode}")
            else:
                self.active = False 
                logger.warning("Proxies reloaded, but no proxies found or file error. ProxyManager remains inactive.")
        else: 
            self.active = False
            logger.info("Proxies reloaded, but current_use_proxies is false. ProxyManager remains disabled.")


# Пример использования (для тестирования)
if __name__ == '__main__':
    # Создаем временные файлы для теста
    temp_config_dir = "temp_test_configs"
    os.makedirs(temp_config_dir, exist_ok=True)

    temp_settings_file = os.path.join(temp_config_dir, "settings.json")
    temp_proxy_file = os.path.join(temp_config_dir, "proxies.json")
    
    with open(temp_settings_file, "w") as f:
        json.dump({"proxy_settings": {"use_proxies": True, "rotation_mode": "once"}}, f)
    
    with open(temp_proxy_file, "w") as f:
        json.dump([
            {"type": "http", "url": "http://proxy1.com:8080"},
            {"type": "socks5", "url": "socks5://proxy2.com:1080"},
            {"type": "http", "url": "http://proxy3.com:3128"}
        ], f)

    proxy_manager_test = ProxyManager(
        proxy_file_path=temp_proxy_file, 
        settings_file_path=temp_settings_file, 
        randomize_on_load=False
    )
    print("--- Testing ProxyManager ---")
    print(f"ProxyManager Active: {proxy_manager_test.active}")
    print(f"Initial Proxy: {proxy_manager_test.get_proxy()}")
    proxy_manager_test.rotate_proxy()
    print(f"Rotated Proxy 1: {proxy_manager_test.get_proxy()}")
    proxy_manager_test.add_proxy("http", "http://newproxy.com")
    print(f"Proxies after add: {proxy_manager_test.proxies}")
    proxy_manager_test.remove_proxy("http://proxy1.com:8080")
    print(f"Proxies after remove: {proxy_manager_test.proxies}")
    
    # Тест set_use_proxies и set_rotation_mode
    proxy_manager_test.set_use_proxies(False)
    print(f"ProxyManager Active after set_use_proxies(False): {proxy_manager_test.active}")
    proxy_manager_test.set_use_proxies(True)
    print(f"ProxyManager Active after set_use_proxies(True): {proxy_manager_test.active}")
    proxy_manager_test.set_rotation_mode("cycle")
    print(f"Rotation mode after set_rotation_mode('cycle'): {proxy_manager_test.current_rotation_mode}")


    # Очистка
    if os.path.exists(temp_proxy_file):
        os.remove(temp_proxy_file)
    if os.path.exists(temp_settings_file):
        os.remove(temp_settings_file)
    if os.path.exists(temp_config_dir) and not os.listdir(temp_config_dir): 
        os.rmdir(temp_config_dir)
