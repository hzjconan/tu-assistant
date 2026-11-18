"""评测指标（T035）。

SC-002 条款识别召回率、SC-003 精确率、SC-006 出处标注完整率、
SC-007 引用准确率（校验前 / 校验后分列）、SC-011 文章身份信息（T058）。
"""

from __future__ import annotations

import re

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


REFUSAL_MARKERS = [
    "超出", "不在", "不支持", "知识范围",
    "无法回答", "无法帮助", "无法协助", "无法为", "无法提供", "无法生成",
    "不能回答", "不能帮助", "不能提供", "不便回答", "不便提供",
]


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


def article_identity_check(turns: list[dict], protected_names: list[dict]) -> dict | None:
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
    known: set[str] = set()
    for i, t in enumerate(turns, 1):
        for pn in protected_names:
            if pn.get("turn") == i:
                known.add(pn["name"])
        for j, a in enumerate(extract_articles(t.get("content") or "")):
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
        "reason": None if items else "无可评文章",
    }


# 文章题拒答需要"明确拒绝或范围说明"的证据，比一般拒答口径更严：
# "不在"这类弱词在正文中（"当事人不在现场"）或追问中都会误中。
# 能力类表述可独立命中；范围类证据须是直接描述知识库/能力覆盖
# 边界的短语——"范围词 + 语境词"两组词分开匹配会被"预算范围"
# "授权范围"或跨句的"知识库"误中。
ARTICLE_REFUSAL_EXPLICIT = (
    "无法生成", "无法提供", "无法撰写", "无法编写", "无法为您生成",
    "不能生成", "不能提供", "不能撰写", "不支持生成",
    "不在本知识库", "缺乏相关依据", "缺乏适用于",
    "库内无", "库内没有", "本知识库没有", "本知识库缺乏",
)
# 正序分支：触发词同句近距接边界词；"超出"前面是否定或疑问
# 词组（未/不/没/无/否/没有/是否/有无/能否/不是/未有/不会/
# 不能/不该/不应）不命中——"未超出""没有超出""是否有超出"
# 不是越界表述；"原因是超出"的"是"保留肯定含义。
# 倒序分支："之外/以外"必须是知识库边界短语的直接结尾
# （连续匹配，不留间隔）——"知识库，除了期货之外"的"之外"
# 属于另一个短语。
RE_ARTICLE_REFUSAL_SCOPE = re.compile(
    r"(?:(?<!未)(?<!不)(?<!没)(?<!无)(?<!否)"
    r"(?<!没有)(?<!是否)(?<!有无)(?<!能否)(?<!不是)(?<!否有)"
    r"(?<!未有)(?<!不会)(?<!不能)(?<!不该)(?<!不应)超出"
    r"|不在|不属于|未收录|未覆盖|不覆盖|没有收录|缺乏)"
    r"[^。？！?!\n]{0,12}?"
    r"(?:知识库|库内|知识范围|能力范围|收录范围|覆盖范围)"
    r"|(?:本?知识库|知识范围|能力范围)(?:的)?(?:(?:收录|覆盖|适用)?范围)?(?:之外|以外)"
)


def article_refusal_correct(final_text: str) -> bool:
    """预期拒答的文章题：有明确拒绝/范围说明的证据且没有交付文章。

    追问（"请补充具体情况"）、事实比较（"金额超出十万元"）或正文
    碰巧含弱拒答词都不算拒答。
    """
    refused = (
        any(m in final_text for m in ARTICLE_REFUSAL_EXPLICIT)
        or bool(RE_ARTICLE_REFUSAL_SCOPE.search(final_text))
    )
    return refused and not extract_articles(final_text)


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
