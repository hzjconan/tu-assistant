"""集成测试：T068 知识库更新、版本差异比对与配置切换全流程闭环（基于 tests/fixtures/）。

覆盖场景：
1. 从 tests/fixtures/ 整批入库生成 v1；
2. 修改《示例工会法》第四条原文、新增第十条、删除第六条后重新入库生成 v2（固定时间戳验证 -01 防撞名后缀）；
3. 用 diff_kbs / tu kb diff 对比 v1 与 v2，验证准确识别新增/删除/原文变化且绝不输出任何条文正文；
4. 仅修改 app.yaml 中的 kb.version（零代码改动），验证校验层与编排层切换版本：
   - 指向 v1 时引用旧原文判 ok；
   - 切到 v2（或 null 取最新）后，旧原文自动替换为 v2 新原文（corrected），已删第六条被拦截（not_found）；
5. 法规修订升级版本标签重导为 v3，验证逻辑键 diff 不误报全法删增，且校验层自动修正旧版本标签并替换为新原文；
6. 配置不存在的 kb.version 时抛 KBError 且不建空库；全流程结束后 v1.sqlite 与 v2.sqlite 哈希 100% 不变。
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from tu_assistant.chat.assistant import TrainedAssistant
from tu_assistant.citation.verify import NOT_FOUND_PLACEHOLDER, verify_output_from_config
from tu_assistant.cli import app
from tu_assistant.kb.diff import diff_kbs, render_diff
from tu_assistant.kb.ingest import import_directory
from tu_assistant.kb.store import KBError
from tu_assistant.runtime.client import ChatResponse

runner = CliRunner()
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class _StubModelClient:
    """确定性 stub 模型客户端：模拟未重训模型仍按 v1 旧记忆输出引用。"""

    def __init__(self, raw_reply: str) -> None:
        self._raw_reply = raw_reply

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> ChatResponse:
        return ChatResponse(content=self._raw_reply)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_config(path: Path, kb_version: str | None, artifacts_dir: Path) -> Path:
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


def test_kb_update_diff_and_config_switch_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """端到端验证：修改条款 -> 重新入库 -> kb diff -> 改 app.yaml 切换版本 -> 校验层与编排层使用新原文。"""
    artifacts_dir = tmp_path / "artifacts"
    corpus_v1 = tmp_path / "corpus_v1"
    corpus_v1.mkdir()
    shutil.copy2(FIXTURES_DIR / "law_sample.txt", corpus_v1 / "law_sample.txt")
    shutil.copy2(FIXTURES_DIR / "notice_sample.txt", corpus_v1 / "notice_sample.txt")

    # 固定同秒时间戳，确定性验证连续入库生成 -01 防撞名后缀
    monkeypatch.setattr(
        "tu_assistant.kb.ingest.new_kb_version",
        lambda: "kb-20261123-000001",
    )

    # 1. 导入初始版本 v1
    res_v1 = import_directory(corpus_v1, artifacts_dir)
    v1_ver = res_v1["kb_version"]
    assert v1_ver == "kb-20261123-000001"
    v1_sqlite = Path(res_v1["sqlite"])
    v1_sha_initial = _sha256(v1_sqlite)
    assert res_v1["files"] == 2

    old_art4_text = "用人单位不得阻挠职工依法参加和组织工会。"
    new_art4_text = "用人单位不得以任何形式阻挠、限制职工依法参加和组织工会。"
    deleted_art6_text = "上级工会可以派员帮助和指导企业职工组建工会。"
    added_art10_text = "本法自公布之日起施行。"

    # 2. 准备 v2 语料：修改第四条、删除第六条、新增第十条，立即重新导入（测试同秒连续入库防撞名）
    corpus_v2 = tmp_path / "corpus_v2"
    corpus_v2.mkdir()
    law_v1_text = (corpus_v1 / "law_sample.txt").read_text(encoding="utf-8")
    assert old_art4_text in law_v1_text
    assert deleted_art6_text in law_v1_text

    law_v2_text = (
        law_v1_text.replace(old_art4_text, new_art4_text)
        .replace(f"\n第六条 {deleted_art6_text}\n", "\n")
        .rstrip()
        + f"\n\n第十条 {added_art10_text}\n"
    )
    (corpus_v2 / "law_sample.txt").write_text(law_v2_text, encoding="utf-8")
    shutil.copy2(FIXTURES_DIR / "notice_sample.txt", corpus_v2 / "notice_sample.txt")

    res_v2 = import_directory(corpus_v2, artifacts_dir)
    v2_ver = res_v2["kb_version"]
    assert v2_ver == "kb-20261123-000001-01"
    v2_sqlite = Path(res_v2["sqlite"])
    v2_sha_initial = _sha256(v2_sqlite)
    assert v2_ver != v1_ver
    assert v2_ver > v1_ver

    # 3. 验证 diff_kbs 与 tu kb diff CLI
    diff_12 = diff_kbs(v1_ver, v2_ver, artifacts_dir=artifacts_dir)
    assert [it.article_no for it in diff_12.modified] == [4]
    assert [it.article_no for it in diff_12.removed] == [6]
    assert [it.article_no for it in diff_12.added] == [10]

    rendered_12 = render_diff(diff_12)
    cli_diff = runner.invoke(
        app,
        ["kb", "diff", v1_ver, v2_ver, "--artifacts", str(artifacts_dir)],
    )
    assert cli_diff.exit_code == 0
    assert cli_diff.stdout == rendered_12
    assert "[~ 原文变化] 《示例工会法》（2020-01-01）第四条" in cli_diff.stdout
    assert "[- 删除] 《示例工会法》（2020-01-01）第六条" in cli_diff.stdout
    assert "[+ 新增] 《示例工会法》（2020-01-01）第十条" in cli_diff.stdout

    # 严格断言任何条文正文均未出现在 diff 输出中
    for clause_body in (old_art4_text, new_art4_text, deleted_art6_text, added_art10_text):
        assert clause_body not in cli_diff.stdout

    # 4. 模拟未重训模型：仍输出 v1 的第四条旧原文与已删除的第六条
    stale_model_output = (
        "关于单位阻挠建会及上级工会指导的法律规定如下：\n"
        "〔《示例工会法》（2020-01-01）第四条〕\n"
        f"> {old_art4_text}\n"
        "此外：\n"
        "〔《示例工会法》（2020-01-01）第六条〕\n"
        f"> {deleted_art6_text}\n"
        "请依法维权。"
    )
    stub_client = _StubModelClient(stale_model_output)
    cfg_path = tmp_path / "app.yaml"

    # 4a. 配置 kb.version = v1 时：两处引用均 ok，输出旧原文
    _write_config(cfg_path, v1_ver, artifacts_dir)
    vr_v1 = verify_output_from_config(stale_model_output, cfg_path)
    assert vr_v1.stats == {"ok": 2, "corrected": 0, "not_found": 0, "incomplete": 0}
    assert old_art4_text in vr_v1.text
    assert deleted_art6_text in vr_v1.text

    with TrainedAssistant.from_config(cfg_path, client=stub_client) as assistant_v1:
        assert assistant_v1.kb_version == v1_ver
        sid = assistant_v1.new_session()
        reply_v1 = assistant_v1.send(sid, "单位不让建工会怎么办？")
        assert old_art4_text in reply_v1.content
        assert deleted_art6_text in reply_v1.content
        assistant_v1.close(sid)

    # 4b. 仅修改 app.yaml 的 kb.version = v2（零代码改动）：第四条自动替换为新原文，第六条被删除拦截
    _write_config(cfg_path, v2_ver, artifacts_dir)
    vr_v2 = verify_output_from_config(stale_model_output, cfg_path)
    assert vr_v2.stats == {"ok": 0, "corrected": 1, "not_found": 1, "incomplete": 0}
    assert new_art4_text in vr_v2.text
    assert old_art4_text not in vr_v2.text
    assert deleted_art6_text not in vr_v2.text
    assert NOT_FOUND_PLACEHOLDER in vr_v2.text

    with TrainedAssistant.from_config(cfg_path, client=stub_client) as assistant_v2:
        assert assistant_v2.kb_version == v2_ver
        sid = assistant_v2.new_session()
        reply_v2 = assistant_v2.send(sid, "单位不让建工会怎么办？")
        assert new_art4_text in reply_v2.content
        assert old_art4_text not in reply_v2.content
        assert deleted_art6_text not in reply_v2.content
        assert NOT_FOUND_PLACEHOLDER in reply_v2.content
        assistant_v2.close(sid)

    # 4c. 将 app.yaml 的 kb.version 设为 null：自动加载最新 v2，并交付 v2 新原文
    _write_config(cfg_path, None, artifacts_dir)
    with TrainedAssistant.from_config(cfg_path, client=stub_client) as assistant_latest:
        assert assistant_latest.kb_version == v2_ver
        sid = assistant_latest.new_session()
        reply_latest = assistant_latest.send(sid, "单位不让建工会怎么办？")
        assert new_art4_text in reply_latest.content
        assert old_art4_text not in reply_latest.content
        assistant_latest.close(sid)

    # 5. 模拟法规修订升级版本标签（2020年1月1日通过 -> 2024年6月1日修正）并微调第四条
    corpus_v3 = tmp_path / "corpus_v3"
    corpus_v3.mkdir()
    v3_art4_text = "用人单位及任何个人均不得阻挠、限制职工依法参加和组织工会。"
    law_v3_text = law_v1_text.replace(
        "（2020年1月1日通过）", "（2024年6月1日修正）"
    ).replace(old_art4_text, v3_art4_text)
    (corpus_v3 / "law_sample.txt").write_text(law_v3_text, encoding="utf-8")
    shutil.copy2(FIXTURES_DIR / "notice_sample.txt", corpus_v3 / "notice_sample.txt")

    res_v3 = import_directory(corpus_v3, artifacts_dir, kb_version="kb-20990101-000003")
    v3_ver = res_v3["kb_version"]
    assert v3_ver == "kb-20990101-000003"

    diff_13 = diff_kbs(v1_ver, v3_ver, artifacts_dir=artifacts_dir)
    assert len(diff_13.added) == 0
    assert len(diff_13.removed) == 0
    assert [it.article_no for it in diff_13.modified] == [4]
    assert diff_13.doc_changes.version_changed_docs == [
        ("示例工会法", "2020-01-01", "2024-06-01")
    ]

    # 切换到 v3 后，模型即便写旧版本号（2020-01-01）和旧原文，校验层也会修正版本号并替换为 v3 新原文
    _write_config(cfg_path, v3_ver, artifacts_dir)
    vr_v3 = verify_output_from_config(stale_model_output, cfg_path)
    assert vr_v3.stats == {"ok": 0, "corrected": 2, "not_found": 0, "incomplete": 0}
    assert "〔《示例工会法》（2024-06-01）第四条〕" in vr_v3.text
    assert "〔《示例工会法》（2024-06-01）第六条〕" in vr_v3.text
    assert v3_art4_text in vr_v3.text
    assert old_art4_text not in vr_v3.text

    # 6. 错误防线（执行单 §3.4 场景 5）：app.yaml 配置不存在的 kb.version -> 报 KBError 且不建空库
    _write_config(cfg_path, "kb-nonexistent-9999", artifacts_dir)
    with pytest.raises(KBError, match="知识库版本不存在"):
        verify_output_from_config(stale_model_output, cfg_path)
    with pytest.raises(KBError, match="知识库版本不存在"):
        TrainedAssistant.from_config(cfg_path, client=stub_client)
    assert not (artifacts_dir / "kb" / "kb-nonexistent-9999.sqlite").exists()

    # 7. 验证历史知识库只读保护：v1 与 v2 文件哈希全程零改动
    assert _sha256(v1_sqlite) == v1_sha_initial
    assert _sha256(v2_sqlite) == v2_sha_initial
