"""意图确认样本合成（T041，FR-010 ~ FR-014）。

模糊开场 → 追问（上限随机 2–6 写入 system prompt）→ 确认意图 → 回答；
含"用户要求跳过追问""中途改变意图"两类变体。
"""

from __future__ import annotations

import random
import re
import sqlite3

from ..chat.prompts import build_system_prompt
from ..kb.store import all_clauses
from .knowledge import _marker, doc_titles
from .llm import ExternalLLM

DIALOG_PROMPT = """\
你是工会法律领域的训练数据编写员。根据下面的法律条款，编写一段多轮对话样本。

条款：
{marker}
> {clause_text}

对话要求：
- 第 1 轮 user：一句含糊的大白话开场（不出现条款编号、法规名称，信息不完整）；
- assistant：编号追问，每个问题一行、以"？"结尾，问题数不超过 {max_q} 个；
- 第 2 轮 user：补充回答，并说明想了解相关法律规定；
- assistant：给出咨询回答，按以下结构：

## 违法行为认定
### 1. <违法主体>：<行为概述>
**适用条款**
{marker}
> {clause_text}
**适用分析**
<分析>
**法律责任**
<如适用，引用相关条款>

{variant}

输出 JSON 数组（共 4 条消息）：
[{{"role": "user", "content": "..."}}, {{"role": "assistant", "content": "..."}}, ...]"""

VARIANTS = {
    "normal": "用户正常补充信息。",
    "skip": "第 1 轮 assistant 追问后，第 2 轮 user 说'不想回答了，直接告诉我结果'；"
            "assistant 基于已有信息回答，并注明哪些结论依赖尚未确认的事实。",
    "switch": "第 2 轮 user 补充信息的同时改口说要生成普法文章；"
              "assistant 确认新意图后按普法文章结构生成（案例/以案说法/普法提示，人物单位虚构）。",
}


def generate(
    kb_conn: sqlite3.Connection,
    llm: ExternalLLM,
    cfg: dict,
    *,
    n_per_variant: int = 20,
) -> list[dict]:
    clauses = [
        c for c in all_clauses(kb_conn)
        if c.item_no is None and 30 <= len(c.text) <= 400
    ]
    rng = random.Random(cfg.get("seed", 42))
    rng.shuffle(clauses)
    titles = doc_titles(kb_conn)

    samples = []
    per_variant = max(1, n_per_variant // len(VARIANTS))
    for variant, instruction in VARIANTS.items():
        for c in clauses[:per_variant]:
            title, version = titles[c.doc_id]
            max_q = rng.randint(2, 6)
            out = llm.chat(
                [{
                    "role": "user",
                    "content": DIALOG_PROMPT.format(
                        marker=_marker(title, version, c),
                        clause_text=c.text,
                        max_q=max_q,
                        variant=instruction,
                    ),
                }],
                input_source="kb_clause",
                max_tokens=2500,
            )
            msgs = _parse_json_array(out)
            if not msgs or len(msgs) < 4:
                continue
            samples.append(
                {
                    "messages": [
                        {
                            "role": "system",
                            "content": build_system_prompt(max_questions=max_q),
                        },
                        *msgs,
                    ],
                    "meta": {"type": "intent", "kind": variant,
                             "doc_id": c.doc_id, "clause_ids": [c.clause_id]},
                }
            )
    return samples


def _parse_json_array(text: str) -> list[dict] | None:
    import json

    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return None
    try:
        arr = json.loads(m.group(0))
        if all("role" in m and "content" in m for m in arr):
            return arr
    except json.JSONDecodeError:
        return None
    return None
