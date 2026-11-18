"""E002 步骤 2：A/B 冒烟验证。

同一个服务进程、同一道题（评测集第 1 题）、同一个 system prompt、
temperature=0，只改请求里的 model 字段：
- "default_model" 应命中挂了 adapter 的微调模型（输出含〔和日期版本标签）；
- current.json 里的 base_model 名应落到不带 adapter 的基座（输出风格不同）。

用法：uv run python scripts/experiments/e002/ab.py [case_index]
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, "src")
from tu_assistant.chat.prompts import build_system_prompt  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
case_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
line = (ROOT / "eval/cases/v1/reviewed.jsonl").read_text(encoding="utf-8").splitlines()[case_idx]
q = json.loads(line)["input"]["message"]
cur = json.loads((ROOT / "artifacts/serve/current.json").read_text(encoding="utf-8"))
base = cur.get("base_model") or cur["model"]
print("case_idx:", case_idx, "| base_model:", base)


def ask(model):
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": 400,
        "messages": [
            {"role": "system", "content": build_system_prompt(5)},
            {"role": "user", "content": q},
        ],
    }
    req = urllib.request.Request(
        "http://127.0.0.1:8080/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req, timeout=600))["choices"][0]["message"]["content"]


outputs = {}
for m in ["default_model", base]:
    out = ask(m)
    outputs[m] = out
    # 法规原文行（> 引用）截断到 15 字
    out = re.sub(r"(^> )(.{15}).*$", r"\1\2……", out, flags=re.M)
    print("=" * 20, m,
          "| 含〔:", "〔" in out,
          "| 含日期版本:", bool(re.search(r"（\d{4}-\d{2}-\d{2}）", out)))
    print(out[:500])

print("=" * 20, "两次输出相同:", outputs["default_model"] == outputs[base])
