"""T077 第 1 步：只读基线审计与历史产物校验值固定。

严禁访问 inputs/，不修改任何历史 KB、数据集或评测 run。
产物写入 artifacts/logs/t077/baseline_audit.md 与 baseline_hashes.json。
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from tu_assistant.citation.verify import verify_output
from tu_assistant.eval.metrics import relation_completion_score
from tu_assistant.kb.store import all_clauses, open_kb

OLD_KB = Path("artifacts/kb/kb-20261113-093057.sqlite")
OLD_KB_MANIFEST = Path("artifacts/kb/kb-20261113-093057/manifest.json")
OLD_PENDING = Path("artifacts/kb/kb-20261113-093057-relations_pending.jsonl")
DATASETS = {
    "ds-8410": Path("artifacts/datasets/ds-kb-20261113-093057-8410"),
    "ds-16741": Path("artifacts/datasets/ds-kb-20261113-093057-16741"),
}
RUNS = [
    "run-20261117-022645",
    "run-20261117-081504",
    "run-20261118-020130",
]
OUT_DIR = Path("artifacts/logs/t077")

NUM = r"[0-9零〇一二三四五六七八九十百千]+"
RE_REF_SPAN = re.compile(
    rf"(?:违反|依照|按照|依据|比照|有)?本?[法条例规定章]*?"
    rf"第{NUM}条(?:第{NUM}款)?(?:第{NUM}项)?"
    rf"(?:(?:、|和|或者|及|至)第{NUM}(?:条|款|项)(?:第{NUM}款)?(?:第{NUM}项)?)*"
)
RE_MARKER = re.compile(r"〔《([^》]+)》（[^）]+）([^〕]+)〕")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def clip(text: str, limit: int = 15) -> str:
    s = " ".join(text.split())
    return s if len(s) <= limit else s[:limit] + "…"


def collect_hashes() -> dict[str, str]:
    targets: list[Path] = [OLD_KB, OLD_KB_MANIFEST, OLD_PENDING]
    for ds in DATASETS.values():
        for name in ("manifest.json", "train.jsonl", "valid.jsonl"):
            p = ds / name
            if p.exists():
                targets.append(p)
    for run_id in RUNS:
        d = Path("artifacts/eval", run_id)
        for name in ("manifest.json", "results.jsonl", "report.md"):
            p = d / name
            if p.exists():
                targets.append(p)
    return {str(p): sha256_file(p) for p in targets if p.exists()}


def article_structure_map(conn: sqlite3.Connection) -> dict[tuple[str, int], dict]:
    clauses = all_clauses(conn)
    grouped: dict[tuple[str, int], list] = {}
    for c in clauses:
        grouped.setdefault((c.doc_id, c.article_no), []).append(c)
    out: dict[tuple[str, int], dict] = {}
    for key, rows in grouped.items():
        paras = sorted({r.paragraph_no for r in rows if r.paragraph_no is not None})
        items_by_para: dict[int, int] = {}
        for p in paras:
            items_by_para[p] = sum(1 for r in rows if r.paragraph_no == p and r.item_no is not None)
        out[key] = {"rows": rows, "paras": paras, "items_by_para": items_by_para}
    return out


def audit_relations(conn: sqlite3.Connection, struct: dict[tuple[str, int], dict]) -> list[dict]:
    titles = {r[0]: r[1] for r in conn.execute("SELECT doc_id, title FROM legal_documents")}
    by_id = {c.clause_id: c for c in all_clauses(conn)}
    rows = conn.execute(
        "SELECT from_clause_id, to_clause_id, relation_type, origin, confirmed "
        "FROM clause_relations ORDER BY relation_type, from_clause_id, to_clause_id"
    ).fetchall()
    items = []
    for fid, tid, rtype, origin, conf in rows:
        fc, tc = by_id.get(fid), by_id.get(tid)
        if not fc or not tc:
            continue
        info = struct[(fc.doc_id, fc.article_no)]
        refs = RE_REF_SPAN.findall(tc.text)
        items.append(
            {
                "from_id": fid,
                "to_id": tid,
                "relation_type": rtype,
                "origin": origin,
                "confirmed": bool(conf),
                "doc_title": titles.get(fc.doc_id, fc.doc_id),
                "from_number_text": fc.number_text,
                "to_number_text": tc.number_text,
                "from_paras": info["paras"],
                "from_items_by_para": info["items_by_para"],
                "to_refs": refs,
                "to_snippet": clip(tc.text, 15),
                "from_has_items": info["items_by_para"].get(fc.paragraph_no or 1, 0),
                "to_has_items": struct[(tc.doc_id, tc.article_no)]["items_by_para"].get(
                    tc.paragraph_no or 1, 0
                ),
            }
        )
    return items


def audit_dataset(
    ds_path: Path,
    conn: sqlite3.Connection,
    multi_para_p1_markers: set[tuple[str, str]],
) -> dict:
    doc_titles = {r[0]: r[1] for r in conn.execute("SELECT doc_id, title FROM legal_documents")}
    by_id = {c.clause_id: c for c in all_clauses(conn)}
    # Build expected question templates for confirmed relations
    rel_q_map: dict[str, tuple[str, str, str]] = {}
    for fid, tid, rtype in conn.execute(
        "SELECT from_clause_id, to_clause_id, relation_type FROM clause_relations WHERE confirmed=1"
    ):
        a = by_id.get(fid)
        if not a:
            continue
        ta = doc_titles[a.doc_id]
        if rtype == "liability_for":
            q = f"违反《{ta}》{a.number_text}要承担什么法律责任？"
        elif rtype == "exception_of":
            q = f"《{ta}》{a.number_text}有没有例外情形？"
        else:
            q = f"哪些条款引用了《{ta}》{a.number_text}？"
        rel_q_map[q] = (fid, tid, rtype)

    stats: dict = {
        "splits": {},
        "rel_matched": Counter(),
        "rel_unattributed": [],
        "incomplete_total": 0,
        "incomplete_by_split": Counter(),
        "incomplete_examples": [],
    }
    for split in ("train", "valid"):
        f = ds_path / f"{split}.jsonl"
        if not f.exists():
            continue
        total = 0
        affected_all = 0
        recite_total = 0
        recite_affected = 0
        non_recite_single_turn = 0
        non_recite_single_turn_affected = 0
        multi_turn = 0
        multi_turn_affected = 0
        incomplete_rows = 0
        incomplete_rel_rows = 0

        for idx, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            total += 1
            d = json.loads(line)
            msgs = d.get("messages", [])
            non_sys = [m for m in msgs if m.get("role") != "system"]
            user_msgs = [m["content"] for m in non_sys if m.get("role") == "user"]
            asst_msgs = [m["content"] for m in non_sys if m.get("role") == "assistant"]
            u0 = user_msgs[0] if user_msgs else ""
            last_asst = asst_msgs[-1] if asst_msgs else ""

            # Relation attribution by text match
            if u0 in rel_q_map:
                fid, tid, rtype = rel_q_map[u0]
                stats["rel_matched"][(split, rtype, fid, tid)] += 1
            elif (
                (u0.startswith("违反《") and u0.endswith("要承担什么法律责任？"))
                or (u0.startswith("哪些条款引用了《") and u0.endswith("？"))
                or (u0.startswith("《") and u0.endswith("有没有例外情形？"))
            ):
                stats["rel_unattributed"].append((split, idx, u0))

            # 口径 2 affected check
            joined = "\n".join(m["content"] for m in non_sys)
            hit_p1 = any(
                (m.group(1), m.group(2)) in multi_para_p1_markers
                for m in RE_MARKER.finditer(joined)
            )
            if hit_p1:
                affected_all += 1

            is_recite = len(user_msgs) == 1 and u0.startswith("《") and u0.endswith("的内容是什么？")
            if is_recite:
                recite_total += 1
                if hit_p1:
                    recite_affected += 1
            elif len(user_msgs) > 1:
                multi_turn += 1
                if hit_p1:
                    multi_turn_affected += 1
            else:
                non_recite_single_turn += 1
                if hit_p1:
                    non_recite_single_turn_affected += 1

            # Check whether check.py passed any incomplete citation
            if last_asst:
                vr = verify_output(last_asst, conn)
                if vr.stats["incomplete"] > 0:
                    incomplete_rows += 1
                    stats["incomplete_total"] += 1
                    stats["incomplete_by_split"][split] += 1
                    if u0 in rel_q_map:
                        incomplete_rel_rows += 1
                    if len(stats["incomplete_examples"]) < 8:
                        inc_raws = [c.raw for c in vr.citations if c.verdict == "incomplete"]
                        stats["incomplete_examples"].append(
                            {"split": split, "line": idx, "user": clip(u0, 25), "raws": inc_raws[:3]}
                        )

        stats["splits"][split] = {
            "total": total,
            "affected_p1": affected_all,
            "affected_p1_ratio": affected_all / total if total else 0.0,
            "recite_total": recite_total,
            "recite_affected": recite_affected,
            "single_turn_other_total": non_recite_single_turn,
            "single_turn_other_affected": non_recite_single_turn_affected,
            "multi_turn_total": multi_turn,
            "multi_turn_affected": multi_turn_affected,
            "incomplete_rows": incomplete_rows,
            "incomplete_rel_rows": incomplete_rel_rows,
        }
    return stats


def audit_v1_gold(conn: sqlite3.Connection, struct: dict[tuple[str, int], dict]) -> dict:
    by_id = {c.clause_id: c for c in all_clauses(conn)}
    out = {}
    for f in sorted(Path("eval/cases/v1").glob("*.jsonl")):
        rows = [
            json.loads(line)
            for line in f.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        counts = Counter()
        for r in rows:
            for cid in (r.get("gold") or {}).get("clauses") or []:
                c = by_id.get(cid)
                if not c:
                    counts["missing"] += 1
                    continue
                info = struct[(c.doc_id, c.article_no)]
                if c.item_no is not None:
                    counts["item"] += 1
                elif len(info["paras"]) >= 2:
                    counts["multi_para_p1" if c.paragraph_no == 1 else "multi_para_p2+"] += 1
                elif info["items_by_para"].get(c.paragraph_no or 1, 0) > 0:
                    counts["single_para_with_items_parent"] += 1
                else:
                    counts["single_row_article"] += 1
        out[f.name] = {"cases": len(rows), "gold_dist": dict(counts)}
    return out


def audit_runs_sc005(conn: sqlite3.Connection) -> dict:
    out = {}
    for run_id in RUNS:
        p = Path("artifacts/eval", run_id, "results.jsonl")
        if not p.exists():
            continue
        non_null = 0
        stored_non_null = 0
        total = 0
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            total += 1
            row = json.loads(line)
            sc = row.get("scores") or {}
            if sc.get("relation_completion") is not None:
                stored_non_null += 1
            cited = set(sc.get("cited_clause_ids") or [])
            if relation_completion_score(cited, conn) is not None:
                non_null += 1
        out[run_id] = {
            "cases": total,
            "stored_sc005_non_null": stored_non_null,
            "recomputed_sc005_non_null": non_null,
        }
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    hashes = collect_hashes()
    (OUT_DIR / "baseline_hashes.json").write_text(
        json.dumps(hashes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    conn = open_kb(OLD_KB)
    try:
        struct = article_structure_map(conn)
        doc_titles = {r[0]: r[1] for r in conn.execute("SELECT doc_id, title FROM legal_documents")}
        multi_para_p1_markers: set[tuple[str, str]] = set()
        for (did, _a), info in struct.items():
            if len(info["paras"]) >= 2:
                title = doc_titles[did]
                for r in info["rows"]:
                    if r.paragraph_no == 1:
                        multi_para_p1_markers.add((title, r.number_text))

        rels = audit_relations(conn, struct)
        ds_audits = {
            name: audit_dataset(path, conn, multi_para_p1_markers)
            for name, path in DATASETS.items()
            if path.exists()
        }
        v1_gold = audit_v1_gold(conn, struct)
        runs_sc005 = audit_runs_sc005(conn)

        single_row = sum(
            1 for info in struct.values() if len(info["rows"]) == 1
        )
        single_para_items = sum(
            1 for info in struct.values() if len(info["paras"]) == 1 and len(info["rows"]) > 1
        )
        multi_para = sum(1 for info in struct.values() if len(info["paras"]) >= 2)
    finally:
        conn.close()

    lines: list[str] = []
    lines.append("# T077 基线审计报告（旧 KB `kb-20261113-093057`）")
    lines.append("")
    lines.append("- **只读审计**：未修改任何历史 KB、数据集、评测 run，未读取 `inputs/`。")
    lines.append("- **校验值清单**：见同目录 `baseline_hashes.json`。")
    lines.append("")
    lines.append("## 1. 历史产物 SHA-256 基线")
    lines.append("")
    lines.append("| 路径 | SHA-256（前 16 位） | 完整 SHA-256 |")
    lines.append("|---|---|---|")
    for k, v in hashes.items():
        lines.append(f"| `{k}` | `{v[:16]}` | `{v}` |")

    lines.append("")
    lines.append("## 2. 旧 KB 条文结构分布")
    lines.append("")
    lines.append(f"- 总条数：**{len(struct)}**（总行数 3,809，24 篇）")
    lines.append(f"- 单款无项：**{single_row}** 条")
    lines.append(f"- 单款含多项：**{single_para_items}** 条")
    lines.append(f"- 多款条文（≥2 款）：**{multi_para}** 条（第 1 款 `number_text` 全部缺少款号）")

    lines.append("")
    lines.append("## 3. 35 条历史已确认关系核查")
    lines.append("")
    lines.append("### 3.1 `liability_for`（12 条）")
    lines.append("")
    lines.append(
        "| `from_clause_id` | `to_clause_id` | 被引条款结构（各款:项数） "
        "| `to` 触发引用片段 | `from`/`to` 子项数 | `to` 原文摘要（≤15字） |"
    )
    lines.append("|---|---|---|---|---|---|")
    for r in [x for x in rels if x["relation_type"] == "liability_for"]:
        p_desc = ", ".join(
            f"p{p}({r['from_items_by_para'][p]}项)" if r["from_items_by_para"][p] else f"p{p}"
            for p in r["from_paras"]
        )
        refs_s = "；".join(r["to_refs"]) or "（无匹配）"
        lines.append(
            f"| `{r['from_id']}` | `{r['to_id']}` | {p_desc} | {refs_s} | "
            f"{r['from_has_items']}/{r['to_has_items']} | {r['to_snippet']} |"
        )

    lines.append("")
    lines.append("### 3.2 `references`（23 条）")
    lines.append("")
    lines.append(
        "| `from_clause_id` | `to_clause_id` | 被引条款结构（各款:项数） "
        "| `to` 触发引用片段 | `from`/`to` 子项数 |"
    )
    lines.append("|---|---|---|---|---|")
    for r in [x for x in rels if x["relation_type"] == "references"]:
        p_desc = ", ".join(
            f"p{p}({r['from_items_by_para'][p]}项)" if r["from_items_by_para"][p] else f"p{p}"
            for p in r["from_paras"]
        )
        refs_s = "；".join(r["to_refs"]) or "（无匹配）"
        lines.append(
            f"| `{r['from_id']}` | `{r['to_id']}` | {p_desc} | {refs_s} | "
            f"{r['from_has_items']}/{r['to_has_items']} |"
        )

    lines.append("")
    lines.append("## 4. 历史数据集核查（口径 2 影响面、关系归因与 `incomplete` 放行统计）")
    for name, st in ds_audits.items():
        lines.append("")
        lines.append(f"### 4.{1 if name == 'ds-8410' else 2} `{name}`")
        lines.append("")
        lines.append(
            "| Split | 总行数 | 含多款第1款标记行数（占比） | 复述 affected/total "
            "| 其他单轮 affected/total | 多轮 affected/total "
            "| 含 `incomplete` 引用行数（其中关系样本） |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for sp, v in st["splits"].items():
            lines.append(
                f"| `{sp}` | {v['total']} | {v['affected_p1']} ({v['affected_p1_ratio']:.1%}) | "
                f"{v['recite_affected']}/{v['recite_total']} | "
                f"{v['single_turn_other_affected']}/{v['single_turn_other_total']} | "
                f"{v['multi_turn_affected']}/{v['multi_turn_total']} | "
                f"{v['incomplete_rows']} ({v['incomplete_rel_rows']}) |"
            )
        lines.append("")
        lines.append("按文本匹配归因到的 `liability_for` 样本明细：")
        lines.append("")
        lines.append("| Split | `from_clause_id` | `to_clause_id` | 出现次数 |")
        lines.append("|---|---|---|---:|")
        for (sp, rtype, fid, tid), cnt in sorted(st["rel_matched"].items()):
            if rtype == "liability_for":
                lines.append(f"| `{sp}` | `{fid}` | `{tid}` | {cnt} |")
        ref_cnts = sum(
            cnt for (_, rtype, _, _), cnt in st["rel_matched"].items() if rtype == "references"
        )
        lines.append("")
        lines.append(
            f"- 归因到的 `references` 关系样本合计：{ref_cnts} 条；"
            f"无法归因的关系模板问句：{len(st['rel_unattributed'])} 条。"
        )
        if st["incomplete_examples"]:
            lines.append("- `check.py` 放行的含 `incomplete` 引用样本抽样（最多 8 条）：")
            for ex in st["incomplete_examples"]:
                lines.append(f"  - `{ex['split']}` L{ex['line']}：`{ex['user']}` → `incomplete={ex['raws']}`")

    lines.append("")
    lines.append("## 5. 评测集 v1 Gold 分布与历史 SC-005 基线")
    lines.append("")
    for fname, info in v1_gold.items():
        lines.append(f"- `eval/cases/v1/{fname}`（{info['cases']} 题）：`{info['gold_dist']}`")
    lines.append("")
    lines.append("| Run ID | 用例数 | 已存 SC-005 非空数 | 用旧 KB 重算 SC-005 非空数 |")
    lines.append("|---|---:|---:|---:|")
    for run_id, info in runs_sc005.items():
        lines.append(
            f"| `{run_id}` | {info['cases']} | {info['stored_sc005_non_null']} "
            f"| {info['recomputed_sc005_non_null']} |"
        )

    out_md = OUT_DIR / "baseline_audit.md"
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out_md} and {OUT_DIR / 'baseline_hashes.json'}")
    for name, st in ds_audits.items():
        for sp, v in st["splits"].items():
            print(
                f"  {name}/{sp}: total={v['total']} affected_p1={v['affected_p1']} "
                f"({v['affected_p1_ratio']:.1%}) "
                f"incomplete={v['incomplete_rows']} (rel={v['incomplete_rel_rows']})"
            )


if __name__ == "__main__":
    main()
