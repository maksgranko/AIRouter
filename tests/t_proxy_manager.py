import json
import os
from proxy_manager import ProxyManager
from main import proxy_manager

def start(proxy_manager_test,temp_proxy_file,temp_settings_file,temp_config_dir):
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