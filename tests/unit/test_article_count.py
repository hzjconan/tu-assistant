"""普法文章数量解析、配置校验、编排接线与回归测试（T056 / FR-028）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tu_assistant.chat.article_count import (
    build_article_count_instruction,
    decide_article_count,
    resolve_count_limits,
    validate_count_limits,
)
from tu_assistant.chat.assistant import SessionConfig, TrainedAssistant
from tu_assistant.chat.orchestrator import process_turn
from tu_assistant.chat.prompts import build_system_prompt
from tu_assistant.chat.session import new_session
from tu_assistant.cli import app
from tu_assistant.eval.cases import load_cases
from tu_assistant.eval.metrics import (
    article_identity_check,
    detect_refusal,
    extract_articles,
)
from tu_assistant.kb.models import Clause, DocumentMeta
from tu_assistant.kb.store import (
    create_kb,
    doc_id_for,
    insert_clause,
    insert_document,
    open_kb,
)
from tu_assistant.runtime.client import ChatResponse

REPO_ROOT = Path(__file__).resolve().parents[2]


class _FakeClient:
    """记录发出的 messages 列表并按预设回复返回的假模型客户端。"""

    def __init__(self, replies: list[str] | None = None) -> None:
        self.replies = list(replies or [])
        self.calls: list[list[dict]] = []

    def chat(self, messages: list[dict], *, temperature: float = 0.7) -> ChatResponse:
        self.calls.append([dict(m) for m in messages])
        if not self.replies:
            raise AssertionError("意外调用了 client.chat")
        return ChatResponse(content=self.replies.pop(0))


def _make_kb():
    conn = create_kb(":memory:")
    meta = DocumentMeta(title="中华人民共和国劳动法", version_label="2018-12-29")
    meta.doc_id = doc_id_for(meta.title, meta.version_label)
    insert_document(conn, meta)
    insert_clause(
        conn,
        Clause(
            doc_id=meta.doc_id,
            article_no=50,
            paragraph_no=1,
            item_no=None,
            number_text="第五十条",
            text="工资应当以货币形式按月支付给劳动者本人。不得克扣或者无故拖欠劳动者的工资。",
        ),
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# 1. 配置校验（Fail-Fast）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("default_n", "max_n"),
    [(1, 1), (3, 10), (10, 10), (2, 5)],
)
def test_valid_count_limits(default_n: int, max_n: int) -> None:
    cfg = SessionConfig(default_article_count=default_n, max_article_count=max_n)
    assert cfg.default_article_count == default_n
    assert cfg.max_article_count == max_n
    assert validate_count_limits(default_n, max_n) == (default_n, max_n)
    assert resolve_count_limits(
        {"default_article_count": default_n, "max_article_count": max_n}
    ) == (default_n, max_n)


def test_resolve_count_limits_fallback() -> None:
    assert resolve_count_limits({}) == (3, 10)
    assert resolve_count_limits(None) == (3, 10)
    assert resolve_count_limits({"max_questions_per_turn": 4}) == (3, 10)


@pytest.mark.parametrize(
    ("default_n", "max_n"),
    [
        (0, 10),
        (-1, 10),
        (3, 0),
        (3, -5),
        (11, 10),
        (True, 10),
        (3, True),
        (False, 10),
        (None, 10),
        ("3", 10),
        (3, 10.0),
    ],
)
def test_invalid_count_limits_raise(default_n, max_n) -> None:
    with pytest.raises(ValueError):
        SessionConfig(default_article_count=default_n, max_article_count=max_n)
    with pytest.raises(ValueError):
        resolve_count_limits(
            {"default_article_count": default_n, "max_article_count": max_n}
        )


def test_process_turn_invalid_session_config_does_not_pollute_session() -> None:
    conn = _make_kb()
    session = new_session({"default_article_count": 0, "max_article_count": 10})
    client = _FakeClient([])
    with pytest.raises(ValueError):
        process_turn(session, "写几篇普法文章", client, conn)
    conn.close()
    assert session.messages == []
    assert client.calls == []


# ---------------------------------------------------------------------------
# 2. 数量解析与防误伤
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("msg", "expected_action", "expected_req", "expected_target"),
    [
        ("帮我写 1 篇普法文章", "use_requested", 1, 1),
        ("帮我写 2 篇普法文章", "use_requested", 2, 2),
        ("帮我写 3 篇普法文章", "use_requested", 3, 3),
        ("帮我写 4 篇普法文章", "use_requested", 4, 4),
        ("帮我写 10 篇普法文章", "use_requested", 10, 10),
        ("写一篇普法文章", "use_requested", 1, 1),
        ("写两篇普法文章", "use_requested", 2, 2),
        ("写二篇普法文章", "use_requested", 2, 2),
        ("写三篇以案说法文章", "use_requested", 3, 3),
        ("给我四篇普法宣传文章", "use_requested", 4, 4),
        ("生成十篇普法短文", "use_requested", 10, 10),
        ("帮我写 2-3 篇普法文章", "use_requested", 3, 3),
        ("帮我写两三篇普法文章", "use_requested", 3, 3),
        ("帮我写几篇关于欠薪的普法文章", "use_default", None, 3),
        ("围绕拖欠工资写普法宣传文章", "use_default", None, 3),
    ],
)
def test_decide_valid_and_default_counts(
    msg: str,
    expected_action: str,
    expected_req: int | None,
    expected_target: int | None,
) -> None:
    d = decide_article_count(msg, {"default_article_count": 3, "max_article_count": 10})
    assert d.applies is True
    assert d.action == expected_action
    assert d.requested == expected_req
    assert d.target == expected_target
    assert d.reason is None
    assert d.notice is None


@pytest.mark.parametrize(
    ("msg", "expected_req", "expected_reason"),
    [
        ("写 11 篇普法文章", 11, "exceeds_max"),
        ("写十五篇普法文章", 15, "exceeds_max"),
        ("生成二十篇以案说法文章", 20, "exceeds_max"),
        ("给我来一百篇普法短文", 100, "exceeds_max"),
        ("帮我写 5-12 篇普法文章", 12, "exceeds_max"),
        ("帮我写 12-15 篇普法文章", 15, "exceeds_max"),
        ("写 5 到 12 篇普法文章", 12, "exceeds_max"),
        ("写 0 篇普法文章", 0, "non_positive"),
        ("写零篇普法文章", 0, "non_positive"),
        ("写 -1 篇普法文章", -1, "non_positive"),
        ("写 -2 篇文章", -2, "non_positive"),
        ("帮我写 0-3 篇普法文章", 0, "non_positive"),
    ],
)
def test_decide_rejected_counts(
    msg: str, expected_req: int, expected_reason: str
) -> None:
    d = decide_article_count(msg, {"default_article_count": 3, "max_article_count": 10})
    assert d.applies is True
    assert d.action == "rejected"
    assert d.requested == expected_req
    assert d.target is None
    assert d.reason == expected_reason
    assert d.notice is not None
    # 文案不得触发 SC-008 域外拒答与文章结构
    assert detect_refusal(d.notice)["refused"] is False
    assert extract_articles(d.notice) == []


def test_approx_pair_respects_custom_max() -> None:
    d = decide_article_count(
        "帮我写两三篇普法文章", {"default_article_count": 1, "max_article_count": 2}
    )
    assert d.action == "rejected"
    assert d.reason == "exceeds_max"
    assert d.requested == 3


@pytest.mark.parametrize(
    ("msg", "active", "expected_action", "expected_target"),
    [
        # B1: 序数词（含/不含空格）不误判为生成篇数，且不遮蔽后文真实篇数
        ("修改第 2 篇，语言更通俗一点", True, "none", None),
        ("把第三篇改通俗一点", True, "none", None),
        ("把文章里的第二篇换成建筑工地", True, "none", None),
        ("重新生成第 2 篇", True, "none", None),
        ("重新生成第 12 篇", True, "none", None),
        ("帮我写第 2 篇普法文章", False, "use_default", 3),
        ("写第 12 篇普法文章", False, "use_default", 3),
        ("写第12篇普法文章", False, "use_default", 3),
        ("重新生成第 2 篇，改成 15 篇", True, "rejected", None),
        # 普通修改不触发默认篇数
        ("措辞再通俗一点", True, "none", None),
        ("换建筑工地再发我一版", True, "none", None),
        # B4: 修改轮/活跃上下文显式指定新篇数（含省略“文章”与单轮扩写）
        ("改成 2 篇", True, "use_requested", 2),
        ("改成 15 篇", True, "rejected", None),
        ("扩写成 12 篇", True, "rejected", None),
        ("再写 11 篇", True, "rejected", None),
        ("改为 0 篇", True, "rejected", None),
        ("帮我写 15 篇", True, "rejected", None),
        ("写 0 篇", True, "rejected", None),
        ("再给我写 15 篇", True, "rejected", None),
        ("把这件事整理成 15 篇", True, "rejected", None),
        ("帮我改写 15 篇", True, "rejected", None),
        ("把这篇文章扩写为 15 篇", False, "rejected", None),
        # B2: 单字来/出构词、过去时陈述与复合否定写稿防误伤
        ("写一篇普法文章：公司克扣 15 篇稿费", False, "use_requested", 1),
        ("我在公司写了 15 篇文章，克扣稿费合法吗？", False, "none", None),
        ("我原来写了 15 篇文章，克扣稿费合法吗？", False, "none", None),
        ("我原来写了 15 篇文章，现在请帮我写一篇新的普法文章", False, "use_requested", 1),
        ("公司发来 12 篇通知，请写一篇普法文章", False, "use_requested", 1),
        ("把公司之前补写了 12 篇材料的事加进案例里", True, "none", None),
        ("不要写 15 篇普法文章，只问怎么处理", False, "none", None),
        ("不要帮我写 15 篇普法文章，只问怎么处理", False, "none", None),
        ("不要再写 15 篇，只写 2 篇普法文章", False, "use_requested", 2),
        ("单位不允许写 15 篇普法文章，合法吗？", False, "none", None),
        ("公司不让我写 15 篇文章，合法吗？", False, "none", None),
        ("写普法文章，依据《某规定》二十篇，案情涉 12 篇稿件", False, "use_default", 3),
        ("帮我写关于公司克扣 15 篇稿费的普法文章", False, "use_default", 3),
        # B3: 非法中文数字组合不误译，回退 use_default；合法多位中文数精确拦截
        ("写三零篇普法文章", False, "use_default", 3),
        ("写十十篇普法文章", False, "use_default", 3),
        ("写零零篇普法文章", False, "use_default", 3),
        ("写一百零篇普法文章", False, "use_default", 3),
        ("写一百零一篇普法文章", False, "rejected", None),
        # R2-B1: 句内带逗号的常见写稿指令不漏判
        ("写 15 篇，关于拖欠工资的普法文章", False, "rejected", None),
        ("请给我写 15 篇，每篇 500 字的普法文章", False, "rejected", None),
        ("写一篇关于欠薪、加班，适合发在宣传栏的普法文章", False, "use_requested", 1),
        ("写一篇，给工厂新职工看的普法短文", False, "use_requested", 1),
        # R2-B2: 口语约数“几十篇/数十篇/上百篇”走 use_default，不误译为 10
        ("写几十篇普法文章", False, "use_default", 3),
        ("写数十篇普法文章", False, "use_default", 3),
        ("写上百篇普法文章", False, "use_default", 3),
        # R2-B3: 序数区间（第 2-12 篇 / 第 2-3 篇）不穿透且不遮蔽后文真实篇数
        ("帮我重写第 2-12 篇", True, "none", None),
        ("写第 2-3 篇普法文章", False, "use_default", 3),
        ("帮我重写第 2-3 篇，改成 15 篇", True, "rejected", None),
        # R2 非阻断建议：给我发了 15 篇通知不误判
        ("公司给我发了 15 篇通知，请写一篇普法文章", False, "use_requested", 1),
    ],
)
def test_ordinal_revise_and_noise_guards(
    msg: str,
    active: bool,
    expected_action: str,
    expected_target: int | None,
) -> None:
    d = decide_article_count(
        msg,
        {"default_article_count": 3, "max_article_count": 10},
        article_task_active=active,
    )
    assert d.action == expected_action
    assert d.target == expected_target


def test_v1_reviewed_60_cases_all_negative_control() -> None:
    cases = load_cases(REPO_ROOT / "eval/cases/v1/reviewed.jsonl")
    assert len(cases) == 60
    for c in cases:
        msg = c.input.get("message") or ""
        d = decide_article_count(msg, {"default_article_count": 3, "max_article_count": 10})
        assert d.action == "none", f"{c.case_id} 误触发: {d}"


def test_v1_articles_10_cases_per_turn_decisions() -> None:
    cases = {c.case_id: c for c in load_cases(REPO_ROOT / "eval/cases/v1/articles.jsonl")}
    assert len(cases) == 10
    cfg = {"default_article_count": 3, "max_article_count": 10}

    # article-001 未指定篇数 -> use_default(3)
    d1 = decide_article_count(cases["article-001"].input["message"], cfg)
    assert (d1.action, d1.target) == ("use_default", 3)

    # article-002..007 明示篇数 -> use_requested
    expected_single = {
        "article-002": 2,
        "article-003": 3,
        "article-004": 4,
        "article-005": 1,
        "article-006": 1,
        "article-007": 1,
    }
    for cid, n in expected_single.items():
        d = decide_article_count(cases[cid].input["message"], cfg)
        assert (d.action, d.requested, d.target) == ("use_requested", n, n), cid

    # article-008: T1 写一篇 -> use_requested(1), T2 改通俗 -> none
    s8 = cases["article-008"].input["script"]
    assert decide_article_count(s8[0], cfg).action == "use_requested"
    assert decide_article_count(s8[1], cfg, article_task_active=True).action == "none"

    # article-009: T1 咨询 -> none, T2 写三篇 -> use_requested(3)
    s9 = cases["article-009"].input["script"]
    assert decide_article_count(s9[0], cfg).action == "none"
    d9_2 = decide_article_count(s9[1], cfg)
    assert (d9_2.action, d9_2.requested, d9_2.target) == ("use_requested", 3, 3)

    # article-010: T1 咨询 -> none, T2 写一篇 -> use_requested(1), T3 换背景 -> none
    s10 = cases["article-010"].input["script"]
    assert decide_article_count(s10[0], cfg).action == "none"
    d10_2 = decide_article_count(s10[1], cfg)
    assert (d10_2.action, d10_2.requested, d10_2.target) == ("use_requested", 1, 1)
    assert decide_article_count(s10[2], cfg, article_task_active=True).action == "none"


def test_t075_route_a_rehearsal_prompts_use_requested_one() -> None:
    prompts = [
        "写一篇给工厂新职工看的普法短文。虚构案例：签完劳动合同，两份都被车间收走了，新职工想自己留一份。请用“案例、以案说法、普法提示”三个小节，只讲谁应当持有合同文本。依据《中华人民共和国劳动合同法》第十六条第二款“劳动合同文本由用人单位和劳动者各执一份”。不要扩写处罚或赔偿。",
        "请把以下工会宣传栏素材整理成一篇简短的普法案例，保留“案例、以案说法、普法提示”三个小节。案例：某企业的技术人员收到一份写着三年的竞业限制协议，签字前想核对期限。法律依据：〔《中华人民共和国劳动合同法》（2012-12-28）第二十四条第2款〕规定，竞业限制期限不得超过二年。提示：发现约定三年，可以先指出期限超出上限，请对方核对。文章到这里结束，只使用给定的事实和依据。",
        "写一篇工会宣传栏短文，分“案例、以案说法、普法提示”三段。虚构案情：某门店招用一名新职工，办好入职手续后还要扣着他的身份证原件。请只讲这个问题。依据〔《中华人民共和国劳动合同法》（2012-12-28）第九条〕：用人单位招用劳动者，不得扣押劳动者的居民身份证和其他证件。结尾提醒职工核对后领回原件。",
    ]
    cfg = {"default_article_count": 3, "max_article_count": 10}
    for p in prompts:
        d = decide_article_count(p, cfg)
        assert (d.action, d.requested, d.target) == ("use_requested", 1, 1)


# ---------------------------------------------------------------------------
# 3. 编排层端到端（假客户端 + 内存 KB）
# ---------------------------------------------------------------------------


def test_orchestrator_reject_exceeds_max_and_preserves_entities() -> None:
    conn = _make_kb()
    article_reply = (
        "# 欠薪维权\n\n"
        "## 案例\n周岚在栖梧样例厂工作三个月未获工资。\n\n"
        "## 以案说法\n〔《中华人民共和国劳动法》（2018-12-29）第五十条〕\n"
        "> 工资应当以货币形式按月支付给劳动者本人。不得克扣或者无故拖欠劳动者的工资。\n\n"
        "## 普法提示\n请保留考勤和工资流水。"
    )
    client = _FakeClient([article_reply])
    assistant = TrainedAssistant(client, conn, eval_mode=True)
    sid = assistant.new_session(SessionConfig(default_article_count=3, max_article_count=10))

    # 首轮超限且披露真实姓名/单位：应硬拒、0 次调用模型、不污染 intent/active
    r1 = assistant.send(sid, "我叫周岚，在栖梧样例厂工作，帮我写 15 篇关于拖欠工资的普法文章。")
    assert len(client.calls) == 0
    assert r1.citations == []
    assert r1.question_count == 0
    assert r1.raw_content is None
    assert r1.intent is None
    assert detect_refusal(r1.content)["refused"] is False
    assert extract_articles(r1.content) == []
    assert "10" in r1.content and "15" in r1.content

    # 第二轮改说写 1 篇：首轮披露的真实姓名/单位仍须在交付稿中被脱敏
    r2 = assistant.send(sid, "那帮我按上面情况写 1 篇普法文章吧。")
    assert len(client.calls) == 1
    assert r2.intent == "article"
    assert "周岚" not in r2.content
    assert "栖梧样例厂" not in r2.content
    assert r2.raw_content == article_reply

    # 已有 article 活跃状态时，非正数/超限硬拒不得污染 intent 与 article_task_active
    r3 = assistant.send(sid, "改成 0 篇")
    assert len(client.calls) == 1
    assert r3.intent == "article"
    assert assistant._sessions[sid].anonymize_state.article_task_active is True
    assert r3.citations == []
    assert r3.raw_content is None
    assert detect_refusal(r3.content)["refused"] is False

    r4 = assistant.send(sid, "写 -1 篇普法文章")
    assert len(client.calls) == 1
    assert r4.intent == "article"
    assert assistant._sessions[sid].anonymize_state.article_task_active is True

    # 已有 consult 状态时，超限硬拒同样不得污染 intent 与 article_task_active
    s_consult = new_session({"default_article_count": 3, "max_article_count": 10})
    s_consult.intent = "consult"
    s_consult.anonymize_state.article_task_active = False
    t_rej = process_turn(s_consult, "写 15 篇普法文章", client, conn, eval_mode=True)
    assert len(client.calls) == 1
    assert t_rej.article_count_action == "rejected"
    assert s_consult.intent == "consult"
    assert s_consult.anonymize_state.article_task_active is False
    conn.close()


def test_orchestrator_use_default_appends_instruction_to_temp_copy_only() -> None:
    conn = _make_kb()
    client = _FakeClient(["# 样例\n\n## 案例\n略\n\n## 以案说法\n略\n\n## 普法提示\n略"] * 3)

    # 自定义 (default=2, max=5)
    session = new_session(
        {"max_questions_per_turn": 5, "default_article_count": 2, "max_article_count": 5}
    )
    user_msg = "帮我写几篇关于拖欠工资的普法宣传文章。"
    turn = process_turn(session, user_msg, client, conn)
    assert turn.article_count_action == "use_default"
    assert turn.target_article_count == 2
    assert turn.requested_article_count is None
    # session.messages 中的用户原话不得被篡改
    assert session.messages[0].content == user_msg
    # system prompt 保持原版 v2-short
    sent = client.calls[0]
    assert sent[0]["role"] == "system"
    assert sent[0]["content"] == build_system_prompt(max_questions=5)
    # 临时请求副本末尾包含 2 篇附注
    assert sent[-1]["content"] == user_msg + build_article_count_instruction(2)

    # 自定义 (default=1, max=1)
    s1 = new_session({"default_article_count": 1, "max_article_count": 1})
    process_turn(s1, user_msg, client, conn)
    assert client.calls[1][-1]["content"] == user_msg + build_article_count_instruction(1)

    # use_system_prompt=False 时无 system 角色
    s_nosys = new_session(
        {"default_article_count": 3, "max_article_count": 10, "use_system_prompt": False}
    )
    process_turn(s_nosys, user_msg, client, conn)
    assert all(m["role"] != "system" for m in client.calls[2])
    assert client.calls[2][-1]["content"] == user_msg + build_article_count_instruction(3)


def test_orchestrator_zero_diff_for_consult_and_explicit_count() -> None:
    conn = _make_kb()
    client = _FakeClient(["咨询答复", "# 文章\n\n## 案例\n略\n\n## 以案说法\n略\n\n## 普法提示\n略"])

    # 咨询路径
    s_consult = new_session({"default_article_count": 3, "max_article_count": 10})
    msg_consult = "单位拖欠工资怎么处理？"
    t1 = process_turn(s_consult, msg_consult, client, conn)
    assert t1.article_count_action == "none"
    assert client.calls[0] == [
        {"role": "system", "content": build_system_prompt(max_questions=5)},
        {"role": "user", "content": msg_consult},
    ]

    # 明示合法篇数路径
    s_art = new_session({"default_article_count": 3, "max_article_count": 10})
    msg_art = "围绕拖欠工资写两篇以案说法的文章。"
    t2 = process_turn(s_art, msg_art, client, conn)
    assert t2.article_count_action == "use_requested"
    assert t2.target_article_count == 2
    assert client.calls[1] == [
        {"role": "system", "content": build_system_prompt(max_questions=5)},
        {"role": "user", "content": msg_art},
    ]


# ---------------------------------------------------------------------------
# 4. CLI 配置透传（tu eval run）
# ---------------------------------------------------------------------------


def test_cli_eval_run_forwards_session_config(tmp_path: Path, monkeypatch) -> None:
    cfg_path = tmp_path / "app.yaml"
    cfg_path.write_text(
        "runtime:\n"
        "  model_endpoint: http://127.0.0.1:8080/v1\n"
        "  allowed_hosts: ['127.0.0.1']\n"
        "  model_name: dummy-model\n"
        "session:\n"
        "  max_questions_per_turn: 3\n"
        "  default_article_count: 2\n"
        "  max_article_count: 4\n",
        encoding="utf-8",
    )
    kb_dir = tmp_path / "artifacts" / "kb"
    kb_dir.mkdir(parents=True)
    create_kb(kb_dir / "kb-test.sqlite").close()

    captured: dict = {}

    def _fake_run_eval(**kwargs):
        captured.update(kwargs)
        return {"run_id": "run-test", "cases": 0, "dir": str(tmp_path), "gold_issues": []}

    monkeypatch.setattr("tu_assistant.eval.runner.run_eval", _fake_run_eval)

    runner = CliRunner()
    res = runner.invoke(
        app,
        [
            "eval",
            "run",
            "--cases",
            str(REPO_ROOT / "eval/cases/v1/articles.jsonl"),
            "--kb-version",
            "kb-test",
            "--config",
            str(cfg_path),
            "--artifacts",
            str(tmp_path / "artifacts"),
        ],
    )
    assert res.exit_code == 0, res.output
    scfg: SessionConfig = captured["session_config"]
    assert scfg.max_questions_per_turn == 3
    assert scfg.default_article_count == 2
    assert scfg.max_article_count == 4
    assert scfg.use_system_prompt is True


def test_cli_chat_forwards_session_config(tmp_path: Path, monkeypatch) -> None:
    cfg_path = tmp_path / "app.yaml"
    cfg_path.write_text(
        "runtime:\n"
        "  model_endpoint: http://127.0.0.1:8080/v1\n"
        "  allowed_hosts: ['127.0.0.1']\n"
        "  model_name: dummy-model\n"
        "session:\n"
        "  max_questions_per_turn: 4\n"
        "  default_article_count: 2\n"
        "  max_article_count: 6\n",
        encoding="utf-8",
    )
    kb_dir = tmp_path / "artifacts" / "kb"
    kb_dir.mkdir(parents=True)
    create_kb(kb_dir / "kb-test.sqlite").close()

    captured_cfgs: list[SessionConfig] = []

    class _DummyAssistant:
        def __init__(self, client, conn) -> None:
            pass

        def new_session(self, config: SessionConfig | None = None) -> str:
            assert config is not None
            captured_cfgs.append(config)
            return "sid-1"

        def close(self, session_id: str) -> None:
            pass

    monkeypatch.setattr("tu_assistant.chat.assistant.TrainedAssistant", _DummyAssistant)

    runner = CliRunner()
    res = runner.invoke(
        app,
        [
            "chat",
            "--kb-version",
            "kb-test",
            "--config",
            str(cfg_path),
            "--artifacts",
            str(tmp_path / "artifacts"),
        ],
        input="/quit\n",
    )
    assert res.exit_code == 0, res.output
    assert len(captured_cfgs) == 1
    assert captured_cfgs[0].max_questions_per_turn == 4
    assert captured_cfgs[0].default_article_count == 2
    assert captured_cfgs[0].max_article_count == 6


# ---------------------------------------------------------------------------
# 5. 离线固定回放回归（依赖本机历史 artifacts，缺失时自动跳过）
# ---------------------------------------------------------------------------


def test_offline_replay_60_consult_zero_diff() -> None:
    kb_path = REPO_ROOT / "artifacts/kb/kb-20261113-093057.sqlite"
    res_path = REPO_ROOT / "artifacts/eval/run-20261117-081504/results.jsonl"
    cases_path = REPO_ROOT / "eval/cases/v1/reviewed.jsonl"
    if not (kb_path.exists() and res_path.exists()):
        pytest.skip("本机缺少历史 60 题评测产物，跳过离线回放")

    cases = {c.case_id: c for c in load_cases(cases_path)}
    rows = [json.loads(line) for line in res_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    conn = open_kb(kb_path)
    try:
        for row in rows:
            cid = row["case_id"]
            msg = cases[cid].input["message"]
            raw = row["final_raw"]
            client = _FakeClient([raw])
            session = new_session({"default_article_count": 3, "max_article_count": 10})
            turn = process_turn(session, msg, client, conn, temperature=0.0, eval_mode=True)
            assert turn.article_count_action == "none", cid
            assert turn.requested_article_count is None, cid
            assert turn.target_article_count is None, cid
            assert client.calls[0] == [
                {"role": "system", "content": build_system_prompt(max_questions=5)},
                {"role": "user", "content": msg},
            ], cid
            assert turn.raw_content == raw, cid
            # 60 题均不触发文章数量控制，且发往模型的 messages 零改动、intent 不误判为 article
            assert session.intent != "article", cid
            assert turn.anonymize_blocked is False, cid
            assert turn.person_replacements == 0 and turn.org_replacements == 0, cid
            # 除 cand-037（run-20261117 早于 T077 整条补原文升级）外，其余 59/60 正文逐字一致
            if cid != "cand-037":
                assert turn.content == row["final_text"], cid
    finally:
        conn.close()


def test_offline_replay_10_articles_zero_diff() -> None:
    kb_path = REPO_ROOT / "artifacts/kb/kb-20261119-045641.sqlite"
    res_path = REPO_ROOT / "artifacts/eval/run-20261122-090101/results.jsonl"
    cases_path = REPO_ROOT / "eval/cases/v1/articles.jsonl"
    if not (kb_path.exists() and res_path.exists()):
        pytest.skip("本机缺少历史 10 题文章评测产物，跳过离线回放")

    cases = {c.case_id: c for c in load_cases(cases_path)}
    rows = [json.loads(line) for line in res_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    conn = open_kb(kb_path)
    try:
        sc011_passed = 0
        sc011_total = 0
        for row in rows:
            cid = row["case_id"]
            c = cases[cid]
            user_turns = c.input.get("script") or [c.input["message"]]
            raws = [
                row["final_raw"] if i == len(row["turns"]) - 1 else t["content"]
                for i, t in enumerate(row["turns"])
            ]
            client = _FakeClient(raws)
            session = new_session({"default_article_count": 3, "max_article_count": 10})
            replayed_turns = []
            for idx, u in enumerate(user_turns):
                turn = process_turn(session, u, client, conn, temperature=0.0, eval_mode=True)
                replayed_turns.append(
                    {
                        "user": u,
                        "content": turn.content,
                        "anonymize": {"blocked": turn.anonymize_blocked},
                    }
                )
                if cid == "article-001":
                    assert turn.article_count_action == "use_default"
                    assert client.calls[idx][-1]["content"] == u + build_article_count_instruction(3)
                else:
                    assert client.calls[idx][-1]["content"] == u, (cid, idx)
            assert replayed_turns[-1]["content"] == row["final_text"], cid
            id_res = article_identity_check(
                replayed_turns, c.gold.get("protected_names")
            )
            if id_res is not None:
                sc011_passed += id_res["passed"]
                sc011_total += id_res["total"]
        assert (sc011_passed, sc011_total) == (2, 2)
    finally:
        conn.close()
