"""评测指标（T035）。

SC-002 条款识别召回率、SC-003 精确率、SC-006 出处标注完整率、
SC-007 引用准确率（校验前 / 校验后分列）。
"""

from __future__ import annotations

from ..citation.parse import parse_citations
from ..citation.verify import verify_output


def clause_recall_precision(
    cited_ids: set[str], gold_ids: set[str]
) -> tuple[float | None, float | None]:
    """返回 (recall, precision)；无 gold 时 recall=None，无引用时 precision=None。"""
    recall = len(cited_ids & gold_ids) / len(gold_ids) if gold_ids else None
    precision = len(cited_ids & gold_ids) / len(cited_ids) if cited_ids else None
    return recall, precision


def citation_completeness(text: str) -> tuple[int, int]:
    """SC-006：输出中出现的条款引用，标明出处的比例。

    返回 (带完整标记的引用数, 引用总数含裸引用)。
    """
    citations = parse_citations(text)
    total = len(citations)
    complete = sum(1 for c in citations if c.title and c.article_no is not None)
    return complete, total


def citation_accuracy(citations: list) -> dict:
    """SC-007：校验前 / 校验后引用准确率。

    citations 为一次 verify_output 的判定结果：
    - 校验后：ok + corrected 视为正确（已按库修正）；not_found / incomplete 为失败；
    - 校验前：ok 才算正确（corrected = 原文本来就写错了）。
    """
    post_ok = sum(1 for c in citations if c.verdict in {"ok", "corrected"})
    pre_ok = sum(1 for c in citations if c.verdict == "ok")
    resolved = [c for c in citations if c.verdict != "incomplete"]
    n = len(resolved)
    return {
        "pre": pre_ok / n if n else None,
        "post": post_ok / n if n else None,
        "n": n,
        "counts": {
            "ok": sum(1 for c in citations if c.verdict == "ok"),
            "corrected": sum(1 for c in citations if c.verdict == "corrected"),
            "not_found": sum(1 for c in citations if c.verdict == "not_found"),
            "incomplete": sum(1 for c in citations if c.verdict == "incomplete"),
        },
    }


def score_case_output(raw_text: str, gold: dict, kb_conn) -> dict:
    """对一条单轮输出打分（条款识别 + 引用指标）。"""
    verified = verify_output(raw_text, kb_conn)
    cited = {c.resolved_clause_id for c in verified.citations if c.resolved_clause_id}
    gold_ids = set(gold.get("clauses", []))
    recall, precision = clause_recall_precision(cited, gold_ids)
    complete, total = citation_completeness(verified.text)
    acc = citation_accuracy(verified.citations)
    return {
        "cited_clause_ids": sorted(cited),
        "recall": recall,
        "precision": precision,
        "citation_complete": complete,
        "citation_total": total,
        "citation_acc": acc,
        "verified_text": verified.text,
        "citations": verified.citations,
    }
