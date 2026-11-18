"""Estimate gold-clause coverage of the existing and unthinned datasets."""

import json
import statistics
from collections import Counter
from pathlib import Path

from tu_assistant.citation.verify import verify_output
from tu_assistant.kb.store import open_kb

root = Path(__file__).resolve().parents[3]
gold = {
    c["gold"]["clauses"][0]
    for line in (root / "eval/cases/v1/reviewed.jsonl").open(encoding="utf-8")
    if (c := json.loads(line))["gold"].get("clauses")
}
kb = open_kb(root / "artifacts/kb/kb-20261113-093057.sqlite")

for name, dataset in [
    ("current", root / "artifacts/datasets/latest/train.jsonl"),
    ("pre-thin-source", root / "artifacts/datasets/ds-kb-20261113-093057-16741/train.jsonl"),
]:
    exp = Counter()
    n = 0
    for line in dataset.open(encoding="utf-8"):
        n += 1
        answer = json.loads(line)["messages"][-1]["content"]
        if "〔" not in answer:
            continue
        ids = {
            c.resolved_clause_id
            for c in verify_output(answer, kb).citations
            if c.resolved_clause_id in gold
        }
        exp.update(ids)
    freq = sorted(exp[g] for g in gold)
    print(name, "train rows:", n, "gold unique:", len(gold),
          "median:", statistics.median(freq),
          "zero:", freq.count(0), "max:", max(freq),
          "histogram:", dict(sorted(Counter(freq).items())))
kb.close()
