"""文档入库：读取 → 解析元数据 → 切分条款 → 校验 → 写入新知识库版本。

不打印任何文件名或条文内容；校验问题清单里只出现文件序号。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from ..manifest import write_manifest
from .models import DocumentMeta
from .parse import parse_clauses
from .readers import SUPPORTED_SUFFIXES, read_document
from .store import create_kb, doc_id_for, insert_clause, insert_document, new_kb_version, set_meta
from .validate import render_report, validate_clauses, validate_meta

RE_TITLE_BOOK = re.compile(r"《([^》]+)》")
RE_VERSION = re.compile(r"[（(]([^（）()]*(?:年|修正|修订|施行|试行|暂行)[^（）()]*)[)）]")
RE_DATE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")


def parse_doc_meta(filename: str, lines: list[str]) -> DocumentMeta:
    """从文件名与文件头推断元数据；识别不出的字段留空，交校验报告提示。"""
    stem = Path(filename).stem
    m = RE_TITLE_BOOK.search(stem)
    title = m.group(1) if m else ""
    vm = RE_VERSION.search(stem)
    version_label = vm.group(1) if vm else ""

    promulgated_on = None
    for line in lines[:5]:
        dm = RE_DATE.search(line)
        if dm:
            promulgated_on = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
            break
        if RE_TITLE_BOOK.search(line) and not title:
            title = RE_TITLE_BOOK.search(line).group(1)

    if not title:
        # 文件名里没有《》：先看文件首行是不是标题行（短、无结构标记、无句号），
        # 否则去掉括号版本部分，用文件名剩余部分当标题
        first = lines[0].strip() if lines else ""
        if (
            first
            and len(first) <= 40
            and "。" not in first
            and not first.startswith(("第", "（", "(", "一", "二", "三"))
        ):
            title = first
        else:
            title = RE_VERSION.sub("", stem).strip(" _-（）()")

    meta = DocumentMeta(
        title=title,
        version_label=version_label,
        promulgated_on=promulgated_on,
        source_file="",
    )
    meta.doc_id = doc_id_for(title, version_label)
    return meta


def _resolve_same_title_versions(
    parsed: list[tuple[DocumentMeta, list[str]]],
) -> dict[int, list[str]]:
    """同名文件按 promulgated_on 推断为同一文件的不同版本。

    最新日期 → current，其余 → amended；version_label 缺的用日期年份补。
    返回 {文件序号: [问题编号]}；日期缺失无法排序时记问题。
    """
    groups: dict[str, list[int]] = {}
    for i, (meta, _) in enumerate(parsed, start=1):
        if meta.title:
            groups.setdefault(meta.title, []).append(i)

    issues: dict[int, list[str]] = {}
    for _title, idxs in groups.items():
        if len(idxs) < 2:
            continue
        metas = [parsed[i - 1][0] for i in idxs]
        if any(m.promulgated_on is None for m in metas):
            # 无法按日期排序：按文件顺序兜底，最后一个当 current，记问题待人工核对
            for pos, i in enumerate(idxs):
                m = parsed[i - 1][0]
                m.status = "current" if pos == len(idxs) - 1 else "amended"
                if not m.version_label:
                    m.version_label = f"文件{pos + 1}"
                issues.setdefault(i, []).append("same_title_no_date")
            continue
        order = sorted(zip(idxs, metas, strict=True), key=lambda t: t[1].promulgated_on)
        for rank, (i, m) in enumerate(order):
            m.status = "current" if rank == len(order) - 1 else "amended"
            if not m.version_label:
                m.version_label = m.promulgated_on[:4]
            issues.setdefault(i, []).append("same_title_multi_version")
    return issues


def import_directory(
    input_dir: str | Path,
    artifacts_dir: str | Path = "artifacts",
) -> dict:
    """整批导入目录下全部文档，生成新知识库版本。

    返回汇总信息（不含文件名与条文内容）：
    ``{"kb_version": ..., "files": n, "clauses": n, "issues": n, "report": path}``
    """
    files = sorted(
        p for p in Path(input_dir).rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )
    kb_version = new_kb_version()
    kb_path = Path(artifacts_dir) / "kb" / f"{kb_version}.sqlite"
    conn = create_kb(kb_path)

    report_rows: list[dict] = []
    total_clauses = 0
    with conn:
        # 先解析全部元数据：同名文件按日期推断为不同版本
        parsed: list[tuple[DocumentMeta, list[str]]] = []
        for path in files:
            lines = read_document(path)
            meta = parse_doc_meta(path.name, lines)
            meta.source_file = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
            parsed.append((meta, lines))

        version_issues = _resolve_same_title_versions(parsed)

        for idx, (meta, lines) in enumerate(parsed, start=1):
            meta.doc_id = doc_id_for(meta.title, meta.version_label)
            clauses, warnings = parse_clauses(lines, meta.doc_id)
            issues = (
                warnings
                + version_issues.get(idx, [])
                + validate_meta(meta)
                + validate_clauses(clauses)
            )

            insert_document(conn, meta)
            for c in clauses:
                insert_clause(conn, c)
            total_clauses += len(clauses)
            report_rows.append(
                {"file_index": idx, "clause_count": len(clauses), "issues": issues}
            )
        set_meta(conn, "kb_version", kb_version)
        set_meta(conn, "file_count", str(len(files)))

    report_path = Path(artifacts_dir) / "kb" / f"{kb_version}-parse_report.md"
    report_path.write_text(render_report(report_rows), encoding="utf-8")
    write_manifest(
        Path(artifacts_dir) / "kb" / kb_version,
        artifact_id=kb_version,
        artifact_type="kb_version",
        inputs={"file_count": len(files), "sqlite": str(kb_path)},
        config={},
        extra={
            "clause_count": total_clauses,
            "issue_count": sum(len(r["issues"]) for r in report_rows),
        },
    )
    conn.close()
    return {
        "kb_version": kb_version,
        "files": len(files),
        "clauses": total_clauses,
        "issues": sum(len(r["issues"]) for r in report_rows),
        "report": str(report_path),
        "sqlite": str(kb_path),
    }
