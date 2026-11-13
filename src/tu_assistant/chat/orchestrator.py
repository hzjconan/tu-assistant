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
from .prompts import build_system_prompt
from .session import Session, Turn, add_turn, to_openai_messages

DISCLAIMER = "\n\n---\n*以上内容仅供参考，不构成法律意见。*"
RE_QUESTION_LINE = re.compile(r"^\s*\d+[.、）)]\s*.+[？?]\s*$", re.M)
RE_CONSULT_STRUCTURE = re.compile(r"违法行为认定|适用条款|法律责任")
RE_ARTICLE_STRUCTURE = re.compile(r"案例|以案说法|普法提示")


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
    """处理一轮用户消息，返回助手 Turn（content 已校验）。"""
    add_turn(session, Turn(role="user", content=user_message))

    system_prompt = build_system_prompt(
        max_questions=session.config.get("max_questions_per_turn", 5),
        default_article_count=session.config.get("default_article_count", 3),
    )
    resp = client.chat(to_openai_messages(session, system_prompt),
                       temperature=temperature)
    raw = resp.content

    verified = verify_output(raw, kb_conn)
    text = verified.text

    # 关联补全兜底（FR-019）：被引用条款的已确认关联若未被引用，追加提示
    resolved = {c.resolved_clause_id for c in verified.citations if c.resolved_clause_id}
    related = confirmed_relations_from(kb_conn, list(resolved))
    extra = [
        rel.to_clause_id for rel in related if rel.to_clause_id not in resolved
    ]
    if extra:
        blocks = [_related_clause_block(cid, kb_conn) for cid in extra]
        blocks = [b for b in blocks if b]
        if blocks:
            text += "\n\n**相关条款（系统补充）**\n\n" + "\n\n".join(blocks)

    # 意图与结构识别（用于会话状态与统计）
    has_citation = bool(verified.citations)
    if RE_ARTICLE_STRUCTURE.search(text):
        session.intent = "article"
    elif RE_CONSULT_STRUCTURE.search(text) or has_citation:
        session.intent = "consult"

    if has_citation:
        text += DISCLAIMER

    question_count = len(RE_QUESTION_LINE.findall(text))

    turn = Turn(
        role="assistant",
        content=text,
        raw_content=raw if eval_mode else None,
        citations=verified.citations,
        question_count=question_count,
    )
    add_turn(session, turn)
    return turn
