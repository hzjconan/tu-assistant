"""Assistant 接口（contracts/system-interface.md §1）。

POC 只实现 TrainedAssistant；RetrievalAssistant 为正式阶段对照组预留。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Protocol

from ..citation.models import Citation
from ..runtime.client import ModelClient
from .orchestrator import process_turn
from .session import Session, new_session


@dataclass
class SessionConfig:
    max_questions_per_turn: int = 5
    default_article_count: int = 3
    max_article_count: int = 10


@dataclass
class Reply:
    content: str
    intent: str | None
    citations: list[Citation] = field(default_factory=list)
    question_count: int = 0
    raw_content: str | None = None


class Assistant(Protocol):
    def new_session(self, config: SessionConfig | None = None) -> str: ...
    def send(self, session_id: str, message: str) -> Reply: ...
    def export_markdown(self, session_id: str, turn_index: int | None = None) -> str: ...
    def close(self, session_id: str) -> None: ...


class TrainedAssistant:
    """POC：自训模型 + 出处校验层，不检索。"""

    def __init__(
        self,
        client: ModelClient,
        kb_conn: sqlite3.Connection,
        *,
        eval_mode: bool = False,
        temperature: float = 0.7,
    ) -> None:
        self._client = client
        self._kb = kb_conn
        self._eval_mode = eval_mode
        self._temperature = temperature
        self._sessions: dict[str, Session] = {}

    def new_session(self, config: SessionConfig | None = None) -> str:
        cfg = config or SessionConfig()
        session = new_session(
            {
                "max_questions_per_turn": cfg.max_questions_per_turn,
                "default_article_count": cfg.default_article_count,
                "max_article_count": cfg.max_article_count,
            }
        )
        self._sessions[session.session_id] = session
        return session.session_id

    def send(self, session_id: str, message: str) -> Reply:
        session = self._sessions[session_id]
        turn = process_turn(
            session,
            message,
            self._client,
            self._kb,
            temperature=self._temperature,
            eval_mode=self._eval_mode,
        )
        return Reply(
            content=turn.content,
            intent=session.intent,
            citations=turn.citations,
            question_count=turn.question_count or 0,
            raw_content=turn.raw_content,
        )

    def export_markdown(self, session_id: str, turn_index: int | None = None) -> str:
        session = self._sessions[session_id]
        replies = [t for t in session.messages if t.role == "assistant"]
        if not replies:
            return ""
        turn = replies[turn_index if turn_index is not None else -1]
        return turn.content

    def close(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
