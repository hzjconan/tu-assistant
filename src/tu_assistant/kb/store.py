"""知识库存储：SQLite。

每次入库生成新的 kb_version 文件 ``artifacts/kb/<kb_version>.sqlite``。
训练与评测引用具体的 kb_version，保证可复现（data-model.md §1）。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import DEFAULT_APP_CONFIG, get, load_app_config
from .models import Clause, ClauseRelation, DocumentMeta


class KBError(ValueError):
    """知识库版本定位、校验或打开错误。"""

SCHEMA = """
CREATE TABLE legal_documents (
    doc_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    issuer TEXT,
    level TEXT,
    version_label TEXT NOT NULL DEFAULT '',
    promulgated_on TEXT,
    status TEXT NOT NULL DEFAULT 'current',
    corpus TEXT NOT NULL DEFAULT 'project',
    source_file TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX one_current_per_title
    ON legal_documents(title) WHERE status = 'current';

CREATE TABLE clauses (
    clause_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES legal_documents(doc_id),
    article_no INTEGER NOT NULL,
    paragraph_no INTEGER,
    item_no INTEGER,
    number_text TEXT NOT NULL,
    heading_path TEXT NOT NULL DEFAULT '[]',
    text TEXT NOT NULL,
    clause_type TEXT NOT NULL DEFAULT 'other',
    parse_warnings TEXT NOT NULL DEFAULT '[]'
);
CREATE UNIQUE INDEX uniq_clause_no
    ON clauses(doc_id, article_no, ifnull(paragraph_no, -1), ifnull(item_no, -1));
CREATE INDEX idx_clauses_doc ON clauses(doc_id);

CREATE TABLE clause_relations (
    from_clause_id TEXT NOT NULL,
    to_clause_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'rule',
    confirmed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (from_clause_id, to_clause_id, relation_type)
);

CREATE TABLE kb_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def new_kb_version() -> str:
    return datetime.now(UTC).strftime("kb-%Y%m%d-%H%M%S")


def create_kb(path: str | Path) -> sqlite3.Connection:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.executescript(SCHEMA)
    return conn


def doc_id_for(title: str, version_label: str) -> str:
    return hashlib.sha256(f"{title}|{version_label}".encode()).hexdigest()[:16]


def insert_document(conn: sqlite3.Connection, meta: DocumentMeta) -> None:
    conn.execute(
        """INSERT INTO legal_documents
           (doc_id, title, issuer, level, version_label, promulgated_on,
            status, corpus, source_file)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            meta.doc_id,
            meta.title,
            meta.issuer,
            meta.level,
            meta.version_label,
            meta.promulgated_on,
            meta.status,
            meta.corpus,
            meta.source_file,
        ),
    )


def insert_clause(conn: sqlite3.Connection, c: Clause) -> None:
    conn.execute(
        """INSERT INTO clauses
           (clause_id, doc_id, article_no, paragraph_no, item_no,
            number_text, heading_path, text, clause_type, parse_warnings)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            c.clause_id,
            c.doc_id,
            c.article_no,
            c.paragraph_no,
            c.item_no,
            c.number_text,
            json.dumps(c.heading_path, ensure_ascii=False),
            c.text,
            c.clause_type,
            json.dumps(c.parse_warnings, ensure_ascii=False),
        ),
    )


