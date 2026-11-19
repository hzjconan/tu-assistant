"""T019 第 1 步（离线预审）：用 DeepSeek 对第二批 references 候选及沿用旧边做第一轮排查。

合规说明（宪章原则 III / IV）：
- 仅读取本地 SQLite KB 中的公开法律条款，绝不触碰 inputs/ 或用户对话数据；
- 通过 src/tu_assistant/synth/llm.py（input_source="kb_clause"）调用外部模型；
- 只产出预审报告（artifacts/logs/t019/batch2_prescreen.md / .jsonl），
  不修改数据库，也不改动审阅文件的 decision 字段（最终确认仍归人工）。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from tu_assistant.config import load_synth_config
from tu_assistant.kb.relations import article_paragraph_count, canonical_clause_text
from tu_assistant.kb.store import get_clause_by_id, get_document, open_kb
from tu_assistant.synth.llm import from_config

NEW_KB_VER = "kb-20261119-045641"
ARTIFACTS = Path("artifacts")
OUT_DIR = Path("artifacts/logs/t019")

SYSTEM_PROMPT = """\
你是中国工会法律知识库的质量预审员。你的任务是核对一条候选条款引用关联 (from -> to) 是否准确成立。
方向约定：
- from = 被引用的条款
- to = 含有该引用的条款（通过“依照 / 按照 / 依据 / 比照 / 所列”等援引 from）

针对 relation_type="references" 的判断标准：
1. 款号/项号必须精确对齐：若 to 原文明指“第X条第Y款”或“第X条第Z项”，则只有 from 恰为该款/该项才算成立；
   指向第 1 款或未细化到对应项的旧边属错款/漏项。
2. 整条引用多款条文时（to 只写“依照本法第X条”）：逐款判断 to 所援引的实体规则/程序/情形是否
   确实涵盖了当前 from 这一款；若该款属于与 to 援引语境无关的附则、定义或另一独立程序/情形，
   应标 reject 或 uncertain。
3. 实质引用 vs 碰巧提及：to 确实依赖 from 的规定（如依照其情形解除/计算/办理/载明事项）才算成立；
   若只是顺带解释名词或毫无实质关联，应标 reject。

若该边目前已在库内（in_db=true）且你判定它错款/漏项或不成立，verdict 请填 "revoke"；
若该边尚未入库（in_db=false）且判定不成立，verdict 请填 "reject"；
判定准确成立填 "confirm"；拿不准或边界有争议填 "uncertain"。

