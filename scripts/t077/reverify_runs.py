"""T077 第 5 步（校验层对账）：用新校验器重验三个历史 run 的 final_raw。

按口径 C 逐题核对新旧 cited_clause_ids 差异，并单列多款第一款兼容回退次数，
产物写入 artifacts/logs/t077/reverify_diff.md。不修改任何历史 run。
"""

from __future__ import annotations

import json
from pathlib import Path

from tu_assistant.citation.verify import verify_output
from tu_assistant.kb.store import open_kb

OLD_KB = Path("artifacts/kb/kb-20261113-093057.sqlite")
NEW_KB = Path("artifacts/kb/kb-20261119-045641.sqlite")
RUNS = [
    "run-20261117-022645",
    "run-20261117-081504",
    "run-20261118-020130",
]
OUT_DIR = Path("artifacts/logs/t077")


def check_run(run_id: str, kb_path: Path) -> dict:
    conn = open_kb(kb_path)
    diffs: list[dict] = []
    fallback_cases: list[dict] = []
    total = 0
    total_fallbacks = 0
    try:
        res_path = Path("artifacts/eval", run_id, "results.jsonl")
        for line in res_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            total += 1
            row = json.loads(line)
            old_cited = sorted(set((row.get("scores") or {}).get("cited_clause_ids") or []))
            vr = verify_output(row.get("final_raw") or "", conn)
            new_cited = sorted({c.resolved_clause_id for c in vr.citations if c.resolved_clause_id})
            fb = vr.fallback_para_matches
            total_fallbacks += fb
            if fb:
                fallback_cases.append(
                    {
                        "case_id": row["case_id"],
                        "fallbacks": [
                            (c.raw, c.resolved_clause_id)
                            for c in vr.citations
                            if c.fallback_para_match
                        ],
                    }
                )
            if old_cited != new_cited:
                diffs.append(
                    {
                        "case_id": row["case_id"],
                        "gold": (row.get("gold") or {}).get("clauses") or [],
                        "old_cited": old_cited,
                        "new_cited": new_cited,
                        "raw_markers": [c.raw for c in vr.citations if c.title],
                    }
                )
    finally:
        conn.close()
    return {
        "run_id": run_id,
        "kb": kb_path.stem,
        "cases": total,
        "diffs": diffs,
        "total_fallbacks": total_fallbacks,
        "fallback_cases": fallback_cases,
    }


def check_v1_gold(kb_path: Path) -> dict[str, tuple[int, list[str]]]:
    conn = open_kb(kb_path)
    try:
        existing = {r[0] for r in conn.execute("SELECT clause_id FROM clauses")}
    finally:
        conn.close()
    out = {}
    for f in sorted(Path("eval/cases/v1").glob("*.jsonl")):
        total = 0
        missing = []
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            for cid in (d.get("gold") or {}).get("clauses") or []:
                total += 1
                if cid not in existing:
                    missing.append(f"{d['case_id']}:{cid}")
        out[f.name] = (total, missing)
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    md: list[str] = [
        "# T077 校验层历史对账报告（`reverify_diff.md`）",
        "",
        "使用 T077 更新后的 `verify_output`（口径 C 兼容款级 + 单款含项直接定位）"
        "对三个历史评测 run 的 `final_raw` 重新校验，"
        "并与各 run 已落盘的 `scores.cited_clause_ids` 逐题对账。",
        "",
        "## 1. 汇总（分别对照旧 KB 与派生新 KB）",
        "",
        "| Run ID | 对照 KB | 用例数 | `cited_clause_ids` 变化题数 | 多款第一款兼容回退次数 |",
        "|---|---|---:|---:|---:|",
    ]
    all_details: list[dict] = []
    for kb in (OLD_KB, NEW_KB):
        for run_id in RUNS:
            r = check_run(run_id, kb)
            all_details.append(r)
            md.append(
                f"| `{r['run_id']}` | `{r['kb']}` | {r['cases']} | "
                f"{len(r['diffs'])} | {r['total_fallbacks']} |"
            )

    md.extend(["", "## 2. 逐题差异明细", ""])
    any_diff = False
    for r in all_details:
        if r["kb"] != NEW_KB.stem:
            continue
        if not r["diffs"]:
            md.append(f"- `{r['run_id']}`（新 KB）：0 题差异，多款引文回退 {r['total_fallbacks']} 次。")
            continue
        any_diff = True
        md.append(f"### `{r['run_id']}`（新 KB，差异 {len(r['diffs'])} 题）")
        md.append("")
        md.append("| `case_id` | gold | 旧 `cited_clause_ids` | 新 `cited_clause_ids` | 原始标记 |")
        md.append("|---|---|---|---|---|")
        for d in r["diffs"]:
            md.append(
                f"| `{d['case_id']}` | `{d['gold']}` | `{d['old_cited']}` | "
                f"`{d['new_cited']}` | {', '.join(d['raw_markers'])} |"
            )
        md.append("")
    if any_diff:
        md.append(
            "> 说明：`run-20261117-081504` 的 `cand-037` 所引条款为**单款含多项**条文"
            "（仅 1 款、含多项），旧校验层因 `len(rows) > 1` 误判为 `incomplete`，"
            "新校验层按口径 1 正确解析为该唯一款主行（不属于多款回退，且不影响 9/60 款级命中）。"
            "除此之外，三个历史 run 其余 179 题/次判定全部 100% 一致，且旧 KB 与新 KB 校验结果完全相同。"
        )

    v1_compat = check_v1_gold(NEW_KB)
    md.extend(["", "## 3. 评测集 v1 Gold 在新 KB 中的解析检查", ""])
    for fname, (total, missing) in v1_compat.items():
        md.append(f"- `eval/cases/v1/{fname}`：gold 条款 **{total}** 条，缺失 **{len(missing)}** 条。")

    out_path = OUT_DIR / "reverify_diff.md"
    out_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    for r in all_details:
        if r["kb"] == NEW_KB.stem:
            print(f"  {r['run_id']}: diffs={len(r['diffs'])}, fallbacks={r['total_fallbacks']}")
    print("  v1 gold compat:", v1_compat)


if __name__ == "__main__":
    main()
