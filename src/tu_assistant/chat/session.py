"""会话（仅内存，FR-009 / data-model.md §2）。

会话结束即销毁，不落盘；跨会话记忆不在范围内。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class Turn:
    role: str                      # user / assistant
    content: str                   # 交付给用户的 Markdown（已经过校验层）
    raw_content: str | None = None  # 模型原始输出（仅评测时保留）
    citations: list = field(default_factory=list)
    question_count: int | None = None


@dataclass
class Session:
    session_id: str
    messages: list[Turn] = field(default_factory=list)
    intent: str | None = None       # consult / article / None
    user_entities: set[str] = field(default_factory=set)
    config: dict = field(default_factory=dict)


def new_session(config: dict) -> Session:
    return Session(session_id=uuid.uuid4().hex[:12], config=config)


def add_turn(session: Session, turn: Turn) -> None:
    session.messages.append(turn)


def to_openai_messages(session: Session, system_prompt: str) -> list[dict]:
    """会话历史转 OpenAI messages（用户输入用原始文本，助手回复用交付文本）。"""
    msgs = [{"role": "system", "content": system_prompt}]
    for t in session.messages:
        msgs.append({"role": t.role, "content": t.content})
    return msgs
