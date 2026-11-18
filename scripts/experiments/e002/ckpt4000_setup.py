"""E002 步骤 4：把续训 exp-20261116-resume500 的 iter4000 检查点复制为可服务形态。

0004000_adapters.safetensors 是续训内第 4000 步（全局约第 4500 步），
作为 ckpt-500 与训满版之间的中间点，连出粗略学习曲线。

用法：uv run python scripts/experiments/e002/ckpt4000_setup.py
"""

import json
import shutil
from pathlib import Path

SRC = Path("artifacts/train/exp-20261116-resume500")
DST = Path("artifacts/train/exp-20261116-resume500-ckpt4000")

(DST / "adapters").mkdir(parents=True, exist_ok=True)
shutil.copy2(
    SRC / "adapters" / "0004000_adapters.safetensors",
    DST / "adapters" / "adapters.safetensors",
)
shutil.copy2(
    SRC / "adapters" / "adapter_config.json",
    DST / "adapters" / "adapter_config.json",
)

manifest = json.loads((SRC / "manifest.json").read_text(encoding="utf-8"))
manifest["id"] = "exp-20261116-resume500-ckpt4000"
manifest["adapter_dir"] = str(DST / "adapters")
manifest["note"] = (
    "续训 iter4000 checkpoint 副本（全局约第 4500 步）："
    "adapters.safetensors <- 0004000_adapters.safetensors"
)
(DST / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("copied:", sorted(p.name for p in (DST / "adapters").iterdir()))
