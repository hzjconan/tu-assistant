"""SC-016 (POC acceptance) check: base vs trained run on the same eval set.

Usage: uv run python scripts/experiments/e003/sc016.py [base_run] [trained_run]
Reuses the loose (file/article) parser and Fisher test from E002 review_stats.py;
paragraph level uses the strict scores.cited_clause_ids from the eval run.
"""

import contextlib
import importlib.util
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "review_stats", ROOT / "scripts/experiments/e002/review_stats.py"
)
rs = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()):
    spec.loader.exec_module(rs)

base_run = sys.argv[1] if len(sys.argv) > 1 else "run-20261117-022645"
trained_run = sys.argv[2] if len(sys.argv) > 2 else "run-20261117-081504"


def load(run):
    path = ROOT / f"artifacts/eval/{run}/results.jsonl"
    return {r["case_id"]: r for line in path.open(encoding="utf-8") if (r := json.loads(line))}


base, trained = load(base_run), load(trained_run)
assert base.keys() == trained.keys()
ids = sorted(base)
n = len(ids)


def gold(r):
    return r["gold"]["clauses"][0]


def doc_hit(r):
    return gold(r).split(":")[0] in rs.loose(r["final_raw"])[1]


def art_hit(r):
    return ":".join(gold(r).split(":")[:2]) in rs.loose(r["final_raw"])[0]


def para_hit(r):
    return gold(r) in (r["scores"]["cited_clause_ids"] or [])


print(f"base={base_run} trained={trained_run} cases={n}")

b = sum(art_hit(base[k]) for k in ids)
t = sum(art_hit(trained[k]) for k in ids)
p1 = rs.fisher(b, n - b, t, n - t)
print(f"(1) article: base {b}/{n} trained {t}/{n} fisher p={p1:.3g} -> {'PASS' if t > b and p1 < 0.05 else 'FAIL'}")

t2 = sum(para_hit(trained[k]) for k in ids)
print(f"(2) paragraph exact: trained {t2}/{n} = {t2 / n:.1%} -> {'PASS' if t2 / n >= 0.10 else 'FAIL'}")

known = {gold(base[k]).split(":")[0] for k in ids if doc_hit(base[k])}
sub = [k for k in ids if gold(base[k]).split(":")[0] not in known]
m = len(sub)
b3 = sum(doc_hit(base[k]) for k in sub)
t3 = sum(doc_hit(trained[k]) for k in sub)
p3 = rs.fisher(b3, m - b3, t3, m - t3)
print(f"(3) files never identified by base: {len(known)} known files, subset {m} cases; "
      f"doc base {b3}/{m} trained {t3}/{m} fisher p={p3:.3g} -> {'PASS' if t3 > b3 and p3 < 0.05 else 'FAIL'}")
