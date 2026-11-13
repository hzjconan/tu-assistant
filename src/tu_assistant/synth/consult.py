"""咨询类样本合成（T042，FR-015 ~ FR-018、FR-020 ~ FR-023）。

- 单违法行为咨询；
- 多违法行为 / 多违法主体（主体不预设类型，FR-017）；
- 例外情形（用 confirmed 的 exception_of 关联）；
- 信息不足时的分情形回答。
"""

from __future__ import annotations

import random
import sqlite3

from ..kb.models import Clause
from ..kb.store import all_clauses
from .knowledge import _marker, _parse_json_pair, doc_titles
from .llm import ExternalLLM

CONSULT_PROMPT = """\
你是工会法律领域的训练数据编写员。根据下面的法律条款，编写一个咨询问答样本。

条款：
{clauses_block}

要求：
- user：一段口语化的案情描述（工会工作人员口吻，不出现条款编号、法规名称），
  案情中 {n_violations}；
- assistant：按"违法行为认定"结构回答，每个违法行为单列：
  ## 违法行为认定
  ### 1. <违法主体>：<行为概述>
  **适用条款** <引用块>
  **适用分析** <该条款如何适用于本案情>
  **法律责任** <引用块>
  {extra_instruction}
- 违法主体不限于用人单位，可以是法规覆盖的任何个人或组织；
- 引用标记格式：〔《文件全称》（版本）第N条第M款〕（换行用 > 给出原文）。

只输出 JSON：{{"user": "...", "assistant": "..."}}"""


def _clauses_block(clauses: list[Clause], titles) -> str:
    return "\n".join(
        f"{_marker(titles[c.doc_id][0], titles[c.doc_id][1], c)}\n> {c.text}"
        for c in clauses
    )


def generate(
    kb_conn: sqlite3.Connection,
    llm: ExternalLLM,
    cfg: dict,
    *,
    n_single: int = 40,
    n_multi: int = 20,
) -> list[dict]:
    clauses = [
        c for c in all_clauses(kb_conn)
        if c.item_no is None and 30 <= len(c.text) <= 400
    ]
    rng = random.Random(cfg.get("seed", 42))
    rng.shuffle(clauses)
    titles = doc_titles(kb_conn)

    samples = []
    # 单违法行为
    for c in clauses[:n_single]:
        samples += _gen_one(
            llm, [c], titles, "含一个违法行为",
            "如存在信息缺口，回答中注明依赖未确认事实的部分。",
        )
    # 多违法行为：随机取 2 条（尽量不同文件）
    pool = clauses[n_single:]
    rng.shuffle(pool)
    for i in range(0, min(n_multi * 2, len(pool) - 1), 2):
        pair = [pool[i], pool[i + 1]]
        samples += _gen_one(
            llm, pair, titles, "含两个独立违法行为，可能涉及不同违法主体",
            "逐一识别每个违法行为，不要漏掉任何一个。",
        )
    return samples


def _gen_one(llm, clauses, titles, n_violations, extra) -> list[dict]:
    out = llm.chat(
        [{
            "role": "user",
            "content": CONSULT_PROMPT.format(
                clauses_block=_clauses_block(clauses, titles),
                n_violations=n_violations,
                extra_instruction=extra,
            ),
        }],
        input_source="kb_clause",
        max_tokens=3000,
    )
    pair = _parse_json_pair(out)
    if pair is None:
        return []
    return [
        {
            "messages": [
                {"role": "user", "content": pair[0]},
                {"role": "assistant", "content": pair[1]},
            ],
            "meta": {
                "type": "consult",
                "doc_id": clauses[0].doc_id,
                "clause_ids": [c.clause_id for c in clauses],
            },
        }
    ]
