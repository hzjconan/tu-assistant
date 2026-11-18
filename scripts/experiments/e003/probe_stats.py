"""E003 train-probe file/article/paragraph recall with exposure buckets."""

import json
import re
import sys
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from tu_assistant.citation.verify import verify_output  # noqa: E402
from tu_assistant.kb.numbers import chinese_to_int  # noqa: E402
from tu_assistant.kb.store import open_kb  # noqa: E402

KB = open_kb(ROOT / "artifacts/kb/kb-20261113-093057.sqlite")
DOCS = KB.execute("select doc_id, title from legal_documents").fetchall()
RE_LOOSE = re.compile(r"《([^》]+)》(?:（[^）]*）)?(?:第([0-9零〇一二三四五六七八九十百千]+)条)?")


def loose(raw):
    arts, docs = set(), set()
    for match in RE_LOOSE.finditer(raw):
        title = match.group(1).replace("中华人民共和国", "")
        candidates = [d for d, t in DOCS if t.replace("中华人民共和国", "") == title]
        if not candidates:
            candidates = [
                d for d, t in DOCS
                if title in t.replace("中华人民共和国", "")
                or t.replace("中华人民共和国", "") in title
            ]
        if candidates:
            docs.add(candidates[0])
            if match.group(2):
                arts.add(f"{candidates[0]}:a{chinese_to_int(match.group(2))}")
    return arts, docs


def fisher(a, b, c, d):
    n, r1, c1 = a + b + c + d, a + b, a + c
    prob = lambda x: comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1)  # noqa: E731
    actual = prob(a)
    return sum(
        prob(x) for x in range(max(0, c1 - (n - r1)), min(r1, c1) + 1)
        if prob(x) <= actual + 1e-12
    )


run = sys.argv[1]
case_path = ROOT / "eval/diagnostics/train-probe-v1.jsonl"
cases = {c["case_id"]: c for line in case_path.open(encoding="utf-8")
         if (c := json.loads(line))}
results = [
    json.loads(line)
    for line in (ROOT / f"artifacts/eval/{run}/results.jsonl").open(encoding="utf-8")
]
assert len(results) == len(cases)
exposure = Counter()
for line in (ROOT / "artifacts/datasets/latest/train.jsonl").open(encoding="utf-8"):
    answer = json.loads(line)["messages"][-1]["content"]
    exposure.update({
        c.resolved_clause_id for c in verify_output(answer, KB).citations
        if c.resolved_clause_id
    })

groups = defaultdict(list)
for result in results:
    case = cases[result["case_id"]]
    gold = case["gold"]["clauses"][0]
    arts, docs = loose(result["final_raw"])
    group = case["case_id"].split("-")[0]
    groups[group].append({
        "file": gold.split(":")[0] in docs,
        "article": ":".join(gold.split(":")[:2]) in arts,
        "paragraph": gold in result["scores"]["cited_clause_ids"],
        "exposure": exposure[gold],
        "gold": gold,
    })

print("run:", run, "cases:", len(results), "P1 distinct gold:",
      len({v["gold"] for v in groups["p1"]}), "P1 denominator excludes P1K")
for group, rows in sorted(groups.items()):
    print(group, "n=", len(rows), "file/article/paragraph:",
          *(f"{sum(r[key] for r in rows)}/{len(rows)}" for key in ("file", "article", "paragraph")))
    buckets = defaultdict(list)
    for row in rows:
        count = row["exposure"]
        bucket = str(count) if count < 3 else "3-5" if count <= 5 else "6+"
        buckets[bucket].append(row["article"])
    print("  article by exposure:", {
        bucket: f"{sum(hits)}/{len(hits)}"
        for bucket, hits in sorted(buckets.items())
    })

for group in ("p1", "p2", "p3"):
    if group in groups:
        hit = sum(r["article"] for r in groups[group])
        n = len(groups[group])
        print(group, "article vs heldout v1 (17/60), unpaired Fisher:",
              f"{fisher(hit, n-hit, 17, 43):.6g}")
if "p3" in groups:
    for group in ("p1", "p2"):
        if group in groups:
            a, b = groups[group], groups["p3"]
            ah, bh = sum(x["article"] for x in a), sum(x["article"] for x in b)
            print(group, "vs P3 unpaired Fisher:",
                  f"{fisher(ah, len(a)-ah, bh, len(b)-bh):.6g}")
KB.close()
