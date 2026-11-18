"""process_turn 的 system prompt 开关（E001 对照实验）。

session.config["use_system_prompt"]=False 时，发给 client 的消息里
不得有 system 角色；默认（True 或未配置）照常 prepend system 消息。
"""

from tu_assistant.chat.orchestrator import process_turn
from tu_assistant.chat.session import new_session
from tu_assistant.kb.store import create_kb
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
