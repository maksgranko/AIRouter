from typing import Any, Dict
from datetime import datetime, timezone
import json
import os
import shutil
import gzip

from utils.config_store import read_json


class GlobalAuditLogger:
    def __init__(self, logs_dir: str, settings_file_path: str):
        self.logs_dir = logs_dir
        self.settings_file_path = settings_file_path

    def log_event(self, payload: Dict[str, Any]) -> None:
        cfg = self._get_settings()
        if not cfg.get("enabled", True):
            return
        retention_days = int(cfg.get("retention_days", 7) or 0)
        gzip_enabled = bool(cfg.get("gzip_enabled", True))

        day_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        day_dir = os.path.join(self.logs_dir, day_str)
        os.makedirs(day_dir, exist_ok=True)
        module_name = self._sanitize_module_name(str(payload.get("module_name", "")).strip())
        target_files = ["airouter.log"]
        if module_name:
            target_files.append(f"{module_name}.log")

        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        try:
            line = json.dumps(event, ensure_ascii=False) + "\n"
            for filename in target_files:
                log_path = os.path.join(day_dir, filename)
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(line)
            self._maintain_logs(day_str, retention_days, gzip_enabled)
        except Exception:
            return

    def _get_settings(self) -> Dict[str, Any]:
        defaults = {"enabled": True, "retention_days": 7, "gzip_enabled": True}
        cfg = read_json(self.settings_file_path, {})
        if not isinstance(cfg, dict):
            return defaults
        merged = dict(defaults)
        merged.update({k: cfg.get(k, merged[k]) for k in defaults.keys()})
        return merged

    def _maintain_logs(self, current_day: str, retention_days: int, gzip_enabled: bool) -> None:
        os.makedirs(self.logs_dir, exist_ok=True)

        day_dirs = []
        for name in os.listdir(self.logs_dir):
            full = os.path.join(self.logs_dir, name)
            if os.path.isdir(full) and self._is_day_string(name):
                day_dirs.append(name)

        if gzip_enabled:
            for day in day_dirs:
                if day == current_day:
                    continue
                day_path = os.path.join(self.logs_dir, day)
                for filename in os.listdir(day_path):
                    if not filename.endswith(".log"):
                        continue
                    src = os.path.join(day_path, filename)
                    dst = src + ".gz"
                    if os.path.exists(dst):
                        continue
                    with open(src, "rb") as f_in, gzip.open(dst, "wb") as f_out:
                        f_out.writelines(f_in)
                    os.remove(src)

        if retention_days <= 0:
            for name in os.listdir(self.logs_dir):
                full = os.path.join(self.logs_dir, name)
                if os.path.isdir(full) and self._is_day_string(name):
                    shutil.rmtree(full, ignore_errors=True)
                elif name.endswith(".gzip") and self._is_day_string(name[:-5]):
                    try:
                        os.remove(full)
                    except Exception:
                        pass
            return

        keep_days = set(sorted(set(day_dirs), reverse=True)[:retention_days])
        for name in os.listdir(self.logs_dir):
            full = os.path.join(self.logs_dir, name)
            if os.path.isdir(full) and self._is_day_string(name) and name not in keep_days:
                shutil.rmtree(full, ignore_errors=True)

    @staticmethod
    def _is_day_string(value: str) -> bool:
        if len(value) != 10:
            return False
        if value[4] != "-" or value[7] != "-":
            return False
        y, m, d = value.split("-")
        return y.isdigit() and m.isdigit() and d.isdigit()

    @staticmethod
    def _sanitize_module_name(value: str) -> str:
        if not value:
            return ""
        safe = []
        for ch in value:
            if ch.isalnum() or ch in "._-":
                safe.append(ch)
            else:
                safe.append("_")
        normalized = "".join(safe).strip("._-")
        return normalized[:120]
