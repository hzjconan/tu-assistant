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
    article_identity_check,
    detect_refusal,
    extract_articles,
    intent_score,
    multi_violation_score,
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
                        "anonymize": assistant._last_turn_anonymize_info(sid),
                    }
                )
            final_raw = reply.raw_content or reply.content if reply else ""
            final_text = reply.content if reply else ""
        else:
            reply = assistant.send(sid, case.input["message"])
            turns = [
                {
                    "user": case.input["message"],
                    "content": reply.content,
                    "anonymize": assistant._last_turn_anonymize_info(sid),
                }
            ]
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


def _expected_refusal(category: str, gold: dict) -> bool:
    if category in {"refusal", "false_refusal"}:
        return gold.get("should_refuse", category == "refusal")
    return gold.get("should_refuse") is True


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

    outside = []
    regular = []
    special = []
    for r in results:
        refused = r["scores"]["refusal_evidence"]["refused"]
        if _expected_refusal(r["category"], r["gold"]):
            outside.append(refused)
        elif r["category"] == "false_refusal":
            special.append(refused)
        else:
            regular.append(refused)

    def _refusal_rate(refused: list[bool], *, count_only: bool = False) -> str:
        if not refused:
            return "无样本（0/0）"
        n = sum(refused)
        if count_only:
            return f"{n}/{len(refused)}"
        return f"{n / len(refused):.3f}（{n}/{len(refused)}）"

    # SC-011：有身份标注的文章题，按篇累计未泄露 / 可评；
    # "覆盖"区分有标注的题和实际有可评文章的题，让分母可还原
    id_pass = id_total = id_cases = id_eval_cases = 0
    unparsed_rounds = 0
    for r in results:
        ic = r["scores"].get("identity_check") or {}
        if "passed" in ic:
            id_cases += 1
            unparsed_rounds += len(ic.get("unparsed_leaks", []))
            if ic["total"]:
                id_eval_cases += 1
                id_pass += ic["passed"]
                id_total += ic["total"]
    ac_ok = ac_n = 0
    for r in results:
        ac = r["scores"].get("article_count") or {}
        if "ok" in ac:
            ac_n += 1
            ac_ok += 1 if ac["ok"] else 0

    blocked_turns: list[tuple[str, int]] = []
    for r in results:
        for idx, t in enumerate(r.get("turns", []), 1):
            if (t.get("anonymize") or {}).get("blocked"):
                blocked_turns.append((r["case_id"], idx))

    def _blocked_summary() -> str:
        if not blocked_turns:
            return "0 轮"
        detail = "、".join(f"{cid} 第{tn}轮" for cid, tn in blocked_turns)
        return f"{len(blocked_turns)} 轮（{detail}）"

    def _sc011() -> str:
        if not id_cases:
            return "-（无身份标注题）"
        cov = f"标注 {id_cases} 题，其中 {id_eval_cases} 题有可评文章"
        if unparsed_rounds:
            cov += f"，另有 {unparsed_rounds} 轮未识别出文章结构但含保护名称"
        if not id_total:
            return f"-（{cov}）"
        return f"{id_pass}/{id_total}（{cov}）"

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
        f"| 拒答初筛 | 范围外正确拒答 {_refusal_rate(outside)}；"
        f"范围内误拒 {_refusal_rate(regular + special)}，"
        f"常规题 {_refusal_rate(regular, count_only=True)}，"
        f"专设误拒题 {_refusal_rate(special, count_only=True)} "
        "| SC-008（自动初筛，依据见 results.jsonl 的 refusal_evidence） |",
        f"| 多违规识别率 | {_fmt(_cat_mean('multi_violation'))} | SC-004 |",
        f"| 意图确认 | {_fmt(_cat_mean('intent'))} | SC-001 |",
        f"| 文章身份检查 | {_sc011()} | SC-011 |",
        f"| 引用冲突暂缓交稿 | {_blocked_summary()} | T054（零交稿不计入 SC-011） |",
        (
            f"| 文章篇数符合 | {ac_ok}/{ac_n} 题 | FR-028 |"
            if ac_n
            else "| 文章篇数符合 | - | FR-028 |"
        ),
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
        expected_refusal = _expected_refusal(case.category, case.gold)
        detection = detect_refusal(r["final_text"])
        r["scores"]["refusal_evidence"] = detection
        r["scores"]["refusal_correct"] = detection["refused"] == expected_refusal
        if case.category == "multi_violation":
            r["scores"]["multi_violation"] = multi_violation_score(
                set(score["cited_clause_ids"]), case.gold.get("violations", [])
            )
        if case.category == "intent":
            r["scores"]["intent"] = intent_score(r["turns"], case.gold)
        if case.category == "article":
            article_turns = set()
            exp = case.gold.get("expect_articles")
            if exp is not None:
                counts = [
                    len(extract_articles(t.get("content") or ""))
                    for t in r["turns"]
                ]
                # expect_articles：int → 核对最后一轮；list → 逐轮核对
                # （null = 该轮是咨询等不要求交稿，不计）
                if isinstance(exp, int):
                    checks = {len(counts) - 1: exp}
                else:
                    checks = {
                        i: e for i, e in enumerate(exp) if e is not None
                    }
                article_turns = {idx + 1 for idx, count in checks.items() if count > 0}
                ok = bool(checks) and all(
                    i < len(counts) and counts[i] == e
                    for i, e in checks.items()
                )
                r["scores"]["article_count"] = {
                    "expected": exp,
                    "per_turn": counts,
                    "ok": ok,
                }
            chk = article_identity_check(r["turns"], case.gold.get("protected_names"), article_turns)
            r["scores"]["identity_check"] = (
                chk if chk is not None else {"skipped": "无保护名称标注"}
            )
        results.append(r)

    results_path = out_dir / "results.jsonl"
    with results_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    (out_dir / "report.md").write_text(
        _render_report(run_id, exp_id, results), encoding="utf-8"
    )

    # E002：从 current.json 记录本次服务的 exp 与基座模型，便于追溯测的是哪个 adapter
    serve_info: dict = {}
    cur = Path(artifacts_dir) / "serve" / "current.json"
    if cur.exists():
        try:
            serve_info = json.loads(cur.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            serve_info = {}

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
        config={
            "temperature": 0.0,
            "model": model_name,
            "use_system_prompt": cfg.use_system_prompt,
            "exp": serve_info.get("exp", exp_id),
            "base_model": serve_info.get("base_model"),
        },
        extra={
            "case_count": len(cases),
            "gold_clause_issues": issues,
        },
    )
    kb_conn.close()
    return {"run_id": run_id, "dir": str(out_dir), "cases": len(cases),
            "gold_issues": issues}
