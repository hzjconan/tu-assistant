"""入库校验：编号连续性缺口、重复、空条款、元数据缺失（FR-005）。

产出的问题清单只含文件序号与问题编号，不含任何条文内容或文件名，
以便在不暴露文档内容的前提下供人工核对（AGENTS.md 约定）。
"""

from __future__ import annotations

from .models import Clause, DocumentMeta


def validate_clauses(clauses: list[Clause]) -> list[str]:
    """返回问题编号列表，如 ["gap_article:5", "empty_clause:a3:p2"]。"""
    issues: list[str] = []
    articles = sorted({c.article_no for c in clauses})
    if articles:
        missing = sorted(set(range(articles[0], articles[-1] + 1)) - set(articles))
        for n in missing:
            issues.append(f"gap_article:{n}")
    seen: set[tuple] = set()
    for c in clauses:
        key = (c.article_no, c.paragraph_no, c.item_no)
        if key in seen:
            issues.append(f"duplicate_clause:{c.clause_id}")
        seen.add(key)
        if not c.text.strip():
            issues.append(f"empty_clause:{c.clause_id}")
        issues.extend(c.parse_warnings)
    return issues


def validate_meta(meta: DocumentMeta) -> list[str]:
    """元数据缺失检查（FR-002）。"""
    issues: list[str] = []
    if not meta.title:
        issues.append("missing_title")
    if not meta.version_label:
        issues.append("missing_version_label")
    if not meta.promulgated_on:
        issues.append("missing_promulgated_on")
    return issues


def render_report(rows: list[dict]) -> str:
    """生成 parse_report.md（只含文件序号、条款数、问题编号）。"""
    lines = [
        "# 入库校验报告",
        "",
        "文件序号为 `inputs/` 目录按字典序排列的序号（从 1 开始）；"
        "问题编号说明见文末。",
        "",
        "| 文件序号 | 条款数 | 问题 |",
        "|---|---|---|",
    ]
    for r in rows:
        issues = "、".join(r["issues"]) if r["issues"] else "—"
        lines.append(f"| {r['file_index']} | {r['clause_count']} | {issues} |")
    lines += [
        "",
        "## 问题编号说明",
        "",
        "- `gap_article:N`：条号不连续，缺第 N 条（可能原文如此，也可能切分漏条）",
        "- `duplicate_clause:<id>` / `duplicate_article:N`：编号重复",
        "- `empty_clause:<id>`：条款正文为空",
        "- `unparseable_article_number:…`：条号无法解析",
        "- `missing_title` / `missing_version_label` / `missing_promulgated_on`："
        "文件元数据缺失，需人工补充",
        "- `no_clause_structure`：未找到条款结构（既不是“第X条”也不是“一、二、”分段）",
        "- `same_title_multi_version`：同名文件按日期推断为不同版本（最新为 current），需人工核对",
        "- `same_title_no_date`：同名文件缺日期无法排序，按文件顺序兜底并记问题，需人工核对",
    ]
    return "\n".join(lines) + "\n"
