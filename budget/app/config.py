"""Application settings.

Value priority: /data/options.json (Home Assistant app options) >
environment variables > defaults.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable

OPTIONS_FILE = "/data/options.json"
DATA_FILE = "/data/budget.db"


def _load_options() -> dict:
    try:
        with open(OPTIONS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _bool(value: Any) -> bool:
    """Cast HA options (real booleans) and env vars ("1"/"true"/...) to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() not in ("0", "false", "no", "off", "")


def _pick(options: dict, key: str, env: str, default: Any, cast: Callable[[Any], Any]) -> Any:
    if options.get(key) is not None:
        try:
            return cast(options[key])
        except (TypeError, ValueError):
            pass
    raw = os.environ.get(env)
    if raw not in (None, ""):
        try:
            return cast(raw)
        except (TypeError, ValueError):
            pass
    return default


class Settings:
    def __init__(self) -> None:
        options = _load_options()

        # 8099 is the Supervisor ingress port: the app gets a panel in the
        # HA sidebar (ingress: true) and is also exposed on host port 8080
        self.port = _pick(options, "port", "PORT", 8099, int)
        self.log_level = str(_pick(options, "log_level", "LOG_LEVEL", "INFO", str)).upper()

        # book recurring expenses automatically on the 1st of each month
        self.auto_recurring = _pick(options, "auto_recurring", "AUTO_RECURRING", True, _bool)

        # SQLite database lives in the app's /data volume (survives updates)
        self.db_path = _pick(options, "db_path", "DB_PATH", DATA_FILE, str)


settings = Settings()
