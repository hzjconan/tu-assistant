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
    # 最终交付文本中已核准标记与 KB 确认原文的半开区间 [start, end)
    protected_spans: list[tuple[int, int]] = field(default_factory=list)

    @property
    def stats(self) -> dict[str, int]:
        s: dict[str, int] = {"ok": 0, "corrected": 0, "not_found": 0, "incomplete": 0}
        for c in self.citations:
            s[c.verdict] = s.get(c.verdict, 0) + 1
        return s

    @property
    def fallback_para_matches(self) -> int:
        """多款条文未写款号、凭引文唯一匹配某款的兼容回退次数（T077 口径 C）。"""
        return sum(1 for c in self.citations if c.fallback_para_match)


def _resolve(
    conn: sqlite3.Connection, c: Citation
) -> tuple[Clause | None, str, list[Clause], bool]:
    """返回 (匹配行, 版本修正后的 version_label, 该条全部行, 是否多款引文回退)。"""
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
        return None, version_label, [], False

    distinct_paras = {r.paragraph_no for r in rows}

    if c.item_no is not None:
        if c.paragraph_no is not None:
            row = next(
                (
                    r
                    for r in rows
                    if r.paragraph_no == c.paragraph_no and r.item_no == c.item_no
                ),
                None,
            )
            return row, version_label, rows, False
        item_rows = [r for r in rows if r.item_no == c.item_no]
        if len(item_rows) == 1:
            return item_rows[0], version_label, rows, False
    elif c.paragraph_no is not None:
        row = next(
            (
                r
                for r in rows
                if r.paragraph_no == c.paragraph_no and r.item_no is None
            ),
            None,
        )
        return row, version_label, rows, False
    elif len(distinct_paras) == 1:
        # 只给了条号且该条只有 1 款（含单款无项与单款含项）：无歧义定位该款主行
        main_rows = [r for r in rows if r.item_no is None]
        if len(main_rows) == 1:
            return main_rows[0], version_label, rows, False

    if c.quoted_text:
        candidates = [
            r for r in rows if _canonical_for_row(r, rows) == c.quoted_text
        ]
        if len(candidates) == 1:
            is_multi_para_fallback = (
                c.paragraph_no is None
                and c.item_no is None
                and len(distinct_paras) >= 2
            )
            return candidates[0], version_label, rows, is_multi_para_fallback
    return None, version_label, rows, False  # 编号/原文都不能唯一定位：incomplete


def _canonical_for_row(row: Clause, rows: list[Clause]) -> str:
    if row.item_no is not None:
        return row.text
    items = [
        r for r in rows
        if r.paragraph_no == row.paragraph_no and r.item_no is not None
    ]
    return row.text + "".join(i.text for i in items) if items else row.text


def _fix_version_in_raw(raw: str, version_label: str) -> str:
    """只修正标记里的版本部分，保留模型原来的编号写法。"""
    import re

    if re.search(r"（[^）]*）", raw):
        return re.sub(r"（[^）]*）", f"（{version_label}）", raw, count=1)
    return re.sub(r"》", f"》（{version_label}）", raw, count=1)


def verify_output(text: str, conn: sqlite3.Connection) -> VerifyResult:
    """校验输出文本，返回修正后的文本、各引用的判定结果与核准区间。"""
    citations = parse_citations(text)
    # (start, end, kind, repl, protect_slice)
    # kind: "edit"（替换/插入）或 "keep"（原样保留但须受保护）
    events: list[tuple[int, int, str, str, tuple[int, int] | None]] = []

    for c in citations:
        if not c.title or c.article_no is None:
            c.verdict = "incomplete"
            continue

        row, version_label, rows, is_fallback = _resolve(conn, c)
        if not rows:
            c.verdict = "not_found"
            end = c.quote_span[1] if c.quote_span else c.span[1]
            events.append((c.span[0], end, "edit", NOT_FOUND_PLACEHOLDER, None))
            continue

        if row is None:
            c.verdict = "incomplete"  # 编号不够精确，无法唯一定位
            continue

        c.resolved_clause_id = row.clause_id
        c.fallback_para_match = is_fallback
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
            events.append(
                (
                    c.span[0],
                    c.span[1],
                    "edit",
                    marker_fixed,
                    (0, len(marker_fixed)),
                )
            )
        else:
            events.append((c.span[0], c.span[1], "keep", "", None))

        if c.quoted_text is None:
            # 省略原文 → 自动补入；仅保护 "> {canonical}"，不含前导换行
            repl = f"\n> {canonical}"
            events.append((c.span[1], c.span[1], "edit", repl, (1, len(repl))))
        elif c.quoted_text != canonical:
            q0, q1 = c.quote_span
            repl = f"> {canonical}"
            events.append((q0, q1, "edit", repl, (0, len(repl))))
            c.verdict = "corrected"
            continue
        else:
            q0, q1 = c.quote_span
            events.append((q0, q1, "keep", "", None))
        c.verdict = "corrected" if version_wrong else "ok"

    # 从左往右应用编辑，精确追踪最终交付文本中的核准区间
    chunks: list[str] = []
    protected_spans: list[tuple[int, int]] = []
    out_len = 0
    cursor = 0
    for start, end, kind, repl, protect_slice in sorted(
        events, key=lambda e: (e[0], e[1])
    ):
        if start < cursor:
            continue
        if start > cursor:
            seg = text[cursor:start]
            chunks.append(seg)
            out_len += len(seg)
            cursor = start
        if kind == "keep":
            seg = text[start:end]
            protected_spans.append((out_len, out_len + len(seg)))
            chunks.append(seg)
            out_len += len(seg)
            cursor = end
        else:
            chunks.append(repl)
            if protect_slice is not None:
                p0, p1 = protect_slice
                protected_spans.append((out_len + p0, out_len + p1))
            out_len += len(repl)
            cursor = end

    if cursor < len(text):
        chunks.append(text[cursor:])

    return VerifyResult(
        text="".join(chunks),
        citations=citations,
        protected_spans=protected_spans,
    )
