"""用户配置独立存储：把端口/密码等用户配置写入 data/config/user_config.json。

设计意图：
- 不写入 plugin.toml（插件更新会被覆盖），也不依赖宿主 profile。
- 用户只需编辑这个独立 json 文件即可改端口/密码，长久存储。
- 优先级：user_config.json > plugin.toml 默认值。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

# user_config.json 里允许持久化的字段（端口/密码/玩家名等用户配置）
_USER_KEYS = (
    "server_host", "server_port", "mod_host", "mod_port",
    "bot_name", "bot_password",
    "tmod_version_str",
)

_DEFAULTS: Dict[str, Any] = {
    "server_host": "127.0.0.1",
    "server_port": 7777,
    "mod_host": "127.0.0.1",
    "mod_port": 9877,
    "bot_name": "Neko",
    "bot_password": "",
    "tmod_version_str": "tModLoader.v2026.6.3.0!2026.6.3",
}


def _config_path() -> Path:
    # core/config_store.py → core/ → neko_terraria/ → data/config/user_config.json
    return Path(__file__).resolve().parent.parent / "data" / "config" / "user_config.json"


def load_user_config() -> Dict[str, Any]:
    """读取用户独立配置文件；不存在/损坏时回退默认值。"""
    path = _config_path()
    if not path.exists():
        return dict(_DEFAULTS)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return dict(_DEFAULTS)
        cfg = dict(_DEFAULTS)
        for k in _USER_KEYS:
            if k in raw and raw[k] not in (None, ""):
                cfg[k] = raw[k]
        return cfg
    except Exception:
        return dict(_DEFAULTS)


def save_user_config(patch: Dict[str, Any]) -> Dict[str, Any]:
    """把用户配置写入 data/config/user_config.json（仅持久化 _USER_KEYS）。

    密码等敏感字段同样落盘（与 plugin.toml 现状一致，明文存储）。
    """
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # 保留文件中已有的其它字段，只覆盖用户配置键
    existing: Dict[str, Any] = {}
    if path.exists():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                existing = parsed
        except Exception:
            existing = {}

    merged = dict(existing)
    for k in _USER_KEYS:
        if k in patch:
            merged[k] = patch[k]

    path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {k: merged.get(k, _DEFAULTS[k]) for k in _USER_KEYS}


def config_file_path() -> str:
    return str(_config_path())
