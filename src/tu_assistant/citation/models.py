"""引用数据类型（data-model.md §1 Citation）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Citation:
    """模型输出中的一处条款引用。"""

    raw: str                       # 原始标记文本
    title: str
    version_label: str = ""
    article_no: int | None = None
    paragraph_no: int | None = None
    item_no: int | None = None
    quoted_text: str | None = None   # 模型给出的原文（> 引用块）
    resolved_clause_id: str | None = None
    verdict: str = "incomplete"      # ok / corrected / not_found / incomplete
    span: tuple[int, int] = (0, 0)   # 在原文中的起止位置
    quote_span: tuple[int, int] | None = None  # 原文引用块的位置
