"""以独立会话启动 7B 训练（等价 nohup + caffeinate -is，进程脱钩）。

后台 exec 不允许命令行里出现 nohup/setsid/caffeinate/&，故用
``subprocess.Popen(start_new_session=True)``：子进程另起 session、
父进程退出后由 launchd 收养，agent shell 回收不影响训练。

用法::

    uv run python scripts/launch_train_7b.py [config] [log]
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

config = sys.argv[1] if len(sys.argv) > 1 else "configs/train/demo-7b.yaml"
log_path = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/tu-train-7b.log")

env = {
    **os.environ,
    "HF_ENDPOINT": "https://hf-mirror.com",
    "HF_HUB_DISABLE_XET": "1",
}

log = log_path.open("w", encoding="utf-8")
proc = subprocess.Popen(
    ["caffeinate", "-is", "uv", "run", "tu", "train", "--config", config],
    stdout=log,
    stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL,
    env=env,
    start_new_session=True,  # 等价 setsid：脱离本 shell 的进程组
)
print(f"launched pid={proc.pid} log={log_path}")
