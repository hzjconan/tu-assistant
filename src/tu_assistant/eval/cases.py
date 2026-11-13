"""评测用例格式与加载（T033，data-model.md §3 EvalCase）。

JSONL 每行一条::

    {"case_id": "...", "category": "clause_id|multi_violation|exception|
      refusal|false_refusal|intent|article",
     "input": {"message": "..."} 或 {"script": ["...", "..."]},
     "gold": {"clauses": ["doc:a1:p1"], "violations": [...], "intent": "consult",
              "should_refuse": true, "rubric": [...]},
     "source": "public_case|manual|synthetic_reviewed",
     "eval_set_version": "v1"}
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

CATEGORIES = {
    "clause_id", "multi_violation", "exception",
    "refusal", "false_refusal", "intent", "article",
}
SOURCES = {"public_case", "manual", "synthetic_reviewed"}


@dataclass
class EvalCase:
    case_id: str
    category: str
    input: dict
    gold: dict = field(default_factory=dict)
    source: str = "manual"
    eval_set_version: str = "v1"


def load_cases(path: str | Path) -> list[EvalCase]:
    """加载一个 JSONL 文件或目录下全部 .jsonl。"""
    p = Path(path)
    files = sorted(p.glob("*.jsonl")) if p.is_dir() else [p]
    cases = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            case = EvalCase(
                case_id=d["case_id"],
                category=d["category"],
                input=d["input"],
                gold=d.get("gold", {}),
                source=d.get("source", "manual"),
                eval_set_version=d.get("eval_set_version", "v1"),
            )
            _validate(case)
            cases.append(case)
    return cases


def _validate(case: EvalCase) -> None:
    if case.category not in CATEGORIES:
        raise ValueError(f"{case.case_id}: 未知 category {case.category}")
    if case.source not in SOURCES:
        raise ValueError(f"{case.case_id}: 未知 source {case.source}")
    if "message" not in case.input and "script" not in case.input:
        raise ValueError(f"{case.case_id}: input 需要 message 或 script")


def validate_gold_clauses(
    cases: list[EvalCase], kb_conn: sqlite3.Connection
) -> list[str]:
    """gold.clauses 中的条款必须存在于知识库；返回问题列表。"""
    from ..kb.store import get_clause_by_id

    issues = []
    for case in cases:
        for cid in case.gold.get("clauses", []):
            if get_clause_by_id(kb_conn, cid) is None:
                issues.append(f"{case.case_id}: gold 条款不存在 {cid}")
        for v in case.gold.get("violations", []):
            for cid in v.get("clauses", []) + v.get("liability", []):
                if get_clause_by_id(kb_conn, cid) is None:
                    issues.append(f"{case.case_id}: gold 条款不存在 {cid}")
    return issues


def eval_questions(cases: list[EvalCase]) -> list[str]:
    """取全部用例的问句（训练数据去重用）。"""
    qs = []
    for c in cases:
        if "message" in c.input:
            qs.append(c.input["message"])
        for turn in c.input.get("script", []):
            qs.append(turn)
    return qs
