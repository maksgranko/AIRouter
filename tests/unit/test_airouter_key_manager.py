import json

from airouter_key_manager import AIRouterApiKeyManager


def test_generates_and_persists_key(tmp_path):
    keys_file = tmp_path / "airouter_keys.json"
    manager = AIRouterApiKeyManager(keys_file_path=str(keys_file))

    generated = manager.generate_and_add_key()
    assert generated is not None
    assert manager.key_exists(generated)

    persisted = json.loads(keys_file.read_text(encoding="utf-8"))
    assert generated in persisted


def test_add_remove_and_reload(tmp_path):
    keys_file = tmp_path / "airouter_keys.json"
    manager = AIRouterApiKeyManager(keys_file_path=str(keys_file))

    assert manager.add_key("abc") is True
    assert manager.add_key("abc") is False
    assert manager.remove_key("abc") is True
    assert manager.remove_key("abc") is False

    keys_file.write_text(json.dumps(["x", "y"]), encoding="utf-8")
    manager.reload_keys()
    assert manager.get_all_keys() == ["x", "y"]
