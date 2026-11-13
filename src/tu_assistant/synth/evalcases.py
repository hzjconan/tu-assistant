"""评测候选用例生成（T037）：`tu synth evalcases`。

用与训练数据不同的提示词生成评测候选（宪章原则 V：问法必须不同）。
输出到 eval/cases/candidates/，经人工校验、改 source 后才进正式评测集。
"""

from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

from ..kb.store import all_clauses
from .llm import ExternalLLM

PROMPT = """\
你是工会法律领域的出题人。根据下面的法律条款，编写一个工会工作人员可能提出
的真实感问题。

要求：
- 问题用口语化表达，不要出现条款编号，不要透露条款出自哪部法规；
- 问题应该需要引用该条款才能回答；
- 只输出问题本身，一行。

条款：
{clause_text}
"""


def generate_candidates(
    kb_conn: sqlite3.Connection,
    llm: ExternalLLM,
    *,
    n: int = 40,
    seed: int = 42,
    out_dir: str | Path = "eval/cases/candidates",
) -> dict:
    """抽取条款 → 让外部模型写问题 → 候选评测用例。"""
    clauses = [
        c for c in all_clauses(kb_conn)
        if c.item_no is None and len(c.text) >= 15
    ]
    rng = random.Random(seed)
    rng.shuffle(clauses)
    picked = clauses[:n]

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "candidates.jsonl"
    written = 0
    with path.open("w", encoding="utf-8") as f:
        for i, c in enumerate(picked, 1):
            q = llm.chat(
                [{"role": "user", "content": PROMPT.format(clause_text=c.text)}],
                input_source="kb_clause",
                temperature=0.8,
                max_tokens=200,
            ).strip().splitlines()[0].strip()
            if not q:
                continue
            f.write(
                json.dumps(
                    {
                        "case_id": f"cand-{i:03d}",
                        "category": "clause_id",
                        "input": {"message": q},
                        "gold": {"clauses": [c.clause_id]},
                        "source": "synthetic",
                        "note": "候选用例：人工核对后改 source=synthetic_reviewed 并移入 v1/",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            written += 1
    return {"written": written, "path": str(path), "generator": llm.meta()}
