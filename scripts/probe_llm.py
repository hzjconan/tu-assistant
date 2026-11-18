"""探测 DeepSeek API 延迟：加载 .env，发一次短调用，打印耗时（不打印 key）。"""

import os
import time
from pathlib import Path

for line in Path(".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    if line.startswith("export "):
        line = line[len("export "):]
    k, _, v = line.partition("=")
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from tu_assistant.config import load_synth_config  # noqa: E402
from tu_assistant.synth.llm import from_config  # noqa: E402

llm = from_config(load_synth_config("configs/synth.yaml"))
t0 = time.time()
out = llm.chat(
    [{"role": "user", "content": "用一句话回答：1+1 等于几？"}],
    input_source="synthetic_template",
    max_tokens=50,
)
print(f"elapsed={time.time() - t0:.1f}s  reply={out[:60]!r}")
