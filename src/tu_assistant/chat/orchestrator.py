"""对话编排（T027、research R6）：模型调用前后的确定性处理。

职责：
- 拼装 system prompt（含 max_questions_per_turn）
- 调用模型
- 出处校验
- 关联补全兜底：已确认 ClauseRelation 中未被引用的关联条款，末尾追加提示（FR-019）
- 咨询回答末尾固定追加免责提示（FR-023）
- 统计本轮追问问题数
- 评测模式下保留模型原始输出（raw_content）
"""

from __future__ import annotations

import re
import sqlite3

from ..citation.verify import verify_output
from ..kb.store import confirmed_relations_from, get_clause_by_id, get_document
from ..runtime.client import ModelClient
from .anonymize import (
    anonymize_article_text,
    classify_turn_intent,
    extract_user_entities,
    sanitize_citations,
)
from .prompts import build_system_prompt
from .session import Session, Turn, add_turn, to_openai_messages

DISCLAIMER = "\n\n---\n*以上内容仅供参考，不构成法律意见。*"
RE_QUESTION_LINE = re.compile(r"^\s*\d+[.、）)]\s*.+[？?]\s*$", re.M)


def _related_clause_block(clause_id: str, conn: sqlite3.Connection) -> str | None:
    c = get_clause_by_id(conn, clause_id)
    if c is None:
        return None
    doc = get_document(conn, c.doc_id)
    title = doc.title if doc else c.doc_id
    version = f"（{doc.version_label}）" if doc and doc.version_label else ""
    no = c.number_text
    return f"〔《{title}》{version}{no}〕\n> {c.text}"


def process_turn(
    session: Session,
    user_message: str,
    client: ModelClient,
    kb_conn: sqlite3.Connection,
    *,
    temperature: float = 0.7,
    eval_mode: bool = False,
) -> Turn:
    """处理一轮用户消息，返回助手 Turn（content 已校验与脱敏）。"""
    extract_user_entities(
        user_message,
        session.anonymize_state,
        session.user_entities,
    )
    add_turn(session, Turn(role="user", content=user_message))

    system_prompt = (
        build_system_prompt(
            max_questions=session.config.get("max_questions_per_turn", 5),
            default_article_count=session.config.get("default_article_count", 3),
        )
        if session.config.get("use_system_prompt", True)
        else None
    )
    resp = client.chat(to_openai_messages(session, system_prompt),
                       temperature=temperature)
    raw = resp.content

    verified = verify_output(raw, kb_conn)
    text = verified.text
    protected_spans = list(verified.protected_spans)

    # 关联补全兜底（FR-019）：被引用条款的已确认关联若未被引用，追加提示
    resolved = {c.resolved_clause_id for c in verified.citations if c.resolved_clause_id}
    related = confirmed_relations_from(kb_conn, list(resolved))
    extra = list(
        dict.fromkeys(
            rel.to_clause_id for rel in related if rel.to_clause_id not in resolved
        )
    )
    if extra:
        blocks = [_related_clause_block(cid, kb_conn) for cid in extra]
        blocks = [b for b in blocks if b]
        if blocks:
            text += "\n\n**相关条款（系统补充）**\n\n"
            for i, block in enumerate(blocks):
                if i > 0:
                    text += "\n\n"
                start = len(text)
                text += block
                protected_spans.append((start, len(text)))

    # 统一维护本轮会话意图、文章续改状态与是否执行身份检查
    has_citation = bool(verified.citations)
    new_intent, new_active, should_anonymize = classify_turn_intent(
        user_message,
        text,
        has_citation=has_citation,
        article_task_active=session.anonymize_state.article_task_active,
        current_intent=session.intent,
    )
    session.intent = new_intent
    session.anonymize_state.article_task_active = new_active

    if has_citation:
        text += DISCLAIMER

    citations = verified.citations
    person_replacements = 0
    org_replacements = 0
    anonymize_blocked = False
    if should_anonymize:
        anon = anonymize_article_text(text, session.anonymize_state, protected_spans)
        text = anon.text
        person_replacements = anon.person_replacements
        org_replacements = anon.org_replacements
        anonymize_blocked = anon.blocked
        if anonymize_blocked:
            citations = []
        else:
            citations = sanitize_citations(
                verified.citations, session.anonymize_state, draft_text=text
            )

    question_count = 0 if anonymize_blocked else len(RE_QUESTION_LINE.findall(text))

    turn = Turn(
        role="assistant",
        content=text,
        raw_content=raw if eval_mode else None,
        citations=citations,
        question_count=question_count,
        person_replacements=person_replacements,
        org_replacements=org_replacements,
        anonymize_blocked=anonymize_blocked,
    )
    add_turn(session, turn)
    return turn
