"""T077 第 4.3 & 第 5 步：导入对账与下游差异核对（关系样本、SC-005、文章素材）。

产物写入 artifacts/logs/t077/：
- relation_samples_diff.md
- sc005_diff.md

不修改任何历史 KB、数据集或评测 run。
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from itertools import combinations
from pathlib import Path

from tu_assistant.citation.verify import verify_output
from tu_assistant.eval.metrics import relation_completion_score
from tu_assistant.kb.store import all_clauses, open_kb
from tu_assistant.synth.articles import ArticleStats, _materials
from tu_assistant.synth.check import CheckStats, check_sample
from tu_assistant.synth.knowledge import doc_titles, relation_samples

OLD_KB_VER = "kb-20261113-093057"
NEW_KB_VER = "kb-20261119-045641"
ARTIFACTS = Path("artifacts")
OUT_DIR = Path("artifacts/logs/t077")
RUNS = [
    "run-20261117-022645",
    "run-20261117-081504",
    "run-20261118-020130",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def clip(text: str, limit: int = 15) -> str:
    s = " ".join(text.split())
    return s if len(s) <= limit else s[:limit] + "…"


def verify_historical_hashes() -> list[str]:
    hashes = json.loads((OUT_DIR / "baseline_hashes.json").read_text(encoding="utf-8"))
    bad = []
    for p, expected in hashes.items():
        if sha256_file(Path(p)) != expected:
            bad.append(p)
    return bad


def reconcile_import(old_conn, new_conn) -> dict:
    old_edges = {
        (r[0], r[1], r[2])
        for r in old_conn.execute(
            "SELECT from_clause_id, to_clause_id, relation_type "
            "FROM clause_relations WHERE confirmed=1"
        )
    }
    new_edges = {
        (r[0], r[1], r[2])
        for r in new_conn.execute(
            "SELECT from_clause_id, to_clause_id, relation_type "
            "FROM clause_relations WHERE confirmed=1"
        )
    }
    return {
        "old_total": len(old_edges),
        "new_total": len(new_edges),
        "old_by_type": dict(Counter(k[2] for k in old_edges)),
        "new_by_type": dict(Counter(k[2] for k in new_edges)),
        "revoked": sorted(old_edges - new_edges),
        "added": sorted(new_edges - old_edges),
        "kept": sorted(old_edges & new_edges),
    }


def _ds_relation_counts(ds_dir: Path, old_conn) -> dict[tuple[str, str], dict[str, int]]:
    """从历史数据集按问题文本统计各旧关系样本的实际落盘情况（split 与出现次数）。"""
    titles = doc_titles(old_conn)
    by_id = {c.clause_id: c for c in all_clauses(old_conn)}
    q_to_key: dict[str, tuple[str, str]] = {}
    for fid, tid, rt in old_conn.execute(
        "SELECT from_clause_id, to_clause_id, relation_type "
        "FROM clause_relations WHERE confirmed=1"
    ):
        a = by_id.get(fid)
        if not a:
            continue
        ta, _ = titles[a.doc_id]
        if rt == "liability_for":
            q = f"违反《{ta}》{a.number_text}要承担什么法律责任？"
        elif rt == "exception_of":
            q = f"《{ta}》{a.number_text}有没有例外情形？"
        else:
            q = f"哪些条款引用了《{ta}》{a.number_text}？"
        q_to_key[q] = (fid, tid)

    out: dict[tuple[str, str], dict[str, int]] = {}
    for sp in ("train", "valid"):
        f = ds_dir / f"{sp}.jsonl"
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            u = next((m["content"] for m in d["messages"] if m["role"] == "user"), "")
            key = q_to_key.get(u)
            if key:
                out.setdefault(key, {"train": 0, "valid": 0})[sp] += 1
    return out


def build_relation_samples_diff(old_conn, new_conn, recon: dict) -> None:
    old_edges_ordered = old_conn.execute(
        "SELECT from_clause_id, to_clause_id, relation_type FROM clause_relations "
        "WHERE confirmed=1 ORDER BY relation_type, from_clause_id, to_clause_id"
    ).fetchall()
    new_edges_ordered = new_conn.execute(
        "SELECT from_clause_id, to_clause_id, relation_type FROM clause_relations "
        "WHERE confirmed=1 ORDER BY relation_type, from_clause_id, to_clause_id"
    ).fetchall()

    old_samples = relation_samples(old_conn, doc_titles(old_conn))
    new_samples = relation_samples(new_conn, doc_titles(new_conn))

    old_chk = CheckStats()
    old_map: dict[tuple[str, str, str], dict] = {}
    for edge, s in zip(old_edges_ordered, old_samples, strict=True):
        ok = check_sample(
            s["messages"][1]["content"],
            old_conn,
            old_chk,
            require_citation=True,
            expected_clause_ids=set(s["meta"]["clause_ids"]),
        )
        old_map[tuple(edge)] = {"sample": s, "check_ok": ok}

    new_chk = CheckStats()
    new_map: dict[tuple[str, str, str], dict] = {}
    for edge, s in zip(new_edges_ordered, new_samples, strict=True):
        ok = check_sample(
            s["messages"][1]["content"],
            new_conn,
            new_chk,
            require_citation=True,
            expected_clause_ids=set(s["meta"]["clause_ids"]),
        )
        new_map[tuple(edge)] = {"sample": s, "check_ok": ok}

    ds8410_hits = _ds_relation_counts(
        ARTIFACTS / "datasets/ds-kb-20261113-093057-8410", old_conn
    )
    ds16741_hits = _ds_relation_counts(
        ARTIFACTS / "datasets/ds-kb-20261113-093057-16741", old_conn
    )

    # 共享同一责任条款（to_clause_id）的 liability_for 分布（供 T057 决定是否合并）
    liab_by_to: dict[str, list[str]] = {}
    for (fid, tid, rt) in sorted(new_map):
        if rt == "liability_for":
            liab_by_to.setdefault(tid, []).append(fid)
    shared_to = {k: v for k, v in liab_by_to.items() if len(v) >= 2}

    # 文章素材统计对比
    old_art_stats = ArticleStats()
    old_pairs = _materials(old_conn, old_art_stats)
    new_art_stats = ArticleStats()
    new_pairs = _materials(new_conn, new_art_stats)

    def _same_doc_multi_pairs(pairs) -> dict[str, int]:
        by_doc: dict[str, list] = {}
        for p in pairs:
            by_doc.setdefault(p.doc_id, []).append(p)
        out = {}
        for did, lst in sorted(by_doc.items()):
            # 同文件内不同 basis/liability 的成对组合数
            combos = [
                (a, b)
                for a, b in combinations(lst, 2)
                if a.basis != b.basis and a.liability != b.liability
            ]
            if combos:
                out[did] = len(combos)
        return out

    old_multi = _same_doc_multi_pairs(old_pairs)
    new_multi = _same_doc_multi_pairs(new_pairs)

    # 口径 2 影响的 KB 复述样本数（多款条文第一款及其子项）
    old_nt = dict(old_conn.execute("SELECT clause_id, number_text FROM clauses"))
    new_nt = dict(new_conn.execute("SELECT clause_id, number_text FROM clauses"))
    nt_changed_ids = {cid for cid in old_nt if old_nt[cid] != new_nt[cid]}
    old_recite_eligible = [c for c in all_clauses(old_conn) if len(c.text) >= 10]
    recite_affected = sum(1 for c in old_recite_eligible if c.clause_id in nt_changed_ids)

    md: list[str] = [
        f"# T077 知识类关系样本与文章素材对比（`{OLD_KB_VER}` vs `{NEW_KB_VER}`）",
        "",
        "## 1. 导入对账与样本检查汇总",
        "",
        f"- 旧 KB 已确认关系：**{recon['old_total']}** 条（{recon['old_by_type']}）",
        f"- 新 KB 已确认关系：**{recon['new_total']}** 条（{recon['new_by_type']}）"
        f"（撤销 {len(recon['revoked'])}，新增 {len(recon['added'])}，保留 {len(recon['kept'])}）",
        f"- 旧 KB `relation_samples` + `check_sample`："
        f"保留 **{old_chk.kept}** / 丢弃 **{old_chk.dropped}**（{old_chk.reasons}）",
        f"- 新 KB `relation_samples` + `check_sample`："
        f"保留 **{new_chk.kept}** / 丢弃 **{new_chk.dropped}**（{new_chk.reasons}）",
        "",
        "## 2. 口径 2 影响面统计（多款条文第 1 款补齐 `第1款`）",
        "",
        f"- KB 内 `number_text` 变化行数：**{len(nt_changed_ids)}** / 3,809 行（覆盖 787 条多款条文）",
        f"- `knowledge.recitation_samples`（长度 ≥10）受影响条数：**{recite_affected}** / "
        f"{len(old_recite_eligible)}（{recite_affected / len(old_recite_eligible):.1%}）",
        "- 历史数据集受影响占比（来自 `baseline_audit.md`）："
        "`ds-8410/train` **1,556 / 8,921（17.4%）**，未超过 20% 阈值；"
        "`ds-16741/train` **2,618 / 19,195（13.6%）**。",
        "",
        "## 3. 关系样本逐条增删改明细",
        "",
        f"### 3.1 撤销删除（{len(recon['revoked'])} 条，均为旧错款 `liability_for`）",
        "",
        "| `from_clause_id` | `to_clause_id` | 旧问句 | `ds-8410` (train/valid) | `ds-16741` (train/valid) |",
        "|---|---|---|---|---|",
    ]
    for fid, tid, rt in recon["revoked"]:
        q = old_map[(fid, tid, rt)]["sample"]["messages"][0]["content"]
        c8 = ds8410_hits.get((fid, tid), {"train": 0, "valid": 0})
        c16 = ds16741_hits.get((fid, tid), {"train": 0, "valid": 0})
        md.append(
            f"| `{fid}` | `{tid}` | {q} | {c8['train']}/{c8['valid']} | {c16['train']}/{c16['valid']} |"
        )

    md.extend(
        [
            "",
            f"### 3.2 新增（{len(recon['added'])} 条，均为第一批审定 `liability_for`）",
            "",
            "| `from_clause_id` | `to_clause_id` | 新问句 | `check_sample` |",
            "|---|---|---|---|",
        ]
    )
    for fid, tid, rt in recon["added"]:
        info = new_map[(fid, tid, rt)]
        q = info["sample"]["messages"][0]["content"]
        md.append(f"| `{fid}` | `{tid}` | {q} | {'PASS' if info['check_ok'] else 'DROP'} |")

    changed_kept = []
    for k in recon["kept"]:
        o_msg = old_map[k]["sample"]["messages"]
        n_msg = new_map[k]["sample"]["messages"]
        if o_msg != n_msg:
            changed_kept.append((k, o_msg[0]["content"], n_msg[0]["content"]))

    md.extend(
        [
            "",
            f"### 3.3 保留但问句或答句标记更新（{len(changed_kept)} / {len(recon['kept'])} 条，"
            "因多款第 1 款显式带 `第1款`）",
            "",
            "| `from_clause_id` | `to_clause_id` | 类型 | 旧问句 | 新问句 |",
            "|---|---|---|---|---|",
        ]
    )
    for (fid, tid, rt), oq, nq in changed_kept:
        md.append(f"| `{fid}` | `{tid}` | `{rt}` | {oq} | {nq} |")

    md.extend(
        [
            "",
            "## 4. 共享同一责任条款的 `liability_for` 分布（供 T057 决定是否合并问答）",
            "",
            f"新 KB 共有 **{len(liab_by_to)}** 个不同的责任条款，"
            f"其中 **{len(shared_to)}** 个责任条款被多条依据指向：",
            "",
            "| 责任条款 `to_clause_id` | 指向它的依据条数 | `from_clause_id` 列表 |",
            "|---|---:|---|",
        ]
    )
    for tid, fids in sorted(shared_to.items()):
        md.append(f"| `{tid}` | {len(fids)} | {', '.join(f'`{x}`' for x in fids)} |")

    md.extend(
        [
            "",
            "## 5. 普法文章素材池对比（`synth/articles._materials`，供 T057）",
            "",
            "| 指标 | 旧 KB `kb-20261113-093057` | 新 KB `kb-20261119-045641` |",
            "|---|---:|---:|",
            "| 已确认 `liability_for` 总数 | 12 | 26 |",
            f"| `paragraph_mismatch` 跳过数 | {old_art_stats.materials['paragraph_mismatch']} | "
            f"**{new_art_stats.materials['paragraph_mismatch']}** |",
            f"| `material_unresolved` 跳过数 | {old_art_stats.materials['material_unresolved']} | "
            f"{new_art_stats.materials['material_unresolved']} |",
            f"| 可用责任素材对数（`eligible`） | {len(old_pairs)} | **{len(new_pairs)}** |",
            f"| 同文件不同责任条文的成对多违法组合数 | {sum(old_multi.values())}（{old_multi}） | "
            f"**{sum(new_multi.values())}**（{new_multi}） |",
            "",
            "> 注：上表多违法组合仅为同文件内不同依据+不同责任条文的候选组合数；"
            "“两项行为能否自然发生在同一纠纷场景”仍按 T057 执行单留待 T057 人工审阅。",
        ]
    )

    out_path = OUT_DIR / "relation_samples_diff.md"
    out_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    print(
        f"  relation_samples check: old={old_chk.kept}/{old_chk.total} "
        f"new={new_chk.kept}/{new_chk.total}"
    )
    old_mm = old_art_stats.materials["paragraph_mismatch"]
    new_mm = new_art_stats.materials["paragraph_mismatch"]
    print(
        f"  article materials: old={len(old_pairs)} (mismatch={old_mm}) -> "
        f"new={len(new_pairs)} (mismatch={new_mm})"
    )


def build_sc005_diff(old_conn, new_conn) -> None:
    # 1. 历史 run 重算 + v1 gold 交集检查
    run_rows_summary = []
    for run_id in RUNS:
        p = ARTIFACTS / "eval" / run_id / "results.jsonl"
        old_hits, new_hits = [], []
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            cited = set((row.get("scores") or {}).get("cited_clause_ids") or [])
            s_old = relation_completion_score(cited, old_conn)
            s_new = relation_completion_score(cited, new_conn)
            if s_old is not None:
                old_hits.append((row["case_id"], sorted(cited), s_old))
            if s_new is not None:
                new_hits.append((row["case_id"], sorted(cited), s_new))
        run_rows_summary.append((run_id, old_hits, new_hits))

    # 检查新 26 对 liability_for 的 from/to 与 v1 gold 的交集
    new_liab_from = {
        r[0]
        for r in new_conn.execute(
            "SELECT from_clause_id FROM clause_relations WHERE confirmed=1 AND relation_type='liability_for'"
        )
    }
    new_liab_to = {
        r[0]
        for r in new_conn.execute(
            "SELECT to_clause_id FROM clause_relations WHERE confirmed=1 AND relation_type='liability_for'"
        )
    }
    v1_overlap = {}
    for f in sorted(Path("eval/cases/v1").glob("*.jsonl")):
        ov_from, ov_to = [], []
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            for cid in (d.get("gold") or {}).get("clauses") or []:
                if cid in new_liab_from:
                    ov_from.append((d["case_id"], cid))
                if cid in new_liab_to:
                    ov_to.append((d["case_id"], cid))
        v1_overlap[f.name] = {"from": ov_from, "to": ov_to}

    # 2. 固定诊断例：先固定引用 ID 只换关系表，再走完整 verify_output + SC-005
    # 阶段 A：固定 cited_clause_ids（只换关系表）
    fixed_id_cases = [
        (
            "D1-错款旧端点无责任",
            "仅引用第十条第1款（旧错边起点），未引第三十八条",
            {"40124ed5e360acee:a10:p1"},
        ),
        (
            "D2-错款修正新端点漏补责任",
            "引用第十条第2款（修正后正确起点），未引第三十八条",
            {"40124ed5e360acee:a10:p2"},
        ),
        (
            "D3-错款修正新端点补齐责任",
            "引用第十条第2款 + 第三十八条",
            {"40124ed5e360acee:a10:p2", "40124ed5e360acee:a38:p1"},
        ),
        (
            "D4-整条展开新增第2款漏补责任",
            "引用第二十一条第2款（整条展开新增），未引第四十条第1款",
            {"40124ed5e360acee:a21:p2"},
        ),
        (
            "D5-整条多款共享同一责任条款去重",
            "同时引用第二十一条第1款 + 第2款 + 工会法第三条第1款，仅补齐第四十条第1款（未补第五十一条）",
            {
                "40124ed5e360acee:a21:p1",
                "40124ed5e360acee:a21:p2",
                "4b6c1f293f717293:a3:p1",
                "40124ed5e360acee:a40:p1",
            },
        ),
        (
            "D6-区间新增条款补齐责任",
            "引用公司法第一百八十三条 + 第一百八十六条",
            {"f603773a50aeb8a5:a183:p1", "f603773a50aeb8a5:a186:p1"},
        ),
    ]

    # 阶段 B：走完整 verify_output → SC-005（区分解析变化与关系变化）
    full_text_cases = [
        (
            "T1-显式新写法第10条第2款+第38条",
            "〔《上海市集体合同条例》（2015-06-18）第十条第2款〕\n\n"
            "〔《上海市集体合同条例》（2015-06-18）第三十八条〕",
        ),
        (
            "T2-显式新写法第21条第1款+第2款+第40条第1款",
            "〔《上海市集体合同条例》（2015-06-18）第二十一条第1款〕\n\n"
            "〔《上海市集体合同条例》（2015-06-18）第二十一条第2款〕\n\n"
            "〔《上海市集体合同条例》（2015-06-18）第四十条第1款〕",
        ),
        (
            "T3-旧写法多款省略款号且无引文（口径C判incomplete）",
            "〔《上海市集体合同条例》（2015-06-18）第二十一条〕\n\n"
            "〔《上海市集体合同条例》（2015-06-18）第四十条第1款〕",
        ),
        (
            "T4-单款含项省略款号无引文（口径1修复）+对应责任",
            "〔《中华人民共和国妇女权益保障法》（2023-01-01）第四十三条〕\n\n"
            "〔《中华人民共和国妇女权益保障法》（2023-01-01）第八十三条〕",
        ),
    ]

    md: list[str] = [
        f"# T077 SC-005 前后对比与固定诊断例验证（`{OLD_KB_VER}` vs `{NEW_KB_VER}`）",
        "",
        "## 1. 历史评测 run 重算与 v1 Gold 交集",
        "",
        "| Run ID | 旧 KB SC-005 非空题数 | 新 KB SC-005 非空题数 | 说明 |",
        "|---|---:|---:|---|",
    ]
    for run_id, old_hits, new_hits in run_rows_summary:
        if not old_hits and not new_hits:
            note = "历史 run 未精确命中已确认责任关系起点"
        else:
            detail = "；".join(f"{cid} 引用 {cids} → SC-005={sc:.3f}" for cid, cids, sc in new_hits)
            note = f"新 KB 整条展开生效：{detail}"
        md.append(f"| `{run_id}` | {len(old_hits)} | {len(new_hits)} | {note} |")

    md.extend(["", "新 KB 26 条已确认 `liability_for` 与 `eval/cases/v1/*.jsonl` gold 的交集：", ""])
    for fname, ov in v1_overlap.items():
        md.append(
            f"- `eval/cases/v1/{fname}`：与 `from` 交集 **{len(ov['from'])}** 条（{ov['from']}）；"
            f"与 `to` 交集 **{len(ov['to'])}** 条（{ov['to']}）。"
        )

    md.extend(
        [
            "",
            "## 2. 固定诊断例 A：固定 `cited_clause_ids`，只换关系表",
            "",
            "| 诊断例 | 场景说明 | 旧 KB SC-005 | 新 KB SC-005 | 变化解读 |",
            "|---|---|---:|---:|---|",
        ]
    )
    for cid_name, desc, cids in fixed_id_cases:
        s_old = relation_completion_score(cids, old_conn)
        s_new = relation_completion_score(cids, new_conn)
        fmt = lambda v: "None" if v is None else f"{v:.3f}"  # noqa: E731
        if cid_name.startswith("D1"):
            note = "旧错边已撤销，引用无关的第1款不再误判漏补责任"
        elif cid_name.startswith("D2"):
            note = "修正后能准确检出漏补第38条责任"
        elif cid_name.startswith("D3"):
            note = "修正后准确计为完整补全 1.000"
        elif cid_name.startswith("D4"):
            note = "整条展开后第2款纳入关联补全检测"
        elif cid_name.startswith("D5"):
            note = "去重生效：a21:p1 与 a21:p2 共指 a40:p1 只计 1 个责任条款（1/2=0.500，而非按边 2/3）"
        else:
            note = "区间新增第183条→第186条开始生效"
        md.append(f"| {cid_name} | {desc} | {fmt(s_old)} | **{fmt(s_new)}** | {note} |")

    md.extend(
        [
            "",
            "## 3. 固定诊断例 B：完整 `verify_output` → `relation_completion_score`",
            "",
            "| 诊断例 | 解析出的 `cited_clause_ids`（新校验器） | 回退数 | 旧 KB SC-005 | 新 KB SC-005 |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for name, raw_text in full_text_cases:
        vr_old = verify_output(raw_text, old_conn)
        vr_new = verify_output(raw_text, new_conn)
        cids_old = {c.resolved_clause_id for c in vr_old.citations if c.resolved_clause_id}
        cids_new = {c.resolved_clause_id for c in vr_new.citations if c.resolved_clause_id}
        assert cids_old == cids_new  # 两版 KB 原文与 clause_id 一致，解析结果一致
        s_old = relation_completion_score(cids_old, old_conn)
        s_new = relation_completion_score(cids_new, new_conn)
        fmt = lambda v: "None" if v is None else f"{v:.3f}"  # noqa: E731
        md.append(
            f"| {name} | `{sorted(cids_new)}` | {vr_new.fallback_para_matches} "
            f"| {fmt(s_old)} | **{fmt(s_new)}** |"
        )

    out_path = OUT_DIR / "sc005_diff.md"
    out_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    print("  historical SC-005:", run_rows_summary)
    print("  v1 overlap with new 26 liability_for:", v1_overlap)


def main() -> None:
    bad = verify_historical_hashes()
    assert not bad, f"历史产物被意外修改：{bad}"

    old_conn = open_kb(ARTIFACTS / "kb" / f"{OLD_KB_VER}.sqlite")
    new_conn = open_kb(ARTIFACTS / "kb" / f"{NEW_KB_VER}.sqlite")
    try:
        recon = reconcile_import(old_conn, new_conn)
        print(
            f"Reconcile OK: old={recon['old_total']} -> new={recon['new_total']} "
            f"(revoked={len(recon['revoked'])}, added={len(recon['added'])}, kept={len(recon['kept'])})"
        )
        build_relation_samples_diff(old_conn, new_conn, recon)
        build_sc005_diff(old_conn, new_conn)
    finally:
        old_conn.close()
        new_conn.close()


if __name__ == "__main__":
    main()
