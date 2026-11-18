"""一次性脚本：截断展示 eval run 中指定 case 的输出（每段 ≤15 字省略号截断）。

用法：uv run python scripts/_show_eval.py <run_dir> cand-001 cand-007 ...
"""

import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
want = set(sys.argv[2:])
rows = {
    json.loads(l)["case_id"]: json.loads(l)
    for l in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
    if l.strip()
}

def trunc(s: str, limit: int = 15) -> str:
    return s if len(s) <= limit else s[:limit] + "…"

for cid in sorted(want):
    r = rows.get(cid)
    if not r:
        print(f"== {cid}: NOT FOUND")
        continue
    print(f"== {cid} ==")
    print("user:", trunc(r["turns"][0]["user"], 40))
    raw = r["final_raw"]
    # 按行截断展示前 40 行
    for line in raw.splitlines()[:40]:
        print("  |", trunc(line, 60))
    if len(raw.splitlines()) > 40:
        print(f"  | …（共 {len(raw.splitlines())} 行）")
    print("scores:", {k: r["scores"][k] for k in ("recall", "precision", "citation_total", "cited_clause_ids")})
    print("acc:", r["scores"]["citation_acc"]["counts"])
    print("gold:", {k: trunc(str(v), 80) for k, v in r["gold"].items()})
    print()
