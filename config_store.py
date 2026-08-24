"""Atomic nested settings storage for the unified workstation."""

from __future__ import annotations

import copy
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "compression": {
        "7z_path": "",
        "prefix": "HGLIST-",
        "tag_prefix": "AAA_",
        "extension": ".1",
        "lvl": "5-标准",
        "dict": "64 MB",
        "word": "64",
        "solid": "16 GB",
        "threads": "自动",
        "pwd": "",
        "hide_name": True,
    },
    "preprocessing": {
        "prefix": "HGLIST-",
        "tag_prefix": "AAA_",
    },
    "extraction": {
        "7z_path": "",
        "password": "",
        "tag_prefix": "AAA_",
        "block_terms": "路径, 中文",
        "output_dir": "",
    },
    "renaming": {
        "tag_prefix": "AAA_",
        "block_terms": "路径, 中文",
    },
}

RENAMER_DEFAULTS = DEFAULT_CONFIG["renaming"]


def default_config_path() -> Path:
    anchor = Path(sys.executable if getattr(sys, "frozen", False) else __file__)
    return anchor.with_name("config.json")


def _merge_defaults(saved: Any) -> dict[str, Any]:
    result = copy.deepcopy(DEFAULT_CONFIG)
    if not isinstance(saved, dict):
        return result
    for section, defaults in DEFAULT_CONFIG.items():
        value = saved.get(section)
        if isinstance(value, dict):
            result[section].update({key: value[key] for key in defaults if key in value})
    return result


class ConfigStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_config_path()
        self._lock = threading.RLock()
        self._data = self._read()

    def _read(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            raw = {}
        return _merge_defaults(raw)

    def section(self, name: str) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data[name])

    def update_section(self, name: str, values: dict[str, Any]) -> None:
        with self._lock:
            if name not in DEFAULT_CONFIG:
                raise KeyError(name)
            self._data[name].update({key: value for key, value in values.items() if key in DEFAULT_CONFIG[name]})
            self._write_locked()

    def _write_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)


# Compatibility helpers used by the former renamer page while it is hosted by
# the unified shell. They intentionally operate on a flat renamer-only file.
def load_config(path: Path) -> dict[str, str]:
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return copy.deepcopy(RENAMER_DEFAULTS)
    if not isinstance(saved, dict):
        return copy.deepcopy(RENAMER_DEFAULTS)
    return {
        "tag_prefix": str(saved.get("tag_prefix", RENAMER_DEFAULTS["tag_prefix"])),
        "block_terms": str(saved.get("block_terms", RENAMER_DEFAULTS["block_terms"])),
    }


def save_config(path: Path, tag_prefix: str, block_terms: str) -> None:
    path.write_text(
        json.dumps({"tag_prefix": tag_prefix, "block_terms": block_terms}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
