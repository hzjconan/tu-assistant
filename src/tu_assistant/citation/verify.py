"""出处校验（research R5）：把模型输出与知识库逐字比对。

对每处引用块：
- 找不到（编号或文件不存在）→ 删除引用块，替换为"此处引用未通过校验，已删除"
- 找到但原文不一致 → 用知识库原文替换（corrected）
- 找到且一致 → 保留（ok）
- 原文省略 → 自动补入知识库原文
- 裸引用（无完整标记的"第X条"）→ 保留，记为 incomplete
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from ..kb.models import Clause
from ..kb.store import article_clauses
from .models import Citation
from .parse import parse_citations

NOT_FOUND_PLACEHOLDER = "〔此处引用未通过校验，已删除〕"


@dataclass
class VerifyResult:
    text: str                     # 校验后的输出（交付给用户）
    citations: list[Citation] = field(default_factory=list)

    @property
    def stats(self) -> dict[str, int]:
        s: dict[str, int] = {"ok": 0, "corrected": 0, "not_found": 0, "incomplete": 0}
        for c in self.citations:
            s[c.verdict] = s.get(c.verdict, 0) + 1
        return s


def _resolve(
    conn: sqlite3.Connection, c: Citation
) -> tuple[Clause | None, str, list[Clause]]:
    """返回 (匹配行, 版本修正后的 version_label, 该条全部行)。"""
    rows = article_clauses(conn, c.title, c.article_no, version_label=c.version_label)
    version_label = c.version_label
    if not rows and c.version_label:
        rows = article_clauses(conn, c.title, c.article_no)
        if rows:
            # 版本写错：按现行版本兜底，版本部分重写为现行版本标签
            doc = conn.execute(
                "SELECT version_label FROM legal_documents WHERE doc_id=?",
                (rows[0].doc_id,),
            ).fetchone()
            version_label = doc[0] if doc else ""
    if rows and not c.version_label:
        # 引用没写版本：若该文件有多个版本，补上现行版本标签（FR-008）
        versions = {
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT version_label FROM legal_documents WHERE title=?",
                (c.title,),
            )
        }
        if len(versions) > 1:
            cur = conn.execute(
                "SELECT version_label FROM legal_documents WHERE title=? AND status='current'",
                (c.title,),
            ).fetchone()
            if cur and cur[0]:
                version_label = cur[0]
    if not rows:
        return None, version_label, []

    if c.item_no is not None:
        row = next(
            (r for r in rows if r.paragraph_no == c.paragraph_no and r.item_no == c.item_no),
            None,
        )
        return row, version_label, rows
    if c.paragraph_no is not None:
        row = next(
            (
                r
                for r in rows
                if r.paragraph_no == c.paragraph_no and r.item_no is None
            ),
            None,
        )
        return row, version_label, rows
    # 只给了条号：整"条"只有一行（单款无项）才能精确解析
    if len(rows) == 1:
        return rows[0], version_label, rows
    return None, version_label, rows  # 多款多条：incomplete


def _fix_version_in_raw(raw: str, version_label: str) -> str:
    """只修正标记里的版本部分，保留模型原来的编号写法。"""
    import re

    if re.search(r"（[^）]*）", raw):
        return re.sub(r"（[^）]*）", f"（{version_label}）", raw, count=1)
    return re.sub(r"》", f"》（{version_label}）", raw, count=1)


def verify_output(text: str, conn: sqlite3.Connection) -> VerifyResult:
    """校验输出文本，返回修正后的文本与各引用的判定结果。"""
    citations = parse_citations(text)
    edits: list[tuple[int, int, str]] = []

    for c in citations:
        if not c.title or c.article_no is None:
            c.verdict = "incomplete"
            continue

        row, version_label, rows = _resolve(conn, c)
        if not rows:
            c.verdict = "not_found"
            end = c.quote_span[1] if c.quote_span else c.span[1]
            edits.append((c.span[0], end, NOT_FOUND_PLACEHOLDER))
            continue

        if row is None:
            c.verdict = "incomplete"  # 编号不够精确，无法唯一定位
            continue

        c.resolved_clause_id = row.clause_id
        canonical = row.text
        if c.item_no is None:
            # "第M款"包含该款下的各项：原文 = 引言 + 各项
            items = [
                r
                for r in rows
                if r.paragraph_no == row.paragraph_no and r.item_no is not None
            ]
            if items:
                canonical = row.text + "".join(i.text for i in items)

        # 版本写错/缺版本需要重写标记的版本部分（编号写法保留模型的）
        marker_fixed = (
            _fix_version_in_raw(c.raw, version_label)
            if version_label != c.version_label
            else c.raw
        )
        version_wrong = marker_fixed != c.raw
        if version_wrong:
            edits.append((c.span[0], c.span[1], marker_fixed))

        if c.quoted_text is None:
            # 省略原文 → 自动补入
            edits.append((c.span[1], c.span[1], f"\n> {canonical}"))
        elif c.quoted_text != canonical:
            q0, q1 = c.quote_span
            edits.append((q0, q1, f"> {canonical}"))
            c.verdict = "corrected"
            continue
        c.verdict = "corrected" if version_wrong else "ok"

    # 从右往左应用编辑
    out = text
    for start, end, repl in sorted(edits, key=lambda e: e[0], reverse=True):
        out = out[:start] + repl + out[end:]

    return VerifyResult(text=out, citations=citations)