def insert_relation(conn: sqlite3.Connection, r: ClauseRelation) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO clause_relations
           (from_clause_id, to_clause_id, relation_type, origin, confirmed)
           VALUES (?,?,?,?,?)""",
        (r.from_clause_id, r.to_clause_id, r.relation_type, r.origin, int(r.confirmed)),
    )


def delete_relation(
    conn: sqlite3.Connection,
    from_clause_id: str,
    to_clause_id: str,
    relation_type: str,
) -> int:
    """删除指定条款关联，返回实际删除行数。"""
    cur = conn.execute(
        """DELETE FROM clause_relations
           WHERE from_clause_id=? AND to_clause_id=? AND relation_type=?""",
        (from_clause_id, to_clause_id, relation_type),
    )
    return cur.rowcount


def article_clauses(
    conn: sqlite3.Connection,
    title: str,
    article_no: int,
    *,
    version_label: str | None = None,
    status: str | None = "current",
) -> list[Clause]:
    """返回某文件某条下的全部条款行（各款、项），按款/项排序。"""
    sql = """SELECT c.* FROM clauses c
             JOIN legal_documents d ON c.doc_id = d.doc_id
             WHERE d.title = ? AND c.article_no = ?"""
    params: list = [title, article_no]
    if version_label:
        sql += " AND d.version_label = ?"
        params.append(version_label)
    elif status:
        sql += " AND d.status = ?"
        params.append(status)
    sql += " ORDER BY ifnull(c.paragraph_no,0), ifnull(c.item_no,0)"
    return [_row_to_clause(r) for r in conn.execute(sql, params)]


def get_clause(
    conn: sqlite3.Connection,
    title: str,
    article_no: int,
    paragraph_no: int | None = None,
    item_no: int | None = None,
    *,
    version_label: str | None = None,
    status: str | None = "current",
) -> Clause | None:
    """按 文件名 + 编号 查条款。version_label 为空时取 status=current 的版本。"""
    sql = """SELECT c.* FROM clauses c
             JOIN legal_documents d ON c.doc_id = d.doc_id
             WHERE d.title = ? AND c.article_no = ?"""
    params: list = [title, article_no]
    if version_label:
        sql += " AND d.version_label = ?"
        params.append(version_label)
    elif status:
        sql += " AND d.status = ?"
        params.append(status)
    if paragraph_no is None:
        sql += " AND c.paragraph_no IS NULL"
    else:
        sql += " AND c.paragraph_no = ?"
        params.append(paragraph_no)
    if item_no is None:
        sql += " AND c.item_no IS NULL"
    else:
        sql += " AND c.item_no = ?"
        params.append(item_no)
    row = conn.execute(sql, params).fetchone()
    return _row_to_clause(row) if row else None


def get_document(conn: sqlite3.Connection, doc_id: str) -> DocumentMeta | None:
    row = conn.execute("SELECT * FROM legal_documents WHERE doc_id=?", (doc_id,)).fetchone()
    if not row:
        return None
    cols = [d[0] for d in conn.execute("SELECT * FROM legal_documents LIMIT 0").description]
    data = dict(zip(cols, row, strict=True))
    return DocumentMeta(**{k: data.get(k) for k in DocumentMeta.__dataclass_fields__})


def list_documents(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.execute(
        """SELECT d.doc_id, d.title, d.version_label, d.status, COUNT(c.clause_id)
           FROM legal_documents d LEFT JOIN clauses c ON c.doc_id = d.doc_id
           GROUP BY d.doc_id ORDER BY d.title"""
    )
    return [
        {"doc_id": r[0], "title": r[1], "version_label": r[2], "status": r[3], "clauses": r[4]}
        for r in cur
    ]


def find_clauses_by_number(
    conn: sqlite3.Connection, doc_id: str, article_no: int
) -> list[Clause]:
    cur = conn.execute(
        """SELECT * FROM clauses WHERE doc_id=? AND article_no=?
           ORDER BY paragraph_no, item_no""",
        (doc_id, article_no),
    )
    return [_row_to_clause(r) for r in cur]


def all_clauses(conn: sqlite3.Connection, doc_id: str | None = None) -> list[Clause]:
    """取全部条款，或某文件的全部条款。"""
    if doc_id:
        cur = conn.execute(
            "SELECT * FROM clauses WHERE doc_id=? ORDER BY article_no, paragraph_no, item_no",
            (doc_id,),
        )
    else:
        cur = conn.execute(
            "SELECT * FROM clauses ORDER BY doc_id, article_no, paragraph_no, item_no"
        )
    return [_row_to_clause(r) for r in cur]


def get_clause_by_id(conn: sqlite3.Connection, clause_id: str) -> Clause | None:
    row = conn.execute(
        "SELECT * FROM clauses WHERE clause_id=?", (clause_id,)
    ).fetchone()
    return _row_to_clause(row) if row else None


def confirmed_relations_from(
    conn: sqlite3.Connection, clause_ids: list[str]
) -> list[ClauseRelation]:
    """给定一组 clause_id，返回以它们为起点的已确认关联。"""
    if not clause_ids:
        return []
    placeholders = ",".join("?" for _ in clause_ids)
    cur = conn.execute(
        f"""SELECT from_clause_id, to_clause_id, relation_type, origin, confirmed
            FROM clause_relations
            WHERE confirmed = 1 AND from_clause_id IN ({placeholders})""",
        clause_ids,
    )
    return [
        ClauseRelation(r[0], r[1], r[2], r[3], bool(r[4])) for r in cur.fetchall()
    ]


def _row_to_clause(row: tuple) -> Clause:
    cols = [
        "clause_id", "doc_id", "article_no", "paragraph_no", "item_no",
        "number_text", "heading_path", "text", "clause_type", "parse_warnings",
    ]
    data = dict(zip(cols, row, strict=True))
    return Clause(
        doc_id=data["doc_id"],
        article_no=data["article_no"],
        paragraph_no=data["paragraph_no"],
        item_no=data["item_no"],
        number_text=data["number_text"],
        heading_path=json.loads(data["heading_path"]),
        text=data["text"],
        clause_type=data["clause_type"],
        parse_warnings=json.loads(data["parse_warnings"]),
    )


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO kb_meta VALUES (?,?)", (key, value))


def _validate_kb_version(version: Any) -> str:
    """校验 kb_version 合法性，防止非法类型、空白或路径穿越。"""
    if not isinstance(version, str):
        raise KBError(f"非法知识库版本号（必须为非空字符串）：{version!r}")
    v = version.strip()
    if not v or v != version:
        raise KBError(f"非法知识库版本号（不能为空或含首尾空白）：{version!r}")
    if v in {".", ".."} or "/" in v or "\\" in v or ".." in v:
        raise KBError(f"非法知识库版本号（含非法路径字符）：{version!r}")
    return v


def latest_kb_path(artifacts_dir: str | Path = "artifacts") -> Path:
    """查找 artifacts_dir/kb 下最新的 kb-*.sqlite 文件；不存在时抛 KBError。

    按 stem（不含 .sqlite 后缀）排序，确保同秒派生的 kb-YYYYMMDD-HHMMSS-01
    排在 kb-YYYYMMDD-HHMMSS 之后（避免 '.' > '-' 导致带后缀版本反排在前面）。
    """
    kb_dir = Path(artifacts_dir) / "kb"
    files = sorted(
        (p for p in kb_dir.glob("kb-*.sqlite") if p.is_file()),
        key=lambda p: p.stem,
    )
    if not files:
        raise KBError("没有知识库版本，请先运行 tu kb import")
    return files[-1]


def normalize_artifacts_dir(
    artifacts_dir: str | Path | None = None,
    *,
    config: dict[str, Any] | None = None,
) -> Path:
    """统一规范化 artifacts_dir：显式参数 > config['paths.artifacts'] > 'artifacts'。"""
    raw = (
        artifacts_dir
        if artifacts_dir is not None
        else get(config or {}, "paths.artifacts", "artifacts")
    )
    if not isinstance(raw, (str, Path)) or not str(raw).strip():
        return Path("artifacts")
    return Path(raw)


def resolve_kb_path(
    kb_version: str | None = None,
    *,
    config: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    artifacts_dir: str | Path | None = None,
) -> Path:
    """按优先级解析知识库路径：显式 kb_version > config['kb.version'] > 最新版本。

    同时支持从 config['paths.artifacts'] 回退产物目录（显式 artifacts_dir 优先）。
    目标版本文件不存在时抛 KBError，绝不静默创建 0 字节空库。
    """
    if config is not None:
        cfg = config
    elif config_path is not None:
        cfg = load_app_config(config_path)
    else:
        cfg = {}

    eff_artifacts = normalize_artifacts_dir(artifacts_dir, config=cfg)

    eff_version = kb_version if kb_version is not None else get(cfg, "kb.version")
    if eff_version is None:
        return latest_kb_path(eff_artifacts)

    valid_version = _validate_kb_version(eff_version)
    p = eff_artifacts / "kb" / f"{valid_version}.sqlite"
    if not p.is_file():
        raise KBError(f"知识库版本不存在：{valid_version}（未找到 {p}）")
    return p


def open_kb(
    path: str | Path,
    *,
    read_only: bool = False,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """打开已存在的 SQLite 知识库文件（或 :memory:）。

    文件不存在时抛 KBError，防止 sqlite3.connect 静默创建 0 字节空库。
    """
    if str(path) == ":memory:":
        return sqlite3.connect(":memory:", check_same_thread=check_same_thread)
    p = Path(path)
    if not p.is_file():
        raise KBError(f"知识库文件不存在：{p}")
    if read_only:
        try:
            return sqlite3.connect(
                f"{p.resolve().as_uri()}?mode=ro",
                uri=True,
                check_same_thread=check_same_thread,
            )
        except sqlite3.Error as e:
            raise KBError(f"无法只读打开知识库 {p}：{e}") from e
    return sqlite3.connect(p, check_same_thread=check_same_thread)


def open_kb_from_config(
    config_path: str | Path = DEFAULT_APP_CONFIG,
    *,
    kb_version: str | None = None,
    artifacts_dir: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
    read_only: bool = True,
    check_same_thread: bool = True,
) -> tuple[sqlite3.Connection, Path]:
    """按配置文件（及可选覆盖项）解析并打开指定版本的知识库，返回 (conn, kb_path)。"""
    cfg = load_app_config(config_path, overrides=overrides)
    kb_path = resolve_kb_path(
        kb_version,
        config=cfg,
        artifacts_dir=artifacts_dir,
    )
    conn = open_kb(kb_path, read_only=read_only, check_same_thread=check_same_thread)
    return conn, kb_path
