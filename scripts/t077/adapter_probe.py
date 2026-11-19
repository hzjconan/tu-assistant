"""T077 第 6 步：已训练 adapter（exp-20261116-resume500）定向探针实测。

只连接本地白名单端点（127.0.0.1:8080，model=default_model），temperature=0，
测试 8 处已知问题（6 对错款 + 2 处整条引用）× 3 种问法 = 24 条探针，
检验旧 adapter 究竟记住了错款还是正确款，产物写入 artifacts/logs/t077/adapter_probe.md / .jsonl。
"""

from __future__ import annotations

import json
from pathlib import Path

from tu_assistant.chat.prompts import build_system_prompt
from tu_assistant.citation.verify import verify_output
from tu_assistant.config import get, load_app_config
from tu_assistant.eval.compare import load_doc_index, loose
from tu_assistant.kb.store import open_kb
from tu_assistant.runtime.client import ModelClient

OLD_KB = Path("artifacts/kb/kb-20261113-093057.sqlite")
NEW_KB = Path("artifacts/kb/kb-20261119-045641.sqlite")
OUT_DIR = Path("artifacts/logs/t077")

ISSUES = [
    {
        "id": "P1",
        "kind": "错款",
        "in_ds8410": True,
        "title": "上海市集体合同条例",
        "art_cn": "十",
        "old_from": "40124ed5e360acee:a10:p1",
        "target_from": "40124ed5e360acee:a10:p2",
        "target_para": 2,
        "to_id": "40124ed5e360acee:a38:p1",
        "to_art": "40124ed5e360acee:a38",
    },
    {
        "id": "P2",
        "kind": "错款",
        "in_ds8410": True,
        "title": "上海市集体合同条例",
        "art_cn": "十五",
        "old_from": "40124ed5e360acee:a15:p1",
        "target_from": "40124ed5e360acee:a15:p2",
        "target_para": 2,
        "to_id": "40124ed5e360acee:a39:p2",
        "to_art": "40124ed5e360acee:a39",
    },
    {
        "id": "P3",
        "kind": "错款",
        "in_ds8410": True,
        "title": "中华人民共和国妇女权益保障法",
        "art_cn": "二十二",
        "old_from": "a98741e9ca9f6fa1:a22:p1",
        "target_from": "a98741e9ca9f6fa1:a22:p2",
        "target_para": 2,
        "to_id": "a98741e9ca9f6fa1:a79:p1",
        "to_art": "a98741e9ca9f6fa1:a79",
    },
    {
        "id": "P4",
        "kind": "错款",
        "in_ds8410": True,
        "title": "上海市就业促进条例",
        "art_cn": "四十",
        "old_from": "c2699265cef115bb:a40:p1",
        "target_from": "c2699265cef115bb:a40:p4",
        "target_para": 4,
        "to_id": "c2699265cef115bb:a77:p1",
        "to_art": "c2699265cef115bb:a77",
    },
    {
        "id": "P5",
        "kind": "错款",
        "in_ds8410": False,
        "title": "上海市就业促进条例",
        "art_cn": "四十一",
        "old_from": "c2699265cef115bb:a41:p1",
        "target_from": "c2699265cef115bb:a41:p2",
        "target_para": 2,
        "to_id": "c2699265cef115bb:a78:p1",
        "to_art": "c2699265cef115bb:a78",
    },
    {
        "id": "P6",
        "kind": "错款",
        "in_ds8410": True,
        "title": "女职工劳动保护特别规定",
        "art_cn": "六",
        "old_from": "cd730370ca29c4df:a6:p1",
        "target_from": "cd730370ca29c4df:a6:p2",
        "target_para": 2,
        "to_id": "cd730370ca29c4df:a13:p1",
        "to_art": "cd730370ca29c4df:a13",
    },
    {
        "id": "P7",
        "kind": "整条覆盖",
        "in_ds8410": False,
        "title": "上海市集体合同条例",
        "art_cn": "二十一",
        "old_from": "40124ed5e360acee:a21:p1",
        "target_from": "40124ed5e360acee:a21:p2",
        "target_para": 2,
        "to_id": "40124ed5e360acee:a40:p1",
        "to_art": "40124ed5e360acee:a40",
    },
    {
        "id": "P8",
        "kind": "整条覆盖(p2已reject)",
        "in_ds8410": False,
        "title": "中华人民共和国工会法",
        "art_cn": "三",
        "old_from": "4b6c1f293f717293:a3:p1",
        "target_from": "4b6c1f293f717293:a3:p2",
        "target_para": 2,
        "to_id": "4b6c1f293f717293:a51:p1",
        "to_art": "4b6c1f293f717293:a51",
    },
]


