"""带 NaN 日志监控的训练启动器（E001 尝试 4 修复 3：日志自动停训）。

用法::

    uv run python scripts/run_training_guarded.py [config] [guard_log]

    config    训练配置（默认 configs/train/demo-7b-resume.yaml）
    guard_log 本脚本的日志（默认 /tmp/tu-train-guard.log）

行为：

- **与 agent shell 脱钩**：外层调用以 ``Popen(start_new_session=True)``
  重新拉起自身（等价 nohup/setsid，env ``TU_GUARD_CHILD=1`` 标记），
  外层打印 detached 副本的 pid 后立即返回；副本由 launchd 收养（PPID=1）。
- detached 副本内以 ``caffeinate -is uv run tu train --config <cfg>``
  拉起训练（新 session，独立进程组）。
- 每 10s tail ``artifacts/train/<exp_id>/train.log``：剥掉 ANSI 后 iter/val
  行出现 ``nan``（``[NaN-guard]`` 告警行除外）→ 记录停止位置、
  ``killpg`` 先发 SIGTERM、15s 后未退再 SIGKILL。
- **退出码**：0 = 训练正常完成；20 = 因 nan 中止；其他 = 训练进程返回码。

exp_id 取自配置里的 ``exp_id``；为 null 时取 artifacts/train 下最新出现的
``exp-*`` 目录（训练启动后由 ``tu train`` 创建）。
"""

from __future__ import annotations

import contextlib
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import yaml

EXIT_NAN_ABORT = 20

CONFIG = sys.argv[1] if len(sys.argv) > 1 else "configs/train/demo-7b-resume.yaml"
GUARD_LOG = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/tu-train-guard.log")

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
NAN_RE = re.compile(r"\bnan\b", re.IGNORECASE)
ITER_RE = re.compile(r"^\s*(\d+)\s")
POLL_S = 10
TERM_GRACE_S = 15


def log(msg: str, fh) -> None:
    line = f"[guard {time.strftime('%H:%M:%S')}] {msg}"
    fh.write(line + "\n")
    fh.flush()


def resolve_train_log(config_path: str) -> Path | None:
    """从配置解析 exp 目录的 train.log 路径；exp_id 为 null 时找最新 exp-*。"""
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    exp_id = cfg.get("exp_id")
    if exp_id:
        return Path("artifacts/train") / exp_id / "train.log"
    # exp_id 由 tu train 按时间戳生成：等目录出现后由轮询发现
    return None


def newest_train_log() -> Path | None:
    train_root = Path("artifacts/train")
    if not train_root.is_dir():
        return None
    logs = sorted(train_root.glob("exp-*/train.log"), key=lambda p: p.stat().st_mtime)
    return logs[-1] if logs else None


def main() -> int:
    if os.environ.get("TU_GUARD_CHILD") != "1":
        # 外层：以独立 session 拉起 detached 副本后立即返回（等价 nohup）
        env = {**os.environ, "TU_GUARD_CHILD": "1"}
        fh = GUARD_LOG.open("w", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, "-u", str(Path(__file__).resolve()), CONFIG, str(GUARD_LOG)],
            stdout=fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )
        print(f"guard detached pid={proc.pid} log={GUARD_LOG} config={CONFIG}")
        return 0

    # ---- detached 副本 ----
    env = {
        **os.environ,
        "HF_ENDPOINT": "https://hf-mirror.com",
        "HF_HUB_DISABLE_XET": "1",
    }
    train_log = resolve_train_log(CONFIG)
    with GUARD_LOG.open("a", encoding="utf-8") as fh:
        log(f"starting: caffeinate -is uv run tu train --config {CONFIG}", fh)
        proc = subprocess.Popen(
            ["caffeinate", "-is", "uv", "run", "tu", "train", "--config", CONFIG],
            stdout=fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            start_new_session=True,  # 独立进程组：killpg 可整组停训
        )
        log(f"training pid={proc.pid} train_log={train_log or '(discover)'}", fh)

        offset = 0
        last_iter = 0
        rc = None
        while True:
            rc = proc.poll()
            if train_log is None:
                train_log = newest_train_log()
            if train_log is not None and train_log.exists():
                try:
                    size = train_log.stat().st_size
                    if size < offset:  # 日志被重写（理论上不会）
                        offset = 0
                    with train_log.open("r", encoding="utf-8", errors="replace") as tf:
                        tf.seek(offset)
                        chunk = tf.read()
                        offset = tf.tell()
                    for raw in chunk.splitlines():
                        line = ANSI_RE.sub("", raw)
                        if m := ITER_RE.match(line):
                            last_iter = max(last_iter, int(m.group(1)))
                        if NAN_RE.search(line) and "guard" not in line.lower():
                            log(
                                f"nan detected in train.log at line: {line.strip()!r} "
                                f"(last_iter={last_iter}); stopping training",
                                fh,
                            )
                            rc = EXIT_NAN_ABORT
                            break
                    if rc == EXIT_NAN_ABORT:
                        break
                except OSError as e:
                    log(f"tail error: {e}", fh)
            if rc is not None:
                break
            time.sleep(POLL_S)

        if rc == EXIT_NAN_ABORT:
            # NaN 中止：先 SIGTERM 整组，超时 SIGKILL
            if proc.poll() is None:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGTERM)
                deadline = time.time() + TERM_GRACE_S
                while proc.poll() is None and time.time() < deadline:
                    time.sleep(1)
                if proc.poll() is None:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
            log(f"aborted at last_iter={last_iter}", fh)
            return EXIT_NAN_ABORT

        log(f"training exited rc={rc} last_iter={last_iter}", fh)
        return int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
