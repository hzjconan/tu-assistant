"""T077: 条款关联抽取、派生新 KB、事务化差异确认与关系样本规范原文的单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tu_assistant.cli import app
from tu_assistant.kb.derive import derive_kb, sha256_file
from tu_assistant.kb.models import Clause, ClauseRelation, DocumentMeta
from tu_assistant.kb.parse import parse_clauses
from tu_assistant.kb.relations import (
    RelationImportError,
    apply_relations_diff,
    extract_relations,
)
from tu_assistant.kb.store import (
    create_kb,
    doc_id_for,
    insert_clause,
    insert_document,
    insert_relation,
    open_kb,
)
from tu_assistant.manifest import write_manifest
from tu_assistant.synth.check import CheckStats, check_sample
from tu_assistant.synth.knowledge import doc_titles, relation_samples


def _make_doc_clauses() -> tuple[DocumentMeta, list[Clause]]:
    lines = [
        "示例条例",
        "第一条 总则内容。",
        "第二条 第一款规定。",
        "用人单位不得有禁止行为。",
        "第三条 应当遵守以下规定：（一）项一；（二）项二。",
        "第四条 第一款总原则。",
        "企业不得有下列行为：（一）行为甲；（二）行为乙。",
        "职工不得有下列行为：（一）行为丙；（二）行为丁。",
        "第五条 义务五。",
        "第六条 义务六。",
        "第七条 义务七。",
        "第八条 义务八第一款。",
        "义务八第二款。",
        "第九条 违反本条例第二条第二款规定的，责令改正。",
        "第十条 违反本条例第四条规定的，予以处理。",
        "第十一条 违反本条例第五条、第六条、第八条第一款规定的，给予警告。",
        "第十二条 违反本条例第五条至第七条规定的，依法处罚。",
        "第十三条 依照本条例第三条第一项、第二项和《治安管理处罚法》第二条处理。",
        "第十四条 本条例第八条第二款除外；违反本条例第九十九条以及第二条第九款均无效。",
        "第十五条 违反本条例第十五条规定的自引用应忽略。",
    ]
    meta = DocumentMeta(title="示例条例", version_label="2026-01-01")
    meta.doc_id = doc_id_for(meta.title, meta.version_label)
    clauses, warnings = parse_clauses(lines, meta.doc_id)
    assert not warnings
    return meta, clauses


class TestExtractRelations:
    def test_explicit_paragraph_and_whole_article_expansion(self):
        meta, clauses = _make_doc_clauses()
        rels = extract_relations(clauses)
        by_key = {(r.from_clause_id, r.to_clause_id, r.relation_type): r for r in rels}
        d = meta.doc_id

        # 明指第 2 款，不误落到第 1 款
        assert (f"{d}:a2:p2", f"{d}:a9:p1", "liability_for") in by_key
        assert (f"{d}:a2:p1", f"{d}:a9:p1", "liability_for") not in by_key
        r9 = by_key[(f"{d}:a2:p2", f"{d}:a9:p1", "liability_for")]
        assert r9.scope == "explicit_paragraph"
        assert "第二条第二款" in r9.evidence

        # 整条引用多款条文（第 4 条共 3 款）按款展开
        for p in (1, 2, 3):
            key = (f"{d}:a4:p{p}", f"{d}:a10:p1", "liability_for")
            assert key in by_key
            assert by_key[key].scope == "whole_article_expanded"

    def test_enumerations_ranges_items_and_exceptions(self):
        meta, clauses = _make_doc_clauses()
        rels = extract_relations(clauses)
        by_key = {(r.from_clause_id, r.to_clause_id, r.relation_type): r for r in rels}
        d = meta.doc_id

        # 并列：第五条、第六条、第八条第一款
        assert (f"{d}:a5:p1", f"{d}:a11:p1", "liability_for") in by_key
        assert (f"{d}:a6:p1", f"{d}:a11:p1", "liability_for") in by_key
        assert (f"{d}:a8:p1", f"{d}:a11:p1", "liability_for") in by_key
        assert (f"{d}:a8:p2", f"{d}:a11:p1", "liability_for") not in by_key
        assert by_key[(f"{d}:a5:p1", f"{d}:a11:p1", "liability_for")].scope == "single_paragraph_article"
        assert by_key[(f"{d}:a8:p1", f"{d}:a11:p1", "liability_for")].scope == "explicit_paragraph"

        # 区间：第五条至第七条 → 5, 6, 7
        for a in (5, 6, 7):
            assert (f"{d}:a{a}:p1", f"{d}:a12:p1", "liability_for") in by_key

        # 并列项：第三条第一项、第二项；跨法《治安管理处罚法》第二条不得误抽
        assert (f"{d}:a3:p1:i1", f"{d}:a13:p1", "references") in by_key
        assert (f"{d}:a3:p1:i2", f"{d}:a13:p1", "references") in by_key
        assert by_key[(f"{d}:a3:p1:i1", f"{d}:a13:p1", "references")].scope == "explicit_item"
        assert (f"{d}:a2:p1", f"{d}:a13:p1", "references") not in by_key

        # 例外、无效编号、自引用
        assert (f"{d}:a8:p2", f"{d}:a14:p1", "exception_of") in by_key
        assert all(r.to_clause_id != f"{d}:a15:p1" for r in rels)
        assert all(":a99:" not in r.from_clause_id for r in rels)


def _setup_legacy_kb(tmp_path: Path) -> tuple[Path, str, str]:
    """构造带旧编号惯例（多款第 1 款无款号）与旧错边的历史 KB。"""
    artifacts = tmp_path / "artifacts"
    kb_ver = "kb-20261113-000001"
    kb_path = artifacts / "kb" / f"{kb_ver}.sqlite"
    conn = create_kb(kb_path)
    meta, clauses = _make_doc_clauses()
    insert_document(conn, meta)
    # 模拟旧库：把多款条文第一款及其子项去掉"第1款"
    for c in clauses:
        if c.paragraph_no == 1 and "第1款" in c.number_text:
            c = Clause(
                c.doc_id,
                c.article_no,
                c.paragraph_no,
                c.item_no,
                c.number_text.replace("第1款", ""),
                c.heading_path,
                c.text,
            )
        insert_clause(conn, c)
    d = meta.doc_id
    # 旧错边 + 一条无关但已确认的保留边
    insert_relation(conn, ClauseRelation(f"{d}:a2:p1", f"{d}:a9:p1", "liability_for", "rule", True))
    insert_relation(conn, ClauseRelation(f"{d}:a5:p1", f"{d}:a11:p1", "liability_for", "rule", True))
    conn.commit()
    conn.close()
    # 旧库 manifest 无 writable 标记
    write_manifest(
        artifacts / "kb" / kb_ver,
        artifact_id=kb_ver,
        artifact_type="kb_version",
        inputs={"file_count": 1, "sqlite": str(kb_path)},
        config={},
    )
    return artifacts, kb_ver, d


class TestDeriveAndConfirm:
    def test_derive_matches_parse_and_preserves_source(self, tmp_path):
        artifacts, old_ver, d = _setup_legacy_kb(tmp_path)
        old_kb = artifacts / "kb" / f"{old_ver}.sqlite"
        old_hash = sha256_file(old_kb)

        res = derive_kb(old_kb, artifacts, kb_version="kb-20261119-000001")
        assert sha256_file(old_kb) == old_hash
        assert res["multi_para_articles_updated"] == 3  # 第 2、4、8 条

        # 派生库 number_text 与重新 parse_clauses 的结果逐行一致
        _, parsed = _make_doc_clauses()
        expected_nt = {c.clause_id: c.number_text for c in parsed}
        conn = open_kb(res["sqlite"])
        actual_nt = dict(conn.execute("SELECT clause_id, number_text FROM clauses").fetchall())
        conn.close()
        assert actual_nt == expected_nt
        assert actual_nt[f"{d}:a2:p1"] == "第二条第1款"
        assert actual_nt[f"{d}:a3:p1"] == "第三条"  # 单款含项保持不带款号

    def test_confirm_diff_revoke_add_idempotent_and_preserves_unlisted(self, tmp_path):
        artifacts, old_ver, d = _setup_legacy_kb(tmp_path)
        old_kb = artifacts / "kb" / f"{old_ver}.sqlite"
        new_ver = "kb-20261119-000002"
        derive_kb(old_kb, artifacts, kb_version=new_ver)

        review_file = tmp_path / "batch1.jsonl"
        rows = [
            # 撤销旧错边 a2:p1 -> a9:p1
            {
                "from_clause_id": f"{d}:a2:p1",
                "to_clause_id": f"{d}:a9:p1",
                "relation_type": "liability_for",
                "origin": "rule",
                "decision": "revoke",
                "confirmed": False,
            },
            # 确认正确边 a2:p2 -> a9:p1
            {
                "from_clause_id": f"{d}:a2:p2",
                "to_clause_id": f"{d}:a9:p1",
                "relation_type": "liability_for",
                "origin": "rule",
                "decision": "confirm",
                "confirmed": True,
            },
            # 拒绝与待查不生效
            {
                "from_clause_id": f"{d}:a4:p1",
                "to_clause_id": f"{d}:a10:p1",
                "relation_type": "liability_for",
                "origin": "rule",
                "decision": "reject",
                "confirmed": False,
            },
            {
                "from_clause_id": f"{d}:a4:p2",
                "to_clause_id": f"{d}:a10:p1",
                "relation_type": "liability_for",
                "origin": "rule",
                "decision": "pending",
                "confirmed": False,
            },
        ]
        review_file.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )

        r1 = apply_relations_diff(review_file, new_ver, artifacts, batch="b1")
        assert r1["confirmed"] == 1
        assert r1["revoked"] == 1 and r1["revoked_deleted"] == 1
        assert r1["rejected"] == 1 and r1["pending"] == 1
        assert r1["total_confirmed_after"] == 2  # a2:p2->a9:p1 + 未列出的保留边 a5:p1->a11:p1

        # 重复导入幂等
        r2 = apply_relations_diff(review_file, new_ver, artifacts, batch="b1")
        assert r2["revoked_deleted"] == 0
        assert r2["total_confirmed_after"] == 2

        conn = open_kb(artifacts / "kb" / f"{new_ver}.sqlite")
        edges = set(
            conn.execute(
                "SELECT from_clause_id, to_clause_id, relation_type FROM clause_relations WHERE confirmed=1"
            ).fetchall()
        )
        conn.close()
        assert edges == {
            (f"{d}:a2:p2", f"{d}:a9:p1", "liability_for"),
            (f"{d}:a5:p1", f"{d}:a11:p1", "liability_for"),
        }

    def test_confirm_rollback_on_bad_line_or_missing_endpoint(self, tmp_path):
        artifacts, old_ver, d = _setup_legacy_kb(tmp_path)
        new_ver = "kb-20261119-000003"
        derive_kb(artifacts / "kb" / f"{old_ver}.sqlite", artifacts, kb_version=new_ver)

        # 1) 第一行合法 confirm，第二行端点不存在 → 整批回滚，第一行也不得落库
        bad_ep = tmp_path / "bad_endpoint.jsonl"
        bad_ep.write_text(
            json.dumps(
                {
                    "from_clause_id": f"{d}:a2:p2",
                    "to_clause_id": f"{d}:a9:p1",
                    "relation_type": "liability_for",
                    "decision": "confirm",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "from_clause_id": f"{d}:a999:p1",
                    "to_clause_id": f"{d}:a9:p1",
                    "relation_type": "liability_for",
                    "decision": "confirm",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        with pytest.raises(RelationImportError, match="未找到的端点"):
            apply_relations_diff(bad_ep, new_ver, artifacts)

        # 2) 第二行坏 JSON → 整批回滚
        bad_json = tmp_path / "bad_json.jsonl"
        bad_json.write_text(
            json.dumps(
                {
                    "from_clause_id": f"{d}:a2:p2",
                    "to_clause_id": f"{d}:a9:p1",
                    "relation_type": "liability_for",
                    "decision": "confirm",
                }
            )
            + "\n{not valid json\n",
            encoding="utf-8",
        )
        with pytest.raises(RelationImportError, match="第 2 行"):
            apply_relations_diff(bad_json, new_ver, artifacts)

        conn = open_kb(artifacts / "kb" / f"{new_ver}.sqlite")
        edges = set(
            conn.execute(
                "SELECT from_clause_id, to_clause_id FROM clause_relations WHERE confirmed=1"
            ).fetchall()
        )
        conn.close()
        assert (f"{d}:a2:p2", f"{d}:a9:p1") not in edges
        assert (f"{d}:a2:p1", f"{d}:a9:p1") in edges  # 原状态未变

    def test_confirm_refuses_historical_or_referenced_kb(self, tmp_path):
        artifacts, old_ver, d = _setup_legacy_kb(tmp_path)
        review = tmp_path / "r.jsonl"
        review.write_text(
            json.dumps(
                {
                    "from_clause_id": f"{d}:a2:p2",
                    "to_clause_id": f"{d}:a9:p1",
                    "relation_type": "liability_for",
                    "decision": "confirm",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        # 1) 旧库未标记 writable=true → 拒写
        with pytest.raises(RelationImportError, match="拒绝原地写入"):
            apply_relations_diff(review, old_ver, artifacts)

        # 2) 新派生库一旦被数据集引用 → 拒写
        new_ver = "kb-20261119-000004"
        derive_kb(artifacts / "kb" / f"{old_ver}.sqlite", artifacts, kb_version=new_ver)
        write_manifest(
            artifacts / "datasets" / "ds-ref",
            artifact_id="ds-ref",
            artifact_type="dataset",
            inputs={"kb_version": new_ver},
        )
        with pytest.raises(RelationImportError, match="已被产物引用"):
            apply_relations_diff(review, new_ver, artifacts)

        # 3) CLI 入口对历史库返回非零
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "kb",
                "relations",
                "confirm",
                str(review),
                "--kb-version",
                old_ver,
                "--artifacts",
                str(artifacts),
            ],
        )
        assert result.exit_code == 2

    def test_cli_confirm_warns_when_revoking_missing_edge(self, tmp_path):
        artifacts, old_ver, d = _setup_legacy_kb(tmp_path)
        new_ver = "kb-20261119-000005"
        derive_kb(artifacts / "kb" / f"{old_ver}.sqlite", artifacts, kb_version=new_ver)
        revoke_missing = tmp_path / "revoke_missing.jsonl"
        revoke_missing.write_text(
            json.dumps(
                {
                    "from_clause_id": f"{d}:a1:p1",
                    "to_clause_id": f"{d}:a9:p1",
                    "relation_type": "liability_for",
                    "decision": "revoke",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "kb",
                "relations",
                "confirm",
                str(revoke_missing),
                "--kb-version",
                new_ver,
                "--artifacts",
                str(artifacts),
            ],
        )
        assert result.exit_code == 0
        assert "警告：有 1 条 revoke 边在目标知识库中本就不存在" in result.output

    def test_relation_samples_include_canonical_items(self):
        conn = create_kb(":memory:")
        meta, clauses = _make_doc_clauses()
        insert_document(conn, meta)
        for c in clauses:
            insert_clause(conn, c)
        d = meta.doc_id
        # a4:p2 有 2 个子项，建立 a4:p2 -> a10:p1 责任关系，另加一条 references 关系
        insert_relation(conn, ClauseRelation(f"{d}:a4:p2", f"{d}:a10:p1", "liability_for", "rule", True))
        insert_relation(conn, ClauseRelation(f"{d}:a3:p1:i1", f"{d}:a13:p1", "references", "rule", True))
        conn.commit()

        samples = relation_samples(conn, doc_titles(conn))
        assert len(samples) == 2
        liab = next(s for s in samples if s["meta"]["kind"] == "relation_liability_for")
        ref = next(s for s in samples if s["meta"]["kind"] == "relation_references")
        assert "（一）行为甲；（二）行为乙。" in liab["messages"][1]["content"]
        stats = CheckStats()
        for s in (liab, ref):
            assert check_sample(
                s["messages"][1]["content"],
                conn,
                stats,
                require_citation=True,
                expected_clause_ids=set(s["meta"]["clause_ids"]),
            )
        conn.close()
