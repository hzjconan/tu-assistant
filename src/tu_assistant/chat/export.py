"""Markdown 导出（T046，FR-032）。

当前轮回复本身就是 Markdown，因此导出函数只负责选取并返回该轮内容；
后续若需要附加会话元信息，可在这里统一处理。
"""

from __future__ import annotations

from .session import Session


def export_markdown(session: Session, turn_index: int | None = None) -> str:
    """返回某轮 assistant 回复的 Markdown；默认最后一轮。"""
    replies = [t for t in session.messages if t.role == "assistant"]
    if not replies:
        return ""
    return replies[turn_index if turn_index is not None else -1].content
