"""从已有 SQLite 知识库派生新版本（T077 口径 2/3）。

不重新导入 inputs/，直接复制旧库并在新副本上为多款条文第一款（含其子项）
补齐显式款号 ``第1款``，同时保持 ``clause_id``、条款原文与原有关联完全不变。
旧库文件及其 manifest 全程只读、零修改。
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path

from ..manifest import write_manifest
from .parse import add_first_paragraph_label
from .store import new_kb_version, open_kb, set_meta


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_derived_invariants(src_conn: sqlite3.Connection, dst_conn: sqlite3.Connection) -> None:
    """确认派生库与源库只有 clauses.number_text（以及 kb_meta）不同。"""
    src_docs = src_conn.execute(
        "SELECT doc_id, title, issuer, level, version_label, promulgated_on, status, corpus, source_file "
        "FROM legal_documents ORDER BY doc_id"
    ).fetchall()
    dst_docs = dst_conn.execute(
        "SELECT doc_id, title, issuer, level, version_label, promulgated_on, status, corpus, source_file "
        "FROM legal_documents ORDER BY doc_id"
    ).fetchall()
    if src_docs != dst_docs:
        raise RuntimeError("派生校验失败：legal_documents 与源库不一致")

    clause_sql = (
        "SELECT clause_id, doc_id, article_no, paragraph_no, item_no, "
        "heading_path, text, clause_type, parse_warnings "
        "FROM clauses ORDER BY clause_id"
    )
    src_clauses = src_conn.execute(clause_sql).fetchall()
    dst_clauses = dst_conn.execute(clause_sql).fetchall()
    if src_clauses != dst_clauses:
        raise RuntimeError("派生校验失败：clause_id 或条款原文与源库不一致")

    src_rels = src_conn.execute(
        "SELECT from_clause_id, to_clause_id, relation_type, origin, confirmed "
        "FROM clause_relations ORDER BY from_clause_id, to_clause_id, relation_type"
    ).fetchall()
    dst_rels = dst_conn.execute(
        "SELECT from_clause_id, to_clause_id, relation_type, origin, confirmed "
        "FROM clause_relations ORDER BY from_clause_id, to_clause_id, relation_type"
    ).fetchall()
    if src_rels != dst_rels:
        raise RuntimeError("派生校验失败：clause_relations 与源库不一致")


def derive_kb(
    source_kb: str | Path,
    artifacts_dir: str | Path = "artifacts",
    *,
    kb_version: str | None = None,
    update_first_paragraph_label: bool = True,
) -> dict:
    """从 ``source_kb`` 派生新知识库版本并写入 manifest。"""
    src_path = Path(source_kb)
    if not src_path.is_file():
        raise FileNotFoundError(f"源知识库不存在：{src_path}")

    source_version = src_path.stem
    source_sha256 = sha256_file(src_path)

    kb_dir = Path(artifacts_dir) / "kb"
    kb_dir.mkdir(parents=True, exist_ok=True)
    target_version = kb_version or new_kb_version()
    dst_path = kb_dir / f"{target_version}.sqlite"
    if dst_path.exists():
        raise FileExistsError(f"目标知识库已存在：{dst_path}")
    if dst_path.resolve() == src_path.resolve():
        raise ValueError("目标版本不能与源版本相同")

    shutil.copy2(src_path, dst_path)

    articles_updated = 0
    rows_updated = 0
    total_clauses = 0
    file_count = 0

    dst_conn = open_kb(dst_path)
    src_conn = open_kb(src_path)
    try:
        file_count = dst_conn.execute("SELECT COUNT(*) FROM legal_documents").fetchone()[0]
        total_clauses = dst_conn.execute("SELECT COUNT(*) FROM clauses").fetchone()[0]

        with dst_conn:
            if update_first_paragraph_label:
                multi_arts = dst_conn.execute(
                    """SELECT doc_id, article_no
                       FROM clauses
                       WHERE paragraph_no IS NOT NULL
                       GROUP BY doc_id, article_no
                       HAVING COUNT(DISTINCT paragraph_no) >= 2"""
                ).fetchall()
                for doc_id, article_no in multi_arts:
                    p1_rows = dst_conn.execute(
                        "SELECT clause_id, number_text FROM clauses "
                        "WHERE doc_id=? AND article_no=? AND paragraph_no=1",
                        (doc_id, article_no),
                    ).fetchall()
                    art_changed = False
                    for cid, old_nt in p1_rows:
                        new_nt = add_first_paragraph_label(old_nt)
                        if new_nt != old_nt:
                            dst_conn.execute(
                                "UPDATE clauses SET number_text=? WHERE clause_id=?",
                                (new_nt, cid),
                            )
                            rows_updated += 1
                            art_changed = True
                    if art_changed:
                        articles_updated += 1

            set_meta(dst_conn, "kb_version", target_version)
            set_meta(dst_conn, "derived_from", source_version)
            set_meta(dst_conn, "derived_from_sha256", source_sha256)

        _verify_derived_invariants(src_conn, dst_conn)
    except Exception:
        dst_conn.close()
        src_conn.close()
        dst_path.unlink(missing_ok=True)
        raise
    else:
        dst_conn.close()
        src_conn.close()

    if sha256_file(src_path) != source_sha256:
        raise RuntimeError("派生后源知识库校验值发生变化，违反只读约定")

    dst_sha256 = sha256_file(dst_path)
    manifest_path = write_manifest(
        kb_dir / target_version,
        artifact_id=target_version,
        artifact_type="kb_version",
        inputs={
            "derived_from": source_version,
            "source_sqlite": str(src_path),
            "source_sha256": source_sha256,
            "file_count": file_count,
            "sqlite": str(dst_path),
        },
        config={"update_first_paragraph_label": update_first_paragraph_label},
        extra={
            "writable": True,
            "clause_count": total_clauses,
            "multi_para_articles_updated": articles_updated,
            "number_text_rows_updated": rows_updated,
            "sqlite_sha256": dst_sha256,
            "relation_imports": [],
        },
    )
    return {
        "kb_version": target_version,
        "derived_from": source_version,
        "source_sha256": source_sha256,
        "sqlite": str(dst_path),
        "sqlite_sha256": dst_sha256,
        "manifest": str(manifest_path),
        "files": file_count,
        "clauses": total_clauses,
        "multi_para_articles_updated": articles_updated,
        "number_text_rows_updated": rows_updated,
    }
