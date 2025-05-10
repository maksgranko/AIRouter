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
                 proxy_file_path: str = "proxies.json", 
                 randomize_on_load: bool = True):
        """
        Инициализирует менеджер прокси.
        :param proxy_file_path: Путь к JSON-файлу со списком прокси.
        :param randomize_on_load: Перемешивать ли список прокси при загрузке.
        """
        self.proxy_file_path = proxy_file_path
        self.proxies: List[ProxyConfig] = []
        self.current_proxy_index: int = -1 
        self.randomize_on_load = randomize_on_load

        # Чтение настроек из переменных окружения
        self.use_proxies_env = os.getenv("USE_PROXIES", "true").lower() == "true"
        self.proxy_rotation_mode_env = os.getenv("PROXY_ROTATION_MODE", "once").lower() # "once" или "cycle"
        
        self.active = False # Становится True, если use_proxies_env=True и прокси успешно загружены

        if self.use_proxies_env:
            self._load_proxies()
            if self.proxies:
                self.active = True
                logger.info(f"ProxyManager is active. Rotation mode: {self.proxy_rotation_mode_env}.")
            else:
                logger.warning("ProxyManager is configured to use proxies, but no proxies were loaded. Will operate without proxies.")
        else:
            logger.info("ProxyManager is disabled via USE_PROXIES=false. Operating without proxies.")


    def _load_proxies(self):
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
            if self.proxy_rotation_mode_env == "cycle":
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
        if use_proxies:
            if not self.proxies: # Если список прокси пуст
                self._load_proxies() # Попытка загрузить, если ранее не были загружены
            
            if self.proxies: # Если прокси есть (или были успешно загружены)
                self.active = True
                logger.info(f"Proxy usage enabled. Current mode: {self.proxy_rotation_mode_env}. Proxies available: {len(self.proxies)}")
            else:
                self.active = False # Не удалось загрузить прокси
                logger.warning("Attempted to enable proxies, but no proxies are loaded. Proxies remain disabled.")
        else:
            self.active = False
            logger.info("Proxy usage disabled.")
        # Эта настройка не меняет self.use_proxies_env, которая отражает исходную настройку из окружения.
        # Она меняет только текущее рабочее состояние self.active.

    def set_rotation_mode(self, mode: str):
        """Устанавливает режим ротации прокси во время выполнения."""
        if mode in ["once", "cycle"]:
            self.proxy_rotation_mode_env = mode # Перезаписываем значение из окружения для текущей сессии
            logger.info(f"Proxy rotation mode set to: {self.proxy_rotation_mode_env}")
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
        
        # Если менеджер не был активен из-за отсутствия прокси, но теперь прокси есть и USE_PROXIES=true
        if not self.active and self.use_proxies_env and self.proxies:
            self.active = True
            if self.current_proxy_index == -1 : # Если это первый добавленный прокси
                 self.current_proxy_index = 0
            logger.info("ProxyManager became active after adding a proxy.")
        elif self.active and self.current_proxy_index == -1 and len(self.proxies) == 1:
            # Если был активен, но список был пуст (например, все удалили), и добавили первый
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
        # self.active будет обновлен в _load_proxies в зависимости от use_proxies_env и наличия прокси
        initial_active_state = self.active 
        self.active = False # Временно деактивируем перед загрузкой

        if self.use_proxies_env:
            self._load_proxies()
            if self.proxies:
                self.active = True
                logger.info(f"Proxies reloaded. Active: {self.active}, Count: {len(self.proxies)}, Mode: {self.proxy_rotation_mode_env}")
            else:
                # self.active остается False, если прокси не загрузились
                logger.warning("Proxies reloaded, but no proxies found or file error. ProxyManager remains inactive or becomes inactive.")
        else: # Если USE_PROXIES=false, то менеджер не должен быть активен
            self.active = False
            logger.info("Proxies reloaded, but USE_PROXIES is false. ProxyManager remains disabled.")


# Пример использования (для тестирования)
if __name__ == '__main__':
    # Установка переменных окружения для теста
    # os.environ["USE_PROXIES"] = "true" 
    # os.environ["PROXY_ROTATION_MODE"] = "cycle"

    # Создаем временный файл прокси для теста
    temp_proxy_file = "temp_proxies.json"
    with open(temp_proxy_file, "w") as f:
        json.dump([
            {"type": "http", "url": "http://proxy1.com:8080"},
            {"type": "socks5", "url": "socks5://proxy2.com:1080"},
            {"type": "http", "url": "http://proxy3.com:3128"}
        ], f)

    proxy_manager_no_random = ProxyManager(proxy_file_path=temp_proxy_file, randomize_on_load=False)
    print("--- Testing with randomize_on_load=False ---")
    print(f"Initial Proxy: {proxy_manager_no_random.get_proxy()}")
    proxy_manager_no_random.rotate_proxy()
    print(f"Rotated Proxy 1: {proxy_manager_no_random.get_proxy()}")
    proxy_manager_no_random.rotate_proxy()
    print(f"Rotated Proxy 2: {proxy_manager_no_random.get_proxy()}")
    proxy_manager_no_random.rotate_proxy()
    print(f"Rotated Proxy 3 (should be None): {proxy_manager_no_random.get_proxy()}")
    proxy_manager_no_random.reset_proxies()
    print(f"Proxy after reset: {proxy_manager_no_random.get_proxy()}")

    print("\n--- Testing with randomize_on_load=True ---")
    proxy_manager_random = ProxyManager(proxy_file_path=temp_proxy_file, randomize_on_load=True)
    print(f"Initial Proxy (randomized): {proxy_manager_random.get_proxy()}")
    p1 = proxy_manager_random.get_proxy()
    proxy_manager_random.rotate_proxy()
    p2 = proxy_manager_random.get_proxy()
    print(f"Rotated Proxy 1 (randomized): {p2}")
    assert p1 != p2 or len(proxy_manager_random.proxies) == 1 # Проверка, что прокси действительно меняются (если их больше одного)
    
    os.remove(temp_proxy_file)
