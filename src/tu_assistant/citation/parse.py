"""引用解析：从模型输出中解析引用块与裸引用（contracts/citation-format.md §1）。

引用块::

    〔《文件全称》（版本）第N条第M款第K项〕
    > 条款原文（可省略）

裸引用：正文里出现"第X条"但不在 〔〕 标记内的，记为 incomplete。
"""

from __future__ import annotations

import re

from ..kb.numbers import chinese_to_int
from .models import Citation

_NUM = r"[0-9零〇一二三四五六七八九十百千]+"
RE_MARKER = re.compile(
    rf"〔《(?P<title>[^》]+)》（(?P<version>[^）]+)）"
    rf"第(?P<article>{_NUM})条"
    rf"(?:第(?P<paragraph>[0-9零〇一二三四五六七八九十]+)款)?"
    rf"(?:第(?P<item>[0-9零〇一二三四五六七八九十]+)项)?〕"
)
# 版本部分可选的宽松形式：〔《文件》第N条〕（缺版本时按 incomplete 处理）
RE_MARKER_NO_VERSION = re.compile(
    rf"〔《(?P<title>[^》]+)》第(?P<article>{_NUM})条"
    rf"(?:第(?P<paragraph>[0-9零〇一二三四五六七八九十]+)款)?"
    rf"(?:第(?P<item>[0-9零〇一二三四五六七八九十]+)项)?〕"
)
RE_QUOTE_LINE = re.compile(r"^>\s?", re.M)
RE_BARE_ARTICLE = re.compile(rf"第({_NUM})条")


def parse_citations(text: str) -> list[Citation]:
    """解析输出中的全部引用块与裸引用。"""
    citations: list[Citation] = []

    for m in RE_MARKER.finditer(text):
        citations.append(_make(m, text, has_version=True))
    covered = [(c.span[0], c.span[1]) for c in citations]
    for m in RE_MARKER_NO_VERSION.finditer(text):
        if any(s <= m.start() < e for s, e in covered):
            continue  # 已被带版本的形式吃掉
        citations.append(_make(m, text, has_version=False))

    citations.sort(key=lambda c: c.span[0])

    # 裸引用：标记以外的"第X条"
    for m in RE_BARE_ARTICLE.finditer(text):
        pos = m.start()
        if any(c.span[0] <= pos < c.span[1] for c in citations):
            continue
        # 引用块原文（> 行）里的不算裸引用
        line_start = text.rfind("\n", 0, pos) + 1
        if text[line_start:].startswith(">"):
            continue
        citations.append(
            Citation(
                raw=m.group(0),
                title="",
                article_no=chinese_to_int(m.group(1)),
                verdict="incomplete",
                span=(m.start(), m.end()),
            )
        )
    citations.sort(key=lambda c: c.span[0])
    return citations


def _make(m: re.Match, text: str, has_version: bool) -> Citation:
    c = Citation(
        raw=m.group(0),
        title=m.group("title"),
        version_label=m.group("version") if has_version else "",
        article_no=chinese_to_int(m.group("article")),
        paragraph_no=(
            chinese_to_int(m.group("paragraph")) if m.group("paragraph") else None
        ),
        item_no=chinese_to_int(m.group("item")) if m.group("item") else None,
        span=(m.start(), m.end()),
    )
    if not has_version:
        c.verdict = "incomplete"
    # 标记下一行起连续的 "> " 行为引用的原文
    tail = text[m.end() :]
    quoted: list[str] = []
    qstart = qend = None
    offset = 0
    for line in tail.split("\n"):
        stripped = line.lstrip("\r")
        if not stripped.strip():
            offset += len(line) + 1
            if quoted:
                break
            continue
        if RE_QUOTE_LINE.match(stripped):
            if qstart is None:
                qstart = m.end() + offset
            quoted.append(RE_QUOTE_LINE.sub("", stripped))
            qend = m.end() + offset + len(line)
            offset += len(line) + 1
            continue
        break
    if quoted:
        c.quoted_text = "\n".join(quoted).strip()
        c.quote_span = (qstart, qend) if qstart is not None else None
    return c
