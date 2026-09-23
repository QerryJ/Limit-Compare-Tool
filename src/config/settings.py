"""Local settings / recent-files persistence.

Offline desktop tool: no database, no network. Everything lives in
``<project>/config/*.json``. Only ``mapping_*.json`` (human alignment
decisions) is meant to be committed; settings and recents are per-machine.
"""

import json
import os
from typing import Any, Dict, List

CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config",
)

DEFAULTS: Dict[str, Any] = {
    "density": "comfortable",   # comfortable | compact
    "zone": "Room",
    "cpk_tight": 1.33,
    "cpk_loose": 2.0,
    "cpk_skew": 0.30,
    "gu_sigma_k": 3.0,
    "export_dir": "",
    "author": "",
}


def _read(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def _write(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def load_settings() -> Dict[str, Any]:
    data = dict(DEFAULTS)
    data.update(_read(os.path.join(CONFIG_DIR, "settings.json")))
    return data


def save_settings(data: Dict[str, Any]) -> None:
    _write(os.path.join(CONFIG_DIR, "settings.json"), data)


RECENT_LIMIT = 10


def load_recent() -> Dict[str, List[str]]:
    data = _read(os.path.join(CONFIG_DIR, "recent.json"))
    return {k: v for k, v in data.items() if isinstance(v, list)}


def add_recent(kind: str, path: str) -> None:
    data = load_recent()
    items = [p for p in data.get(kind, []) if p != path]
    items.insert(0, path)
    data[kind] = items[:RECENT_LIMIT]
    _write(os.path.join(CONFIG_DIR, "recent.json"), data)
