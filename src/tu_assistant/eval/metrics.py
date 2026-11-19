"""评测指标（T035）。

SC-002 条款识别召回率、SC-003 精确率、SC-006 出处标注完整率、
SC-007 引用准确率（校验前 / 校验后分列）、SC-011 文章身份信息（T058）。
"""

from __future__ import annotations

import re

from ..chat.orchestrator import RE_QUESTION_LINE
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
    """SC-005：关联条款完整率（按去重后的责任条款计分，避免整条展开重复计数）。

    对每个被引用且有已确认责任关联的条款，收集其对应的去重责任条款集合，
    计算已出现在输出中的比例。
    """
    from ..kb.store import confirmed_relations_from

    relations = confirmed_relations_from(kb_conn, list(cited_ids))
    liability_targets = {
        r.to_clause_id for r in relations if r.relation_type == "liability_for"
    }
    if not liability_targets:
        return None
    hit = sum(1 for tid in liability_targets if tid in cited_ids)
    return hit / len(liability_targets)


RE_ARTICLE_SEP = re.compile(r"(?m)^-{3,}\s*$")
RE_ARTICLE_H1 = re.compile(r"(?m)^(?=# )")
RE_ARTICLE_SECTION = re.compile(r"(?m)^## (?:案例|以案说法|普法提示)\s*$")


def extract_articles(text: str) -> list[str]:
    """从一轮交付文本中拆出普法文章（citation-format §4）。

    每篇以一级标题开始；标题块内部的 `---`（署名、分隔线）与尾部
    免责声明并入该篇，不另拆。一篇 = 一级标题起、含 ≥1 个文章段落
    （案例/以案说法/普法提示，精确行匹配）的块；标题之前的无标题块
    按 `---` 再分，需 ≥2 个文章段落才算。
    """
    arts = []
    for seg in RE_ARTICLE_H1.split(text):
        seg = seg.strip()
        if not seg:
            continue
        if seg.startswith("# "):
            if RE_ARTICLE_SECTION.search(seg):
                arts.append(seg)
        else:
            for sub in RE_ARTICLE_SEP.split(seg):
                sub = sub.strip()
                if len(RE_ARTICLE_SECTION.findall(sub)) >= 2:
                    arts.append(sub)
    return arts


def article_identity_check(
    turns: list[dict], protected_names: list[dict] | None, article_turns: set[int] | None = None,
) -> dict | None:
    """SC-011：交付文章中不得出现用户在对话中提供的身份信息。

    turns 为 runner 保存的逐轮内容（user/content）；protected_names 为
    [{"name": str, "turn": int}]，turn 是名称首次出现的用户轮次（1 起始），
    该名称自该轮起对之后交付的文章生效。按文章计数：
    可评文章中未出现保护名称的篇数 / 可评篇数。
    返回 None 表示本题无保护名称标注（对照题，不作为 SC-011 证据）。
    """
    if not protected_names:
        return None
    items = []
    unparsed_leaks = []
    reason = "无可评文章"
    known: set[str] = set()
    for i, t in enumerate(turns, 1):
        for pn in protected_names:
            if pn.get("turn") == i:
                known.add(pn["name"])
        content = t.get("content") or ""
        articles = extract_articles(content)
        if article_turns and i in article_turns and not articles and content.strip():
            leaked = sorted(n for n in known if n in content)
            if leaked:
                unparsed_leaks.append({"turn": i, "leaked": leaked})
            if leaked or not detect_refusal(content)["refused"]:
                reason = "未识别出文章结构"
        for j, a in enumerate(articles):
            leaked = sorted(n for n in known if n in a)
            items.append(
                {"turn": i, "article": j + 1, "ok": not leaked, "leaked": leaked}
            )
    passed = sum(1 for it in items if it["ok"])
    return {
        "passed": passed,
        "total": len(items),
        "ratio": passed / len(items) if items else None,
        "protected_count": len(protected_names),
        "items": items,
        "unparsed_leaks": unparsed_leaks,
        "reason": None if items else reason,
    }


REFUSAL_ABILITY = (
    "无法生成", "无法撰写", "无法回答", "无法提供", "无法为您", "不能生成",
    "不能写", "写不了", "没法写", "帮不上忙", "暂不支持", "不便推测作答",
)
REFUSAL_SCOPE = (
    "超出了我的知识范围", "超出本知识库", "超出了本知识库", "超出知识库",
    "不在本知识库", "不在知识范围", "本知识库未收录", "库内没有", "库内无",
    "本知识库缺乏", "缺乏相关依据", "缺乏适用于", "收录范围之外", "知识范围之外",
)
# 保留句末标点，问句之后的独立陈述仍可提供证据。
RE_SENTENCE = re.compile(r"[^。！？!?\n]+[。！？!?]?")


def _scope_match(sentence: str, phrase: str) -> bool:
    pos = sentence.find(phrase)
    while pos >= 0:
        if not phrase.startswith("超出") or pos == 0 or sentence[pos - 1] not in "未没有否不":
            return True
        pos = sentence.find(phrase, pos + len(phrase))
    return False


def detect_refusal(text: str) -> dict:
    """SC-008 初筛，保留结构门槛或证据短语供人工核对。"""
    blocked_by = None
    if extract_articles(text):
        blocked_by = "article"
    elif any(c.title for c in parse_citations(text)):
        blocked_by = "citation"
    if blocked_by:
        return {"refused": False, "evidence": None, "blocked_by": blocked_by}

    follow_up = bool(RE_QUESTION_LINE.search(text) or "请补充" in text)
    for match in RE_SENTENCE.finditer(text):
        sentence = match.group().strip()
        if sentence.endswith(("？", "?")) or sentence.startswith(("如果", "假如", "若", "要是", "一旦")):
            continue
        if not follow_up:
            for phrase in REFUSAL_ABILITY:
                if phrase in sentence:
                    return {"refused": True, "evidence": phrase, "blocked_by": None}
        # 明确的范围说明可以伴随改问建议，证据保留范围短语。
        for phrase in REFUSAL_SCOPE:
            if _scope_match(sentence, phrase):
                return {"refused": True, "evidence": phrase, "blocked_by": None}
    return {"refused": False, "evidence": None, "blocked_by": "follow_up" if follow_up else None}


def refusal_correct(text: str, should_refuse: bool) -> bool:
    return detect_refusal(text)["refused"] == should_refuse


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
