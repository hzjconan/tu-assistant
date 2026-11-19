"""合成样本自动检查（T030）。

对生成的训练样本做与出处校验层一致的检查：引用可解析、条款存在、
原文一致。不通过的样本丢弃并统计——不让坏样本进训练数据。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from ..citation.verify import VerifyResult, verify_output


@dataclass
class CheckStats:
    total: int = 0
    kept: int = 0
    dropped: int = 0
    reasons: dict[str, int] = field(default_factory=dict)

    def record_drop(self, reason: str) -> None:
        self.dropped += 1
        self.reasons[reason] = self.reasons.get(reason, 0) + 1


def check_sample(
    assistant_text: str,
    kb_conn: sqlite3.Connection,
    stats: CheckStats,
    *,
    require_citation: bool = False,
    expected_clause_ids: set[str] | None = None,
) -> bool:
    """检查一条合成样本的助手输出。返回是否保留。"""
    stats.total += 1
    result = verify_output(assistant_text, kb_conn)
    reason = citation_issue(
        result, require_citation=require_citation, expected_clause_ids=expected_clause_ids,
    )
    if reason:
        stats.record_drop(reason)
        return False
    stats.kept += 1
    return True


def citation_issue(
    result: VerifyResult, *, require_citation: bool, expected_clause_ids: set[str] | None,
) -> str | None:
    """按合成流水线口径判定已解析的原稿，供整条样本及逐篇校验共用。"""
    s = result.stats
    if s["not_found"]:
        return "citation_not_found"
    if s["corrected"]:
        # 原文写错的样本直接丢弃（训练数据应使用正确原文）
        return "citation_text_wrong"
    cited_ids = {c.resolved_clause_id for c in result.citations if c.resolved_clause_id}
    if require_citation and not cited_ids:
        return "citation_missing"
    if expected_clause_ids and not expected_clause_ids <= cited_ids:
        return "citation_mismatch"
    return None
