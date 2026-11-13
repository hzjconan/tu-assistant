"""条款关联的规则抽取（T017）。

从条款原文里识别明文引用，生成候选 ClauseRelation（confirmed=false），
经人工确认后才用于训练数据与关联补全兜底。

方向约定：``from`` = 被引用的条款（如被违反的义务条款），
``to`` = 含有该引用的条款（如法律责任条款）。这样编排层拿到
"模型引用了条款 A"就能查"还有没有已确认的相关条款"。

只处理同一份文件内的引用（"本法第X条"）；跨文件引用留到正式阶段。
"""

from __future__ import annotations

import re

from .models import Clause, ClauseRelation
from .numbers import chinese_to_int

# (正则, 关系类型)
# 注意：所有模式都要求"第X条"前面有触发词，避免把普通提及全抽进来
_PATTERNS: list[tuple[re.Pattern, str]] = [
    # "违反本法第X条（规定）" / "违反第X条" → 本条款是第X条的法律责任
    (re.compile(r"违反本?[法条例规定章]*?第([0-9零〇一二三四五六七八九十百千]+)条"), "liability_for"),
    # "有第X条所列（行为|情形）" → 同上
    (re.compile(r"第([0-9零〇一二三四五六七八九十百千]+)条所列"), "liability_for"),
    # "第X条（规定）的除外" → 本条款是第X条的例外
    (re.compile(r"第([0-9零〇一二三四五六七八九十百千]+)条(?:规定)?(?:的)?除外"), "exception_of"),
    # "依照|按照|依据|比照 第X条" → 一般引用
    (
        re.compile(r"(?:依照|按照|依据|比照)本?[法条例]*?第([0-9零〇一二三四五六七八九十百千]+)条"),
        "references",
    ),
]


def _article_representative(clauses: list[Clause], article_no: int) -> Clause | None:
    """一条的代表行：item 为空、款号最小的那一行（用于关系端点）。"""
    candidates = [c for c in clauses if c.article_no == article_no and c.item_no is None]
    if not candidates:
        candidates = [c for c in clauses if c.article_no == article_no]
    if not candidates:
        return None
    return min(candidates, key=lambda c: c.paragraph_no or 0)


def extract_relations(clauses: list[Clause]) -> list[ClauseRelation]:
    """对同一份文件的条款列表抽取候选关联。"""
    doc_ids = {c.doc_id for c in clauses}
    if len(doc_ids) != 1:
        raise ValueError("extract_relations 只接受同一份文件的条款")

    relations: dict[tuple, ClauseRelation] = {}
    for c in clauses:
        for pattern, rel_type in _PATTERNS:
            for m in pattern.finditer(c.text):
                target_no = chinese_to_int(m.group(1))
                if target_no is None or target_no == c.article_no:
                    continue
                target = _article_representative(clauses, target_no)
                if target is None:
                    continue
                # 端点用"款/项为空"的代表行，from=被引用条款
                key = (target.clause_id, c.clause_id, rel_type)
                relations.setdefault(
                    key,
                    ClauseRelation(
                        from_clause_id=target.clause_id,
                        to_clause_id=c.clause_id,
                        relation_type=rel_type,
                        origin="rule",
                        confirmed=False,
                    ),
                )
    return list(relations.values())
