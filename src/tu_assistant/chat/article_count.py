"""普法文章数量解析与确定性边界控制（FR-028 / T056）。

职责：
- 校验 SessionConfig / session.config 中的 default_article_count 与 max_article_count
- 复用 anonymize.classify_user_intent_signals 的前置意图信号，识别写稿与修改轮
- 在写稿/改篇动词子句窗口内解析显式篇数或篇数区间，防法律引文、序数词、过去时陈述与案情干扰
- 对非正数或超上限请求返回确定性硬拒提示（文案与 SC-008 域外拒答隔离）
- 仅在未指定篇数（use_default）时构造当轮临时请求副本的篇数附注
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ..kb.numbers import chinese_to_int
from .anonymize import (
    _RE_LOCAL_NEG_SUFFIX,
    classify_user_intent_signals,
    strip_legal_material,
)

DEFAULT_ARTICLE_COUNT = 3
DEFAULT_MAX_ARTICLE_COUNT = 10

ArticleCountAction = Literal["none", "use_requested", "use_default", "rejected"]
ArticleCountReason = Literal["non_positive", "exceeds_max"]

_CN_NONZERO_DIGITS: dict[str, int] = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}

# 标准中文位权整数校验（千 > 百 > 十 > 个单调递减，禁止连续零、十十、三零等畸形组合）
_RE_STRICT_CN_INT = re.compile(
    r"^(?:"
    r"[零〇○]|"
    r"[一二两三四五六七八九]千"
    r"(?:"
    r"[零〇○]?[一二两三四五六七八九]百"
    r"(?:[一二两三四五六七八九]十[一二两三四五六七八九]?|[零〇○][一二两三四五六七八九]|[一二两三四五六七八九])?"
    r"|[零〇○][一二两三四五六七八九]?十[一二两三四五六七八九]?"
    r"|[零〇○][一二两三四五六七八九]"
    r")?|"
    r"[一二两三四五六七八九]百"
    r"(?:[一二两三四五六七八九]十[一二两三四五六七八九]?|[零〇○][一二两三四五六七八九]|[一二两三四五六七八九])?|"
    r"[一二两三四五六七八九]?十[一二两三四五六七八九]?|"
    r"[一二两三四五六七八九]"
    r")$"
)

_WRITE_VERBS = (
    r"(?P<verb>(?:帮我生成|帮我写|帮忙写|整理成|改写成|扩写成|扩写为|"
    r"撰写|生成|起草|写成|编成|改成|改为|再写|再来|多写|补写|给我|写|"
    r"(?<![进发寄送带拿提导输指说看找查推])出|"
    r"(?<![原后发传寄送带拿过回进出起上下])来))(?!了|过)"
)
_REVISE_COUNT_VERBS = (
    r"(?P<verb>(?:帮我生成|帮我写|帮忙写|扩写成|扩写为|调整为|调整成|"
    r"增加到|重写成|改写成|整理成|改写|改成|改为|增至|再写|再来|多写|补写|写成|生成|给我|写))(?!了|过)"
)
_CLAUSE_WINDOW = r"[^。！？，,；;\n：:]{0,16}?"
_NUM_TOKEN = r"(?:-?\d+|[零〇一二两三四五六七八九十百千]+)"
_NUM_LEFT_GUARD = r"(?<![\d一二两三四五六七八九十百千几数上近约])"
_NON_ARTICLE_NOUN_GUARD = r"(?!稿费|稿件|论文|报道|心得|日记|作文)"
_RE_PAST_TENSE_GAP = re.compile(
    r"(?:写了|写过|生成了|生成过|撰写了|撰写过|补写了|补写过|发来|发了|发过|寄了|寄过|送了|送过|出了|出过)"
)
_RE_ORDINAL_PREFIX = re.compile(
    r"第(?:\s*(?:\d+|[一二两三四五六七八九十百千]+)\s*[-~～到至])?\s*$"
)

_RE_WRITE_RANGE = re.compile(
    _WRITE_VERBS
    + _CLAUSE_WINDOW
    + _NUM_LEFT_GUARD
    + rf"(?P<low>{_NUM_TOKEN})\s*(?:[-~～到至])\s*(?P<high>{_NUM_TOKEN})\s*篇"
    + _NON_ARTICLE_NOUN_GUARD
)
_RE_WRITE_SINGLE = re.compile(
    _WRITE_VERBS
    + _CLAUSE_WINDOW
    + _NUM_LEFT_GUARD
    + rf"(?P<num>{_NUM_TOKEN})\s*篇"
    + _NON_ARTICLE_NOUN_GUARD
)

_RE_REVISE_RANGE = re.compile(
    _REVISE_COUNT_VERBS
    + _CLAUSE_WINDOW
    + _NUM_LEFT_GUARD
    + rf"(?P<low>{_NUM_TOKEN})\s*(?:[-~～到至])\s*(?P<high>{_NUM_TOKEN})\s*篇"
    + _NON_ARTICLE_NOUN_GUARD
)
_RE_REVISE_SINGLE = re.compile(
    _REVISE_COUNT_VERBS
    + _CLAUSE_WINDOW
    + _NUM_LEFT_GUARD
    + rf"(?P<num>{_NUM_TOKEN})\s*篇"
    + _NON_ARTICLE_NOUN_GUARD
)


@dataclass(frozen=True)
class ArticleCountDecision:
    """编排层对当前轮次文章数量的确定性决策。"""

    applies: bool
    requested: int | None = None
    target: int | None = None
    action: ArticleCountAction = "none"
    reason: ArticleCountReason | None = None
    notice: str | None = None


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def validate_count_limits(
    default_article_count: object,
    max_article_count: object,
) -> tuple[int, int]:
    """校验文章篇数配置：两者须为正整数且 default <= max，否则抛 ValueError。"""
    if not _is_positive_int(default_article_count):
        raise ValueError(
            f"default_article_count 必须为正整数，当前为 {default_article_count!r}"
        )
    if not _is_positive_int(max_article_count):
        raise ValueError(
            f"max_article_count 必须为正整数，当前为 {max_article_count!r}"
        )
    assert isinstance(default_article_count, int)
    assert isinstance(max_article_count, int)
    if default_article_count > max_article_count:
        raise ValueError(
            f"default_article_count ({default_article_count}) "
            f"不能大于 max_article_count ({max_article_count})"
        )
    return default_article_count, max_article_count


def resolve_count_limits(config: dict | None) -> tuple[int, int]:
    """从 session.config 解析并校验 (default_article_count, max_article_count)。"""
    cfg = config or {}
    default_count = cfg.get("default_article_count", DEFAULT_ARTICLE_COUNT)
    max_count = cfg.get("max_article_count", DEFAULT_MAX_ARTICLE_COUNT)
    return validate_count_limits(default_count, max_count)


def _is_valid_chinese_number(token: str) -> bool:
    """检查是否为合法的标准中文整数写法（严格位权递减，拒绝三零/十十/零零等）。"""
    return bool(_RE_STRICT_CN_INT.fullmatch(token))


def _parse_single_int(token: str) -> int | None:
    token = token.strip()
    if not token:
        return None
    if re.fullmatch(r"-?\d+", token):
        return int(token)
    if not _is_valid_chinese_number(token):
        return None
    return chinese_to_int(token)


def _parse_single_or_approx_pair(token: str) -> tuple[int, int] | None:
    """解析单个数字或两字相邻小约数（如 '两三' -> (2, 3)），返回 (low, high)。"""
    val = _parse_single_int(token)
    if val is not None:
        return val, val
    token = token.strip()
    if (
        len(token) == 2
        and token[0] in _CN_NONZERO_DIGITS
        and token[1] in _CN_NONZERO_DIGITS
    ):
        d1 = _CN_NONZERO_DIGITS[token[0]]
        d2 = _CN_NONZERO_DIGITS[token[1]]
        if d1 < d2:
            return d1, d2
    return None


def _is_valid_match_context(
    cleaned_message: str,
    verb_start: int,
    verb_end: int,
    num_start: int,
) -> bool:
    """过滤局部否定动词、跨过去时陈述及带/不带空格的序数指代（如 '第 2 篇'）。"""
    if _RE_LOCAL_NEG_SUFFIX.search(cleaned_message[:verb_start]):
        return False
    gap = cleaned_message[verb_end:num_start]
    if _RE_PAST_TENSE_GAP.search(gap):
        return False
    return not _RE_ORDINAL_PREFIX.search(cleaned_message[:num_start])


def _extract_count_bounds(
    cleaned_message: str,
    *,
    range_re: re.Pattern[str],
    single_re: re.Pattern[str],
) -> tuple[int, int] | None:
    """在清洗后的用户消息中提取篇数上下界 (low, high)；未指定返回 None。"""
    for m in range_re.finditer(cleaned_message):
        if not _is_valid_match_context(
            cleaned_message,
            m.start("verb"),
            m.end("verb"),
            m.start("low"),
        ):
            continue
        low = _parse_single_int(m.group("low"))
        high = _parse_single_int(m.group("high"))
        if low is not None and high is not None:
            return (min(low, high), max(low, high))

    for m in single_re.finditer(cleaned_message):
        if not _is_valid_match_context(
            cleaned_message,
            m.start("verb"),
            m.end("verb"),
            m.start("num"),
        ):
            continue
        parsed = _parse_single_or_approx_pair(m.group("num"))
        if parsed is not None:
            return parsed

    return None


def _build_reject_notice(
    reason: ArticleCountReason,
    *,
    requested: int,
    default_count: int,
    max_count: int,
) -> str:
    """构造硬拒提示文案（避开 eval/metrics.py SC-008 拒答关键词）。"""
    if reason == "exceeds_max":
        return (
            f"单次最多支持生成 {max_count} 篇普法文章（默认 {default_count} 篇），"
            f"当前请求为 {requested} 篇。请将篇数调整至 1–{max_count} 篇后重新发送。"
        )
    return (
        f"普法文章生成篇数须为 1–{max_count} 之间的正整数（默认 {default_count} 篇），"
        f"当前请求为 {requested} 篇。请调整篇数后重新发送。"
    )


def _evaluate_bounds(
    low: int,
    high: int,
    *,
    default_count: int,
    max_count: int,
) -> ArticleCountDecision:
    if low <= 0 or high <= 0:
        bad = low if low <= 0 else high
        return ArticleCountDecision(
            applies=True,
            requested=bad,
            target=None,
            action="rejected",
            reason="non_positive",
            notice=_build_reject_notice(
                "non_positive",
                requested=bad,
                default_count=default_count,
                max_count=max_count,
            ),
        )
    if high > max_count:
        return ArticleCountDecision(
            applies=True,
            requested=high,
            target=None,
            action="rejected",
            reason="exceeds_max",
            notice=_build_reject_notice(
                "exceeds_max",
                requested=high,
                default_count=default_count,
                max_count=max_count,
            ),
        )
    return ArticleCountDecision(
        applies=True,
        requested=high,
        target=high,
        action="use_requested",
    )


def decide_article_count(
    user_message: str,
    config: dict | None,
    *,
    article_task_active: bool = False,
) -> ArticleCountDecision:
    """对当前用户输入做出确定性的文章数量决策。"""
    default_count, max_count = resolve_count_limits(config)
    signals = classify_user_intent_signals(
        user_message,
        article_task_active=article_task_active,
    )

    if signals.negated or signals.explicit_consult:
        return ArticleCountDecision(applies=False, action="none")

    cleaned = strip_legal_material(user_message)

    if signals.explicit_write:
        bounds = _extract_count_bounds(
            cleaned,
            range_re=_RE_WRITE_RANGE,
            single_re=_RE_WRITE_SINGLE,
        )
        if bounds is not None:
            return _evaluate_bounds(
                bounds[0],
                bounds[1],
                default_count=default_count,
                max_count=max_count,
            )
        return ArticleCountDecision(
            applies=True,
            requested=None,
            target=default_count,
            action="use_default",
        )

    is_revise_context = (
        signals.explicit_revise
        or signals.elliptical_revise
        or article_task_active
    )
    if is_revise_context:
        bounds = _extract_count_bounds(
            cleaned,
            range_re=_RE_REVISE_RANGE,
            single_re=_RE_REVISE_SINGLE,
        )
        if bounds is not None:
            return _evaluate_bounds(
                bounds[0],
                bounds[1],
                default_count=default_count,
                max_count=max_count,
            )

    return ArticleCountDecision(applies=False, action="none")


def build_article_count_instruction(target: int) -> str:
    """仅在 use_default 时附加到当轮临时请求副本末尾的篇数附注。"""
    if target == 1:
        return "\n（篇数要求：请生成 1 篇普法文章；如主题超出知识库范围请直接拒答。）"
    return (
        f"\n（篇数要求：请生成 {target} 篇普法文章，"
        "每篇以一级标题开始、篇间用 --- 分隔，各篇场景须有实质差异；"
        "如主题超出知识库范围请直接拒答。）"
    )
