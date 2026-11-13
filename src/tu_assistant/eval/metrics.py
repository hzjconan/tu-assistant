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


REFUSAL_MARKERS = ["超出", "无法回答", "不在", "不支持", "无法提供", "无法生成", "知识范围"]


def refusal_correct(text: str, should_refuse: bool) -> bool:
    """SC-008：范围外应拒答，范围内不得误拒。"""
    refused = any(m in text for m in REFUSAL_MARKERS)
    return refused if should_refuse else not refused


def multi_violation_score(cited_ids: set[str], gold_violations: list[dict]) -> float | None:
    """SC-004：多违法行为识别率。

    gold_violations: [{"actor": ..., "clauses": [...]}, ...]。
    每个 gold 违法行为，其条款集合与输出引用有交集即算识别
    （主体名以文本匹配另评，POC 从简）。
    """
    if not gold_violations:
        return None
    hit = sum(
        1 for v in gold_violations if cited_ids & set(v.get("clauses", []))
    )
    return hit / len(gold_violations)


def relation_completion_score(cited_ids: set[str], kb_conn) -> float | None:
    """SC-005：关联条款完整率。

    对每个被引用且有已确认关联的条款，其关联条款也应出现在输出中。
    """
    from ..kb.store import confirmed_relations_from

    relations = confirmed_relations_from(kb_conn, list(cited_ids))
    liability_rels = [r for r in relations if r.relation_type == "liability_for"]
    if not liability_rels:
        return None
    hit = sum(1 for r in liability_rels if r.to_clause_id in cited_ids)
    return hit / len(liability_rels)


def intent_score(turns: list[dict], gold: dict, max_turns: int = 3) -> float | None:
    """SC-001：3 轮以内正确确认意图的比例。

    gold.intent 为期望意图；按各轮 reply.intent 判定，
    在 max_turns 轮内首次出现正确意图记 1.0，否则 0.0。
    """
    expected = gold.get("intent")
    if not expected:
        return None
    for t in turns[:max_turns]:
        if t.get("intent") == expected:
            return 1.0
    return 0.0


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
        "relation_completion": relation_completion_score(cited, kb_conn),
        "verified_text": verified.text,
        "citations": verified.citations,
    }
