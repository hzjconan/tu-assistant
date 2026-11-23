"""单元测试：T067 知识库版本配置化解析、防建空库与编排/校验层接线。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from tu_assistant.chat.assistant import TrainedAssistant
from tu_assistant.citation.verify import verify_output_from_config
from tu_assistant.cli import app
from tu_assistant.kb.models import Clause, DocumentMeta
from tu_assistant.kb.store import (
    KBError,
    create_kb,
    doc_id_for,
    insert_clause,
    insert_document,
    latest_kb_path,
    open_kb,
    open_kb_from_config,
    resolve_kb_path,
    set_meta,
)
from tu_assistant.runtime.client import ChatResponse

runner = CliRunner()


class _StubModelClient:
    """确定性本地 stub 模型客户端，不发网络请求。"""

    def __init__(self, reply_text: str) -> None:
        self._reply = reply_text

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> ChatResponse:
        return ChatResponse(content=self._reply)


def _build_versioned_kb(kb_dir: Path, version: str, clause_text: str) -> Path:
    kb_path = kb_dir / f"{version}.sqlite"
    conn = create_kb(kb_path)
    with conn:
        did = doc_id_for("示例工会法", "2020-01-01")
        insert_document(
            conn,
            DocumentMeta(
                title="示例工会法",
                version_label="2020-01-01",
                status="current",
                doc_id=did,
            ),
        )
        insert_clause(
            conn,
            Clause(
                doc_id=did,
                article_no=4,
                paragraph_no=1,
                item_no=None,
                number_text="第四条",
                text=clause_text,
            ),
        )
        set_meta(conn, "kb_version", version)
    conn.close()
    return kb_path


def _write_app_yaml(
    path: Path,
    *,
    kb_version: Any = None,
    artifacts_dir: str | Path = "artifacts",
) -> Path:
    cfg = {
        "runtime": {
            "model_endpoint": "http://127.0.0.1:8080/v1",
            "allowed_hosts": ["127.0.0.1", "localhost"],
            "model_name": "default",
        },
        "session": {
            "max_questions_per_turn": 5,
            "default_article_count": 3,
            "max_article_count": 10,
        },
        "kb": {
            "version": kb_version,
        },
        "paths": {
            "artifacts": str(artifacts_dir),
            "eval_cases": "eval/cases",
        },
    }
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return path


def test_resolve_kb_path_priority_and_artifacts_fallback(tmp_path: Path) -> None:
    """验证优先级：显式 kb_version > app.yaml kb.version > latest_kb_path，且支持 paths.artifacts。"""
    kb_dir = tmp_path / "custom_artifacts" / "kb"
    v1_path = _build_versioned_kb(kb_dir, "kb-20260101-000001", "第四条版本一原文。")
    v2_path = _build_versioned_kb(kb_dir, "kb-20260102-000001", "第四条版本二原文。")

    # 1. kb.version: null -> 自动取最新 v2
    cfg_null = _write_app_yaml(
        tmp_path / "app_null.yaml",
        kb_version=None,
        artifacts_dir=tmp_path / "custom_artifacts",
    )
    assert resolve_kb_path(config_path=cfg_null) == v2_path

    # 2. kb.version: "kb-20260101-000001" -> 锁定 v1
    cfg_v1 = _write_app_yaml(
        tmp_path / "app_v1.yaml",
        kb_version="kb-20260101-000001",
        artifacts_dir=tmp_path / "custom_artifacts",
    )
    assert resolve_kb_path(config_path=cfg_v1) == v1_path

    # 3. 显式传入 kb_version 覆盖配置文件中的 v1
    assert (
        resolve_kb_path("kb-20260102-000001", config_path=cfg_v1)
        == v2_path
    )


def test_open_kb_and_resolve_reject_missing_or_invalid_without_creating_empty_file(
    tmp_path: Path,
) -> None:
    """验证缺失版本、非法类型、路径穿越均抛 KBError，且绝不静默创建 0 字节空 .sqlite 文件。"""
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir(parents=True)

    # 1. 空目录无任何 KB
    with pytest.raises(KBError, match="没有知识库版本"):
        latest_kb_path(tmp_path)

    # 2. open_kb 指向不存在文件 -> 抛 KBError，且磁盘不生成文件
    ghost_file = kb_dir / "kb-ghost.sqlite"
    with pytest.raises(KBError, match="知识库文件不存在"):
        open_kb(ghost_file)
    assert not ghost_file.exists()

    # 3. open_kb(":memory:") 依然正常支持单元测试内存库
    mem_conn = open_kb(":memory:")
    mem_conn.close()

    # 4. 非法版本号（非字符串、空串、首尾空白、路径穿越）
    for bad_ver in (123, True, "", "  ", "kb-1 ", "../secret", "a/b", "a\\b", ".."):
        cfg_bad = _write_app_yaml(
            tmp_path / "app_bad.yaml",
            kb_version=bad_ver,
            artifacts_dir=tmp_path,
        )
        with pytest.raises(KBError):
            resolve_kb_path(config_path=cfg_bad)

    # 5. 格式合法但文件不存在的版本号
    cfg_missing = _write_app_yaml(
        tmp_path / "app_missing.yaml",
        kb_version="kb-20991231-235959",
        artifacts_dir=tmp_path,
    )
    with pytest.raises(KBError, match="知识库版本不存在"):
        open_kb_from_config(cfg_missing)
    assert not (kb_dir / "kb-20991231-235959.sqlite").exists()


def test_verify_output_and_trained_assistant_switch_kb_via_config_only(
    tmp_path: Path,
) -> None:
    """验证仅修改 app.yaml 中的 kb.version（零代码改动），出处校验层与编排层立即切换知识库版本。"""
    kb_dir = tmp_path / "kb"
    text_v1 = "任何组织或者个人不得随意撤销工会组织。"
    text_v2 = "任何组织或者个人不得以任何形式非法撤销、合并工会组织。"
    _build_versioned_kb(kb_dir, "kb-20260101-000001", text_v1)
    _build_versioned_kb(kb_dir, "kb-20260102-000001", text_v2)

    raw_model_output = (
        "依据以下规定：\n"
        "〔《示例工会法》（2020-01-01）第四条〕\n"
        f"> {text_v1}\n"
        "因此单位做法违法。"
    )

    cfg_path = _write_app_yaml(
        tmp_path / "app.yaml",
        kb_version="kb-20260101-000001",
        artifacts_dir=tmp_path,
    )

    # 1. 配置指向 v1 时：出处校验判定为 ok，保留 v1 原文
    vr1 = verify_output_from_config(raw_model_output, cfg_path)
    assert vr1.stats["ok"] == 1
    assert vr1.stats["corrected"] == 0
    assert text_v1 in vr1.text

    stub_client = _StubModelClient(raw_model_output)
    with TrainedAssistant.from_config(cfg_path, client=stub_client) as assistant1:
        assert assistant1.kb_version == "kb-20260101-000001"
        sid = assistant1.new_session()
        reply1 = assistant1.send(sid, "请直接给出《示例工会法》第四条的法律依据")
        assert text_v1 in reply1.content
        assert reply1.citations[0].verdict == "ok"
        assistant1.close(sid)

    # 2. 仅修改 app.yaml 中的 kb.version 为 v2（不改任何代码）
    _write_app_yaml(
        cfg_path,
        kb_version="kb-20260102-000001",
        artifacts_dir=tmp_path,
    )

    vr2 = verify_output_from_config(raw_model_output, cfg_path)
    assert vr2.stats["ok"] == 0
    assert vr2.stats["corrected"] == 1
    assert text_v2 in vr2.text
    assert text_v1 not in vr2.text

    with TrainedAssistant.from_config(cfg_path, client=stub_client) as assistant2:
        assert assistant2.kb_version == "kb-20260102-000001"
        sid = assistant2.new_session()
        reply2 = assistant2.send(sid, "请直接给出《示例工会法》第四条的法律依据")
        assert text_v2 in reply2.content
        assert text_v1 not in reply2.content
        assert reply2.citations[0].verdict == "corrected"
        assistant2.close(sid)


def test_cli_chat_and_kb_commands_respect_kb_version_and_fail_cleanly(
    tmp_path: Path,
) -> None:
    """验证 tu chat 读取 app.yaml 的 kb.version、--kb-version 可覆盖，且无效版本报退出码 2 不建空库。"""
    kb_dir = tmp_path / "kb"
    _build_versioned_kb(kb_dir, "kb-20260101-000001", "版本一第四条。")
    _build_versioned_kb(kb_dir, "kb-20260102-000001", "版本二第四条。")

    cfg_v1 = _write_app_yaml(
        tmp_path / "app.yaml",
        kb_version="kb-20260101-000001",
        artifacts_dir=tmp_path,
    )

    # 1. tu chat 按 app.yaml 加载 kb-20260101-000001（直接输入 /quit 退出，无需启动模型服务）
    chat_res1 = runner.invoke(
        app,
        ["chat", "--config", str(cfg_v1)],
        input="/quit\n",
    )
    assert chat_res1.exit_code == 0
    assert "知识库：kb-20260101-000001" in chat_res1.stdout

    # 2. tu chat 命令行 --kb-version 覆盖 app.yaml
    chat_res2 = runner.invoke(
        app,
        ["chat", "--config", str(cfg_v1), "--kb-version", "kb-20260102-000001"],
        input="/quit\n",
    )
    assert chat_res2.exit_code == 0
    assert "知识库：kb-20260102-000001" in chat_res2.stdout

    # 3. tu chat 遇到 app.yaml 配置了不存在的 kb.version -> 退出码 2 且不建空库
    cfg_bad = _write_app_yaml(
        tmp_path / "app_bad.yaml",
        kb_version="kb-missing-888",
        artifacts_dir=tmp_path,
    )
    chat_bad = runner.invoke(app, ["chat", "--config", str(cfg_bad)], input="/quit\n")
    assert chat_bad.exit_code == 2
    assert "知识库版本不存在：kb-missing-888" in (chat_bad.stdout + chat_bad.stderr)
    assert not (kb_dir / "kb-missing-888.sqlite").exists()

    # 4. tu kb show 传入不存在的 --kb-version -> 退出码 2 且不建空库
    show_bad = runner.invoke(
        app,
        [
            "kb",
            "show",
            "示例工会法",
            "4",
            "--kb-version",
            "kb-missing-999",
            "--artifacts",
            str(tmp_path),
        ],
    )
    assert show_bad.exit_code == 2
    assert not (kb_dir / "kb-missing-999.sqlite").exists()


def test_cli_eval_run_respects_kb_version_and_artifacts_from_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 tu eval run 读取 app.yaml 的 kb.version 与 paths.artifacts，且 --kb-version 可覆盖。"""
    custom_artifacts = tmp_path / "my_artifacts"
    kb_dir = custom_artifacts / "kb"
    v1_path = _build_versioned_kb(kb_dir, "kb-20260101-000001", "版本一第四条。")
    v2_path = _build_versioned_kb(kb_dir, "kb-20260102-000001", "版本二第四条。")

    cfg_v1 = _write_app_yaml(
        tmp_path / "app_eval.yaml",
        kb_version="kb-20260101-000001",
        artifacts_dir=custom_artifacts,
    )

    captured_calls: list[dict[str, Any]] = []

    def _fake_run_eval(**kwargs: Any) -> dict[str, Any]:
        captured_calls.append(kwargs)
        return {
            "run_id": "run-dummy",
            "cases": 1,
            "dir": str(custom_artifacts / "eval" / "run-dummy"),
            "gold_issues": [],
        }

    monkeypatch.setattr("tu_assistant.eval.runner.run_eval", _fake_run_eval)

    # 1. 不传 --kb-version 与 --artifacts 时，读取 app.yaml 中的 kb.version 与 paths.artifacts
    res1 = runner.invoke(
        app,
        ["eval", "run", "--cases", "eval/cases/v1", "--config", str(cfg_v1)],
    )
    assert res1.exit_code == 0, res1.output
    assert len(captured_calls) == 1
    assert captured_calls[0]["kb_path"] == v1_path
    assert captured_calls[0]["artifacts_dir"] == str(custom_artifacts)

    # 2. 传 --kb-version 覆盖 app.yaml
    res2 = runner.invoke(
        app,
        [
            "eval",
            "run",
            "--cases",
            "eval/cases/v1",
            "--config",
            str(cfg_v1),
            "--kb-version",
            "kb-20260102-000001",
        ],
    )
    assert res2.exit_code == 0, res2.output
    assert len(captured_calls) == 2
    assert captured_calls[1]["kb_path"] == v2_path

    # 3. 传不存在的 --kb-version -> 退出码 2 且不建空库
    res_bad = runner.invoke(
        app,
        [
            "eval",
            "run",
            "--cases",
            "eval/cases/v1",
            "--config",
            str(cfg_v1),
            "--kb-version",
            "kb-missing-eval",
        ],
    )
    assert res_bad.exit_code == 2
    assert not (kb_dir / "kb-missing-eval.sqlite").exists()


