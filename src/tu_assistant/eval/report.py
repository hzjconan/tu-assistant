"""评测报告生成与人工评审汇总（T061 + T063）。

职责：
- 提供确定性、纯函数的单次评测聚合接口 `summarize_run`（供 `render_report`
  与后续 T062 `eval/compare.py` 复用）；
- 解析、校验并汇总人工评审 CSV（`eval/review-template.csv`，FR-037）；
- 抽取确定性失败用例清单与待评审普法文章清单；
- 渲染覆盖 SC-001 ~ SC-011、POC 目标值对照与校验前/后两列表的 Markdown 报告；
- 提供只读读取历史 run 生成报告的 `render_run_report`（不改写历史产物）。
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .metrics import detect_refusal, extract_articles

REQUIRED_REVIEW_COLUMNS: tuple[str, ...] = (
    "run_id",
    "case_id",
    "reviewer",
    "verdict",
    "comment",
    "created_at",
)
VALID_VERDICTS: tuple[str, ...] = ("pass", "minor_issue", "fail")
VALID_DIMENSIONS: tuple[str, ...] = ("correctness", "diversity", "other")

POC_TARGETS: dict[str, str] = {
    "SC-001": "≥90%（3 轮内）",
    "SC-002": "≥90%",
    "SC-003": "≥85%",
    "SC-004": "≥85%",
    "SC-005": "≥90%",
    "SC-006": "100%",
    "SC-007": "100%",
    "SC-008": "范围外 ≥95%；误拒 ≤5%",
    "SC-009": "≥90%",
    "SC-010": "实质重复率 ≤10%",
    "SC-011": "100%",
}


class ReportError(ValueError):
    """评测报告生成或人工评审 CSV 校验失败（确定性输入错误）。"""


@dataclass(frozen=True)
class ReviewEntry:
    run_id: str
    case_id: str
    reviewer: str
    verdict: str
    comment: str
    created_at: str
    dimension: str
    line_no: int = 0


def _expected_refusal(category: str, gold: dict) -> bool:
    if category in {"refusal", "false_refusal"}:
        return gold.get("should_refuse", category == "refusal")
    return gold.get("should_refuse") is True


def _is_multi_article_case(case_row: dict) -> bool:
    gold = case_row.get("gold") or {}
    exp = gold.get("expect_articles")
    if isinstance(exp, int):
        return exp >= 2
    if isinstance(exp, list):
        return any(isinstance(x, int) and x >= 2 for x in exp)
    return False


def _required_dimensions(case_row: dict) -> tuple[str, ...]:
    if case_row.get("category") != "article":
        return ()
    if _expected_refusal("article", case_row.get("gold") or {}):
        return ("other",)
    if _is_multi_article_case(case_row):
        return ("correctness", "diversity")
    return ("correctness",)


def _resolve_refusal_flag(row: dict) -> tuple[bool, bool]:
    """返回 (refused, recomputed)。兼容不含 refusal_evidence 的历史 results.jsonl。"""
    scores = row.get("scores") or {}
    ev = scores.get("refusal_evidence")
    if isinstance(ev, dict) and isinstance(ev.get("refused"), bool):
        return ev["refused"], False
    detection = detect_refusal(row.get("final_text") or "")
    return bool(detection["refused"]), True


def _resolve_refusal_correct(row: dict) -> bool:
    """与 `_resolve_refusal_flag` 同源，避免历史 run 中旧 refusal_correct 与复算结果冲突。"""
    refused, _ = _resolve_refusal_flag(row)
    expected = _expected_refusal(row.get("category", ""), row.get("gold") or {})
    return refused == expected


def _parse_iso_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _is_newer_review(entry: ReviewEntry, prev: ReviewEntry) -> bool:
    """比较同键两条评审记录谁更新：优先按可比 ISO 时间戳，否则按物理行号靠后者胜出。"""
    dt_entry = _parse_iso_timestamp(entry.created_at)
    dt_prev = _parse_iso_timestamp(prev.created_at)
    if dt_entry is not None and dt_prev is not None:
        entry_aware = dt_entry.tzinfo is not None
        prev_aware = dt_prev.tzinfo is not None
        if entry_aware == prev_aware:
            if entry_aware:
                dt_entry = dt_entry.astimezone(UTC)
                dt_prev = dt_prev.astimezone(UTC)
            if dt_entry != dt_prev:
                return dt_entry > dt_prev
    return entry.line_no >= prev.line_no


def load_reviews(
    csv_path: str | Path,
    *,
    run_id: str,
    results: list[dict],
) -> list[ReviewEntry]:
    """读取并确定性校验人工评审 CSV，返回归属 `run_id` 且去重后的评审列表。"""
    path = Path(csv_path)
    if not path.exists():
        raise ReportError(f"人工评审文件不存在：{path}")
    if not path.is_file():
        raise ReportError(f"人工评审路径不是文件：{path}")

    try:
        raw_text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReportError(f"无法以 UTF-8 读取人工评审文件 {path}：{exc}") from exc

    if not raw_text.strip():
        raise ReportError(f"人工评审文件为空，缺少表头：{path}")

    case_by_id = {r["case_id"]: r for r in results}
    dedup: dict[tuple[str, str, str, str], ReviewEntry] = {}
    try:
        reader = csv.DictReader(io.StringIO(raw_text, newline=""))
        fieldnames = [f.strip() for f in (reader.fieldnames or []) if f is not None]
        if len(fieldnames) != len(set(fieldnames)):
            seen: set[str] = set()
            dups = sorted({f for f in fieldnames if f in seen or seen.add(f)})
            raise ReportError(
                f"人工评审 CSV 表头存在重复列名：{', '.join(dups)}（文件：{path}）"
            )
        missing = [col for col in REQUIRED_REVIEW_COLUMNS if col not in fieldnames]
        if missing:
            raise ReportError(
                f"人工评审 CSV 缺少必需列：{', '.join(missing)}（文件：{path}）"
            )
        has_dimension_col = "dimension" in fieldnames

        for raw_row in reader:
            line_no = reader.line_num
            extra_cols = raw_row.get(None)
            # 跳过整行全空的尾行或分隔行
            has_named_value = any(
                isinstance(v, str) and v.strip()
                for k, v in raw_row.items()
                if k is not None
            )
            if not has_named_value and not extra_cols:
                continue

            row = {
                (k.strip() if isinstance(k, str) else k): (
                    v.strip() if isinstance(v, str) else ""
                )
                for k, v in raw_row.items()
                if k is not None
            }
            row_run_id = row.get("run_id", "")
            if not row_run_id:
                raise ReportError(f"第 {line_no} 行：run_id 不能为空")
            if row_run_id != run_id:
                continue

            if extra_cols:
                raise ReportError(
                    f"第 {line_no} 行：列数超出表头（多余 {len(extra_cols)} 列），"
                    "请检查 comment 等字段中的逗号是否已用双引号包裹"
                )

            case_id = row.get("case_id", "")
            if not case_id or case_id not in case_by_id:
                raise ReportError(
                    f"第 {line_no} 行：case_id={case_id!r} 不在 {run_id} 的评测结果中"
                )

            reviewer = row.get("reviewer", "")
            if not reviewer:
                raise ReportError(f"第 {line_no} 行：reviewer 不能为空")

            verdict = row.get("verdict", "").lower()
            if verdict not in VALID_VERDICTS:
                raise ReportError(
                    f"第 {line_no} 行：verdict={row.get('verdict', '')!r} 非法，"
                    "必须为 pass / minor_issue / fail"
                )

            comment = row.get("comment", "")
            created_at = row.get("created_at", "")

            case_row = case_by_id[case_id]
            is_article = case_row.get("category") == "article"
            is_refusal = _expected_refusal(
                case_row.get("category", ""), case_row.get("gold") or {}
            )

            default_dim = "correctness" if (is_article and not is_refusal) else "other"
            if has_dimension_col:
                raw_dim = row.get("dimension", "").lower()
                if not raw_dim:
                    dimension = default_dim
                elif raw_dim in VALID_DIMENSIONS:
                    dimension = raw_dim
                else:
                    raise ReportError(
                        f"第 {line_no} 行：dimension={row.get('dimension', '')!r} 非法，"
                        "必须为 correctness / diversity / other 或留空"
                    )
            else:
                dimension = default_dim

            if dimension in {"correctness", "diversity"}:
                if not is_article:
                    raise ReportError(
                        f"第 {line_no} 行：case_id={case_id} 不是普法文章用例"
                        f"（category={case_row.get('category')}），不能标注 dimension={dimension}"
                    )
                if is_refusal:
                    raise ReportError(
                        f"第 {line_no} 行：case_id={case_id} 为应拒答题（should_refuse=true），"
                        f"不能标注 dimension={dimension}（请使用 other 或留空）"
                    )
                if dimension == "diversity" and not _is_multi_article_case(case_row):
                    raise ReportError(
                        f"第 {line_no} 行：case_id={case_id} 不是多篇生成题，"
                        "不能标注 dimension=diversity"
                    )

            entry = ReviewEntry(
                run_id=row_run_id,
                case_id=case_id,
                reviewer=reviewer,
                verdict=verdict,
                comment=comment,
                created_at=created_at,
                dimension=dimension,
                line_no=line_no,
            )
            key = (entry.run_id, entry.case_id, entry.dimension, entry.reviewer)
            prev = dedup.get(key)
            if prev is None or _is_newer_review(entry, prev):
                dedup[key] = entry
    except csv.Error as exc:
        raise ReportError(f"人工评审 CSV 格式错误（{path}）：{exc}") from exc

    return sorted(
        dedup.values(),
        key=lambda e: (e.case_id, e.dimension, e.reviewer),
    )


def aggregate_reviews(
    results: list[dict],
    reviews: list[ReviewEntry] | None,
) -> dict:
    """按 SC-009（correctness）与 SC-010（diversity）汇总人工评审结果。"""
    eligible_sc009 = {
        r["case_id"]
        for r in results
        if r.get("category") == "article"
        and not _expected_refusal("article", r.get("gold") or {})
    }
    eligible_sc010 = {
        r["case_id"]
        for r in results
        if r.get("category") == "article"
        and not _expected_refusal("article", r.get("gold") or {})
        and _is_multi_article_case(r)
    }

    def _agg_dim(dim: str, eligible: set[str], numerator_verdict: str) -> dict:
        if reviews is None:
            return {
                "status": "missing_file",
                "value": None,
                "counts": {"pass": 0, "minor_issue": 0, "fail": 0},
                "total": 0,
                "covered_cases": 0,
                "eligible_cases": len(eligible),
            }
        matched = [e for e in reviews if e.dimension == dim]
        counts = {v: 0 for v in VALID_VERDICTS}
        for e in matched:
            counts[e.verdict] += 1
        total = len(matched)
        covered = len({e.case_id for e in matched})
        if total == 0:
            return {
                "status": "no_rows",
                "value": None,
                "counts": counts,
                "total": 0,
                "covered_cases": 0,
                "eligible_cases": len(eligible),
            }
        return {
            "status": "scored",
            "value": counts[numerator_verdict] / total,
            "counts": counts,
            "total": total,
            "covered_cases": covered,
            "eligible_cases": len(eligible),
        }

    return {
        "sc009": _agg_dim("correctness", eligible_sc009, "pass"),
        "sc010": _agg_dim("diversity", eligible_sc010, "fail"),
    }


def extract_failures(
    results: list[dict],
    *,
    reviews: list[ReviewEntry] | None = None,
) -> list[dict]:
    """按确定性条件抽取逐条失败用例清单（按 case_id 升序）。"""
    fail_reviews_by_case: dict[str, list[ReviewEntry]] = {}
    for entry in reviews or []:
        if entry.verdict == "fail":
            fail_reviews_by_case.setdefault(entry.case_id, []).append(entry)

    failures: list[dict] = []
    for row in sorted(results, key=lambda r: r.get("case_id", "")):
        case_id = row.get("case_id", "")
        category = row.get("category", "")
        scores = row.get("scores") or {}
        gold = row.get("gold") or {}
        reasons: list[str] = []

        recall = scores.get("recall")
        if recall is not None and recall < 1.0:
            reasons.append(f"条款未全部命中（recall={recall:.3f}）")

        precision = scores.get("precision")
        if precision is not None and precision < 1.0:
            reasons.append(f"存在非标准引用（precision={precision:.3f}）")

        acc_counts = (scores.get("citation_acc") or {}).get("counts") or {}
        not_found = int(acc_counts.get("not_found", 0))
        incomplete = int(acc_counts.get("incomplete", 0))
        cit_complete = int(scores.get("citation_complete", 0))
        cit_total = int(scores.get("citation_total", 0))
        cit_issues: list[str] = []
        if not_found > 0:
            cit_issues.append(f"not_found={not_found}")
        if incomplete > 0:
            cit_issues.append(f"incomplete={incomplete}")
        if cit_complete < cit_total:
            cit_issues.append(f"未标明出处={cit_total - cit_complete}")
        if cit_issues:
            reasons.append(f"引用校验异常（{', '.join(cit_issues)}）")

        if not _resolve_refusal_correct(row):
            if _expected_refusal(category, gold):
                reasons.append("范围外未拒答")
            else:
                reasons.append("范围内误拒")

        rel = scores.get("relation_completion")
        if rel is not None and rel < 1.0:
            reasons.append(f"关联条款未全补（{rel:.3f}）")

        mv = scores.get("multi_violation")
        if category == "multi_violation" and mv is not None and mv < 1.0:
            reasons.append(f"多违法行为未全识别（{mv:.3f}）")

        intent = scores.get("intent")
        if category == "intent" and intent is not None and intent < 1.0:
            reasons.append("意图未在 3 轮内确认")

        ac = scores.get("article_count") or {}
        if ac.get("ok") is False:
            reasons.append(
                f"文章篇数不符（期望={ac.get('expected')}，实得={ac.get('per_turn')}）"
            )

        ic = scores.get("identity_check") or {}
        if "passed" in ic and ic.get("total", 0) > 0 and ic["passed"] < ic["total"]:
            reasons.append(f"文章身份信息泄露（{ic['passed']}/{ic['total']}）")
        unparsed_leaks = ic.get("unparsed_leaks") or []
        if unparsed_leaks:
            reasons.append(f"未拆篇轮次含保护名称（{len(unparsed_leaks)} 轮）")

        blocked_turn_nums = [
            idx
            for idx, turn in enumerate(row.get("turns") or [], 1)
            if (turn.get("anonymize") or {}).get("blocked")
        ]
        if blocked_turn_nums:
            turn_str = "、".join(f"第{n}轮" for n in blocked_turn_nums)
            reasons.append(f"引用冲突暂缓交稿（{turn_str}）")

        for fe in fail_reviews_by_case.get(case_id, []):
            reasons.append(f"人工评审未通过（{fe.dimension}/{fe.reviewer}）")

        if reasons:
            failures.append(
                {
                    "case_id": case_id,
                    "category": category,
                    "reasons": reasons,
                }
            )
    return failures


def extract_pending_articles(
    results: list[dict],
    *,
    run_id: str,
    reviews: list[ReviewEntry] | None = None,
) -> list[dict]:
    """按 case_id 升序抽取全部普法文章用例及其待评审/已评状态（T063）。"""
    reviews_by_case: dict[str, list[ReviewEntry]] = {}
    for entry in reviews or []:
        reviews_by_case.setdefault(entry.case_id, []).append(entry)

    dim_labels = {
        "correctness": "correctness",
        "diversity": "diversity",
        "other": "拒答复核（other）",
    }

    items: list[dict] = []
    article_rows = [r for r in results if r.get("category") == "article"]
    for row in sorted(article_rows, key=lambda r: r.get("case_id", "")):
        case_id = row.get("case_id", "")
        gold = row.get("gold") or {}
        scores = row.get("scores") or {}
        turns = row.get("turns") or []
        ac = scores.get("article_count") or {}
        if "per_turn" in ac:
            actual_per_turn = list(ac["per_turn"])
        else:
            actual_per_turn = [
                len(extract_articles(t.get("content") or "")) for t in turns
            ]
        expected = gold.get("expect_articles")
        is_refusal = _expected_refusal("article", gold)
        req_dims = _required_dimensions(row)
        case_reviews = reviews_by_case.get(case_id, [])

        if reviews is None or not case_reviews:
            status = (
                "待评审（实得 0 篇）"
                if (not is_refusal and sum(actual_per_turn) == 0)
                else "待评审"
            )
        else:
            by_dim: dict[str, list[ReviewEntry]] = {}
            for e in case_reviews:
                by_dim.setdefault(e.dimension, []).append(e)
            parts: list[str] = []
            all_done = True
            for d in req_dims:
                entries = by_dim.get(d, [])
                if not entries:
                    all_done = False
                    parts.append(f"{dim_labels[d]} 待评审")
                else:
                    verdicts = "/".join(e.verdict for e in entries)
                    parts.append(f"{dim_labels[d]}: {verdicts}")
            status = (
                f"已评（{'；'.join(parts)}）"
                if all_done
                else "；".join(parts)
            )

        items.append(
            {
                "run_id": run_id,
                "case_id": case_id,
                "turns_count": len(turns),
                "actual_per_turn": actual_per_turn,
                "expected_articles": expected,
                "required_dimensions": list(req_dims),
                "status": status,
                "rubric": list(gold.get("rubric") or []),
            }
        )
    return items


def summarize_run(
    results: list[dict],
    *,
    reviews: list[ReviewEntry] | None = None,
    run_id: str | None = None,
    _failures: list[dict] | None = None,
) -> dict:
    """单次评测统一指标聚合函数（SC-001 ~ SC-011，供 report 与 compare 复用）。"""
    failures = (
        _failures if _failures is not None else extract_failures(results, reviews=reviews)
    )
    failed_ids = {f["case_id"] for f in failures}

    by_category: dict[str, dict[str, int]] = {}
    for row in results:
        cat = row.get("category", "")
        entry = by_category.setdefault(cat, {"total": 0, "failed": 0})
        entry["total"] += 1
        if row.get("case_id", "") in failed_ids:
            entry["failed"] += 1

    # SC-001 ~ SC-005
    intent_vals = [
        r["scores"]["intent"]
        for r in results
        if r.get("category") == "intent"
        and (r.get("scores") or {}).get("intent") is not None
    ]
    recall_vals = [
        r["scores"]["recall"]
        for r in results
        if (r.get("scores") or {}).get("recall") is not None
    ]
    precision_vals = [
        r["scores"]["precision"]
        for r in results
        if (r.get("scores") or {}).get("precision") is not None
    ]
    mv_vals = [
        r["scores"]["multi_violation"]
        for r in results
        if r.get("category") == "multi_violation"
        and (r.get("scores") or {}).get("multi_violation") is not None
    ]
    rel_vals = [
        r["scores"]["relation_completion"]
        for r in results
        if (r.get("scores") or {}).get("relation_completion") is not None
    ]

    # SC-006
    cit_complete = sum(int((r.get("scores") or {}).get("citation_complete", 0)) for r in results)
    cit_total = sum(int((r.get("scores") or {}).get("citation_total", 0)) for r in results)

    # SC-007
    acc_counts = {"ok": 0, "corrected": 0, "not_found": 0, "incomplete": 0}
    for r in results:
        counts = ((r.get("scores") or {}).get("citation_acc") or {}).get("counts") or {}
        for k in acc_counts:
            acc_counts[k] += int(counts.get(k, 0))
    acc_total = sum(acc_counts.values())
    resolved_total = acc_counts["ok"] + acc_counts["corrected"] + acc_counts["not_found"]

    # SC-008
    outside: list[bool] = []
    regular: list[bool] = []
    special: list[bool] = []
    recomputed_count = 0
    for r in results:
        refused, recomputed = _resolve_refusal_flag(r)
        if recomputed:
            recomputed_count += 1
        cat = r.get("category", "")
        gold = r.get("gold") or {}
        if _expected_refusal(cat, gold):
            outside.append(refused)
        elif cat == "false_refusal":
            special.append(refused)
        else:
            regular.append(refused)
    in_scope = regular + special

    # SC-009 / SC-010
    rev_agg = aggregate_reviews(results, reviews)

    # SC-011 & auxiliary
    id_pass = id_total = id_cases = id_eval_cases = unparsed_rounds = 0
    ac_ok = ac_n = 0
    blocked_turns: list[tuple[str, int]] = []
    for r in results:
        scores = r.get("scores") or {}
        ic = scores.get("identity_check") or {}
        if "passed" in ic:
            id_cases += 1
            unparsed_rounds += len(ic.get("unparsed_leaks") or [])
            if ic.get("total"):
                id_eval_cases += 1
                id_pass += int(ic["passed"])
                id_total += int(ic["total"])
        ac = scores.get("article_count") or {}
        if "ok" in ac:
            ac_n += 1
            ac_ok += 1 if ac["ok"] else 0
        for idx, t in enumerate(r.get("turns") or [], 1):
            if (t.get("anonymize") or {}).get("blocked"):
                blocked_turns.append((r.get("case_id", ""), idx))

    return {
        "run_id": run_id,
        "case_count": len(results),
        "by_category": dict(sorted(by_category.items())),
        "sc001": {
            "value": sum(intent_vals) / len(intent_vals) if intent_vals else None,
            "hits": sum(1 for v in intent_vals if v >= 1.0),
            "total": len(intent_vals),
        },
        "sc002": {
            "value": sum(recall_vals) / len(recall_vals) if recall_vals else None,
            "n": len(recall_vals),
        },
        "sc003": {
            "value": sum(precision_vals) / len(precision_vals) if precision_vals else None,
            "n": len(precision_vals),
        },
        "sc004": {
            "value": sum(mv_vals) / len(mv_vals) if mv_vals else None,
            "n": len(mv_vals),
        },
        "sc005": {
            "value": sum(rel_vals) / len(rel_vals) if rel_vals else None,
            "n": len(rel_vals),
        },
        "sc006": {
            "value": cit_complete / cit_total if cit_total else None,
            "complete": cit_complete,
            "total": cit_total,
        },
        "sc007": {
            "pre": acc_counts["ok"] / acc_total if acc_total else None,
            "post": (acc_counts["ok"] + acc_counts["corrected"]) / acc_total
            if acc_total
            else None,
            "total": acc_total,
            "resolved_pre": acc_counts["ok"] / resolved_total if resolved_total else None,
            "resolved_post": (acc_counts["ok"] + acc_counts["corrected"]) / resolved_total
            if resolved_total
            else None,
            "resolved_total": resolved_total,
            "counts": acc_counts,
        },
        "sc008": {
            "outside_rate": sum(outside) / len(outside) if outside else None,
            "outside_hits": sum(outside),
            "outside_total": len(outside),
            "false_refusal_rate": sum(in_scope) / len(in_scope) if in_scope else None,
            "false_refusal_hits": sum(in_scope),
            "false_refusal_total": len(in_scope),
            "regular_hits": sum(regular),
            "regular_total": len(regular),
            "special_hits": sum(special),
            "special_total": len(special),
            "recomputed_count": recomputed_count,
        },
        "sc009": rev_agg["sc009"],
        "sc010": rev_agg["sc010"],
        "sc011": {
            "ratio": id_pass / id_total if id_total else None,
            "passed": id_pass,
            "total": id_total,
            "annotated_cases": id_cases,
            "evaluable_cases": id_eval_cases,
            "unparsed_leak_rounds": unparsed_rounds,
        },
        "auxiliary": {
            "blocked_turns": blocked_turns,
            "article_count_ok": ac_ok,
            "article_count_total": ac_n,
        },
    }


def _fmt_float(v: float | None) -> str:
    return f"{v:.3f}" if v is not None else "-"


def _esc_cell(text: str) -> str:
    return (
        text.replace("|", "\\|")
        .replace("\r\n", " ")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _fmt_refusal_rate(hits: int, total: int, *, count_only: bool = False) -> str:
    if total == 0:
        return "无样本（0/0）"
    if count_only:
        return f"{hits}/{total}"
    return f"{hits / total:.3f}（{hits}/{total}）"


def _fmt_manual_metric(agg: dict, *, metric_code: str) -> str:
    if agg["eligible_cases"] == 0 and agg["total"] == 0:
        return "-（无适用普法文章题）"
    status = agg["status"]
    if status == "missing_file":
        return f"待评审（适用 {agg['eligible_cases']} 题，未加载人工评审 CSV）"
    if status == "no_rows":
        if metric_code == "SC-010":
            return (
                f"待评审（适用 {agg['eligible_cases']} 题，"
                "缺少 diversity 维度标注）"
            )
        return f"待评审（适用 {agg['eligible_cases']} 题，评审 CSV 无匹配记录）"
    c = agg["counts"]
    return (
        f"{agg['value']:.3f}（pass={c['pass']}, minor_issue={c['minor_issue']}, "
        f"fail={c['fail']}；覆盖 {agg['covered_cases']}/{agg['eligible_cases']} 题，"
        f"共 {agg['total']} 条）"
    )


def render_report(
    run_id: str,
    exp_id: str | None,
    results: list[dict],
    *,
    kb_version: str | None = None,
    cases_path: str | None = None,
    reviews: list[ReviewEntry] | None = None,
    reviews_path: str | Path | None = None,
) -> str:
    """渲染覆盖 SC-001 ~ SC-011、失败清单与待评审普法文章清单的 Markdown 报告。"""
    failures = extract_failures(results, reviews=reviews)
    summary = summarize_run(results, reviews=reviews, run_id=run_id, _failures=failures)
    pending_articles = extract_pending_articles(results, run_id=run_id, reviews=reviews)

    sc001 = summary["sc001"]
    sc002 = summary["sc002"]
    sc003 = summary["sc003"]
    sc004 = summary["sc004"]
    sc005 = summary["sc005"]
    sc006 = summary["sc006"]
    sc007 = summary["sc007"]
    sc008 = summary["sc008"]
    sc009 = summary["sc009"]
    sc010 = summary["sc010"]
    sc011 = summary["sc011"]
    aux = summary["auxiliary"]

    sc001_str = (
        f"{sc001['value']:.3f}（{sc001['hits']}/{sc001['total']}）"
        if sc001["value"] is not None
        else "-"
    )
    sc006_str = (
        f"{sc006['value']:.3f}（{sc006['complete']}/{sc006['total']}）"
        if sc006["value"] is not None
        else "-"
    )
    sc007_str = (
        f"校验前 {_fmt_float(sc007['pre'])} / 校验后 {_fmt_float(sc007['post'])}"
        f"（共 {sc007['total']} 处引用，详见下表）"
        if sc007["total"]
        else "-"
    )

    sc008_str = (
        f"范围外正确拒答 {_fmt_refusal_rate(sc008['outside_hits'], sc008['outside_total'])}；"
        f"范围内误拒 {_fmt_refusal_rate(sc008['false_refusal_hits'], sc008['false_refusal_total'])}，"
        f"常规题 {_fmt_refusal_rate(sc008['regular_hits'], sc008['regular_total'], count_only=True)}，"
        f"专设误拒题 {_fmt_refusal_rate(sc008['special_hits'], sc008['special_total'], count_only=True)}"
    )

    if not sc011["annotated_cases"]:
        sc011_str = "-（无身份标注题）"
    else:
        cov = (
            f"标注 {sc011['annotated_cases']} 题，"
            f"其中 {sc011['evaluable_cases']} 题有可评文章"
        )
        if sc011["unparsed_leak_rounds"]:
            cov += (
                f"，另有 {sc011['unparsed_leak_rounds']} 轮"
                "未识别出文章结构但含保护名称"
            )
        sc011_str = (
            f"-（{cov}）"
            if not sc011["total"]
            else f"{sc011['passed']}/{sc011['total']}（{cov}）"
        )

    blocked_turns = aux["blocked_turns"]
    if not blocked_turns:
        blocked_str = "0 轮"
    else:
        detail = "、".join(f"{cid} 第{tn}轮" for cid, tn in blocked_turns)
        blocked_str = f"{len(blocked_turns)} 轮（{detail}）"

    ac_str = (
        f"{aux['article_count_ok']}/{aux['article_count_total']} 题"
        if aux["article_count_total"]
        else "-"
    )

    lines = [
        f"# 评测报告 {run_id}",
        "",
        f"- 实验：{exp_id or '-'}",
        f"- 知识库：{kb_version or '-'}",
        f"- 评测集：{cases_path or '-'}",
        f"- 用例数：{summary['case_count']}",
    ]
    if reviews_path is not None:
        lines.append(f"- 人工评审文件：{reviews_path}")
    if sc008["recomputed_count"]:
        lines.append(
            f"- 兼容提示：有 {sc008['recomputed_count']} 条历史结果缺少 `refusal_evidence`，"
            "已按 `detect_refusal(final_text)` 只读复算 SC-008。"
        )
    lines += [
        "",
        "> 注：POC 阶段目标值仅供参考、用于观察差距，不作为验收条件"
        "（spec.md Success Criteria；POC 验收以 SC-016 为准）。",
        "",
        "## 总体指标（SC-001 ~ SC-011）",
        "",
        "| 编号 | 指标 | 实测值 | POC 目标值（仅供参考） | 口径 |",
        "|---|---|---|---|---|",
        f"| SC-001 | 意图确认 | {sc001_str} | {POC_TARGETS['SC-001']} | 3 轮内确认意图比例 |",
        (
            f"| SC-002 | 条款召回率 | {_fmt_float(sc002['value'])} | "
            f"{POC_TARGETS['SC-002']} | gold 条款命中均值（n={sc002['n']}） |"
        ),
        (
            f"| SC-003 | 条款精确率 | {_fmt_float(sc003['value'])} | "
            f"{POC_TARGETS['SC-003']} | 输出条款命中均值（n={sc003['n']}） |"
        ),
        (
            f"| SC-004 | 多违规识别率 | {_fmt_float(sc004['value'])} | "
            f"{POC_TARGETS['SC-004']} | 多违法行为覆盖均值（n={sc004['n']}） |"
        ),
        (
            f"| SC-005 | 关联条款完整率 | {_fmt_float(sc005['value'])} | "
            f"{POC_TARGETS['SC-005']} | 已确认责任关联补全均值（n={sc005['n']}） |"
        ),
        (
            f"| SC-006 | 出处标注完整率 | {sc006_str} | "
            f"{POC_TARGETS['SC-006']} | 带完整标记引用 / 全部引用 |"
        ),
        (
            f"| SC-007 | 引用准确率 | {sc007_str} | "
            f"{POC_TARGETS['SC-007']} | 全分母（含 incomplete），见下表 |"
        ),
        (
            f"| SC-008 | 拒答初筛 | {sc008_str} | {POC_TARGETS['SC-008']} | "
            "SC-008（自动初筛，依据见 results.jsonl 的 refusal_evidence） |"
        ),
        (
            f"| SC-009 | 普法文章正确性 | {_fmt_manual_metric(sc009, metric_code='SC-009')} | "
            f"{POC_TARGETS['SC-009']} | 人工评审 correctness（pass/total，POC 按题×评审人记录统计） |"
        ),
        (
            f"| SC-010 | 普法文章多样性 | {_fmt_manual_metric(sc010, metric_code='SC-010')} | "
            f"{POC_TARGETS['SC-010']} | "
            "人工评审 diversity 实质重复率（fail/total，POC 按题×评审人记录统计） |"
        ),
        f"| SC-011 | 文章身份检查 | {sc011_str} | {POC_TARGETS['SC-011']} | SC-011（按篇计数） |",
        f"| 辅助 | 引用冲突暂缓交稿 | {blocked_str} | - | T054（零交稿不计入 SC-011） |",
        f"| 辅助 | 文章篇数符合 | {ac_str} | - | FR-028 |",
        "",
        "## SC-007 引用准确率（校验前 / 校验后对照）",
        "",
        "| 统计口径 | 校验前 | 校验后 | POC 目标值 | 分子 / 分母说明 |",
        "|---|---|---|---|---|",
        (
            f"| 严格全分母（主口径） | {_fmt_float(sc007['pre'])} | "
            f"{_fmt_float(sc007['post'])} | {POC_TARGETS['SC-007']} | "
            f"校验前 ok / all，校验后 (ok+corrected) / all（all={sc007['total']}，含 incomplete） |"
        ),
        (
            f"| 已定位引用（对照） | {_fmt_float(sc007['resolved_pre'])} | "
            f"{_fmt_float(sc007['resolved_post'])} | {POC_TARGETS['SC-007']} | "
            f"排除 incomplete（resolved={sc007['resolved_total']}） |"
        ),
        "",
        "## 引用判定分布",
        "",
        f"ok={sc007['counts']['ok']}  corrected={sc007['counts']['corrected']}  "
        f"not_found={sc007['counts']['not_found']}  incomplete={sc007['counts']['incomplete']}",
        "",
        "## 按类别统计",
        "",
        "| 类别 | 用例数 | 失败用例数 |",
        "|---|---|---|",
    ]
    for cat, stats in summary["by_category"].items():
        lines.append(f"| {_esc_cell(cat)} | {stats['total']} | {stats['failed']} |")

    lines += ["", "## 逐条失败用例清单", ""]
    if not failures:
        lines.append("无失败用例。")
    else:
        lines += [
            "| case_id | 类别 | 失败原因 |",
            "|---|---|---|",
        ]
        for f in failures:
            reason_text = "；".join(f["reasons"])
            lines.append(
                f"| {_esc_cell(f['case_id'])} | {_esc_cell(f['category'])} | {_esc_cell(reason_text)} |"
            )

    lines += ["", "## 待评审普法文章清单（FR-037 / T063）", ""]
    if not pending_articles:
        lines.append("本评测集无普法文章用例。")
    else:
        dim_map = {
            "correctness": "correctness",
            "diversity": "diversity",
            "other": "拒答复核（other）",
        }
        lines += [
            "| run_id | case_id | 轮数 / 实得篇数 | 期望篇数 | 需评维度 | 评审状态 | 评分要点（rubric） |",
            "|---|---|---|---|---|---|---|",
        ]
        for item in pending_articles:
            turns_info = f"{item['turns_count']} 轮 / {item['actual_per_turn']}"
            exp_info = (
                str(item["expected_articles"])
                if item["expected_articles"] is not None
                else "-"
            )
            dims_info = " + ".join(dim_map[d] for d in item["required_dimensions"])
            rubric_info = "；".join(item["rubric"]) if item["rubric"] else "-"
            lines.append(
                f"| {_esc_cell(item['run_id'])} | {_esc_cell(item['case_id'])} | "
                f"{_esc_cell(turns_info)} | {_esc_cell(exp_info)} | "
                f"{_esc_cell(dims_info)} | {_esc_cell(item['status'])} | "
                f"{_esc_cell(rubric_info)} |"
            )
        lines += [
            "",
            "人工评审请复制模板 `eval/review-template.csv` 按行填写，随后执行：",
            f"`uv run tu eval report {run_id} --reviews <评审表.csv>`（只读输出，不覆盖历史报告）。",
        ]

    lines += ["", "逐条结果见 results.jsonl。", ""]
    return "\n".join(lines)


def _validate_run_id(run_id: str) -> None:
    if (
        not run_id
        or run_id != run_id.strip()
        or run_id in {".", ".."}
        or "/" in run_id
        or "\\" in run_id
        or ".." in run_id
        or Path(run_id).name != run_id
    ):
        raise ReportError(f"非法的 run_id：{run_id!r}")


def load_run_artifacts(
    artifacts_dir: str | Path,
    run_id: str,
) -> tuple[dict, list[dict]]:
    """只读加载已有评测 run 的 manifest.json 与 results.jsonl。"""
    _validate_run_id(run_id)
    run_dir = Path(artifacts_dir) / "eval" / run_id
    if not run_dir.exists():
        raise ReportError(f"评测目录不存在：{run_dir}")

    manifest_path = run_dir / "manifest.json"
    results_path = run_dir / "results.jsonl"
    if not manifest_path.exists():
        raise ReportError(f"缺少 manifest.json：{manifest_path}")
    if not results_path.exists():
        raise ReportError(f"缺少 results.jsonl：{results_path}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError(f"无法解析 manifest.json（{manifest_path}）：{exc}") from exc
    if not isinstance(manifest, dict):
        raise ReportError(f"manifest.json 格式错误（期望 JSON 对象）：{manifest_path}")

    results: list[dict] = []
    try:
        raw_lines = results_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ReportError(f"无法读取 results.jsonl（{results_path}）：{exc}") from exc
    for idx, line in enumerate(raw_lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReportError(
                f"results.jsonl 第 {idx} 行 JSON 非法（{results_path}）：{exc}"
            ) from exc
        if not isinstance(row, dict) or "case_id" not in row:
            raise ReportError(
                f"results.jsonl 第 {idx} 行缺少 case_id（{results_path}）"
            )
        results.append(row)

    return manifest, results


def render_run_report(
    artifacts_dir: str | Path,
    run_id: str,
    *,
    reviews_path: str | Path | None = None,
) -> str:
    """只读读取已有 run 目录并渲染完整报告（绝不修改磁盘文件）。"""
    manifest, results = load_run_artifacts(artifacts_dir, run_id)
    reviews = (
        load_reviews(reviews_path, run_id=run_id, results=results)
        if reviews_path is not None
        else None
    )
    inputs = manifest.get("inputs") or {}
    config = manifest.get("config") or {}
    exp_id = config.get("exp") or inputs.get("exp_id")
    kb_raw = inputs.get("kb")
    kb_version = Path(kb_raw).stem if isinstance(kb_raw, str) and kb_raw else None
    cases_path = inputs.get("cases") if isinstance(inputs.get("cases"), str) else None

    return render_report(
        run_id,
        exp_id,
        results,
        kb_version=kb_version,
        cases_path=cases_path,
        reviews=reviews,
        reviews_path=reviews_path,
    )