def main() -> None:
    cfg = load_app_config("configs/app.yaml")
    serve_meta_path = Path("artifacts/serve/current.json")
    if not serve_meta_path.is_file():
        raise SystemExit(
            "缺少 artifacts/serve/current.json，请先启动 tu serve model --exp exp-20261116-resume500"
        )
    serve_meta = json.loads(serve_meta_path.read_text(encoding="utf-8"))
    assert serve_meta.get("model") == "default_model", f"路由异常：{serve_meta}"
    assert serve_meta.get("exp") == "exp-20261116-resume500", f"非目标实验：{serve_meta}"

    client = ModelClient(
        endpoint=serve_meta.get("endpoint") or get(cfg, "runtime.model_endpoint"),
        allowed_hosts=get(cfg, "runtime.allowed_hosts"),
        model=serve_meta["model"],
        timeout_s=120.0,
    )
    sys_prompt = build_system_prompt(max_questions=5)

    old_conn = open_kb(OLD_KB)
    new_conn = open_kb(NEW_KB)
    docs = load_doc_index(NEW_KB)

    rows: list[dict] = []
    try:
        for item in ISSUES:
            t = item["title"]
            acn = item["art_cn"]
            tp = item["target_para"]
            variants = [
                ("A_条号(训练分布)", f"违反《{t}》第{acn}条要承担什么法律责任？"),
                (f"B_目标款(第{tp}款)", f"违反《{t}》第{acn}条第{tp}款要承担什么法律责任？"),
                ("C_第1款对照", f"违反《{t}》第{acn}条第1款要承担什么法律责任？"),
            ]
            for vname, question in variants:
                resp = client.chat(
                    [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": question},
                    ],
                    temperature=0.0,
                    max_tokens=1024,
                )
                raw = resp.content
                vr_new = verify_output(raw, new_conn)
                vr_old = verify_output(raw, old_conn)
                cited_new = sorted({c.resolved_clause_id for c in vr_new.citations if c.resolved_clause_id})
                cited_old = sorted({c.resolved_clause_id for c in vr_old.citations if c.resolved_clause_id})
                loose_arts, _ = loose(raw, docs)

                hit_to_exact = item["to_id"] in cited_new
                hit_to_loose = item["to_art"] in loose_arts
                hit_old_from = item["old_from"] in cited_new
                hit_target_from = item["target_from"] in cited_new

                rec = {
                    "id": item["id"],
                    "kind": item["kind"],
                    "in_ds8410": item["in_ds8410"],
                    "variant": vname,
                    "question": question,
                    "raw": raw,
                    "raw_markers": [c.raw for c in vr_new.citations if c.title],
                    "cited_new": cited_new,
                    "cited_old": cited_old,
                    "verdict_stats_new": vr_new.stats,
                    "fallback_para_matches": vr_new.fallback_para_matches,
                    "hit_to_exact": hit_to_exact,
                    "hit_to_loose": hit_to_loose,
                    "hit_old_from": hit_old_from,
                    "hit_target_from": hit_target_from,
                    "expected_to": item["to_id"],
                    "old_from": item["old_from"],
                    "target_from": item["target_from"],
                }
                rows.append(rec)
                print(
                    f"[{item['id']} {vname}] to_exact={hit_to_exact} to_loose={hit_to_loose} "
                    f"old_from={hit_old_from} target_from={hit_target_from} "
                    f"stats={vr_new.stats} markers={rec['raw_markers'][:3]}"
                )
    finally:
        old_conn.close()
        new_conn.close()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jsonl_path = OUT_DIR / "adapter_probe.jsonl"
    jsonl_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )

    # 汇总统计
    def _cnt(subset: list[dict], key: str) -> int:
        return sum(1 for r in subset if r[key])

    wrong6 = [r for r in rows if r["kind"] == "错款"]
    w6_a = [r for r in wrong6 if r["variant"].startswith("A_")]
    w6_b = [r for r in wrong6 if r["variant"].startswith("B_")]
    w6_c = [r for r in wrong6 if r["variant"].startswith("C_")]
    whole2 = [r for r in rows if r["kind"].startswith("整条")]

    md = [
        "# T077 已训练 Adapter（`exp-20261116-resume500`）定向探针实测报告",
        "",
        f"- **服务身份**：`exp={serve_meta['exp']}`，`base_model={serve_meta['base_model']}`，"
        f"`model={serve_meta['model']}`，`endpoint={serve_meta['endpoint']}`，`temperature=0.0`",
        f"- **校验口径**：同时对照旧 KB `{OLD_KB.stem}` 与新 KB `{NEW_KB.stem}`（两者条款原文与 ID 一致）",
        "- **原始回复归档**：`artifacts/logs/t077/adapter_probe.jsonl`（24 条，含全文与逐引用判定）",
        "",
        "## 1. 核心统计（6 对错款 × 3 问法 = 18 探针；2 处整条 × 3 问法 = 6 探针）",
        "",
        "| 分组 | 探针数 | 精确命中目标责任条款(`to_id`) | 宽松命中目标责任条(`to_art`) "
        "| 精确引出旧错款(`p1`) | 精确引出正确款(`target_from`) | 多款回退次数 |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| 错款6对 · A 条号问法（训练分布） | {len(w6_a)} | {_cnt(w6_a, 'hit_to_exact')} | "
        f"{_cnt(w6_a, 'hit_to_loose')} | {_cnt(w6_a, 'hit_old_from')} | "
        f"{_cnt(w6_a, 'hit_target_from')} | {sum(r['fallback_para_matches'] for r in w6_a)} |",
        f"| 错款6对 · B 正确款号问法 | {len(w6_b)} | {_cnt(w6_b, 'hit_to_exact')} | "
        f"{_cnt(w6_b, 'hit_to_loose')} | {_cnt(w6_b, 'hit_old_from')} | "
        f"{_cnt(w6_b, 'hit_target_from')} | {sum(r['fallback_para_matches'] for r in w6_b)} |",
        f"| 错款6对 · C 第1款对照问法 | {len(w6_c)} | {_cnt(w6_c, 'hit_to_exact')} | "
        f"{_cnt(w6_c, 'hit_to_loose')} | {_cnt(w6_c, 'hit_old_from')} | "
        f"{_cnt(w6_c, 'hit_target_from')} | {sum(r['fallback_para_matches'] for r in w6_c)} |",
        f"| 整条2处 · 全部3问法 | {len(whole2)} | {_cnt(whole2, 'hit_to_exact')} | "
        f"{_cnt(whole2, 'hit_to_loose')} | {_cnt(whole2, 'hit_old_from')} | "
        f"{_cnt(whole2, 'hit_target_from')} | {sum(r['fallback_para_matches'] for r in whole2)} |",
        "",
        "## 2. 逐条实测明细（24 条探针）",
        "",
        "| 组别 | 进 `ds-8410` | 问法 | 命中目标责任（精/宽） "
        "| 引出旧p1/正确款 | 校验统计（新KB） | 模型输出标记 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        hit_to = f"{'✅' if r['hit_to_exact'] else '❌'}/{'✅' if r['hit_to_loose'] else '❌'}"
        hit_fr = f"{'✅' if r['hit_old_from'] else '·'}/{'✅' if r['hit_target_from'] else '·'}"
        st = r["verdict_stats_new"]
        st_s = f"ok={st['ok']},cor={st['corrected']},nf={st['not_found']},inc={st['incomplete']}"
        mk = "；".join(r["raw_markers"][:3]) or "（无结构标记）"
        md.append(
            f"| {r['id']}({r['kind']}) | {'是' if r['in_ds8410'] else '否'} | {r['variant']} "
            f"| {hit_to} | {hit_fr} | {st_s} | {mk} |"
        )

    md.extend(
        [
            "",
            "## 3. 实测结论与对 T075 的建议",
            "",
            "（以下结论仅依据上表 24 条实测输出自动汇总，供结合明细复核：）",
            "",
            f"- 6 对错款在训练分布条号问法（A）下：目标责任精确命中 **{_cnt(w6_a, 'hit_to_exact')}/6**"
            f"（宽松 **{_cnt(w6_a, 'hit_to_loose')}/6**）；"
            f"正确款号问法（B）下：精确命中 **{_cnt(w6_b, 'hit_to_exact')}/6**"
            f"（宽松 **{_cnt(w6_b, 'hit_to_loose')}/6**）；"
            f"第 1 款对照问法（C）下：精确命中 **{_cnt(w6_c, 'hit_to_exact')}/6**"
            f"（宽松 **{_cnt(w6_c, 'hit_to_loose')}/6**）。",
            f"- 新旧两版 KB 校验出的 `cited_clause_ids` 是否逐条完全一致："
            f"**{all(r['cited_new'] == r['cited_old'] for r in rows)}**。",
            "- 若 A/C 问法复现出旧错款映射，或 B 问法未能稳定命中正确责任条款，"
            "T057 组装新数据集时应包含新 KB 修正后的 26 条 `liability_for` 关系样本及相应文章样本，"
            "供 T075 续训覆盖并纠偏。",
        ]
    )

    md_path = OUT_DIR / "adapter_probe.md"
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\nWrote {md_path} and {jsonl_path}")


if __name__ == "__main__":
    main()
