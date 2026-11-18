"""校验 safetensors 全部张量有限（E001 检查点健康检查）。

用法：uv run python scripts/check_safetensors_finite.py <file.safetensors> [...]
退出码 0 = 全有限；1 = 存在非有限值。
"""

import sys

import numpy as np
from safetensors import safe_open

rc = 0
for path in sys.argv[1:]:
    total = bad = 0
    with safe_open(path, framework="numpy") as f:
        for k in f.keys():
            t = f.get_tensor(k)
            total += 1
            if not np.isfinite(t.astype(np.float32)).all():
                bad += 1
                print(f"  NON-FINITE: {k}")
    status = "OK" if bad == 0 else "BAD"
    if bad:
        rc = 1
    print(f"{status} {path}: tensors={total} non_finite={bad}")
raise SystemExit(rc)
