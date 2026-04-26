import json
import os
import threading
from typing import Any, Callable, Dict


_GLOBAL_LOCK = threading.RLock()
_FILE_LOCKS: Dict[str, threading.RLock] = {}


def _normalized_path(file_path: str) -> str:
    return os.path.abspath(file_path)


def _get_lock(file_path: str) -> threading.RLock:
    normalized = _normalized_path(file_path)
    with _GLOBAL_LOCK:
        lock = _FILE_LOCKS.get(normalized)
        if lock is None:
            lock = threading.RLock()
            _FILE_LOCKS[normalized] = lock
        return lock


def read_json(file_path: str, default: Any):
    lock = _get_lock(file_path)
    with lock:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except json.JSONDecodeError:
            return default


def write_json(file_path: str, payload: Any, ensure_ascii: bool = False) -> None:
    lock = _get_lock(file_path)
    with lock:
        parent = os.path.dirname(file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=ensure_ascii)


def update_json(file_path: str, default: Any, mutator: Callable[[Any], Any], ensure_ascii: bool = False):
    lock = _get_lock(file_path)
    with lock:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                current = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            current = default

        updated = mutator(current)
        parent = os.path.dirname(file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(updated, f, indent=2, ensure_ascii=ensure_ascii)
        return updated
