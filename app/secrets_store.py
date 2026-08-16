from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SECRETS_FILE = Path(os.environ.get("CENSORARR_SECRETS", "/config/secrets.json"))


def _load() -> dict[str, str]:
    try:
        data = json.loads(SECRETS_FILE.read_text(encoding="utf-8")) if SECRETS_FILE.exists() else {}
        return {str(k): str(v) for k, v in data.items() if v is not None}
    except Exception:
        return {}


def _write(data: dict[str, str]) -> None:
    SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SECRETS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, SECRETS_FILE)
    try:
        os.chmod(SECRETS_FILE, 0o600)
    except OSError:
        pass


def get(name: str, *, env: str | None = None, legacy: Any = "") -> str:
    """GUI-saved value wins, then environment, then legacy config value."""
    saved = _load().get(name, "").strip()
    if saved:
        return saved
    if env:
        val = str(os.environ.get(env, "") or "").strip()
        if val:
            return val
    return str(legacy or "").strip()


def has(name: str, *, env: str | None = None, legacy: Any = "") -> bool:
    return bool(get(name, env=env, legacy=legacy))


def source(name: str, *, env: str | None = None, legacy: Any = "") -> str:
    data = _load()
    if str(data.get(name, "")).strip():
        return "gui"
    if env and str(os.environ.get(env, "") or "").strip():
        return "environment"
    if str(legacy or "").strip():
        return "legacy-config"
    return "none"


def set_secret(name: str, value: str) -> None:
    data = _load()
    value = str(value or "").strip()
    if value:
        data[name] = value
    else:
        data.pop(name, None)
    _write(data)


def clear(name: str) -> None:
    data = _load()
    data.pop(name, None)
    _write(data)


def statuses(spec: dict[str, tuple[str | None, Any]]) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "set": has(name, env=env, legacy=legacy),
            "source": source(name, env=env, legacy=legacy),
        }
        for name, (env, legacy) in spec.items()
    }
