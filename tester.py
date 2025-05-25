
import json
import os
from proxy_manager import ProxyManager
import tests
import tests.handlers.misc.libs
import tests.handlers.misc.libs.tokenizer
import tests.handlers.misc.libs.tokenizer.t_main
import tests.t_airouter_key_manager
import tests.t_api_key_manager
import tests.t_proxy_manager


if __name__ == "__main__":
    print(
        "##############################",
        "######Proxy Manager Test######",
        "##############################"
        )
    
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
    tests.t_proxy_manager.start(proxy_manager_test,temp_proxy_file,temp_settings_file,temp_config_dir)
    print(
        "##############################",
        "#####API-Key Manager Test#####",
        "##############################"
        )
    tests.t_api_key_manager.start()
    print(
        "##############################",
        "###AIR API-Key Manager Test###",
        "##############################"
        )
    tests.t_airouter_key_manager.start()
    print(
        "##############################",
        "########Tokenizer Test########",
        "##############################"
        )
    tests.handlers.misc.libs.tokenizer.t_main.start()