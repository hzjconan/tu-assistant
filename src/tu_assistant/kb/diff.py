"""知识库版本差异比对（T066：tu kb diff <v1> <v2>）。

严格遵守以下设计约束：
1. 只读打开两个知识库（``mode=ro``），绝不创建空库或写入任何字节；
2. 默认对现行文档（``status='current'``）按逻辑键
   ``(title, article_no, paragraph_no, item_no)`` 对齐，使得同一法规修订升级
   ``version_label`` 时仍能逐条精准比对原文差异，不会误报“整部法规全删全增”；
3. 主清单严格三分法：``added``（新增）、``removed``（删除）、``modified``（原文变化，
   仅依据 ``Clause.text`` 逐字相等性判定）；
4. 顶部摘要补充文档级版本变化、``number_text`` 编号写法变化计数与已确认条款关联
   （``confirmed=1``）变化计数；
5. **全程只输出编号与变化类型，严禁在数据结构或输出文本中暴露任何条款正文（Clause.text）**。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .store import KBError, _validate_kb_version, open_kb

ClauseKey = tuple[str, int, int | None, int | None]

_REQUIRED_TABLES = ("legal_documents", "clauses", "clause_relations")


@dataclass(frozen=True)
class ClauseDiffItem:
    """单条条款差异记录（不含条款正文 text）。"""

    change_type: str  # "added" | "removed" | "modified"
    title: str
    article_no: int
    paragraph_no: int | None
    item_no: int | None
    number_text_v1: str | None = None
    number_text_v2: str | None = None
    clause_id_v1: str | None = None
    clause_id_v2: str | None = None
    version_label_v1: str | None = None
    version_label_v2: str | None = None

    @property
    def display_number(self) -> str:
        base = self.number_text_v2 or self.number_text_v1 or f"第{self.article_no}条"
        if self.item_no is not None and "项" not in base:
            return f"{base}第{self.item_no}项"
        return base


@dataclass(frozen=True)
class DocumentDiffSummary:
    """文档级变化汇总。"""

    v1_current_docs: int = 0
    v2_current_docs: int = 0
    v1_non_current_docs: int = 0
    v2_non_current_docs: int = 0
    added_docs: list[tuple[str, str]] = field(default_factory=list)
    removed_docs: list[tuple[str, str]] = field(default_factory=list)
    version_changed_docs: list[tuple[str, str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class RelationsDiffSummary:
    """已确认条款关联（confirmed=1）变化汇总。"""

    v1_confirmed: int = 0
    v2_confirmed: int = 0
    added_count: int = 0
    removed_count: int = 0
    unchanged_count: int = 0


@dataclass(frozen=True)
class KBDiffResult:
    """两个知识库版本的完整对比结果（不含任何条款正文）。"""

    v1_version: str
    v2_version: str
    v1_path: str
    v2_path: str
    v1_total_clauses: int
    v2_total_clauses: int
    added: list[ClauseDiffItem] = field(default_factory=list)
    removed: list[ClauseDiffItem] = field(default_factory=list)
    modified: list[ClauseDiffItem] = field(default_factory=list)
    unchanged_count: int = 0
    number_text_changed_count: int = 0
    doc_changes: DocumentDiffSummary = field(default_factory=DocumentDiffSummary)
    relations_diff: RelationsDiffSummary = field(default_factory=RelationsDiffSummary)

    @property
    def has_clause_changes(self) -> bool:
        return bool(self.added or self.removed or self.modified)


def resolve_diff_kb(
    ref: str | Path,
    artifacts_dir: str | Path = "artifacts",
) -> Path:
    """将版本号（如 kb-20261119-045641）或显式 .sqlite 路径解析为已存在文件。

    不存在时抛 KBError，绝不创建空文件。
    """
    if isinstance(ref, Path):
        if ref.is_file():
            return ref
        raise KBError(f"知识库文件不存在：{ref}")

    if not isinstance(ref, str) or not ref.strip():
        raise KBError(f"非法知识库引用：{ref!r}")

    candidate = Path(ref)
    if candidate.is_file():
        return candidate

    # 若包含路径分隔符或 .sqlite 后缀但文件不存在，直接报路径不存在
    if "/" in ref or "\\" in ref or ref.endswith(".sqlite"):
        raise KBError(f"知识库文件不存在：{candidate}")

    valid_ver = _validate_kb_version(ref)
    kb_path = Path(artifacts_dir) / "kb" / f"{valid_ver}.sqlite"
    if not kb_path.is_file():
        raise KBError(f"知识库版本不存在：{valid_ver}（未找到 {kb_path}）")
    return kb_path


def _check_kb_schema(conn: sqlite3.Connection, label: str) -> None:
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    except sqlite3.Error as e:
        raise KBError(f"知识库 {label} 无法读取表结构：{e}") from e
    tables = {r[0] for r in rows}
    missing = [t for t in _REQUIRED_TABLES if t not in tables]
    if missing:
        raise KBError(f"知识库 {label} 缺少必需表：{', '.join(missing)}")


def _kb_version_name(conn: sqlite3.Connection, path: Path) -> str:
    try:
        row = conn.execute(
            "SELECT value FROM kb_meta WHERE key='kb_version'"
        ).fetchone()
        if row and row[0]:
            return str(row[0])
    except sqlite3.Error:
        pass
    return path.stem


def _clause_sort_key(key: ClauseKey) -> tuple[str, int, int, int]:
    title, art, para, item = key
    return (title, art, para if para is not None else 0, item if item is not None else 0)


def _item_sort_key(item: ClauseDiffItem) -> tuple[str, int, int, int]:
    return (
        item.title,
        item.article_no,
        item.paragraph_no if item.paragraph_no is not None else 0,
        item.item_no if item.item_no is not None else 0,
    )


def _load_snapshot(conn: sqlite3.Connection) -> tuple[
    dict[str, str],
    int,
    dict[ClauseKey, tuple[str, str, str, str]],
    set[tuple[ClauseKey | str, ClauseKey | str, str]],
]:
    """只读读取单库快照。

    返回：
    - current_docs: {title: version_label}
    - non_current_count: 非 current 文档数
    - clauses_map: {ClauseKey: (clause_id, number_text, text, version_label)}
    - confirmed_relations: 基于逻辑条款键（若端点不在 current 则回退 clause_id）的已确认关系集合
    """
    docs_rows = conn.execute(
        "SELECT doc_id, title, version_label, status FROM legal_documents"
    ).fetchall()
    current_docs: dict[str, str] = {}
    non_current_count = 0
    for _doc_id, title, version_label, status in docs_rows:
        if status == "current":
            current_docs[title] = version_label or ""
        else:
            non_current_count += 1

    clause_rows = conn.execute(
        """SELECT c.clause_id, d.title, d.version_label, d.status,
                  c.article_no, c.paragraph_no, c.item_no, c.number_text, c.text
           FROM clauses c
           JOIN legal_documents d ON c.doc_id = d.doc_id"""
    ).fetchall()

    clauses_map: dict[ClauseKey, tuple[str, str, str, str]] = {}
    id_to_logical: dict[str, ClauseKey] = {}
    for cid, title, ver_label, status, art_no, para_no, item_no, num_text, text in clause_rows:
        key: ClauseKey = (title, int(art_no), para_no, item_no)
        if status == "current":
            clauses_map[key] = (cid, num_text, text, ver_label or "")
            id_to_logical[cid] = key

    rel_rows = conn.execute(
        """SELECT from_clause_id, to_clause_id, relation_type
           FROM clause_relations
           WHERE confirmed = 1"""
    ).fetchall()
    confirmed_rels: set[
        tuple[ClauseKey | str, ClauseKey | str, str]
    ] = set()
    for from_cid, to_cid, rel_type in rel_rows:
        f_ep: ClauseKey | str = id_to_logical.get(from_cid, from_cid)
        t_ep: ClauseKey | str = id_to_logical.get(to_cid, to_cid)
        confirmed_rels.add((f_ep, t_ep, rel_type))

    return current_docs, non_current_count, clauses_map, confirmed_rels


def diff_kbs(
    v1_ref: str | Path,
    v2_ref: str | Path,
    *,
    artifacts_dir: str | Path = "artifacts",
) -> KBDiffResult:
    """只读对比两个知识库版本，返回 KBDiffResult（不含任何条文正文）。"""
    p1 = resolve_diff_kb(v1_ref, artifacts_dir=artifacts_dir)
    p2 = resolve_diff_kb(v2_ref, artifacts_dir=artifacts_dir)

    conn1 = open_kb(p1, read_only=True)
    try:
        conn2 = open_kb(p2, read_only=True)
    except Exception:
        conn1.close()
        raise

    try:
        _check_kb_schema(conn1, str(p1))
        _check_kb_schema(conn2, str(p2))

        ver1 = _kb_version_name(conn1, p1)
        ver2 = _kb_version_name(conn2, p2)

        try:
            docs1, non_cur1, clauses1, rels1 = _load_snapshot(conn1)
            docs2, non_cur2, clauses2, rels2 = _load_snapshot(conn2)
        except sqlite3.Error as e:
            raise KBError(f"读取知识库快照失败：{e}") from e
    finally:
        conn1.close()
        conn2.close()

    # 1. 文档级差异
    titles1 = set(docs1.keys())
    titles2 = set(docs2.keys())
    added_docs = sorted((t, docs2[t]) for t in (titles2 - titles1))
    removed_docs = sorted((t, docs1[t]) for t in (titles1 - titles2))
    version_changed_docs = sorted(
        (t, docs1[t], docs2[t])
        for t in (titles1 & titles2)
        if docs1[t] != docs2[t]
    )
    doc_summary = DocumentDiffSummary(
        v1_current_docs=len(docs1),
        v2_current_docs=len(docs2),
        v1_non_current_docs=non_cur1,
        v2_non_current_docs=non_cur2,
        added_docs=added_docs,
        removed_docs=removed_docs,
        version_changed_docs=version_changed_docs,
    )

    # 2. 条款级差异（仅按 text 判定 modified；数据结构不存 text）
    keys1 = set(clauses1.keys())
    keys2 = set(clauses2.keys())

    added_items: list[ClauseDiffItem] = []
    for k in sorted(keys2 - keys1, key=_clause_sort_key):
        cid2, nt2, _text2, vlabel2 = clauses2[k]
        added_items.append(
            ClauseDiffItem(
                change_type="added",
                title=k[0],
                article_no=k[1],
                paragraph_no=k[2],
                item_no=k[3],
                number_text_v2=nt2,
                clause_id_v2=cid2,
                version_label_v2=vlabel2,
            )
        )

    removed_items: list[ClauseDiffItem] = []
    for k in sorted(keys1 - keys2, key=_clause_sort_key):
        cid1, nt1, _text1, vlabel1 = clauses1[k]
        removed_items.append(
            ClauseDiffItem(
                change_type="removed",
                title=k[0],
                article_no=k[1],
                paragraph_no=k[2],
                item_no=k[3],
                number_text_v1=nt1,
                clause_id_v1=cid1,
                version_label_v1=vlabel1,
            )
        )

    modified_items: list[ClauseDiffItem] = []
    unchanged_count = 0
    number_text_changed_count = 0
    for k in sorted(keys1 & keys2, key=_clause_sort_key):
        cid1, nt1, text1, vlabel1 = clauses1[k]
        cid2, nt2, text2, vlabel2 = clauses2[k]
        if text1 != text2:
            modified_items.append(
                ClauseDiffItem(
                    change_type="modified",
                    title=k[0],
                    article_no=k[1],
                    paragraph_no=k[2],
                    item_no=k[3],
                    number_text_v1=nt1,
                    number_text_v2=nt2,
                    clause_id_v1=cid1,
                    clause_id_v2=cid2,
                    version_label_v1=vlabel1,
                    version_label_v2=vlabel2,
                )
            )
        else:
            unchanged_count += 1
            if nt1 != nt2:
                number_text_changed_count += 1

    # 3. 已确认条款关联差异
    rel_added = len(rels2 - rels1)
    rel_removed = len(rels1 - rels2)
    rel_unchanged = len(rels1 & rels2)
    rel_summary = RelationsDiffSummary(
        v1_confirmed=len(rels1),
        v2_confirmed=len(rels2),
        added_count=rel_added,
        removed_count=rel_removed,
        unchanged_count=rel_unchanged,
    )

    return KBDiffResult(
        v1_version=ver1,
        v2_version=ver2,
        v1_path=str(p1),
        v2_path=str(p2),
        v1_total_clauses=len(clauses1),
        v2_total_clauses=len(clauses2),
        added=added_items,
        removed=removed_items,
        modified=modified_items,
        unchanged_count=unchanged_count,
        number_text_changed_count=number_text_changed_count,
        doc_changes=doc_summary,
        relations_diff=rel_summary,
    )


def _format_clause_line(item: ClauseDiffItem) -> str:
    tag_map = {
        "added": "[+ 新增]",
        "removed": "[- 删除]",
        "modified": "[~ 原文变化]",
    }
    tag = tag_map.get(item.change_type, f"[{item.change_type}]")
    if item.change_type == "added":
        v_str = f"（{item.version_label_v2}）" if item.version_label_v2 else ""
        cid_str = f"clause_id={item.clause_id_v2}"
    elif item.change_type == "removed":
        v_str = f"（{item.version_label_v1}）" if item.version_label_v1 else ""
        cid_str = f"clause_id={item.clause_id_v1}"
    else:
        if item.version_label_v1 != item.version_label_v2:
            v1_l = item.version_label_v1 or "无版本"
            v2_l = item.version_label_v2 or "无版本"
            v_str = f"（{v1_l} -> {v2_l}）"
        elif item.version_label_v2:
            v_str = f"（{item.version_label_v2}）"
        else:
            v_str = ""
        if item.clause_id_v1 == item.clause_id_v2:
            cid_str = f"clause_id={item.clause_id_v2}"
        else:
            cid_str = f"clause_id={item.clause_id_v1}->{item.clause_id_v2}"
    return f"  {tag} 《{item.title}》{v_str}{item.display_number} ({cid_str})"


def render_diff(result: KBDiffResult, *, summary_only: bool = False) -> str:
    """渲染知识库版本差异文本报告（只输出编号与变化类型，绝不含条款原文）。"""
    dc = result.doc_changes
    rd = result.relations_diff
    lines: list[str] = [
        f"知识库版本对比：{result.v1_version} -> {result.v2_version}",
        (
            f"现行文件：{dc.v1_current_docs} 篇 -> {dc.v2_current_docs} 篇  |  "
            f"现行条款：{result.v1_total_clauses} 条 -> {result.v2_total_clauses} 条"
        ),
        (
            f"条款变化汇总：新增 {len(result.added)} 条 / "
            f"删除 {len(result.removed)} 条 / "
            f"原文变化 {len(result.modified)} 条 / "
            f"原文未变 {result.unchanged_count} 条"
        ),
    ]

    if dc.v1_non_current_docs or dc.v2_non_current_docs:
        lines.append(
            f"非现行版本文件（未纳入现行条款对比）："
            f"{dc.v1_non_current_docs} 篇 -> {dc.v2_non_current_docs} 篇"
        )

    if dc.added_docs or dc.removed_docs or dc.version_changed_docs:
        lines.append("文件级变化：")
        for title, ver in dc.added_docs:
            v_s = f"（{ver}）" if ver else ""
            lines.append(f"  [+ 新增文件] 《{title}》{v_s}")
        for title, ver in dc.removed_docs:
            v_s = f"（{ver}）" if ver else ""
            lines.append(f"  [- 删除文件] 《{title}》{v_s}")
        for title, ver1, ver2 in dc.version_changed_docs:
            lines.append(
                f"  [~ 版本更新] 《{title}》（{ver1 or '无版本'} -> {ver2 or '无版本'}）"
            )

    if result.number_text_changed_count > 0:
        lines.append(
            f"编号写法变化（原文未变）：{result.number_text_changed_count} 条"
        )

    if (
        rd.v1_confirmed > 0
        or rd.v2_confirmed > 0
        or rd.added_count > 0
        or rd.removed_count > 0
    ):
        lines.append(
            f"已确认条款关联：{rd.v1_confirmed} 条 -> {rd.v2_confirmed} 条"
            f"（+{rd.added_count} / -{rd.removed_count}，保留 {rd.unchanged_count}）"
        )

    if summary_only:
        return "\n".join(lines) + "\n"

    all_items = sorted(
        [*result.added, *result.removed, *result.modified],
        key=lambda it: (
            _item_sort_key(it),
            {"removed": 0, "modified": 1, "added": 2}.get(it.change_type, 3),
        ),
    )
    if not all_items:
        lines.append("条款明细：无新增、删除或原文变化的条款。")
    else:
        lines.append(f"条款变更明细（共 {len(all_items)} 条，仅列编号与变化类型）：")
        for item in all_items:
            lines.append(_format_clause_line(item))

    return "\n".join(lines) + "\n"
