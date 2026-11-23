"""T069: Gradio 演示界面控制器、安全边界、跨线程与 CLI 单元测试。"""

from __future__ import annotations

import sqlite3
import threading
import time
import warnings
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from tu_assistant.chat.assistant import Reply, SessionConfig, TrainedAssistant
from tu_assistant.cli import app as cli_app
from tu_assistant.kb.models import Clause, DocumentMeta
from tu_assistant.kb.store import create_kb, insert_clause, insert_document, set_meta
from tu_assistant.runtime.client import ChatResponse
from tu_assistant.ui.app import (
    ChatUIController,
    build_ui_theme,
    create_ui_app,
    launch_ui,
    validate_ui_host,
)


class _StubAssistant:
    """最小确定性 Assistant 替身，仅实现 Assistant 协议。"""

    def __init__(self, reply_fn=None) -> None:
        self._counter = 0
        self._sessions: dict[str, list[str]] = {}
        self.closed_sessions: list[str] = []
        self.send_calls: list[tuple[str, str]] = []
        self._reply_fn = reply_fn

    def new_session(self, config: SessionConfig | None = None) -> str:
        self._counter += 1
        sid = f"stub-s{self._counter}"
        self._sessions[sid] = []
        return sid

    def send(self, session_id: str, message: str) -> Reply:
        self.send_calls.append((session_id, message))
        if self._reply_fn is not None:
            content = self._reply_fn(session_id, message)
        else:
            turn_no = len(self._sessions[session_id]) + 1
            content = (
                f"第{turn_no}轮答复：{message}\n\n"
                "〔《示例工会法》（2021年修正）第十条〕\n"
                "> 企业应当依法建立工会组织。\n\n"
                "---\n*以上内容仅供参考，不构成法律意见。*"
            )
        self._sessions[session_id].append(content)
        return Reply(content=content, intent="consult")

    def export_markdown(self, session_id: str, turn_index: int | None = None) -> str:
        turns = self._sessions.get(session_id, [])
        if not turns:
            return ""
        idx = -1 if turn_index is None else turn_index
        return turns[idx]

    def close(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self.closed_sessions.append(session_id)


class _FakeModelClient:
    """可切换异常/正常响应的模型客户端替身，用于测试编排层回滚与跨线程查库。"""

    def __init__(self, responses: list[str | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        self.calls.append([dict(m) for m in messages])
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return ChatResponse(content=item)


def _build_temp_kb(artifacts_dir: Path, kb_version: str = "kb-20261123-000001") -> Path:
    kb_path = artifacts_dir / "kb" / f"{kb_version}.sqlite"
    conn = create_kb(kb_path)
    meta = DocumentMeta(
        doc_id="doc-ui-test",
        title="示例工会法",
        issuer="示例机关",
        level="法律",
        version_label="2021年修正",
        promulgated_on="2021-12-24",
        status="current",
        corpus="fixture",
        source_file="fixture.txt",
    )
    insert_document(conn, meta)
    insert_clause(
        conn,
        Clause(
            doc_id="doc-ui-test",
            article_no=10,
            paragraph_no=None,
            item_no=None,
            number_text="第十条",
            heading_path=["第二章"],
            text="企业应当依法建立工会组织，保障职工合法权益。",
            clause_type="obligation",
            parse_warnings=[],
        ),
    )
    set_meta(conn, "kb_version", kb_version)
    conn.commit()
    conn.close()
    return kb_path


def _write_app_yaml(
    path: Path,
    *,
    artifacts_dir: Path,
    kb_version: str | None = "kb-20261123-000001",
    endpoint: str = "http://127.0.0.1:8080/v1",
) -> Path:
    cfg = {
        "kb": {"version": kb_version},
        "runtime": {
            "model_endpoint": endpoint,
            "allowed_hosts": ["127.0.0.1", "localhost"],
            "model_name": "test-model",
        },
        "session": {
            "max_questions_per_turn": 4,
            "default_article_count": 3,
            "max_article_count": 10,
        },
        "paths": {"artifacts": str(artifacts_dir)},
    }
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return path


class TestHostValidation:
    def test_allows_only_loopback_ipv4(self) -> None:
        assert validate_ui_host("127.0.0.1") == "127.0.0.1"

    @pytest.mark.parametrize(
        "bad_host",
        ["localhost", "0.0.0.0", "192.168.1.10", "example.com", "", " 127.0.0.1 "],
    )
    def test_rejects_non_loopback_hosts(self, bad_host: str) -> None:
        with pytest.raises(ValueError, match="127.0.0.1"):
            validate_ui_host(bad_host)


class TestChatUIController:
    def test_empty_input_ignored_without_calling_assistant(self) -> None:
        stub = _StubAssistant()
        ctrl = ChatUIController(stub, SessionConfig())
        try:
            state, history, cleared, export_file, status = ctrl.send_message(None, "   \n\t ")
            assert stub.send_calls == []
            assert state.session_id is None
            assert history == []
            assert cleared == ""
            assert export_file is None
            assert "请输入" in status
        finally:
            ctrl.cleanup_all()

    def test_multi_turn_session_and_markdown_export_byte_exact(self) -> None:
        stub = _StubAssistant()
        ctrl = ChatUIController(stub, SessionConfig())
        repo_root = Path(__file__).resolve().parents[2]
        try:
            state, h1, cleared1, exp1, status1 = ctrl.send_message(None, "我们单位不让建工会")
            assert cleared1 == ""
            assert state.session_id == "stub-s1"
            assert len(h1) == 2
            assert h1[0] == {"role": "user", "content": "我们单位不让建工会"}
            assert h1[1]["role"] == "assistant"
            assert exp1 is not None
            exp1_path = Path(exp1)
            assert exp1_path.is_file()
            assert exp1_path.suffix == ".md"
            assert not exp1_path.resolve().is_relative_to(repo_root)
            assert exp1_path.read_bytes() == h1[1]["content"].encode("utf-8")
            assert exp1_path.read_text(encoding="utf-8") == stub.export_markdown("stub-s1")
            assert "第 1 轮" in status1

            state, h2, _, exp2, _ = ctrl.send_message(state, "那法律责任是什么")
            assert state.session_id == "stub-s1"
            assert len(h2) == 4
            assert exp2 is not None
            exp2_path = Path(exp2)
            assert exp2_path.is_file()
            assert exp2_path.read_bytes() == h2[3]["content"].encode("utf-8")
            assert not exp1_path.exists()
        finally:
            ctrl.cleanup_all()

    def test_two_tabs_isolated_and_reset_plus_delete_callback_cleanup(self) -> None:
        stub = _StubAssistant()
        ctrl = ChatUIController(stub, SessionConfig())
        try:
            s_a, h_a, _, exp_a, _ = ctrl.send_message(None, "标签页A的问题")
            s_b, h_b, _, exp_b, _ = ctrl.send_message(None, "标签页B的问题")
            assert s_a.session_id != s_b.session_id
            assert len(h_a) == 2 and len(h_b) == 2
            assert exp_a != exp_b
            assert exp_a is not None and Path(exp_a).is_file()
            assert exp_b is not None and Path(exp_b).is_file()

            old_sid_a = s_a.session_id
            new_s_a, new_h_a, cleared, new_exp, reset_status = ctrl.reset_session(s_a)
            assert old_sid_a in stub.closed_sessions
            assert not Path(exp_a).exists()
            assert new_s_a.session_id is None
            assert new_h_a == []
            assert cleared == ""
            assert new_exp is None
            assert "新会话" in reset_status

            # 标签页 A 开启下一轮获得新 session_id，且不影响标签页 B
            s_a2, _, _, _, _ = ctrl.send_message(new_s_a, "新问题")
            assert s_a2.session_id not in {old_sid_a, s_b.session_id}
            assert Path(exp_b).is_file()

            # 模拟标签页 B 关闭（gr.State delete_callback）
            old_sid_b = s_b.session_id
            ctrl.cleanup_session(s_b)
            assert old_sid_b in stub.closed_sessions
            assert not Path(exp_b).exists()
        finally:
            ctrl.cleanup_all()

    def test_export_current_reply_when_empty(self) -> None:
        stub = _StubAssistant()
        ctrl = ChatUIController(stub, SessionConfig())
        try:
            _, path, msg = ctrl.export_current_reply(None)
            assert path is None
            assert "暂无" in msg
        finally:
            ctrl.cleanup_all()

    def test_cleanup_session_nonblocking_when_lock_held(self) -> None:
        """delete_callback 运行在事件循环线程上：拿不到锁时必须立即返回并交由后台线程清理。"""
        stub = _StubAssistant()
        ctrl = ChatUIController(stub, SessionConfig())
        try:
            state, _, _, exp, _ = ctrl.send_message(None, "先发一条消息")
            sid = state.session_id
            assert sid is not None
            assert exp is not None and Path(exp).is_file()

            with ctrl._lock:
                t0 = time.monotonic()
                ctrl.cleanup_session(state)
                elapsed = time.monotonic() - t0
                # 不得阻塞等待互斥锁
                assert elapsed < 0.2

            # 释放锁后，后台守护线程应迅速完成全部清理
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if (
                    sid in stub.closed_sessions
                    and not Path(exp).exists()
                    and state.session_id is None
                    and state.export_path is None
                ):
                    break
                time.sleep(0.01)
            assert stub.closed_sessions.count(sid) == 1
            assert not Path(exp).exists()
            assert state.session_id is None
            assert state.export_path is None

            # 交错场景：cleanup_all 先回收后，延迟清理不得二次调用 assistant.close(sid)
            s2, _, _, exp2, _ = ctrl.send_message(None, "第二条消息")
            sid2 = s2.session_id
            assert sid2 is not None and exp2 is not None
            with ctrl._lock:
                ctrl.cleanup_session(s2)
                # 仍在持锁期间执行内部清理模拟 cleanup_all 抢先拿到锁
                ctrl._active_sessions.pop(sid2, None)
                stub.close(sid2)
            deadline = time.monotonic() + 2.0
            while s2.session_id is not None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert stub.closed_sessions.count(sid2) == 1
            assert s2.session_id is None
            assert not Path(exp2).exists()
        finally:
            ctrl.cleanup_all()


class TestErrorRecoveryAndCrossThreadKB:
    def test_connect_error_rolls_back_hanging_user_turn_and_recovers(
        self, tmp_path: Path
    ) -> None:
        artifacts = tmp_path / "artifacts"
        _build_temp_kb(artifacts)
        cfg_path = _write_app_yaml(tmp_path / "app.yaml", artifacts_dir=artifacts)

        http_err = httpx.HTTPStatusError(
            "Internal Server Error",
            request=httpx.Request("POST", "http://127.0.0.1:8080/v1/chat/completions"),
            response=httpx.Response(500),
        )
        client = _FakeModelClient(
            [
                httpx.ConnectError("Connection refused"),
                httpx.ReadTimeout("Timed out"),
                "依据〔《示例工会法》（2021年修正）第十条〕\n> 原文待核对",
                http_err,
            ]
        )
        assistant = TrainedAssistant.from_config(
            cfg_path, client=client, check_same_thread=False
        )
        ctrl = ChatUIController(
            assistant,
            SessionConfig(),
            kb_version=assistant.kb_version,
            model_endpoint="http://127.0.0.1:8080/v1",
        )
        try:
            # 第一次断连：保留用户输入、不写历史、底层无悬挂 user 轮
            s1, h1, msg1, exp1, st1 = ctrl.send_message(None, "不让建工会怎么办")
            assert h1 == []
            assert msg1 == "不让建工会怎么办"
            assert exp1 is None
            assert "tu serve model" in st1
            assert s1.session_id is not None
            assert assistant._sessions[s1.session_id].messages == []

            # 第二次超时：同样回滚
            s2, h2, msg2, exp2, st2 = ctrl.send_message(s1, "不让建工会怎么办")
            assert h2 == []
            assert msg2 == "不让建工会怎么办"
            assert exp2 is None
            assert "超时" in st2
            assert assistant._sessions[s2.session_id].messages == []

            # 服务恢复后重试：发往模型的 messages 只有 1 条 user（无重复悬挂消息）
            s3, h3, msg3, exp3, _ = ctrl.send_message(s2, "不让建工会怎么办")
            assert msg3 == ""
            assert len(h3) == 2
            assert exp3 is not None and Path(exp3).is_file()
            user_msgs = [m for m in client.calls[-1] if m["role"] == "user"]
            assert len(user_msgs) == 1
            # 出处校验自动替换为知识库原文并附加免责声明
            assert "企业应当依法建立工会组织，保障职工合法权益。" in h3[1]["content"]
            assert "不构成法律意见" in h3[1]["content"]

            # 第 2 轮返回 HTTP 500：保留第 1 轮历史与导出文件，回滚第 2 轮悬挂 user 消息
            s4, h4, msg4, exp4, st4 = ctrl.send_message(s3, "追问法律责任")
            assert len(h4) == 2
            assert h4 == h3
            assert msg4 == "追问法律责任"
            assert exp4 == exp3
            assert Path(exp4).is_file()
            assert "HTTP 500" in st4
            assert len(assistant._sessions[s4.session_id].messages) == 2
        finally:
            ctrl.cleanup_all()
            assistant.close_kb()

    def test_post_chat_sqlite_error_rolls_back_user_turn_and_shows_chinese_status(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """client.chat 之后的 verify/KB 步骤抛 sqlite3.Error 时，同样回滚悬挂 user 轮并友好提示。"""
        artifacts = tmp_path / "artifacts"
        _build_temp_kb(artifacts)
        cfg_path = _write_app_yaml(tmp_path / "app.yaml", artifacts_dir=artifacts)

        client = _FakeModelClient(
            ["依据〔《示例工会法》（2021年修正）第十条〕\n> 原文待核对"]
        )
        assistant = TrainedAssistant.from_config(
            cfg_path, client=client, check_same_thread=False
        )
        ctrl = ChatUIController(assistant, SessionConfig(), kb_version=assistant.kb_version)

        def _boom(*_args: Any, **_kwargs: Any) -> Any:
            raise sqlite3.OperationalError("database disk image is malformed")

        monkeypatch.setattr("tu_assistant.chat.orchestrator.verify_output", _boom)
        try:
            s1, h1, msg1, exp1, st1 = ctrl.send_message(None, "不让建工会怎么办")
            assert h1 == []
            assert msg1 == "不让建工会怎么办"
            assert exp1 is None
            assert "知识库读取失败" in st1
            assert s1.session_id is not None
            sess = assistant._sessions[s1.session_id]
            assert sess.messages == []
            assert sess.intent is None
            assert sess.anonymize_state.article_task_active is False
        finally:
            ctrl.cleanup_all()
            assistant.close_kb()

    def test_post_classify_error_rolls_back_intent_and_article_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """classify_turn_intent 之后的步骤抛错时，session.intent 与 article_task_active 一并回滚。"""
        artifacts = tmp_path / "artifacts"
        _build_temp_kb(artifacts)
        cfg_path = _write_app_yaml(tmp_path / "app.yaml", artifacts_dir=artifacts)

        client = _FakeModelClient(
            [
                "### 案例\n【案情】某厂阻挠建工会。\n"
                "〔《示例工会法》（2021年修正）第十条〕\n> 原文"
            ]
        )
        assistant = TrainedAssistant.from_config(
            cfg_path, client=client, check_same_thread=False
        )
        ctrl = ChatUIController(assistant, SessionConfig(), kb_version=assistant.kb_version)

        def _boom_anon(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("anonymizer failed")

        monkeypatch.setattr("tu_assistant.chat.orchestrator.anonymize_article_text", _boom_anon)
        try:
            s1, h1, msg1, exp1, st1 = ctrl.send_message(
                None, "请帮我写1篇关于阻挠建工会的普法文章"
            )
            assert h1 == []
            assert msg1 == "请帮我写1篇关于阻挠建工会的普法文章"
            assert exp1 is None
            assert "请求处理失败" in st1
            assert s1.session_id is not None
            sess = assistant._sessions[s1.session_id]
            assert sess.messages == []
            assert sess.intent is None
            assert sess.anonymize_state.article_task_active is False
        finally:
            ctrl.cleanup_all()
            assistant.close_kb()

    def test_worker_thread_queries_readonly_kb_and_anonymizes(
        self, tmp_path: Path
    ) -> None:
        artifacts = tmp_path / "artifacts"
        _build_temp_kb(artifacts)
        cfg_path = _write_app_yaml(tmp_path / "app.yaml", artifacts_dir=artifacts)

        article_raw = (
            "### 案例标题\n\n"
            "【案情】王明在晨光制造公司工作，单位阻挠建立工会。\n\n"
            "【适用条款】\n〔《示例工会法》（2021年修正）第十条〕\n> 待校验\n\n"
            "【提示】依法维权。"
        )
        client = _FakeModelClient([article_raw])
        assistant = TrainedAssistant.from_config(
            cfg_path, client=client, check_same_thread=False
        )
        ctrl = ChatUIController(assistant, SessionConfig(), kb_version=assistant.kb_version)

        result: dict[str, Any] = {}
        err: list[BaseException] = []

        def _worker() -> None:
            try:
                result["out"] = ctrl.send_message(
                    None,
                    "我叫王明，在晨光制造公司工作，请帮我写1篇关于阻挠建工会的普法文章。",
                )
            except BaseException as exc:  # pragma: no cover - 失败时断言暴露
                err.append(exc)

        try:
            t = threading.Thread(target=_worker)
            t.start()
            t.join(timeout=10)
            assert not err, f"工作线程执行失败：{err}"
            _state, history, _cleared, export_file, _status = result["out"]
            reply_text = history[1]["content"]
            assert "企业应当依法建立工会组织，保障职工合法权益。" in reply_text
            assert "王明" not in reply_text
            assert "晨光制造公司" not in reply_text
            assert export_file is not None
            assert Path(export_file).read_bytes() == reply_text.encode("utf-8")
        finally:
            ctrl.cleanup_all()
            assistant.close_kb()


class TestGradioAssemblyAndCLI:
    def test_create_ui_app_and_launch_ui_params_zero_warnings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import gradio as gr

        stub = _StubAssistant()
        ctrl = ChatUIController(
            stub,
            SessionConfig(),
            kb_version="kb-20261119-045641",
            model_endpoint="http://127.0.0.1:8080/v1",
        )
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                demo = create_ui_app(ctrl)
            bad_warnings = [
                f"{w.category.__name__}: {w.message}"
                for w in caught
                if issubclass(w.category, (UserWarning, DeprecationWarning, FutureWarning))
            ]
            assert bad_warnings == []
            assert isinstance(demo, gr.Blocks)
            assert demo.analytics_enabled is False
            assert demo.delete_cache == (600, 7200)

            theme = build_ui_theme()
            assert theme._stylesheets == []

            captured: dict[str, Any] = {}

            def _fake_launch(**kwargs: Any) -> str:
                captured.update(kwargs)
                return "launched"

            monkeypatch.setattr(demo, "launch", _fake_launch)
            ret = launch_ui(
                demo,
                host="127.0.0.1",
                port=7861,
                inbrowser=False,
            )
            assert ret == "launched"
            assert captured["server_name"] == "127.0.0.1"
            assert captured["server_port"] == 7861
            assert captured["share"] is False
            assert captured["inbrowser"] is False
            assert captured["footer_links"] == []
            assert "allowed_paths" not in captured
            assert captured["theme"]._stylesheets == []
        finally:
            ctrl.cleanup_all()

    @pytest.mark.parametrize(
        "extra_args",
        [
            ["--host", "0.0.0.0"],
            ["--host", "localhost"],
            ["--port", "0"],
            ["--port", "70000"],
            ["--temperature", "-0.1"],
            ["--temperature", "nan"],
            ["--temperature", "inf"],
        ],
    )
    def test_cli_ui_rejects_invalid_args(self, extra_args: list[str]) -> None:
        runner = CliRunner()
        res = runner.invoke(cli_app, ["ui", *extra_args])
        assert res.exit_code == 2

    def test_cli_ui_rejects_invalid_session_config(self, tmp_path: Path) -> None:
        artifacts = tmp_path / "artifacts"
        _build_temp_kb(artifacts)
        cfg_path = tmp_path / "bad_session.yaml"
        cfg = {
            "kb": {"version": "kb-20261123-000001"},
            "runtime": {
                "model_endpoint": "http://127.0.0.1:8080/v1",
                "allowed_hosts": ["127.0.0.1", "localhost"],
                "model_name": "test-model",
            },
            "session": {
                "max_questions_per_turn": 5,
                "default_article_count": 12,
                "max_article_count": 10,
            },
            "paths": {"artifacts": str(artifacts)},
        }
        cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
        runner = CliRunner()
        res = runner.invoke(cli_app, ["ui", "--config", str(cfg_path)])
        assert res.exit_code == 2

    def test_cli_ui_rejects_missing_kb_without_creating_empty_file(
        self, tmp_path: Path
    ) -> None:
        artifacts = tmp_path / "artifacts"
        (artifacts / "kb").mkdir(parents=True)
        cfg_path = _write_app_yaml(
            tmp_path / "app.yaml",
            artifacts_dir=artifacts,
            kb_version="kb-nonexistent",
        )
        runner = CliRunner()
        res = runner.invoke(cli_app, ["ui", "--config", str(cfg_path)])
        assert res.exit_code == 2
        assert not (artifacts / "kb" / "kb-nonexistent.sqlite").exists()

    def test_cli_ui_rejects_disallowed_model_endpoint(self, tmp_path: Path) -> None:
        artifacts = tmp_path / "artifacts"
        _build_temp_kb(artifacts)
        cfg_path = _write_app_yaml(
            tmp_path / "app.yaml",
            artifacts_dir=artifacts,
            endpoint="https://api.example.com/v1",
        )
        runner = CliRunner()
        res = runner.invoke(cli_app, ["ui", "--config", str(cfg_path)])
        assert res.exit_code == 2

    def test_cli_ui_wires_config_and_cleans_up_resources(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        artifacts = tmp_path / "artifacts"
        _build_temp_kb(artifacts)
        cfg_path = _write_app_yaml(tmp_path / "app.yaml", artifacts_dir=artifacts)

        launched: dict[str, Any] = {}
        wired: dict[str, Any] = {}
        export_dirs: list[Path] = []
        kb_closed = {"called": False}

        orig_from_config = TrainedAssistant.from_config
        orig_close_kb = TrainedAssistant.close_kb
        orig_create_ui_app = create_ui_app

        def _spy_from_config(cls: type[TrainedAssistant], *args: Any, **kwargs: Any) -> TrainedAssistant:
            wired["from_config_kwargs"] = dict(kwargs)
            inst = orig_from_config(*args, **kwargs)
            wired["assistant_kb_version"] = inst.kb_version
            wired["assistant_temperature"] = inst._temperature
            return inst

        def _spy_create_ui_app(controller: ChatUIController) -> Any:
            wired["controller_kb_version"] = controller.kb_version
            wired["controller_session_config"] = controller.session_config
            wired["controller_endpoint"] = controller.model_endpoint
            export_dirs.append(controller.export_dir)
            assert controller.export_dir.is_dir()
            return orig_create_ui_app(controller)

        def _spy_close_kb(self: TrainedAssistant) -> None:
            kb_closed["called"] = True
            orig_close_kb(self)

        def _fake_launch_ui(
            demo: Any,
            *,
            host: str = "127.0.0.1",
            port: int = 7860,
            inbrowser: bool = False,
        ) -> None:
            launched.update(
                host=host,
                port=port,
                inbrowser=inbrowser,
            )

        monkeypatch.setattr(TrainedAssistant, "from_config", classmethod(_spy_from_config))
        monkeypatch.setattr(TrainedAssistant, "close_kb", _spy_close_kb)
        monkeypatch.setattr("tu_assistant.ui.app.create_ui_app", _spy_create_ui_app)
        monkeypatch.setattr("tu_assistant.ui.app.launch_ui", _fake_launch_ui)

        runner = CliRunner()
        res = runner.invoke(
            cli_app,
            [
                "ui",
                "--config",
                str(cfg_path),
                "--port",
                "7865",
                "--temperature",
                "0.3",
            ],
        )
        assert res.exit_code == 0, res.output
        assert wired["from_config_kwargs"]["check_same_thread"] is False
        assert wired["from_config_kwargs"]["temperature"] == pytest.approx(0.3)
        assert wired["assistant_kb_version"] == "kb-20261123-000001"
        assert wired["assistant_temperature"] == pytest.approx(0.3)
        assert wired["controller_kb_version"] == "kb-20261123-000001"
        assert wired["controller_session_config"].max_questions_per_turn == 4
        assert wired["controller_session_config"].default_article_count == 3
        assert wired["controller_session_config"].max_article_count == 10
        assert wired["controller_endpoint"] == "http://127.0.0.1:8080/v1"
        assert launched["host"] == "127.0.0.1"
        assert launched["port"] == 7865
        assert launched["inbrowser"] is False
        assert kb_closed["called"] is True
        assert export_dirs and not export_dirs[0].exists()
