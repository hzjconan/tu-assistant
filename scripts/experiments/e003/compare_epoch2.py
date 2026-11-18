"""Compare E003 pre/post results using identical cases and paired exact tests."""

import json
import re
from math import comb
from pathlib import Path

from tu_assistant.kb.numbers import chinese_to_int
from tu_assistant.kb.store import open_kb

ROOT = Path(__file__).resolve().parents[3]
KB = open_kb(ROOT / "artifacts/kb/kb-20261113-093057.sqlite")
DOCS = KB.execute("SELECT doc_id, title FROM legal_documents").fetchall()
SH = {d for d, t in DOCS if "上海" in t}
NUM = r"[0-9零〇一二三四五六七八九十百千]+"
PATTERN = re.compile(rf"《([^》]+)》(?:（[^）]*）)?(?:第({NUM})条)?")
RUNS = {
    "v1": ("run-20261117-081504", "run-20261118-020130"),
    "probe": ("run-20261117-124545", "run-20261118-020647"),
}


def loose(raw):
    arts, docs = set(), set()
    for match in PATTERN.finditer(raw):
        title = match.group(1).replace("中华人民共和国", "")
        candidates = [
            d for d, t in DOCS if t.replace("中华人民共和国", "") == title
        ] or [
            d for d, t in DOCS
            if title in t.replace("中华人民共和国", "")
            or t.replace("中华人民共和国", "") in title
        ]
        if candidates:
            docs.add(candidates[0])
            if match.group(2):
                arts.add(f"{candidates[0]}:a{chinese_to_int(match.group(2))}")
    return arts, docs


def paired_p(before, after):
    gains = sum(not before[k] and after[k] for k in before)
    losses = sum(before[k] and not after[k] for k in before)
    n = gains + losses
    p = min(1.0, 2 * sum(comb(n, i) for i in range(min(gains, losses) + 1)) / 2**n) if n else 1.0
    return gains, losses, p


def load(run):
    path = ROOT / f"artifacts/eval/{run}/results.jsonl"
    return {r["case_id"]: r for line in path.open(encoding="utf-8") if (r := json.loads(line))}


def score(r, key):
    gold = r["gold"]["clauses"][0]
    arts, docs = loose(r["final_raw"])
    if key == "file":
        return gold.split(":")[0] in docs
    if key == "article":
        return ":".join(gold.split(":")[:2]) in arts
    if key == "paragraph":
        return gold in r["scores"]["cited_clause_ids"]
    raise ValueError(key)


for split, (old, new) in RUNS.items():
    if new is None:
        continue
    before, after = load(old), load(new)
    assert before.keys() == after.keys()
    print(f"\n{split}: {old} -> {new}; n={len(before)}")
    for group, ids in [
        ("all", sorted(before)),
        ("Shanghai", sorted(
            k for k, r in before.items()
            if r["gold"]["clauses"][0].split(":")[0] in SH
        )) if split == "v1" else ("P1", sorted(k for k in before if k.startswith("p1-"))),
        *([] if split == "v1" else [
            ("P2", sorted(k for k in before if k.startswith("p2-"))),
            ("P3", sorted(k for k in before if k.startswith("p3-"))),
        ]),
    ]:
        for level in ("file", "article", "paragraph"):
            b = {k: score(before[k], level) for k in ids}
            a = {k: score(after[k], level) for k in ids}
            gained, lost, p = paired_p(b, a)
            print(
                f"{group:8s} {level:9s} {sum(b.values())}/{len(ids)} -> "
                f"{sum(a.values())}/{len(ids)} gains={gained} losses={lost} "
                f"paired_exact_p={p:.5g}"
            )
    if split == "v1":
        for tag, rows in [("old", before), ("new", after)]:
            recalls = [r["scores"]["recall"] for r in rows.values()
                       if r["scores"]["recall"] is not None]
            precisions = [r["scores"]["precision"] for r in rows.values()
                          if r["scores"]["precision"] is not None]
            print(tag, "avg_recall", sum(recalls) / len(recalls) if recalls else None,
                  "avg_precision", sum(precisions) / len(precisions) if precisions else None,
                  "citation_marker", sum("〔" in r["final_raw"] for r in rows.values()))
KB.close()
