"""Build deduplicated, answer-free train questions for E003.

Usage: uv run python scripts/experiments/e003/build_probes.py [--include-p3]
"""

import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from tu_assistant.citation.verify import verify_output
from tu_assistant.kb.store import open_kb

ROOT = Path(__file__).resolve().parents[3]
KB = open_kb(ROOT / "artifacts/kb/kb-20261113-093057.sqlite")
TRAIN = ROOT / "artifacts/datasets/latest/train.jsonl"
OUT = ROOT / "eval/diagnostics/train-probe-v1.jsonl"
GOLD = {
    c["gold"]["clauses"][0]
    for line in (ROOT / "eval/cases/v1/reviewed.jsonl").open(encoding="utf-8")
    if (c := json.loads(line))["gold"].get("clauses")
}
UNSEEN = set(json.loads(
    (ROOT / "artifacts/logs/e003/unseen_ids.json").read_text(encoding="utf-8")
)["unseen_line_numbers"])

exposure = Counter()
by_clause = defaultdict(list)
seen_questions = set()
for number, line in enumerate(TRAIN.open(encoding="utf-8"), 1):
    messages = json.loads(line)["messages"]
    if not messages or messages[-1]["role"] != "assistant":
        continue
    citations = verify_output(messages[-1]["content"], KB).citations
    ids = {c.resolved_clause_id for c in citations if c.resolved_clause_id}
    exposure.update(ids)
    if len(messages) != 3 or [m["role"] for m in messages] != [
        "system", "user", "assistant"
    ] or len(ids) != 1:
        continue
    question = messages[1]["content"]
    if question in seen_questions:
        continue
    seen_questions.add(question)
    clause = next(iter(ids))
    if not re.search(r":p\d+", clause):
        continue
    by_clause[clause].append((number, question))

probes = []
def append(group, clause, number, question):
    probes.append({
        "case_id": f"{group}-{len(probes) + 1:04d}",
        "category": "clause_id",
        "input": {"message": question},
        "gold": {"clauses": [clause]},
        "source": "train_probe",
        "eval_set_version": "train-probe-v1",
        "note": f"train.jsonl:{number}",
    })

def answer_free(question):
    return "《" not in question and re.search(r"第[0-9零〇一二三四五六七八九十百千]+条", question) is None

covered = set()
for clause in sorted(GOLD):
    examples = [
        (n, q) for n, q in by_clause[clause]
        if n not in UNSEEN and answer_free(q)
    ][:3]
    if examples:
        covered.add(clause)
    for number, question in examples:
        append("p1", clause, number, question)

# If under 30 distinct clauses, include leaky knowledge examples separately.
if len(covered) < 30:
    for clause in sorted(GOLD - covered):
        examples = [
            (n, q) for n, q in by_clause[clause]
            if n not in UNSEEN and not answer_free(q)
        ][:3]
        for number, question in examples:
            append("p1k", clause, number, question)

other = [
    (clause, n, q)
    for clause, items in by_clause.items() if clause not in GOLD
    for n, q in items if n not in UNSEEN and answer_free(q)
]
for clause, number, question in random.Random(42).sample(other, min(100, len(other))):
    append("p2", clause, number, question)

if "--include-p3" in sys.argv:
    for clause in sorted(by_clause):
        for number, question in by_clause[clause]:
            if number in UNSEEN and answer_free(question):
                append("p3", clause, number, question)

with OUT.open("w", encoding="utf-8") as out:
    for case in probes:
        out.write(json.dumps(case, ensure_ascii=False) + "\n")
stats = Counter(c["case_id"].split("-")[0] for c in probes)
print("groups:", dict(stats), "P1 gold coverage:", len(covered), "/", len(GOLD))
print("eligible non-gold:", len(other), "out:", OUT.relative_to(ROOT))
print("P1/P2 exposure bins:", dict(Counter(
    exposure[c["gold"]["clauses"][0]]
    for c in probes if c["case_id"].startswith(("p1-", "p2-"))
)))
KB.close()
