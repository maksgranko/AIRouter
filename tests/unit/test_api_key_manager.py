import json

from api_key_manager import ApiKeyManager


def test_loads_keys_from_files(tmp_path):
    openai_file = tmp_path / "openai.json"
    gemini_file = tmp_path / "gemini.json"
    openai_file.write_text(json.dumps(["k1", "k2"]), encoding="utf-8")
    gemini_file.write_text(json.dumps(["g1"]), encoding="utf-8")

    manager = ApiKeyManager({"openai": str(openai_file), "gemini": str(gemini_file)})

    assert manager.get_key("openai") == "k1"
    assert manager.get_key("gemini") == "g1"


def test_add_remove_rotate_and_reload(tmp_path):
    key_file = tmp_path / "openai.json"
    key_file.write_text(json.dumps(["k1", "k2"]), encoding="utf-8")
    manager = ApiKeyManager({"openai": str(key_file)})

    assert manager.add_key("openai", "k3") is True
    assert manager.add_key("openai", "k3") is False

    assert manager.get_key("openai") == "k1"
    assert manager.rotate_key("openai") is True
    assert manager.get_key("openai") == "k2"

    assert manager.remove_key("openai", "k2") is True
    assert manager.get_key("openai") in {"k1", "k3"}

    key_file.write_text(json.dumps(["new1"]), encoding="utf-8")
    manager.reload_keys_for_service("openai")
    assert manager.get_key("openai") == "new1"


def test_handles_invalid_file_format(tmp_path):
    broken_file = tmp_path / "broken.json"
    broken_file.write_text("{}", encoding="utf-8")

    manager = ApiKeyManager({"openai": str(broken_file)})

    assert manager.get_key("openai") is None
    assert manager.rotate_key("openai") is False
