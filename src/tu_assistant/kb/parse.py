"""条款切分：把纯文本法律文档切成条 / 款 / 项。

识别：
- ``第X编 / 第X章 / 第X节`` 标题路径
- ``第X条``（含"第X条之一"）开始新条款
- 条内自然段为"款"（"第X条"同一行的内容算第 1 款）
- ``（一）（二）`` 为"项"（可在行首或行内）
- 没有"第X条"结构的文件，用"一、二、"分段（通知类文件）

输出 Clause 列表；结构性问题记入返回的 warnings（文件级）。
"""

from __future__ import annotations

import re

from .models import Clause
from .numbers import chinese_to_int

RE_HEADING = re.compile(r"^第([0-9零〇一二三四五六七八九十百千]+)(编|章|节)\s*(.*)$")
RE_ARTICLE = re.compile(r"^第([0-9零〇一二三四五六七八九十百千]+)条(之[一二三四五六七八九十])?\s*(.*)$")
RE_ITEM_INLINE = re.compile(r"（([0-9零〇一二三四五六七八九十]+)）")
RE_ITEM_AT_START = re.compile(r"^（([0-9零〇一二三四五六七八九十]+)）\s*(.*)$")
RE_SECTION_CN = re.compile(r"^([0-9零〇一二三四五六七八九十]+)、\s*(.*)$")

_HEADING_ORDER = {"编": 0, "章": 1, "节": 2}
_CN_NUM = "零一二三四五六七八九"


def parse_clauses(lines: list[str], doc_id: str) -> tuple[list[Clause], list[str]]:
    """切分行列表。返回 (clauses, warnings)。"""
    if not lines:
        return [], ["empty_document"]

    has_article = any(RE_ARTICLE.match(line) for line in lines)
    if has_article:
        return _parse_article_style(lines, doc_id)
    return _parse_section_style(lines, doc_id)


def _split_items(text: str) -> tuple[str, list[tuple[int, str]]]:
    """把含（一）（二）… 的段落拆成引言 + 各项。"""
    matches = list(RE_ITEM_INLINE.finditer(text))
    if not matches:
        return text, []
    intro = text[: matches[0].start()].strip()
    items: list[tuple[int, str]] = []
    for i, m in enumerate(matches):
        no = chinese_to_int(m.group(1)) or i + 1
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        # 项的原文保留（N）标记，便于逐字引用
        items.append((no, text[m.start() : end].strip()))
    return intro, items


def _emit_paragraph(
    clauses: list[Clause],
    doc_id: str,
    article_no: int,
    para_no: int,
    number_text: str,
    heading: list[str],
    text: str,
) -> None:
    """一款入列；含（N）项时拆为引言（item_no=None）+ 各项。"""
    text = text.strip()
    if not text:
        return
    intro, items = _split_items(text)
    if not items:
        clauses.append(
            Clause(doc_id, article_no, para_no, None, number_text, list(heading), text)
        )
        return
    if intro:
        clauses.append(
            Clause(doc_id, article_no, para_no, None, number_text, list(heading), intro)
        )
    for item_no, item_text in items:
        clauses.append(
            Clause(
                doc_id,
                article_no,
                para_no,
                item_no,
                (
                    f"{number_text}第{_CN_NUM[item_no]}项"
                    if item_no and item_no < 10
                    else f"{number_text}第{item_no}项"
                ),
                list(heading),
                item_text,
            )
        )


def _parse_article_style(
    lines: list[str], doc_id: str
) -> tuple[list[Clause], list[str]]:
    clauses: list[Clause] = []
    warnings: list[str] = []
    heading: list[tuple[int, str]] = []  # (层级, 标题)
    cur_article: int | None = None
    cur_number_text = ""
    cur_para_no = 0
    cur_para_lines: list[str] = []
    seen_articles: set[int] = set()

    def heading_titles() -> list[str]:
        return [t for _, t in heading]

    def flush_para() -> None:
        nonlocal cur_para_lines
        if cur_article is not None and cur_para_lines:
            _emit_paragraph(
                clauses,
                doc_id,
                cur_article,
                cur_para_no,
                cur_number_text + (f"第{cur_para_no}款" if cur_para_no > 1 else ""),
                heading_titles(),
                "".join(cur_para_lines),
            )
        cur_para_lines = []

    for line in lines:
        m = RE_HEADING.match(line)
        if m:
            level = _HEADING_ORDER[m.group(2)]
            heading = [h for h in heading if h[0] < level]
            heading.append((level, line.strip()))
            continue

        m = RE_ARTICLE.match(line)
        if m:
            flush_para()
            no = chinese_to_int(m.group(1))
            suffix = m.group(2) or ""
            if no is None:
                warnings.append(f"unparseable_article_number: {line[:20]}")
                continue
            if no in seen_articles and not suffix:
                warnings.append(f"duplicate_article: {no}")
            seen_articles.add(no)
            cur_article = no
            cur_number_text = f"第{m.group(1)}条{suffix}"
            cur_para_no = 1
            rest = m.group(3).strip()
            cur_para_lines = [rest] if rest else []
            continue

        if cur_article is None:
            continue  # 第一条之前的文件头（标题、公布机关、日期等）

        if RE_ITEM_AT_START.match(line):
            # （一）（二）… 项是当前款的组成部分，并入当前款再按项拆分
            cur_para_lines.append(line)
            continue

        # 条内的其他行都是新的一款（"一、"开头同样按款处理）
        flush_para()
        cur_para_no += 1
        cur_para_lines = [line]

    flush_para()
    return clauses, warnings


def _parse_section_style(
    lines: list[str], doc_id: str
) -> tuple[list[Clause], list[str]]:
    """无"第X条"结构：用"一、二、"分段；段内（一）（二）为项。"""
    clauses: list[Clause] = []
    warnings: list[str] = []
    cur_no = 0
    cur_lines: list[str] = []
    started = False

    def flush() -> None:
        nonlocal cur_lines
        if not cur_lines:
            return
        text = "".join(cur_lines)
        intro, items = _split_items(text)
        if items:
            if intro:
                clauses.append(Clause(doc_id, cur_no, 1, None, f"第{cur_no}段", [], intro))
            for item_no, item_text in items:
                clauses.append(
                    Clause(doc_id, cur_no, 1, item_no, f"第{cur_no}段", [], item_text)
                )
        else:
            clauses.append(Clause(doc_id, cur_no, 1, None, f"第{cur_no}段", [], text))
        cur_lines = []

    for line in lines:
        m = RE_SECTION_CN.match(line)
        if m and chinese_to_int(m.group(1)) is not None:
            flush()
            cur_no += 1
            started = True
            cur_lines = [m.group(2).strip()]
            continue
        if not started:
            continue  # 文件头
        cur_lines.append(line)

    flush()
    if not clauses:
        warnings.append("no_clause_structure")
    return clauses, warnings
