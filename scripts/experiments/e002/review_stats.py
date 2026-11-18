"""E002 复审：按"文件 / 条 / 款"三级重算定位，并统计 gold 条款的训练曝光。

用法：uv run python scripts/experiments/e002/review_stats.py > artifacts/logs/e002/review-stats.txt

- 宽松解析：只认 `《文件名》第N条`（〔〕可有可无），基座与 adapter 用同一口径，可横向比较；
- 款级 = report.md 的严格口径（scores.cited_clause_ids ⊇ gold）；
- 训练曝光：引用了该条款的 train 样本数（最后一个 assistant 段经 verify_output 解析，
  样本内去重；consult 等类别在 train 中已 ×2 过采样，计数含过采样副本）；
- Fisher 精确检验（双侧）用于判断小样本差异是否显著。
"""

import json
import re
import sys
from collections import Counter
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from tu_assistant.citation.verify import verify_output  # noqa: E402
from tu_assistant.kb.numbers import chinese_to_int  # noqa: E402
from tu_assistant.kb.store import open_kb  # noqa: E402

KB = open_kb(ROOT / "artifacts/kb/kb-20261113-093057.sqlite")
DOCS = KB.execute("select doc_id, title from legal_documents").fetchall()
SH = {d for d, t in DOCS if "上海" in t}
CASES = [json.loads(l) for l in (ROOT / "eval/cases/v1/reviewed.jsonl").read_text("utf-8").splitlines() if l.strip()]
GOLD = {c["case_id"]: c["gold"]["clauses"][0] for c in CASES}
NUM = r"[0-9零〇一二三四五六七八九十百千]+"
RE_LOOSE = re.compile(rf"《([^》]+)》(?:（[^）]*）)?(?:第({NUM})条)?")

RUNS = [
    ("run-20261117-022645", "7B 基座（E002 前误测）"),
    ("run-20261117-082903", "7B ckpt-500"),
    ("run-20261117-085434", "7B ckpt-4000"),
    ("run-20261117-081504", "7B 训满"),
    ("run-20261115-025552", "1.5B 基座（E002 前误测）"),
    ("run-20261117-085921", "1.5B adapter + v2"),
    ("run-20261117-090638", "1.5B adapter 无 sysp"),
]


def norm(t: str) -> str:
    return t.replace("中华人民共和国", "")


def loose(raw: str) -> tuple[set[str], set[str]]:
    arts, docs = set(), set()
    for m in RE_LOOSE.finditer(raw):
        t = norm(m.group(1))
        cand = [d for d, tt in DOCS if norm(tt) == t] or [
            d for d, tt in DOCS if t in norm(tt) or norm(tt) in t
        ]
        if cand:
            docs.add(cand[0])
            if m.group(2):
                arts.add(f"{cand[0]}:a{chinese_to_int(m.group(2))}")
    return arts, docs


def fisher(a: int, b: int, c: int, d: int) -> float:
    n, r1, c1 = a + b + c + d, a + b, a + c
    p = lambda x: comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1)  # noqa: E731
    p0 = p(a)
    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    return sum(p(x) for x in range(lo, hi + 1) if p(x) <= p0 + 1e-12)


def art_of(cid: str) -> str:
    return ":".join(cid.split(":")[:2])


print("## 1. 文件 / 条 / 款 三级定位（60 题；沪 = gold 在上海文件的 22 题）\n")
print(f"{'run':<22} {'模型':<24} {'文件':>5} {'条':>5} {'款(严格)':>8} {'沪文件':>6} {'沪条':>5} {'沪款':>5}")
funnel = {}
for run, label in RUNS:
    res = [json.loads(l) for l in (ROOT / f"artifacts/eval/{run}/results.jsonl").read_text("utf-8").splitlines() if l.strip()]
    f = Counter()
    for x in res:
        g = x["gold"]["clauses"][0]
        gd, ga = g.split(":")[0], art_of(g)
        arts, docs = loose(x["final_raw"])
        strict = g in set(x["scores"].get("cited_clause_ids") or [])
        f["doc"] += gd in docs
        f["art"] += ga in arts
        f["para"] += strict
        if gd in SH:
            f["sh_doc"] += gd in docs
            f["sh_art"] += ga in arts
            f["sh_para"] += strict
    funnel[run] = f
    print(f"{run:<22} {label:<24} {f['doc']:>5} {f['art']:>5} {f['para']:>8} "
          f"{f['sh_doc']:>6} {f['sh_art']:>5} {f['sh_para']:>5}")

print("\n## 2. gold 条款的训练曝光（artifacts/datasets/latest/train.jsonl）\n")
gset = set(GOLD.values())
exp = Counter()
n_train = 0
for line in (ROOT / "artifacts/datasets/latest/train.jsonl").read_text("utf-8").splitlines():
    n_train += 1
    a = json.loads(line)["messages"][-1]["content"]
    if "〔" not in a:
        continue
    for cid in {c.resolved_clause_id for c in verify_output(a, KB).citations} & gset:
        exp[cid] += 1
freq = sorted(exp[g] for g in gset)
print(f"train 样本数 {n_train}；KB 条款行数 {KB.execute('select count(*) from clauses').fetchone()[0]}")
print(f"60 个 gold 条款曝光：0 次 {freq.count(0)} 个；中位 {freq[len(freq)//2]}；最大 {freq[-1]}")
print("上海 gold 曝光：", sorted(exp[g] for g in gset if g.split(":")[0] in SH))
print("非沪 gold 曝光：", sorted(exp[g] for g in gset if g.split(":")[0] not in SH))
full = {json.loads(l)["case_id"]: json.loads(l) for l in (ROOT / "artifacts/eval/run-20261117-081504/results.jsonl").read_text("utf-8").splitlines() if l.strip()}
hit = sorted(exp[g] for cid, g in GOLD.items() if g in full[cid]["scores"]["cited_clause_ids"])
miss = sorted(exp[g] for cid, g in GOLD.items() if g not in full[cid]["scores"]["cited_clause_ids"])
print(f"7B 训满：命中题的 gold 曝光 {hit}；未命中题曝光中位 {miss[len(miss)//2]}")

print("\n## 3. 显著性（Fisher 双侧）\n")
b, c4, fl = funnel["run-20261117-022645"], funnel["run-20261117-085434"], funnel["run-20261117-081504"]
for name, a, n1, x, n2 in [
    ("条级：基座 vs 训满", b["art"], 60, fl["art"], 60),
    ("条级：ckpt-4000 vs 训满", c4["art"], 60, fl["art"], 60),
    ("款级：ckpt-4000 vs 训满", c4["para"], 60, fl["para"], 60),
    ("款级：训满 沪 vs 非沪", fl["sh_para"], 22, fl["para"] - fl["sh_para"], 38),
]:
    print(f"{name}: {a}/{n1} vs {x}/{n2}  p={fisher(a, n1 - a, x, n2 - x):.4g}")
