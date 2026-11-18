"""E002 步骤 6：对每个评测 run 统计补充指标。

用法：uv run python scripts/experiments/e002/eval_stats.py artifacts/eval/run-XXX [run-YYY ...]

输出（每个 run 一行 + 明细）：
- 含〔的题数、含（YYYY-MM-DD）日期版本标签的题数（final_raw）；
- gold 条款全部命中的题数；只命中 gold 文件、条款不对的题数；
- 上海地方文件题（gold 在 6 个上海市法规中的 22 题）的召回；
- 先追问再回答的题数（RE_QUESTION_LINE，同 orchestrator）。
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from tu_assistant.chat.orchestrator import RE_QUESTION_LINE  # noqa: E402

RE_DATE_TAG = re.compile(r"（\d{4}-\d{2}-\d{2}）")
KB = ROOT / "artifacts/kb/kb-20261113-093057.sqlite"


def stats(run_dir: Path) -> dict:
    results = [json.loads(l) for l in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    conn = sqlite3.connect(KB)
    sh_docs = {r[0] for r in conn.execute(
        "select doc_id from legal_documents where title like '%上海%'")}
    conn.close()

    n = len(results)
    has_bracket = has_date = full_hit = doc_only = asked_first = 0
    sh_cases = sh_hit = 0
    sh_recall_sum = 0.0
    for r in results:
        raw = r.get("final_raw") or ""
        gold = set(r["gold"].get("clauses", []))
        cited = set(r["scores"].get("cited_clause_ids") or [])
        has_bracket += "〔" in raw
        has_date += bool(RE_DATE_TAG.search(raw))
        asked_first += bool(RE_QUESTION_LINE.search(raw))
        if gold and gold <= cited:
            full_hit += 1
        elif gold and {c.split(":")[0] for c in cited} & {g.split(":")[0] for g in gold}:
            doc_only += 1
        if gold and {g.split(":")[0] for g in gold} <= sh_docs:
            sh_cases += 1
            rec = r["scores"].get("recall")
            sh_recall_sum += rec if rec is not None else 0.0
            sh_hit += 1 if gold <= cited else 0

    return {
        "run": run_dir.name, "n": n,
        "bracket": has_bracket, "date_tag": has_date,
        "full_hit": full_hit, "doc_only": doc_only,
        "asked_first": asked_first,
        "sh_cases": sh_cases, "sh_full_hit": sh_hit,
        "sh_recall": sh_recall_sum / sh_cases if sh_cases else None,
    }


print(f"{'run':<26} {'n':>3} {'含〔':>4} {'日期':>4} {'全中':>4} {'仅文件':>5} "
      f"{'先追问':>5} {'沪题':>4} {'沪全中':>5} {'沪召回':>7}")
for d in sys.argv[1:]:
    s = stats(ROOT / d if not Path(d).is_absolute() else Path(d))
    shr = f"{s['sh_recall']:.3f}" if s["sh_recall"] is not None else "-"
    print(f"{s['run']:<26} {s['n']:>3} {s['bracket']:>4} {s['date_tag']:>4} "
          f"{s['full_hit']:>4} {s['doc_only']:>5} {s['asked_first']:>5} "
          f"{s['sh_cases']:>4} {s['sh_full_hit']:>5} {shr:>7}")
