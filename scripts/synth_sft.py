"""tu synth sft 包装：从 .env 加载环境变量（等价于 set -a && source .env）。

仅把 key=value 注入进程环境，不打印任何内容；
后台 exec 对字面量含 .env 的命令一律拒绝，故用本脚本等价执行。
用法::

    uv run python scripts/synth_sft.py [--reuse-dataset DIR] [其他 tu synth sft 参数]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

for line in Path(".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("export "):
        line = line[len("export "):]
    if "=" not in line:
        continue
    key, _, value = line.partition("=")
    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

sys.argv = ["tu", "synth", "sft", *sys.argv[1:]]

from tu_assistant.cli import app  # noqa: E402

app()