严格只输出一个 JSON 对象，不要代码块和多余文字：
{"verdict": "confirm|revoke|reject|uncertain", "target_accurate": true/false,
 "substantive": true/false, "reason": "不超过60字的简明中文理由"}"""


def _load_dotenv_key() -> None:
    if os.environ.get("TU_EXTERNAL_LLM_API_KEY"):
        return
    env_path = Path(".env")
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == "TU_EXTERNAL_LLM_API_KEY":
            os.environ["TU_EXTERNAL_LLM_API_KEY"] = v.strip().strip('"').strip("'")
            return


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {
            "verdict": "uncertain",
            "target_accurate": None,
            "substantive": None,
            "reason": f"解析失败：{text[:40]}",
        }
    try:
        d = json.loads(m.group(0))
        return {
            "verdict": str(d.get("verdict", "uncertain")),
            "target_accurate": d.get("target_accurate"),
            "substantive": d.get("substantive"),
            "reason": str(d.get("reason", ""))[:120],
        }
    except json.JSONDecodeError:
        return {
            "verdict": "uncertain",
            "target_accurate": None,
            "substantive": None,
            "reason": f"JSON错误：{text[:40]}",
        }


def main() -> None:
    _load_dotenv_key()
    cfg = load_synth_config("configs/synth.yaml")
    llm = from_config(cfg)

    kb_path = ARTIFACTS / "kb" / f"{NEW_KB_VER}.sqlite"
    batch2_path = ARTIFACTS / "kb" / f"{NEW_KB_VER}-batch2-references_review.jsonl"
    batch2_rows = [
        json.loads(line)
        for line in batch2_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    conn = open_kb(kb_path)
    try:
        in_db_set = {
            (r[0], r[1], r[2])
            for r in conn.execute(
                "SELECT from_clause_id, to_clause_id, relation_type "
                "FROM clause_relations WHERE confirmed=1"
            ).fetchall()
        }
        batch2_keys = {
            (r["from_clause_id"], r["to_clause_id"], r["relation_type"]) for r in batch2_rows
        }
        retained_refs = [
            {
                "from_clause_id": fid,
                "to_clause_id": tid,
                "relation_type": rtype,
                "scope": "retained_in_db",
                "evidence": "",
                "suggested_decision": "confirm",
                "note": "旧库沿用 references（健康复核）",
            }
            for fid, tid, rtype in sorted(in_db_set)
            if rtype != "liability_for" and (fid, tid, rtype) not in batch2_keys
        ]

        all_items: list[tuple[str, int, dict]] = [
            ("batch2", i, r) for i, r in enumerate(batch2_rows, 1)
        ] + [("retained", i, r) for i, r in enumerate(retained_refs, 1)]

        results: list[dict] = []
        for group, idx, r in all_items:
            fc = get_clause_by_id(conn, r["from_clause_id"])
            tc = get_clause_by_id(conn, r["to_clause_id"])
            fdoc = get_document(conn, fc.doc_id) if fc else None
            tdoc = get_document(conn, tc.doc_id) if tc else None
            if not fc or not tc or not fdoc or not tdoc:
                continue

            in_db = (r["from_clause_id"], r["to_clause_id"], r["relation_type"]) in in_db_set
            total_p = article_paragraph_count(conn, fc)
            f_text = canonical_clause_text(conn, fc)
            t_text = canonical_clause_text(conn, tc)

            # 附带同条全部款/项摘要，帮助模型判断整条展开中该款是否真被援引
            sib_rows = conn.execute(
                "SELECT clause_id, paragraph_no, item_no, number_text FROM clauses "
                "WHERE doc_id=? AND article_no=? AND item_no IS NULL ORDER BY paragraph_no",
                (fc.doc_id, fc.article_no),
            ).fetchall()
            siblings_desc = []
            for sid, sp, _si, snt in sib_rows:
                sc = get_clause_by_id(conn, sid)
                stxt = canonical_clause_text(conn, sc) if sc else ""
                mark = "（← 当前 from 所在款）" if sp == fc.paragraph_no else ""
                siblings_desc.append(f"- 第{sp}款 {snt}{mark}：{stxt}")

            user_prompt = (
                f"关系类型：{r['relation_type']}\n"
                f"是否已在当前库中（in_db）：{in_db}\n"
                f"来源范围（scope）：{r.get('scope') or 'unknown'}\n"
                f"触发引用片段：{r.get('evidence') or '（见 to 原文）'}\n\n"
                f"【from 条款】《{fdoc.title}》{fc.number_text}"
                f"（该条共 {total_p} 款，当前第 {fc.paragraph_no or 1} 款"
                f"{f'第 {fc.item_no} 项' if fc.item_no else ''}）\n"
                f"{f_text}\n\n"
                f"【from 所在整条的全部各款】\n" + "\n".join(siblings_desc) + "\n\n"
                f"【to 条款】《{tdoc.title}》{tc.number_text}\n"
                f"{t_text}\n"
            )
            raw = llm.chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                input_source="kb_clause",
                temperature=0.0,
                max_tokens=300,
            )
            parsed = _parse_json(raw)
            rec = {
                "group": group,
                "row": idx,
                "in_db": in_db,
                "from_clause_id": r["from_clause_id"],
                "to_clause_id": r["to_clause_id"],
                "from_label": f"《{fdoc.title}》{fc.number_text}",
                "to_label": f"《{tdoc.title}》{tc.number_text}",
                "total_paras": total_p,
                "scope": r.get("scope", ""),
                "evidence": r.get("evidence", ""),
                "rule_suggested": r.get("suggested_decision", ""),
                "llm_verdict": parsed["verdict"],
                "target_accurate": parsed["target_accurate"],
                "substantive": parsed["substantive"],
                "llm_reason": parsed["reason"],
            }
            results.append(rec)
            print(
                f"[{group} #{idx:02d}] {rec['from_label']} -> {rec['to_label']} | "
                f"rule={rec['rule_suggested']} llm={rec['llm_verdict']} | {rec['llm_reason']}"
            )
    finally:
        conn.close()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jsonl_path = OUT_DIR / "batch2_prescreen.jsonl"
    jsonl_path.write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in results),
        encoding="utf-8",
    )
    meta_path = OUT_DIR / "batch2_prescreen_meta.json"
    meta_path.write_text(
        json.dumps({"kb_version": NEW_KB_VER, "llm": llm.meta()}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    md = [
        f"# T019 第二批 `references` DeepSeek 预审报告（`{NEW_KB_VER}`）",
        "",
        f"- 模型：`{llm.model}`（`temperature=0`，`input_source=kb_clause`，调用 {llm.usage.calls} 次，"
        f"prompt {llm.usage.prompt_tokens} / completion {llm.usage.completion_tokens} tokens）",
        "- 说明：本报告仅作人工审阅辅助参考，**未修改数据库，也未改动审阅文件的 `decision`**。",
        "",
    ]

    def add_section(title: str, subset: list[dict]) -> None:
        md.append(f"## {title}（{len(subset)} 条）")
        md.append("")
        md.append(
            "| 行号 | from → to | scope | 规则建议 | DeepSeek 预审 | 一致？ | 预审理由 |"
        )
        md.append("|---:|---|---|---|---|---|---|")
        for x in subset:
            same = "✅" if x["rule_suggested"] == x["llm_verdict"] else "⚠️ **重点复核**"
            md.append(
                f"| {x['row']} | {x['from_label']}（共{x['total_paras']}款） → {x['to_label']} "
                f"| `{x['scope']}` | `{x['rule_suggested']}` | **`{x['llm_verdict']}`** "
                f"| {same} | {x['llm_reason']} |"
            )
        md.append("")

    b2 = [x for x in results if x["group"] == "batch2"]
    add_section("1. 待撤销旧错边（行 1–4）", [x for x in b2 if x["row"] <= 4])
    add_section("2. 新增 `references` 候选（行 5–47）", [x for x in b2 if x["row"] > 4])
    add_section(
        "3. 库内沿用的 19 条旧 `references` 健康复核",
        [x for x in results if x["group"] == "retained"],
    )

    diverged = [
        x
        for x in results
        if x["rule_suggested"] != x["llm_verdict"] or x["llm_verdict"] == "uncertain"
    ]
    md.append(f"## 4. 需要你重点复核的分歧 / 不确定项（共 {len(diverged)} 条）")
    md.append("")
    if not diverged:
        md.append("无分歧项，规则建议与 DeepSeek 预审全部一致。")
    else:
        for x in diverged:
            md.append(
                f"- **[{x['group']} 行 {x['row']}]** {x['from_label']} → {x['to_label']}："
                f"规则 `{x['rule_suggested']}` vs DeepSeek **`{x['llm_verdict']}`** — {x['llm_reason']}"
            )
    md.append("")

    md_path = OUT_DIR / "batch2_prescreen.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(f"\nWrote {md_path} and {jsonl_path}")
    print(f"LLM usage: {llm.meta()['usage']}")


if __name__ == "__main__":
    main()