def test_from_config_default_client_null_artifacts_and_connection_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 from_config(client=None) 在 paths.artifacts 为 null 时的回退与连接清理。"""
    from tu_assistant.runtime.client import EndpointNotAllowedError

    monkeypatch.chdir(tmp_path)
    kb_dir = tmp_path / "artifacts" / "kb"
    _build_versioned_kb(kb_dir, "kb-20260101-000001", "第四条原文。")

    serve_dir = tmp_path / "artifacts" / "serve"
    serve_dir.mkdir(parents=True)
    (serve_dir / "current.json").write_text(
        '{"model": "default_model", "exp": "exp-test"}',
        encoding="utf-8",
    )

    # 1. paths.artifacts 为 null 且 client=None 时，回退到 "artifacts" 并正确读取 serve/current.json
    cfg_null_art = _write_app_yaml(
        tmp_path / "app_null_art.yaml",
        kb_version="kb-20260101-000001",
        artifacts_dir="artifacts",
    )
    raw_cfg = yaml.safe_load(cfg_null_art.read_text(encoding="utf-8"))
    raw_cfg["paths"]["artifacts"] = None
    cfg_null_art.write_text(
        yaml.safe_dump(raw_cfg, allow_unicode=True), encoding="utf-8"
    )

    with TrainedAssistant.from_config(cfg_null_art) as assistant:
        assert assistant.kb_version == "kb-20260101-000001"
        assert assistant._client.model == "default_model"

    # 2. 当 ModelClient 因非法端点抛 EndpointNotAllowedError 时，from_config 已打开的 conn 不会泄漏
    raw_cfg["runtime"]["model_endpoint"] = "http://evil.example.com:8080/v1"
    cfg_bad_ep = tmp_path / "app_bad_ep.yaml"
    cfg_bad_ep.write_text(
        yaml.safe_dump(raw_cfg, allow_unicode=True), encoding="utf-8"
    )
    with pytest.raises(EndpointNotAllowedError):
        TrainedAssistant.from_config(cfg_bad_ep)

    # 3. 外部直接传入 kb_conn 构造 TrainedAssistant 时，close_kb() 不会误关外部连接
    ext_conn = open_kb(kb_dir / "kb-20260101-000001.sqlite", read_only=True)
    ext_assistant = TrainedAssistant(_StubModelClient("ok"), ext_conn)
    ext_assistant.close_kb()
    # 验证 ext_conn 依然可用（未被关闭）
    assert ext_conn.execute("SELECT COUNT(*) FROM clauses").fetchone()[0] == 1
    ext_conn.close()


def test_latest_kb_path_stem_order_and_import_directory_collision_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确定性验证同秒入库生成 -01/-02 后缀、显式重名报错及 latest_kb_path 按 stem 排序。"""
    from tu_assistant.kb.ingest import import_directory

    fixtures_dir = Path(__file__).resolve().parent.parent / "fixtures"
    monkeypatch.setattr(
        "tu_assistant.kb.ingest.new_kb_version",
        lambda: "kb-20261123-120000",
    )

    r1 = import_directory(fixtures_dir, tmp_path)
    r2 = import_directory(fixtures_dir, tmp_path)
    r3 = import_directory(fixtures_dir, tmp_path)

    assert r1["kb_version"] == "kb-20261123-120000"
    assert r2["kb_version"] == "kb-20261123-120000-01"
    assert r3["kb_version"] == "kb-20261123-120000-02"

    # latest_kb_path 必须选出 -02，而不是无后缀的 base 版本
    assert latest_kb_path(tmp_path).stem == "kb-20261123-120000-02"

    # 显式传入已存在的 kb_version 必须抛 FileExistsError
    with pytest.raises(FileExistsError, match="目标知识库已存在"):
        import_directory(
            fixtures_dir, tmp_path, kb_version="kb-20261123-120000"
        )
