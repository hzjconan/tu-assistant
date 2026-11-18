"""一次性辅助脚本：把 exp-20261115-124801 的 iter500 检查点复制为可服务形态并校验无 NaN。

用法：uv run python scripts/_ckpt500_setup.py
"""

import json
import shutil
from pathlib import Path

import numpy as np
from safetensors import safe_open

SRC = Path("artifacts/train/exp-20261115-124801")
DST = Path("artifacts/train/exp-20261115-124801-ckpt500")

(DST / "adapters").mkdir(parents=True, exist_ok=True)
shutil.copy2(
    SRC / "adapters" / "0000500_adapters.safetensors",
    DST / "adapters" / "adapters.safetensors",
)
shutil.copy2(
    SRC / "adapters" / "adapter_config.json",
    DST / "adapters" / "adapter_config.json",
)

manifest = json.loads((SRC / "manifest.json").read_text(encoding="utf-8"))
manifest["id"] = "exp-20261115-124801-ckpt500"
manifest["adapter_dir"] = str(DST / "adapters")
manifest["note"] = (
    "iter500 checkpoint 副本：adapters.safetensors <- 0000500_adapters.safetensors"
    "（iter550 起 NaN，后续检查点不可用）"
)
(DST / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("copied:", sorted(p.name for p in (DST / "adapters").iterdir()))

total = bad = 0
with safe_open(str(DST / "adapters" / "adapters.safetensors"), framework="numpy") as f:
    for k in f.keys():
        t = f.get_tensor(k)
        total += 1
        if np.isnan(t.astype(np.float32)).any():
            bad += 1
            print("NaN in", k)
print(f"tensors={total} nan_tensors={bad}")
