"""process_turn 的 system prompt 开关（E001 对照实验）。

session.config["use_system_prompt"]=False 时，发给 client 的消息里
不得有 system 角色；默认（True 或未配置）照常 prepend system 消息。
"""

from tu_assistant.chat.orchestrator import process_turn
from tu_assistant.chat.session import new_session
from tu_assistant.kb.models import Clause, ClauseRelation, DocumentMeta
from tu_assistant.kb.store import (
    create_kb,
    doc_id_for,
    insert_clause,
    insert_document,
    insert_relation,
)
from tu_assistant.runtime.client import ChatResponse


class _RecordingClient:
    """记录最后一次收到的 messages 的假客户端。"""

    def __init__(self) -> None:
        self.messages: list[dict] | None = None

    def chat(self, messages, temperature=0.7, max_tokens=4096):
        self.messages = messages
        return ChatResponse(content="好的。")


def test_system_prompt_sent_by_default():
    conn = create_kb(":memory:")
    client = _RecordingClient()
    process_turn(new_session({}), "你好", client, conn)
    conn.close()
    assert client.messages[0]["role"] == "system"


def test_system_prompt_sent_when_enabled():
    conn = create_kb(":memory:")
    client = _RecordingClient()
    process_turn(
        new_session({"use_system_prompt": True}), "你好", client, conn
    )
    conn.close()
    assert client.messages[0]["role"] == "system"


def test_no_system_prompt_when_disabled():
    conn = create_kb(":memory:")
    client = _RecordingClient()
    process_turn(
        new_session({"use_system_prompt": False}), "你好", client, conn
    )
    conn.close()
    assert client.messages
    assert all(m["role"] != "system" for m in client.messages)
    assert client.messages[0]["role"] == "user"


def test_related_clause_completion_deduplicates_shared_liability():
    conn = create_kb(":memory:")
    meta = DocumentMeta(title="示例条例", version_label="2026")
    meta.doc_id = doc_id_for(meta.title, meta.version_label)
    insert_document(conn, meta)
    d = meta.doc_id
    for c in (
        Clause(d, 21, 1, None, "第二十一条第1款", text="不得破坏生产秩序。"),
        Clause(d, 21, 2, None, "第二十一条第2款", text="企业不得阻挠协商。"),
        Clause(d, 40, 1, None, "第四十条", text="违反第二十一条的依法处理。"),
    ):
        insert_clause(conn, c)
    insert_relation(conn, ClauseRelation(f"{d}:a21:p1", f"{d}:a40:p1", "liability_for", "rule", True))
    insert_relation(conn, ClauseRelation(f"{d}:a21:p2", f"{d}:a40:p1", "liability_for", "rule", True))
    conn.commit()

    class _StaticClient:
        def chat(self, messages, temperature=0.7, max_tokens=4096):
            return ChatResponse(
                content=(
                    "〔《示例条例》（2026）第二十一条第1款〕\n> 不得破坏生产秩序。\n\n"
                    "〔《示例条例》（2026）第二十一条第2款〕\n> 企业不得阻挠协商。"
                )
            )

    turn = process_turn(new_session({}), "咨询", _StaticClient(), conn)
    conn.close()
    assert turn.content.count("〔《示例条例》（2026）第四十条〕") == 1
