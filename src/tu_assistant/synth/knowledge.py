"""知识类样本合成（T040，research R3）。

四类：
1. 条款复述：编号 → 原文（确定性生成，不需要外部模型）
2. 编号与内容互查：描述内容 → 识别条款（外部模型改写场景）
3. 改写问答：每条条款 × rewrite_factor 种说法（外部模型）
4. 条款关系：只用 confirmed=true 的关联（确定性生成）

所有样本的 assistant 输出都遵守引用格式（contracts/citation-format.md）。
"""

from __future__ import annotations

import re
import sqlite3

from ..kb.models import Clause
from ..kb.store import all_clauses
from .llm import ExternalLLM


def _marker(title: str, version: str, c: Clause) -> str:
    v = f"（{version}）" if version else ""
    return f"〔《{title}》{v}{c.number_text}〕"


def _canonical_text(c: Clause, clauses: list[Clause]) -> str:
    """与校验层一致的"完整原文"：该款有项时 = 引言 + 各项。"""
    if c.item_no is not None:
        return c.text
    items = [
        x
        for x in clauses
        if x.doc_id == c.doc_id
        and x.article_no == c.article_no
        and x.paragraph_no == c.paragraph_no
        and x.item_no is not None
    ]
    return c.text + "".join(i.text for i in items) if items else c.text


def recitation_samples(
    clauses: list[Clause], titles: dict[str, tuple[str, str]]
) -> list[dict]:
    """条款复述：确定性生成"第N条内容是什么 → 引用块+原文"。"""
    samples = []
    for c in clauses:
        title, version = titles[c.doc_id]
        q = f"《{title}》{c.number_text}的内容是什么？"
        a = f"{_marker(title, version, c)}\n> {_canonical_text(c, clauses)}"
        samples.append(
            {
                "messages": [
                    {"role": "user", "content": q},
                    {"role": "assistant", "content": a},
                ],
                "meta": {"type": "knowledge", "kind": "recite",
                         "doc_id": c.doc_id, "clause_ids": [c.clause_id]},
            }
        )
    return samples


REWRITE_PROMPT = """\
你是工会法律领域的训练数据编写员。根据下面的法律条款，写一个自然语言问答样本：
- user：一个工会工作人员可能问的问题或描述的场景（口语化，不出现条款编号
  与法规名称）；
- assistant：简短回答，必须引用如下标记给出条款出处：
  {marker}
  > {clause_text}

条款：{clause_text}
只输出 JSON：{{"user": "...", "assistant": "..."}}"""


def paraphrase_samples(
    clauses: list[Clause],
    titles: dict[str, tuple[str, str]],
    llm: ExternalLLM,
    rewrite_factor: int,
) -> list[dict]:
    """改写问答：每条条款让外部模型写 rewrite_factor 种问法。"""
    samples = []
    for c in clauses:
        title, version = titles[c.doc_id]
        marker = _marker(title, version, c)
        for _ in range(rewrite_factor):
            out = llm.chat(
                [{
                    "role": "user",
                    "content": REWRITE_PROMPT.format(
                        marker=marker, clause_text=c.text
                    ),
                }],
                input_source="kb_clause",
            )
            pair = _parse_json_pair(out)
            if pair is None:
                continue
            samples.append(
                {
                    "messages": [
                        {"role": "user", "content": pair[0]},
                        {"role": "assistant", "content": pair[1]},
                    ],
                    "meta": {"type": "knowledge", "kind": "paraphrase",
                             "doc_id": c.doc_id, "clause_ids": [c.clause_id]},
                }
            )
    return samples


def relation_samples(
    kb_conn: sqlite3.Connection,
    titles: dict[str, tuple[str, str]],
) -> list[dict]:
    """条款关系样本：只用 confirmed 关联。"""
    from ..kb.store import get_clause_by_id

    rows = kb_conn.execute(
        "SELECT from_clause_id, to_clause_id, relation_type FROM clause_relations "
        "WHERE confirmed=1"
    ).fetchall()
    samples = []
    for from_id, to_id, rel_type in rows:
        a = get_clause_by_id(kb_conn, from_id)
        b = get_clause_by_id(kb_conn, to_id)
        if a is None or b is None:
            continue
        ta, va = titles[a.doc_id]
        tb, vb = titles[b.doc_id]
        if rel_type == "liability_for":
            q = f"违反《{ta}》{a.number_text}要承担什么法律责任？"
            ans = (
                f"违反该条款的法律责任见：\n{_marker(tb, vb, b)}\n> {b.text}\n\n"
                f"被违反的条款：\n{_marker(ta, va, a)}\n> {a.text}"
            )
        elif rel_type == "exception_of":
            q = f"《{ta}》{a.number_text}有没有例外情形？"
            ans = f"存在例外规定：\n{_marker(tb, vb, b)}\n> {b.text}"
        else:
            q = f"哪些条款引用了《{ta}》{a.number_text}？"
            ans = f"以下条款涉及该条款：\n{_marker(tb, vb, b)}\n> {b.text}"
        samples.append(
            {
                "messages": [
                    {"role": "user", "content": q},
                    {"role": "assistant", "content": ans},
                ],
                "meta": {"type": "knowledge", "kind": f"relation_{rel_type}",
                         "doc_id": a.doc_id, "clause_ids": [a.clause_id, b.clause_id]},
            }
        )
    return samples


def _parse_json_pair(text: str) -> tuple[str, str] | None:
    import json

    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        return d["user"], d["assistant"]
    except (json.JSONDecodeError, KeyError):
        return None


def doc_titles(kb_conn: sqlite3.Connection) -> dict[str, tuple[str, str]]:
    """doc_id → (title, version_label)。"""
    return {
        r[0]: (r[1], r[2] or "")
        for r in kb_conn.execute(
            "SELECT doc_id, title, version_label FROM legal_documents"
        )
    }


def generate(kb_conn: sqlite3.Connection, llm: ExternalLLM | None, cfg: dict) -> list[dict]:
    clauses = [c for c in all_clauses(kb_conn) if len(c.text) >= 10]
    titles = doc_titles(kb_conn)
    samples = recitation_samples(clauses, titles)
    samples += relation_samples(kb_conn, titles)
    if llm is not None:
        samples += paraphrase_samples(
            clauses, titles, llm, cfg.get("rewrite_factor", 4)
        )
    return samples
