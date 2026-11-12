"""配置加载：读取 YAML，支持命令行覆盖。

用法::

    cfg = load_app_config()                      # configs/app.yaml
    cfg = load_app_config(overrides={"session.max_questions_per_turn": "3"})
    get(cfg, "runtime.model_endpoint")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_APP_CONFIG = Path("configs/app.yaml")
DEFAULT_SYNTH_CONFIG = Path("configs/synth.yaml")

API_KEY_ENV = "TU_EXTERNAL_LLM_API_KEY"


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _set_nested(cfg: dict[str, Any], dotted_key: str, value: Any) -> None:
    keys = dotted_key.split(".")
    node = cfg
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value


def get(cfg: dict[str, Any], dotted_key: str, default: Any = None) -> Any:
    node: Any = cfg
    for k in dotted_key.split("."):
        if not isinstance(node, dict) or k not in node:
            return default
        node = node[k]
    return node


def load_app_config(
    path: str | Path = DEFAULT_APP_CONFIG,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """加载应用配置并应用覆盖项（``--set a.b=value`` 形式）。"""
    cfg = load_yaml(path)
    for k, v in (overrides or {}).items():
        _set_nested(cfg, k, v)
    return cfg


def load_synth_config(path: str | Path = DEFAULT_SYNTH_CONFIG) -> dict[str, Any]:
    return load_yaml(path)


def external_api_key() -> str:
    """外部大模型 API Key：只从环境变量读取，缺失时抛错而不是静默。"""
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key:
        raise RuntimeError(
            f"缺少环境变量 {API_KEY_ENV}。外部大模型 API Key 只能来自环境变量，"
            "不得写入配置文件或代码。"
        )
    return key
