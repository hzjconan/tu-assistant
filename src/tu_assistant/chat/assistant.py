"""Assistant 接口（contracts/system-interface.md §1）。

POC 只实现 TrainedAssistant；RetrievalAssistant 为正式阶段对照组预留。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Protocol

from ..citation.models import Citation
from ..runtime.client import ModelClient
from .export import export_markdown
from .orchestrator import process_turn
from .session import Session, new_session


@dataclass
class SessionConfig:
    max_questions_per_turn: int = 5
    default_article_count: int = 3
    max_article_count: int = 10
    use_system_prompt: bool = True


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
                "use_system_prompt": cfg.use_system_prompt,
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
        return export_markdown(self._sessions[session_id], turn_index)

    def _last_turn_anonymize_info(self, session_id: str) -> dict:
        """仅供合成评测 runner 在 close 前读取最近一轮的内存脱敏统计。"""
        session = self._sessions.get(session_id)
        if not session or not session.messages:
            return {
                "person_replacements": 0,
                "org_replacements": 0,
                "blocked": False,
            }
        last = session.messages[-1]
        return {
            "person_replacements": last.person_replacements,
            "org_replacements": last.org_replacements,
            "blocked": last.anonymize_blocked,
        }

    def close(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
