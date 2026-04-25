import json

from proxy_manager import ProxyManager


def test_proxy_manager_loads_and_rotates(tmp_path):
    settings_file = tmp_path / "settings.json"
    proxy_file = tmp_path / "proxies.json"

    settings_file.write_text(
        json.dumps({"proxy_settings": {"use_proxies": True, "rotation_mode": "once"}}),
        encoding="utf-8",
    )
    proxy_file.write_text(
        json.dumps(
            [
                {"type": "http", "url": "http://proxy1:8080"},
                {"type": "socks5", "url": "socks5://proxy2:1080"},
            ]
        ),
        encoding="utf-8",
    )

    manager = ProxyManager(str(proxy_file), str(settings_file), randomize_on_load=False)

    assert manager.active is True
    assert manager.get_proxy()["url"] == "http://proxy1:8080"
    manager.rotate_proxy()
    assert manager.get_proxy()["url"] == "socks5://proxy2:1080"


def test_add_remove_reload_shuffle(tmp_path):
    settings_file = tmp_path / "settings.json"
    proxy_file = tmp_path / "proxies.json"
    settings_file.write_text(
        json.dumps({"proxy_settings": {"use_proxies": True, "rotation_mode": "cycle"}}),
        encoding="utf-8",
    )
    proxy_file.write_text(json.dumps([]), encoding="utf-8")

    manager = ProxyManager(str(proxy_file), str(settings_file), randomize_on_load=False)
    assert manager.add_proxy("http", "proxy.local:8000") is True
    assert manager.proxies[0]["url"].startswith("http://")
    assert manager.remove_proxy(manager.proxies[0]["url"]) is True

    proxy_file.write_text(
        json.dumps(
            [
                {"type": "http", "url": "http://a:1"},
                {"type": "http", "url": "http://b:2"},
            ]
        ),
        encoding="utf-8",
    )
    manager.reload_proxies()
    assert len(manager.proxies) == 2
    assert manager.shuffle_proxies_in_memory_and_save() is True
