import json
import os
from typing import List, Dict, Optional, TypedDict
import logging
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProxyConfig(TypedDict):
    type: str
    url: str

class ProxyManager:
    def __init__(self,
                 proxy_file_path: str,
                 settings_file_path: str,
                 randomize_on_load: bool = True):
        self.proxy_file_path = proxy_file_path
        self.settings_file_path = settings_file_path
        self.proxies: List[ProxyConfig] = []
        self.current_proxy_index: int = -1
        self.current_use_proxies: bool = True
        self.current_rotation_mode: str = "once"
        self.select_random_proxy_each_request: bool = False

        self._load_runtime_settings()
        env_use_proxies_val = os.getenv("USE_PROXIES")
        if env_use_proxies_val is not None:
            self.current_use_proxies = env_use_proxies_val.lower() == "true"
        env_proxy_rotation_mode_val = os.getenv("PROXY_ROTATION_MODE")
        if env_proxy_rotation_mode_val is not None:
            if env_proxy_rotation_mode_val.lower() in ["once", "cycle", "failover_cycle"]:
                self.current_rotation_mode = env_proxy_rotation_mode_val.lower()
            else:
                logger.warning(f"Invalid PROXY_ROTATION_MODE from env: '{env_proxy_rotation_mode_val}'. Using '{self.current_rotation_mode}'.")
        env_select_random_proxy_val = os.getenv("SELECT_RANDOM_PROXY_EACH_REQUEST")
        if env_select_random_proxy_val is not None:
            self.select_random_proxy_each_request = env_select_random_proxy_val.lower() == "true"
        self.active = False
        if self.current_use_proxies:
            self._load_proxies_from_file()
            if self.proxies:
                self.active = True
                logger.info(f"ProxyManager is active. Rotation mode: {self.current_rotation_mode}.")
            else:
                logger.warning("ProxyManager is set to use proxies, but no proxies were loaded. Will operate without proxies.")
        else:
            logger.info("ProxyManager is disabled by configuration (USE_PROXIES=false or settings.json). Operating without proxies.")

    def _load_runtime_settings(self):
        try:
            if os.path.exists(self.settings_file_path):
                with open(self.settings_file_path, 'r') as f:
                    settings = json.load(f)
                    proxy_settings = settings.get("proxy_settings", {})
                    if "use_proxies" in proxy_settings:
                        self.current_use_proxies = bool(proxy_settings["use_proxies"])
                    if "rotation_mode" in proxy_settings and proxy_settings["rotation_mode"] in ["once", "cycle", "failover_cycle"]:
                         self.current_rotation_mode = proxy_settings["rotation_mode"]
                    if "select_random_proxy_each_request" in proxy_settings:
                        self.select_random_proxy_each_request = bool(proxy_settings["select_random_proxy_each_request"])
                    logger.info(f"Loaded proxy settings from {self.settings_file_path}: use_proxies={self.current_use_proxies}, rotation_mode={self.current_rotation_mode}, select_random_proxy_each_request={self.select_random_proxy_each_request}")
            else:
                logger.info(f"{self.settings_file_path} not found. Using defaults or environment variables for proxy settings.")
                self._save_runtime_settings()
        except Exception as e:
            logger.error(f"Error loading runtime proxy settings from {self.settings_file_path}: {e}. Using defaults or environment variables.")

    def _save_runtime_settings(self):
        try:
            all_settings = {}
            if os.path.exists(self.settings_file_path):
                try:
                    with open(self.settings_file_path, 'r') as f:
                        all_settings = json.load(f)
                except json.JSONDecodeError:
                    logger.warning(f"Could not decode JSON from {self.settings_file_path}, will overwrite with new settings.")
                    all_settings = {}
            all_settings["proxy_settings"] = {
                "use_proxies": self.current_use_proxies,
                "rotation_mode": self.current_rotation_mode,
                "select_random_proxy_each_request": self.select_random_proxy_each_request
            }
            os.makedirs(os.path.dirname(self.settings_file_path), exist_ok=True)
            with open(self.settings_file_path, 'w') as f:
                json.dump(all_settings, f, indent=2)
            logger.info(f"Saved proxy settings to {self.settings_file_path}: use_proxies={self.current_use_proxies}, rotation_mode={self.current_rotation_mode}, select_random_proxy_each_request={self.select_random_proxy_each_request}")
        except Exception as e:
            logger.error(f"Error saving runtime proxy settings to {self.settings_file_path}: {e}")

    def _load_proxies_from_file(self):
        try:
            if os.path.exists(self.proxy_file_path):
                with open(self.proxy_file_path, 'r') as f:
                    loaded_proxies = json.load(f)
                    if isinstance(loaded_proxies, list):
                        self.proxies = []
                        for proxy_data in loaded_proxies:
                            if isinstance(proxy_data, dict) and "type" in proxy_data and "url" in proxy_data:
                                proxy_type = proxy_data["type"].lower()
                                proxy_url = proxy_data["url"].strip()
                                corrected_url = self._ensure_correct_scheme(proxy_url, proxy_type)
                                if corrected_url != proxy_url:
                                    logger.info(f"Corrected URL scheme for proxy type '{proxy_type}': '{proxy_url}' -> '{corrected_url}'")
                                self.proxies.append(ProxyConfig(type=proxy_type, url=corrected_url))
                            else:
                                logger.warning(f"Invalid proxy entry format in {self.proxy_file_path}: {proxy_data}. Skipping.")
                        if self.proxies:
                            logger.info(f"Successfully loaded {len(self.proxies)} proxies from {self.proxy_file_path} (order preserved).")
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
        if not self.active or not self.proxies:
            logger.debug("ProxyManager inactive or no proxies loaded.")
            return None
        if self.select_random_proxy_each_request:
            selected_proxy = random.choice(self.proxies)
            logger.debug(f"Random proxy selected: {selected_proxy['url']}")
            return selected_proxy
        if self.current_proxy_index < 0 or self.current_proxy_index >= len(self.proxies):
            logger.debug("No valid proxy index for sequential selection / all tried (in 'once' mode).")
            return None
        return self.proxies[self.current_proxy_index]

    def rotate_proxy(self) -> Optional[ProxyConfig]:
        if not self.active or not self.proxies:
            logger.warning("Cannot rotate proxy: ProxyManager inactive or no proxies loaded.")
            return None
        if self.select_random_proxy_each_request:
            logger.debug("rotate_proxy called in random selection mode. No index change. Next get_proxy() will be random.")
            return None
        if self.current_proxy_index < 0:
            self.current_proxy_index = 0
            new_proxy = self.proxies[self.current_proxy_index]
            logger.info(f"Proxy index was invalid, reset to 0. Current proxy: {new_proxy['url']}")
            return new_proxy
        self.current_proxy_index += 1
        if self.current_proxy_index < len(self.proxies):
            new_proxy = self.proxies[self.current_proxy_index]
            logger.info(f"Rotated to next proxy: {new_proxy['url']} (Index: {self.current_proxy_index})")
            return new_proxy
        else:
            if self.current_rotation_mode == "cycle" or self.current_rotation_mode == "failover_cycle":
                logger.info(f"Reached end of proxy list in mode '{self.current_rotation_mode}'. Cycling back to the first proxy.")
                self.current_proxy_index = 0
                return self.proxies[self.current_proxy_index]
            elif self.current_rotation_mode == "once":
                logger.warning("All proxies have been tried (mode 'once'). Cannot rotate further for the current cycle.")
                return None

    def reset_proxies(self):
        if not self.active or not self.proxies:
            logger.debug("ProxyManager inactive or no proxies to reset.")
            return
        self.current_proxy_index = 0
        current_proxy_url = self.get_proxy()['url'] if self.get_proxy() else 'None'
        logger.info(f"Proxy index reset. Current proxy: {current_proxy_url}. List order preserved during reset.")

    def set_use_proxies(self, use_proxies: bool):
        self.current_use_proxies = use_proxies
        if use_proxies:
            if not self.proxies:
                self._load_proxies_from_file()
            if self.proxies:
                self.active = True
                logger.info(f"Proxy usage set to enabled. Proxies available: {len(self.proxies)}. Active: {self.active}.")
            else:
                self.active = False
                logger.warning("Proxy usage set to enabled, but no proxies are loaded. ProxyManager remains inactive.")
        else:
            self.active = False
            logger.info("Proxy usage set to disabled. ProxyManager is inactive.")
        self._save_runtime_settings()

    def set_rotation_mode(self, mode: str):
        if mode in ["once", "cycle", "failover_cycle"]:
            self.current_rotation_mode = mode
            logger.info(f"Proxy rotation mode set to: {self.current_rotation_mode}")
            self._save_runtime_settings()
            self.reset_proxies()
        else:
            logger.warning(f"Invalid proxy rotation mode: {mode}. Mode not changed. Allowed: 'once', 'cycle', 'failover_cycle'.")

    def set_select_random_proxy_each_request(self, select_random: bool):
        self.select_random_proxy_each_request = select_random
        logger.info(f"Proxy selection mode set to: {'random_each_request' if self.select_random_proxy_each_request else 'sequential'}")
        self._save_runtime_settings()
        if not self.select_random_proxy_each_request:
            self.reset_proxies()

    def _ensure_correct_scheme(self, url: str, proxy_type: str) -> str:
        url = url.strip()
        proxy_type = proxy_type.lower()
        current_scheme = ""
        if "://" in url:
            current_scheme = url.split("://", 1)[0].lower()
        expected_scheme = proxy_type
        if proxy_type == "http" and current_scheme == "https":
            expected_scheme = "https"
        elif proxy_type not in ["http", "https", "socks4", "socks5"]:
            logger.warning(f"Unknown proxy type '{proxy_type}' for URL '{url}'. Cannot ensure correct scheme.")
            return url
        if current_scheme == expected_scheme:
            return url
        url_no_scheme = url.split("://", 1)[-1] if "://" in url else url
        if not url_no_scheme:
            logger.warning(f"URL became empty after attempting to correct scheme for type '{proxy_type}', original URL '{url}'.")
            return url
        return f"{expected_scheme}://{url_no_scheme}"

    def _save_proxies_to_file(self) -> bool:
        if not self.proxy_file_path:
            logger.error("Cannot save proxies: proxy_file_path is not defined.")
            return False
        try:
            os.makedirs(os.path.dirname(self.proxy_file_path), exist_ok=True)
            with open(self.proxy_file_path, 'w') as f:
                json.dump(self.proxies, f, indent=2)
            logger.info(f"Successfully saved {len(self.proxies)} proxies to {self.proxy_file_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving proxies to {self.proxy_file_path}: {e}")
            return False

    def add_proxy(self, proxy_type: str, proxy_url: str) -> bool:
        if not proxy_type or not proxy_url:
            logger.error("Invalid proxy type or URL provided.")
            return False
        proxy_type_lower = proxy_type.lower()
        proxy_url_stripped = proxy_url.strip()
        corrected_url = self._ensure_correct_scheme(proxy_url_stripped, proxy_type_lower)
        if corrected_url != proxy_url_stripped:
            logger.info(f"Corrected URL scheme for new proxy type '{proxy_type_lower}': '{proxy_url_stripped}' -> '{corrected_url}'")
        new_proxy = ProxyConfig(type=proxy_type_lower, url=corrected_url)
        if any(p['url'] == new_proxy['url'] for p in self.proxies):
            logger.warning(f"Proxy with URL '{new_proxy['url']}' already exists. Not adding.")
            return False
        self.proxies.append(new_proxy)
        logger.info(f"Added proxy: {new_proxy}. Total proxies: {len(self.proxies)}")
        if not self.active and self.current_use_proxies and self.proxies:
            self.active = True
            if self.current_proxy_index == -1 :
                 self.current_proxy_index = 0
            logger.info("ProxyManager became active after adding a proxy.")
        elif self.active and self.current_proxy_index == -1 and len(self.proxies) == 1:
            self.current_proxy_index = 0
        return self._save_proxies_to_file()

    def remove_proxy(self, proxy_url_to_remove: str) -> bool:
        if not self.proxies:
            logger.warning("No proxies to remove.")
            return False
        initial_len = len(self.proxies)
        current_selected_proxy_obj = self.get_proxy()
        self.proxies = [p for p in self.proxies if p['url'] != proxy_url_to_remove]
        if len(self.proxies) < initial_len:
            logger.info(f"Removed proxy with URL '{proxy_url_to_remove}'. Remaining proxies: {len(self.proxies)}")
            if not self.proxies:
                self.current_proxy_index = -1
                logger.info("All proxies removed.")
            elif current_selected_proxy_obj and current_selected_proxy_obj['url'] == proxy_url_to_remove:
                self.reset_proxies()
            elif self.current_proxy_index >= len(self.proxies):
                 self.current_proxy_index = 0 if self.proxies else -1
            return self._save_proxies_to_file()
        else:
            logger.warning(f"Proxy with URL '{proxy_url_to_remove}' not found.")
            return False

    def reload_proxies(self):
        logger.info(f"Reloading proxies from {self.proxy_file_path}...")
        self.proxies = []
        self.current_proxy_index = -1
        self.active = False
        if self.current_use_proxies:
            self._load_proxies_from_file()
            if self.proxies:
                self.active = True
                logger.info(f"Proxies reloaded. Active: {self.active}, Count: {len(self.proxies)}, Mode: {self.current_rotation_mode}")
            else:
                self.active = False
                logger.warning("Proxies reloaded, but no proxies found or file error. ProxyManager remains inactive.")
        else:
            self.active = False
            logger.info("Proxies reloaded, but current_use_proxies is false. ProxyManager remains disabled.")

    def shuffle_proxies_in_memory_and_save(self) -> bool:
        if not self.proxies:
            logger.warning("No proxies to shuffle.")
            return False
        logger.info(f"Shuffling {len(self.proxies)} proxies in memory...")
        random.shuffle(self.proxies)
        self.current_proxy_index = 0
        logger.info("Proxies shuffled. Saving new order to file.")
        if self._save_proxies_to_file():
            logger.info(f"Successfully saved shuffled proxy list. Current proxy after shuffle: {self.get_proxy()['url'] if self.get_proxy() else 'None'}")
            return True
        else:
            logger.error("Failed to save shuffled proxy list. Original order might be lost in memory if not reloaded.")
            return False

if __name__ == '__main__':
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
    proxy_manager_test.set_use_proxies(False)
    print(f"ProxyManager Active after set_use_proxies(False): {proxy_manager_test.active}")
    proxy_manager_test.set_use_proxies(True)
    print(f"ProxyManager Active after set_use_proxies(True): {proxy_manager_test.active}")
    proxy_manager_test.set_rotation_mode("cycle")
    print(f"Rotation mode after set_rotation_mode('cycle'): {proxy_manager_test.current_rotation_mode}")
    if os.path.exists(temp_proxy_file):
        os.remove(temp_proxy_file)
    if os.path.exists(temp_settings_file):
        os.remove(temp_settings_file)
    if os.path.exists(temp_config_dir) and not os.listdir(temp_config_dir):
        os.rmdir(temp_config_dir)
