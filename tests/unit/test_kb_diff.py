"""单元测试：T066 知识库版本差异比对（src/tu_assistant/kb/diff.py 与 tu kb diff）。"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tu_assistant.cli import app
from tu_assistant.kb.diff import ClauseDiffItem, diff_kbs, render_diff, resolve_diff_kb
from tu_assistant.kb.models import Clause, ClauseRelation, DocumentMeta
from tu_assistant.kb.store import (
    KBError,
    create_kb,
    doc_id_for,
    insert_clause,
    insert_document,
    insert_relation,
    set_meta,
)

runner = CliRunner()


def _make_kb(
    kb_path: Path,
    version: str,
    docs: list[tuple[str, str, str, list[tuple[int, int | None, int | None, str, str]]]],
    relations: list[tuple[str, str, str, bool]] | None = None,
) -> Path:
    """辅助创建测试 SQLite 知识库。

    docs: [(title, version_label, status, [(art_no, para_no, item_no, number_text, text), ...])]
    """
    conn = create_kb(kb_path)
    with conn:
        for title, ver_label, status, clauses in docs:
            did = doc_id_for(title, ver_label)
            insert_document(
                conn,
                DocumentMeta(
                    title=title,
                    version_label=ver_label,
                    status=status,
                    doc_id=did,
                ),
            )
            for art_no, para_no, item_no, num_text, text in clauses:
                insert_clause(
                    conn,
                    Clause(
                        doc_id=did,
                        article_no=art_no,
                        paragraph_no=para_no,
                        item_no=item_no,
                        number_text=num_text,
                        text=text,
                    ),
                )
        for from_cid, to_cid, rel_type, confirmed in relations or []:
            insert_relation(
                conn,
                ClauseRelation(
                    from_clause_id=from_cid,
                    to_clause_id=to_cid,
                    relation_type=rel_type,
                    confirmed=confirmed,
                ),
            )
        set_meta(conn, "kb_version", version)
    conn.close()
    return kb_path


def test_diff_added_removed_modified_and_no_text_leak(tmp_path: Path) -> None:
    """验证新增、删除、原文变化三类判定准确，且数据结构与渲染文本均不含任何条文正文。"""
    secret_old = "【绝密旧条文正文_不得出现在diff输出_ALPHA_991】"
    secret_new = "【绝密新条文正文_不得出现在diff输出_BETA_992】"
    secret_del = "【绝密删除条文正文_不得出现在diff输出_GAMMA_993】"
    secret_add = "【绝密新增条文正文_不得出现在diff输出_DELTA_994】"
    secret_keep = "【绝密未变条文正文_不得出现在diff输出_EPSILON_995】"

    kb_dir = tmp_path / "kb"
    v1_path = _make_kb(
        kb_dir / "kb-20260101-000001.sqlite",
        "kb-20260101-000001",
        [
            (
                "示例工会法",
                "2020-01-01",
                "current",
                [
                    (1, 1, None, "第一条", secret_keep),
                    (2, 1, None, "第二条", secret_old),
                    (3, 1, None, "第三条", secret_del),
                ],
            )
        ],
    )
    v2_path = _make_kb(
        kb_dir / "kb-20260102-000001.sqlite",
        "kb-20260102-000001",
        [
            (
                "示例工会法",
                "2020-01-01",
                "current",
                [
                    (1, 1, None, "第一条", secret_keep),
                    (2, 1, None, "第二条", secret_new),
                    (4, 1, None, "第四条", secret_add),
                ],
            )
        ],
    )

    res = diff_kbs("kb-20260101-000001", "kb-20260102-000001", artifacts_dir=tmp_path)
    assert res.v1_version == "kb-20260101-000001"
    assert res.v2_version == "kb-20260102-000001"
    assert res.unchanged_count == 1
    assert len(res.added) == 1
    assert res.added[0].article_no == 4
    assert res.added[0].change_type == "added"
    assert len(res.removed) == 1
    assert res.removed[0].article_no == 3
    assert res.removed[0].change_type == "removed"
    assert len(res.modified) == 1
    assert res.modified[0].article_no == 2
    assert res.modified[0].change_type == "modified"

    # 验证 ClauseDiffItem 字段定义中本身就不含 text 属性
    assert not hasattr(res.modified[0], "text")
    assert "text" not in ClauseDiffItem.__dataclass_fields__

    rendered = render_diff(res)
    assert "[~ 原文变化] 《示例工会法》（2020-01-01）第二条" in rendered
    assert "[- 删除] 《示例工会法》（2020-01-01）第三条" in rendered
    assert "[+ 新增] 《示例工会法》（2020-01-01）第四条" in rendered

    for secret in (secret_old, secret_new, secret_del, secret_add, secret_keep):
        assert secret not in rendered
        assert secret not in repr(res)
    assert str(v1_path) == res.v1_path
    assert str(v2_path) == res.v2_path


def test_diff_version_label_revision_aligns_by_logical_key(tmp_path: Path) -> None:
    """同一法规修订升级 version_label（导致 doc_id 与 clause_id 全变）时，只报真正改动的条款。"""
    kb_dir = tmp_path / "kb"
    _make_kb(
        kb_dir / "kb-v1.sqlite",
        "kb-v1",
        [
            (
                "示例劳动法",
                "2018-01-01",
                "current",
                [
                    (1, 1, None, "第一条", "第一条原文保持不变。"),
                    (2, 1, None, "第二条", "第二条旧版原文。"),
                    (3, 1, None, "第三条", "第三条原文保持不变。"),
                ],
            )
        ],
    )
    _make_kb(
        kb_dir / "kb-v2.sqlite",
        "kb-v2",
        [
            (
                "示例劳动法",
                "2024-06-01",
                "current",
                [
                    (1, 1, None, "第一条", "第一条原文保持不变。"),
                    (2, 1, None, "第二条", "第二条2024年修正后新原文。"),
                    (3, 1, None, "第三条", "第三条原文保持不变。"),
                ],
            )
        ],
    )

    res = diff_kbs("kb-v1", "kb-v2", artifacts_dir=tmp_path)
    assert len(res.added) == 0
    assert len(res.removed) == 0
    assert len(res.modified) == 1
    assert res.unchanged_count == 2
    assert res.modified[0].article_no == 2
    assert res.modified[0].version_label_v1 == "2018-01-01"
    assert res.modified[0].version_label_v2 == "2024-06-01"
    assert res.modified[0].clause_id_v1 != res.modified[0].clause_id_v2
    assert res.doc_changes.version_changed_docs == [
        ("示例劳动法", "2018-01-01", "2024-06-01")
    ]

    rendered = render_diff(res)
    assert "[~ 版本更新] 《示例劳动法》（2018-01-01 -> 2024-06-01）" in rendered
    assert "[~ 原文变化] 《示例劳动法》（2018-01-01 -> 2024-06-01）第二条" in rendered
    assert "第二条旧版原文" not in rendered
    assert "第二条2024年修正后新原文" not in rendered


def test_diff_number_text_and_confirmed_relations_summary(tmp_path: Path) -> None:
    """原文未变但 number_text 或已确认关联变化时，不误报 modified，但在摘要中准确统计。"""
    kb_dir = tmp_path / "kb"
    did = doc_id_for("示例条例", "2021-01-01")
    _make_kb(
        kb_dir / "kb-old.sqlite",
        "kb-old",
        [
            (
                "示例条例",
                "2021-01-01",
                "current",
                [
                    (10, 1, None, "第十条", "第十条第一款原文。"),
                    (10, 2, None, "第十条第二款", "第十条第二款原文。"),
                    (38, 1, None, "第三十八条", "违反第十条规定的法律责任。"),
                ],
            )
        ],
        relations=[
            (f"{did}:a10:p1", f"{did}:a38:p1", "liability_for", True),
            (f"{did}:a10:p2", f"{did}:a38:p1", "references", False),  # 未确认的不计入
        ],
    )
    _make_kb(
        kb_dir / "kb-new.sqlite",
        "kb-new",
        [
            (
                "示例条例",
                "2021-01-01",
                "current",
                [
                    (10, 1, None, "第十条第一款", "第十条第一款原文。"),
                    (10, 2, None, "第十条第二款", "第十条第二款原文。"),
                    (38, 1, None, "第三十八条", "违反第十条规定的法律责任。"),
                ],
            )
        ],
        relations=[
            (f"{did}:a10:p2", f"{did}:a38:p1", "liability_for", True),
        ],
    )

    res = diff_kbs("kb-old", "kb-new", artifacts_dir=tmp_path)
    assert not res.has_clause_changes
    assert res.unchanged_count == 3
    assert res.number_text_changed_count == 1
    assert res.relations_diff.v1_confirmed == 1
    assert res.relations_diff.v2_confirmed == 1
    assert res.relations_diff.added_count == 1
    assert res.relations_diff.removed_count == 1
    assert res.relations_diff.unchanged_count == 0

    rendered = render_diff(res)
    assert "编号写法变化（原文未变）：1 条" in rendered
    assert "已确认条款关联：1 条 -> 1 条（+1 / -1，保留 0）" in rendered
    assert "条款明细：无新增、删除或原文变化的条款。" in rendered


def test_diff_non_current_docs_reported_and_excluded_from_current_clauses(
    tmp_path: Path,
) -> None:
    """非 current 文档在摘要中单独提示，不混入 current 条款对比。"""
    kb_dir = tmp_path / "kb"
    _make_kb(
        kb_dir / "kb-1.sqlite",
        "kb-1",
        [
            ("示例法", "2010", "amended", [(1, 1, None, "第一条", "2010旧版第一条")]),
            ("示例法", "2020", "current", [(1, 1, None, "第一条", "2020现行第一条")]),
        ],
    )
    _make_kb(
        kb_dir / "kb-2.sqlite",
        "kb-2",
        [
            ("示例法", "2020", "current", [(1, 1, None, "第一条", "2020现行第一条")]),
        ],
    )
    res = diff_kbs("kb-1", "kb-2", artifacts_dir=tmp_path)
    assert res.doc_changes.v1_non_current_docs == 1
    assert res.doc_changes.v2_non_current_docs == 0
    assert not res.has_clause_changes
    text = render_diff(res)
    assert "非现行版本文件（未纳入现行条款对比）：1 篇 -> 0 篇" in text


def test_diff_error_handling_and_no_empty_sqlite_created(tmp_path: Path) -> None:
    """不存在的版本、路径穿越或损坏库应抛 KBError（CLI 退出码 2），且绝不在磁盘创建空文件。"""
    kb_dir = tmp_path / "kb"
    v1_path = _make_kb(
        kb_dir / "kb-ok.sqlite",
        "kb-ok",
        [("示例法", "2020", "current", [(1, 1, None, "第一条", "正文")])],
    )
    v1_sha_before = hashlib.sha256(v1_path.read_bytes()).hexdigest()

    # 1. 不存在的版本号
    missing_ver = "kb-nonexistent-999"
    with pytest.raises(KBError, match="知识库版本不存在"):
        diff_kbs("kb-ok", missing_ver, artifacts_dir=tmp_path)
    assert not (kb_dir / f"{missing_ver}.sqlite").exists()

    # 2. 路径穿越版本号
    with pytest.raises(KBError):
        resolve_diff_kb("../evil", artifacts_dir=tmp_path)

    # 3. 缺少必需表的损坏 sqlite
    bad_sqlite = kb_dir / "kb-corrupt.sqlite"
    conn = sqlite3.connect(bad_sqlite)
    conn.execute("CREATE TABLE dummy (id INT)")
    conn.close()
    with pytest.raises(KBError, match="缺少必需表"):
        diff_kbs("kb-ok", "kb-corrupt", artifacts_dir=tmp_path)

    # 4. CLI 调用失败时退出码为 2 且不建空库
    cli_res = runner.invoke(
        app,
        ["kb", "diff", "kb-ok", "kb-missing-cli", "--artifacts", str(tmp_path)],
    )
    assert cli_res.exit_code == 2
    assert "对比失败" in (cli_res.stdout + cli_res.stderr)
    assert not (kb_dir / "kb-missing-cli.sqlite").exists()

    # 5. CLI 正常调用退出码为 0（支持 --summary-only）
    ok_res = runner.invoke(
        app,
        ["kb", "diff", "kb-ok", "kb-ok", "--summary-only", "--artifacts", str(tmp_path)],
    )
    assert ok_res.exit_code == 0
    assert "条款变化汇总：新增 0 条 / 删除 0 条 / 原文变化 0 条" in ok_res.stdout
    assert "条款变更明细" not in ok_res.stdout

    # 6. 支持直接传显式 .sqlite 文件路径（或 Path 对象）
    res_by_path = diff_kbs(v1_path, str(v1_path))
    assert not res_by_path.has_clause_changes

    # 7. 非 SQLite 垃圾文件或含同名表但缺必需列的损坏库均抛 KBError
    not_sqlite = kb_dir / "kb-garbage.sqlite"
    not_sqlite.write_bytes(b"not a valid sqlite database header")
    with pytest.raises(KBError):
        diff_kbs("kb-ok", "kb-garbage", artifacts_dir=tmp_path)

    bad_cols = kb_dir / "kb-badcols.sqlite"
    c_bad = sqlite3.connect(bad_cols)
    c_bad.executescript(
        "CREATE TABLE legal_documents (id INT);"
        "CREATE TABLE clauses (id INT);"
        "CREATE TABLE clause_relations (id INT);"
    )
    c_bad.close()
    with pytest.raises(KBError, match="读取知识库快照失败"):
        diff_kbs("kb-ok", "kb-badcols", artifacts_dir=tmp_path)

    # 8. 原库字节零修改
    assert hashlib.sha256(v1_path.read_bytes()).hexdigest() == v1_sha_before
