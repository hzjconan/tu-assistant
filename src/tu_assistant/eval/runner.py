"""评测运行器（T034）：`tu eval run`。

- 单轮（input.message）与固定对话脚本（input.script）两种输入；
- temperature=0；评测模式保留 raw_content；
- 产出 artifacts/eval/<run_id>/：results.jsonl、report.md、manifest.json。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ..chat.assistant import SessionConfig, TrainedAssistant
from ..kb.store import open_kb
from ..manifest import write_manifest
from ..runtime.client import ModelClient
from .cases import EvalCase, load_cases, validate_gold_clauses
from .metrics import (
    intent_score,
    multi_violation_score,
    refusal_correct,
    score_case_output,
)


def _run_case(
    assistant: TrainedAssistant, case: EvalCase, cfg: SessionConfig
) -> dict:
    sid = assistant.new_session(cfg)
    try:
        if "script" in case.input:
            reply = None
            turns = []
            for msg in case.input["script"]:
                reply = assistant.send(sid, msg)
                turns.append(
                    {
                        "user": msg,
                        "content": reply.content,
                        "raw_content": reply.raw_content,
                        "question_count": reply.question_count,
                        "intent": reply.intent,
                    }
                )
            final_raw = reply.raw_content or reply.content if reply else ""
            final_text = reply.content if reply else ""
        else:
            reply = assistant.send(sid, case.input["message"])
            turns = [{"user": case.input["message"], "content": reply.content}]
            final_raw = reply.raw_content or reply.content
            final_text = reply.content
    finally:
        assistant.close(sid)
    return {
        "case_id": case.case_id,
        "category": case.category,
        "turns": turns,
        "final_raw": final_raw,
        "final_text": final_text,
        "gold": case.gold,
    }


def _render_report(run_id: str, exp_id: str | None, results: list[dict]) -> str:
    """按类别聚合各指标，生成 markdown 报告。"""

    def _mean(vals: list) -> float | None:
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    def _fmt(v: float | None) -> str:
        return f"{v:.3f}" if v is not None else "-"

    acc = {"ok": 0, "corrected": 0, "not_found": 0, "incomplete": 0}
    for r in results:
        for k, v in r["scores"]["citation_acc"]["counts"].items():
            acc[k] += v
    acc_total = sum(acc.values())
    pre = acc["ok"] / acc_total if acc_total else None
    post = (acc["ok"] + acc["corrected"]) / acc_total if acc_total else None

    def _cat_mean(key: str) -> float | None:
        return _mean(
            [r["scores"].get(key) for r in results if key in r["scores"]]
        )

    lines = [
        f"# 评测报告 {run_id}",
        "",
        f"- 实验：{exp_id or '-'}",
        f"- 用例数：{len(results)}",
        "",
        "## 总体指标",
        "",
        "| 指标 | 值 | 口径 |",
        "|---|---|---|",
        f"| 条款召回率 | {_fmt(_cat_mean('recall'))} | SC-002 |",
        f"| 条款精确率 | {_fmt(_cat_mean('precision'))} | SC-003 |",
        f"| 引用准确率（校验前） | {_fmt(pre)} | ok / 全部引用 |",
        f"| 引用准确率（校验后） | {_fmt(post)} | (ok+corrected) / 全部引用 |",
        f"| 关联条款完整率 | {_fmt(_cat_mean('relation_completion'))} | SC-005 |",
        f"| 拒答正确率 | {_fmt(_cat_mean('refusal_correct'))} | SC-008 |",
        f"| 多违规识别率 | {_fmt(_cat_mean('multi_violation'))} | SC-004 |",
        f"| 意图确认 | {_fmt(_cat_mean('intent'))} | SC-001 |",
        "",
        "## 引用判定分布",
        "",
        f"ok={acc['ok']}  corrected={acc['corrected']}  "
        f"not_found={acc['not_found']}  incomplete={acc['incomplete']}",
        "",
        "## 按类别",
        "",
        "| 类别 | 用例数 |",
        "|---|---|",
    ]
    cats: dict[str, int] = {}
    for r in results:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    for c, n in sorted(cats.items()):
        lines.append(f"| {c} | {n} |")
    lines += ["", "逐条结果见 results.jsonl。", ""]
    return "\n".join(lines)


def run_eval(
    *,
    cases_path: str | Path,
    kb_path: str | Path,
    endpoint: str,
    allowed_hosts: list[str],
    model_name: str = "default",
    artifacts_dir: str | Path = "artifacts",
    exp_id: str | None = None,
    session_config: SessionConfig | None = None,
) -> dict:
    cases = load_cases(cases_path)
    kb_conn = open_kb(kb_path)
    issues = validate_gold_clauses(cases, kb_conn)

    client = ModelClient(endpoint, allowed_hosts, model=model_name)
    assistant = TrainedAssistant(
        client, kb_conn, eval_mode=True, temperature=0.0
    )
    cfg = session_config or SessionConfig()

    run_id = datetime.now(UTC).strftime("run-%Y%m%d-%H%M%S")
    out_dir = Path(artifacts_dir) / "eval" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for case in cases:
        r = _run_case(assistant, case, cfg)
        score = score_case_output(r["final_raw"], case.gold, kb_conn)
        r["scores"] = {
            "recall": score["recall"],
            "precision": score["precision"],
            "citation_complete": score["citation_complete"],
            "citation_total": score["citation_total"],
            "citation_acc": score["citation_acc"],
            "cited_clause_ids": score["cited_clause_ids"],
            "relation_completion": score["relation_completion"],
        }
        if case.category in {"refusal", "false_refusal"}:
            r["scores"]["refusal_correct"] = refusal_correct(
                r["final_text"],
                should_refuse=case.gold.get("should_refuse", True),
            )
        if case.category == "multi_violation":
            r["scores"]["multi_violation"] = multi_violation_score(
                set(score["cited_clause_ids"]), case.gold.get("violations", [])
            )
        if case.category == "intent":
            r["scores"]["intent"] = intent_score(r["turns"], case.gold)
        results.append(r)

    results_path = out_dir / "results.jsonl"
    with results_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    (out_dir / "report.md").write_text(
        _render_report(run_id, exp_id, results), encoding="utf-8"
    )

    write_manifest(
        out_dir,
        artifact_id=run_id,
        artifact_type="eval_run",
        inputs={
            "cases": str(cases_path),
            "kb": str(kb_path),
            "exp_id": exp_id,
            "endpoint": endpoint,
        },
        config={"temperature": 0.0, "model": model_name},
        extra={
            "case_count": len(cases),
            "gold_clause_issues": issues,
        },
    )
    kb_conn.close()
    return {"run_id": run_id, "dir": str(out_dir), "cases": len(cases),
            "gold_issues": issues}
