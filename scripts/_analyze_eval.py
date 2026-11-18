"""一次性分析脚本：统计 eval run 的引用指标与抽查输出（截断展示）。

用法：uv run python scripts/_analyze_eval.py <run_dir>
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

run_dir = Path(sys.argv[1])
rows = [json.loads(l) for l in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

n = len(rows)
has_bracket = sum(1 for r in rows if "〔" in r["final_raw"])
has_cited = sum(1 for r in rows if r["scores"].get("cited_clause_ids"))
acc = Counter()
cit_total = 0
lens = []
empty = 0
for r in rows:
    for k, v in r["scores"]["citation_acc"]["counts"].items():
        acc[k] += v
    cit_total += r["scores"].get("citation_total", 0)
    lens.append(len(r["final_text"]))
    if not r["final_text"].strip():
        empty += 1

recalls = [r["scores"]["recall"] for r in rows if r["scores"].get("recall") is not None]
precs = [r["scores"]["precision"] for r in rows if r["scores"].get("precision") is not None]

print(f"cases={n}")
print(f"含〔〕题数={has_bracket}/{n}  cited_clause_ids非空={has_cited}/{n}")
print(f"citation_total={cit_total}  判定: {dict(acc)}")
print(f"recall_mean={sum(recalls)/len(recalls):.4f} ({len(recalls)} cases)" if recalls else "recall: none")
print(f"precision_mean={sum(precs)/len(precs):.4f} ({len(precs)} cases)" if precs else "precision: none")
lens.sort()
print(f"len median={lens[n//2]} min={lens[0]} max={lens[-1]} empty={empty}")

# 每题的〔〕块数 & 裸引用数（"第N条"模式）
for r in rows[:0]:
    pass

print("\n--- 逐题引用标记统计 ---")
nb = []
for r in rows:
    nb.append((r["case_id"], r["final_raw"].count("〔"), len(re.findall(r"第[0-9一二三四五六七八九十百]+条", r["final_raw"]))))
print("含〔〕的题:", [x for x in nb if x[1] > 0])
print("裸引用条数 top5:", sorted(nb, key=lambda x: -x[2])[:5])
