"""产物清单：为 artifacts/ 下每个产物写 manifest.json（宪章原则 VI）。

每个产物（知识库版本、数据集、适配器、评测结果）记录：
产物 ID、创建时间、输入版本、配置哈希、随机种子——保证可追溯、可复现。
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def config_hash(config: dict[str, Any]) -> str:
    """配置的稳定哈希：内容不变则哈希不变。"""
    blob = json.dumps(config, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def write_manifest(
    artifact_dir: str | Path,
    *,
    artifact_id: str,
    artifact_type: str,
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    seed: int | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """在 artifact_dir 下写 manifest.json 并返回路径。"""
    d = Path(artifact_dir)
    d.mkdir(parents=True, exist_ok=True)
    manifest = {
        "id": artifact_id,
        "type": artifact_type,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "inputs": inputs or {},
        "config_hash": config_hash(config) if config is not None else None,
        "config": config or {},
        "seed": seed,
    }
    if extra:
        manifest.update(extra)
    path = d / "manifest.json"
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def read_manifest(artifact_dir: str | Path) -> dict[str, Any]:
    return json.loads((Path(artifact_dir) / "manifest.json").read_text(encoding="utf-8"))
