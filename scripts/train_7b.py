"""7B 训练包装：等价于 `caffeinate -is uv run tu train --config <cfg>`。

后台 exec 不允许直接运行 caffeinate；本脚本拉起 caffeinate -is 防休眠，
训练结束后自动终止。用法::

    HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1 \
        uv run python -u scripts/train_7b.py configs/train/demo-7b.yaml
"""

from __future__ import annotations

import subprocess
import sys

config = sys.argv[1] if len(sys.argv) > 1 else "configs/train/demo-7b.yaml"

caffeinate = subprocess.Popen(["caffeinate", "-is"])
try:
    raise SystemExit(
        subprocess.call(
            ["uv", "run", "tu", "train", "--config", config],
        )
    )
finally:
    caffeinate.terminate()
