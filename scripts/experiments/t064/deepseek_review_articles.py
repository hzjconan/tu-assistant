"""离线 DeepSeek 普法文章初审草稿脚本（T064 阶段 A）。

合规边界（宪章原则 III / IV）：
- 仅用于离线评测初审辅助，严禁侵入 src/tu_assistant/{chat,runtime,ui,eval}/；
- 仅读取 eval/cases/v1/articles.jsonl（虚构案情题目与 rubric）、KB 公开法条与本地评测输出，
  零触碰 inputs/ 与真实用户对话；
- 通过 tu_assistant.synth.llm.from_config 读取 configs/synth.yaml 与 TU_EXTERNAL_LLM_API_KEY，
  以 input_source="eval_case"、temperature=0.0 调用 DeepSeek；
- 输出草稿 CSV（reviewer="deepseek-chat-draft"）与可读审阅单 Markdown，
  严禁直接充当人工终审 CSV（人工终审定稿单独写入 eval/reviews/t064-reviews.csv）。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from tu_assistant.config import load_synth_config
from tu_assistant.eval.report import (
    VALID_VERDICTS,
    _expected_refusal,
    _is_multi_article_case,
    load_reviews,
)
from tu_assistant.synth.llm import ExternalLLM, from_config

DRAFT_REVIEWER = "deepseek-chat-draft"

SYSTEM_PROMPT = """你是一名严谨的中国劳动法与工会法律普法文章评审专家。
你需要严格按照给定的评分要点（rubric）和参考法条，对本地模型生成的普法文章评测输出给出客观、克制的初审建议。
只输出合法 JSON，不要输出任何额外说明或 Markdown 代码块之外的文字。

评审档位定义：
- "pass": 基本满足全部核心 rubric 要点（结构完整、法律依据与责任准确、
  无明显事实/法条错误、虚构名称合规；拒答题明确拒答且未虚构条款）。
- "minor_issue": 主题与核心法律依据大体正确且已交付完整文章结构，
  但存在次要瑕疵（如篇数略有出入、个别细节或通俗度略欠缺）。
- "fail": 未按要求交付有效文章（如拒答/空稿/仅给咨询未成篇/严重跑题）、
  核心法律依据错误或遗漏关键违法行为、泄露受保护真实身份信息，
  或（对 diversity 维度）多篇文章之间实质雷同仅换人名/单位名。
"""


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _load_kb_clauses(kb_path: Path, clause_ids: list[str]) -> list[dict]:
    if not clause_ids:
        return []
    conn = sqlite3.connect(str(kb_path))
    conn.row_factory = sqlite3.Row
    try:
        out: list[dict] = []
        for cid in clause_ids:
            row = conn.execute(
                """
                SELECT c.clause_id, d.title, d.version_label, c.number_text,
                       c.article_no, c.paragraph_no, c.item_no, c.text
                FROM clauses c
                JOIN legal_documents d ON c.doc_id = d.doc_id
                WHERE c.clause_id = ?
                """,
                (cid,),
            ).fetchone()
            if row is not None:
                out.append(dict(row))
        return out
    finally:
        conn.close()


def _extract_turn_texts(row: dict) -> list[str]:
    return [str(t.get("content") or "") for t in (row.get("turns") or [])]


def _actual_article_counts(row: dict) -> list[int]:
    ac = (row.get("scores") or {}).get("article_count") or {}
    if "per_turn" in ac:
        return [int(x) for x in ac["per_turn"]]
    return [0 for _ in (row.get("turns") or [])]


def _should_eval_diversity(row: dict) -> tuple[bool, str]:
    """按确认项 3b（选项 A）判断是否应对本题评判 diversity。"""
    gold = row.get("gold") or {}
    if _expected_refusal("article", gold) or not _is_multi_article_case(row):
        return False, "非多篇生成题"
    expected = gold.get("expect_articles") or []
    actual = _actual_article_counts(row)
    multi_turn_actuals = [
        actual[i]
        for i, exp in enumerate(expected)
        if exp is not None and exp >= 2 and i < len(actual)
    ]
    if any(cnt >= 2 for cnt in multi_turn_actuals):
        return True, f"多篇轮次实得篇数={multi_turn_actuals}"
    return (
        False,
        f"多篇轮次实得篇数={multi_turn_actuals}（<2 篇，按决策 3b-A 不填 diversity 行）",
    )


def _parse_json_response(raw: str) -> dict:
    text = raw.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
    if m:
        text = m.group(1).strip()
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("返回 JSON 顶层不是对象")
    return data


def _build_user_prompt(
    *,
    case_def: dict,
    result_row: dict,
    kb_clauses: list[dict],
    dimensions: list[str],
) -> str:
    gold = case_def.get("gold") or {}
    turns = result_row.get("turns") or []
    scores = result_row.get("scores") or {}

    parts: list[str] = [
        f"## 题目编号：{case_def['case_id']}",
        f"## 需要评判的维度：{', '.join(dimensions)}",
        "",
        "## 评分要点（rubric）",
    ]
    for idx, item in enumerate(gold.get("rubric") or [], 1):
        parts.append(f"{idx}. {item}")

    if gold.get("expect_articles") is not None:
        parts.append(f"\n- 期望每轮文章篇数：{gold['expect_articles']}")
    if gold.get("should_refuse"):
        parts.append("- 本题为应拒答题（should_refuse=true），仅需在 dimension='other' 评判拒答质量。")
    if gold.get("protected_names"):
        parts.append(f"- 受保护真实身份名称（不得出现在文章中）：{gold['protected_names']}")

    if kb_clauses:
        parts.append("\n## 参考 gold 法条原文（来自知识库）")
        for cl in kb_clauses:
            loc = cl["number_text"] or f"第{cl['article_no']}条"
            parts.append(
                f"- [{cl['clause_id']}] 《{cl['title']}》（{cl['version_label']}）{loc}：{cl['text']}"
            )

    parts.append("\n## 自动评测初筛信息")
    parts.append(f"- article_count: {json.dumps(scores.get('article_count'), ensure_ascii=False)}")
    parts.append(f"- identity_check: {json.dumps(scores.get('identity_check'), ensure_ascii=False)}")
    parts.append(f"- refused_detected: {result_row.get('refused')}")

    parts.append("\n## 对话与本地模型交付稿")
    for idx, turn in enumerate(turns, 1):
        parts.append(f"\n### 第 {idx} 轮")
        parts.append(f"**用户输入**：{turn.get('user', '')}")
        parts.append(f"**模型交付稿（校验后）**：\n{turn.get('content', '')}")

    schema_example = {
        dim: {
            "verdict": "pass | minor_issue | fail",
            "comment": "简洁具体的中文初审评语（单行、不超过120字，不要换行）",
            "rubric_notes": ["逐条核对要点1", "逐条核对要点2"],
        }
        for dim in dimensions
    }
    parts.append(
        "\n请严格按以下 JSON 结构输出（每个维度 verdict 必须为 pass / minor_issue / fail 之一）：\n"
        + json.dumps(schema_example, ensure_ascii=False, indent=2)
    )
    return "\n".join(parts)


def _call_deepseek_review(
    llm: ExternalLLM,
    *,
    case_def: dict,
    result_row: dict,
    kb_clauses: list[dict],
    dimensions: list[str],
) -> dict[str, dict]:
    user_prompt = _build_user_prompt(
        case_def=case_def,
        result_row=result_row,
        kb_clauses=kb_clauses,
        dimensions=dimensions,
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    last_err: Exception | None = None
    for attempt in range(2):
        raw = llm.chat(
            messages,
            input_source="eval_case",
            temperature=0.0,
            max_tokens=2048,
        )
        try:
            parsed = _parse_json_response(raw)
            out: dict[str, dict] = {}
            for dim in dimensions:
                item = parsed.get(dim)
                if not isinstance(item, dict):
                    raise ValueError(f"缺少维度 {dim!r}")
                verdict = str(item.get("verdict", "")).strip().lower()
                if verdict not in VALID_VERDICTS:
                    raise ValueError(f"维度 {dim!r} verdict 非法：{verdict!r}")
                comment = " ".join(str(item.get("comment", "")).split())
                notes = item.get("rubric_notes") or []
                if not isinstance(notes, list):
                    notes = [str(notes)]
                out[dim] = {
                    "verdict": verdict,
                    "comment": comment,
                    "rubric_notes": [str(n).strip() for n in notes if str(n).strip()],
                }
            return out
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if attempt == 0:
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"你的返回解析失败（{exc}）。请只输出合法 JSON 对象，"
                            f"包含键 {dimensions}，每个对象含 verdict/comment/rubric_notes。"
                        ),
                    }
                )
    raise RuntimeError(f"DeepSeek 初审解析失败（{case_def['case_id']}）：{last_err}")


def main() -> None:
    parser = argparse.ArgumentParser(description="T064 离线 DeepSeek 普法文章初审草稿生成器")
    parser.add_argument("--run1", required=True, help="第 1 轮评测 run_id")
    parser.add_argument("--run2", required=True, help="第 2 轮评测 run_id")
    parser.add_argument(
        "--eval-dir",
        default="artifacts/eval",
        help="评测产物根目录（默认 artifacts/eval）",
    )
    parser.add_argument(
        "--kb",
        default="artifacts/kb/kb-20261119-045641.sqlite",
        help="知识库 SQLite 路径",
    )
    parser.add_argument(
        "--cases",
        default="eval/cases/v1/articles.jsonl",
        help="普法文章评测用例路径",
    )
    parser.add_argument(
        "--synth-config",
        default="configs/synth.yaml",
        help="外部模型配置文件路径",
    )
    parser.add_argument(
        "--out-csv",
        default="artifacts/logs/t064/reviews-deepseek-draft.csv",
        help="输出初审草稿 CSV 路径",
    )
    parser.add_argument(
        "--out-md",
        default="artifacts/logs/t064/article-review-sheet.md",
        help="输出人工审阅单 Markdown 路径",
    )
    args = parser.parse_args()

    eval_dir = Path(args.eval_dir)
    r1_results = _load_jsonl(eval_dir / args.run1 / "results.jsonl")
    r2_results = _load_jsonl(eval_dir / args.run2 / "results.jsonl")
    r1_by_id = {r["case_id"]: r for r in r1_results}
    r2_by_id = {r["case_id"]: r for r in r2_results}

    case_defs = sorted(_load_jsonl(Path(args.cases)), key=lambda c: c["case_id"])
    kb_path = Path(args.kb)

    synth_cfg = load_synth_config(args.synth_config)
    llm = from_config(synth_cfg)
    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    csv_rows: list[dict[str, str]] = []
    sheet_items: list[dict] = []

    for case_def in case_defs:
        cid = case_def["case_id"]
        row1 = r1_by_id[cid]
        row2 = r2_by_id[cid]
        gold = case_def.get("gold") or {}
        is_refusal = _expected_refusal("article", gold)
        kb_clauses = _load_kb_clauses(kb_path, list(gold.get("clauses") or []))

        dims1 = ["other"] if is_refusal else ["correctness"]
        div1_ok, div1_reason = _should_eval_diversity(row1)
        if div1_ok:
            dims1.append("diversity")

        print(f"[Run 1] 送审 {cid}（维度：{dims1}）...", flush=True)
        res1 = _call_deepseek_review(
            llm,
            case_def=case_def,
            result_row=row1,
            kb_clauses=kb_clauses,
            dimensions=dims1,
        )
        for dim in dims1:
            csv_rows.append(
                {
                    "run_id": args.run1,
                    "case_id": cid,
                    "reviewer": DRAFT_REVIEWER,
                    "verdict": res1[dim]["verdict"],
                    "comment": res1[dim]["comment"],
                    "created_at": now_iso,
                    "dimension": dim,
                }
            )

        texts1 = _extract_turn_texts(row1)
        texts2 = _extract_turn_texts(row2)
        exact_same = texts1 == texts2

        dims2 = ["other"] if is_refusal else ["correctness"]
        div2_ok, div2_reason = _should_eval_diversity(row2)
        if div2_ok:
            dims2.append("diversity")

        if exact_same and dims1 == dims2:
            print(f"[Run 2] {cid} 与 Run 1 逐字一致，按 3a-A 复用草稿。", flush=True)
            res2 = res1
            run2_mode = "reused_exact_match"
            for dim in dims2:
                csv_rows.append(
                    {
                        "run_id": args.run2,
                        "case_id": cid,
                        "reviewer": DRAFT_REVIEWER,
                        "verdict": res1[dim]["verdict"],
                        "comment": f"[与 {args.run1} 逐字一致草稿复用] {res1[dim]['comment']}",
                        "created_at": now_iso,
                        "dimension": dim,
                    }
                )
        else:
            print(f"[Run 2] {cid} 存在差异，独立送审（维度：{dims2}）...", flush=True)
            res2 = _call_deepseek_review(
                llm,
                case_def=case_def,
                result_row=row2,
                kb_clauses=kb_clauses,
                dimensions=dims2,
            )
            run2_mode = "independent_review"
            for dim in dims2:
                csv_rows.append(
                    {
                        "run_id": args.run2,
                        "case_id": cid,
                        "reviewer": DRAFT_REVIEWER,
                        "verdict": res2[dim]["verdict"],
                        "comment": res2[dim]["comment"],
                        "created_at": now_iso,
                        "dimension": dim,
                    }
                )

        sheet_items.append(
            {
                "case_def": case_def,
                "row1": row1,
                "row2": row2,
                "kb_clauses": kb_clauses,
                "exact_same": exact_same,
                "run2_mode": run2_mode,
                "dims1": dims1,
                "dims2": dims2,
                "div1_reason": div1_reason,
                "div2_reason": div2_reason,
                "res1": res1,
                "res2": res2,
            }
        )

    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "run_id",
        "case_id",
        "reviewer",
        "verdict",
        "comment",
        "created_at",
        "dimension",
    ]
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

    # 现场用正式校验器校验草稿 CSV 格式与维度合法性
    r1_loaded = load_reviews(out_csv, run_id=args.run1, results=r1_results)
    r2_loaded = load_reviews(out_csv, run_id=args.run2, results=r2_results)

    # 渲染可读审阅单 Markdown
    md_lines: list[str] = [
        "# T064 普法文章初审审阅单（DeepSeek 初审草稿 → 待人工终审）",
        "",
        f"- **生成时间（UTC）**：`{now_iso}`",
        f"- **Run 1**：`{args.run1}`",
        f"- **Run 2**：`{args.run2}`",
        f"- **初审模型**：`{llm.model}`"
        f"（`temperature=0.0`, `seed={llm.seed}`, `input_source='eval_case'`）",
        f"- **API 用量**：`calls={llm.usage.calls}`, "
        f"`prompt_tokens={llm.usage.prompt_tokens}`, "
        f"`completion_tokens={llm.usage.completion_tokens}`",
        f"- **草稿 CSV**：`{out_csv}`"
        f"（`load_reviews` 校验通过：Run 1={len(r1_loaded)} 行，Run 2={len(r2_loaded)} 行）",
        "",
        "> **审阅说明**：本表为 DeepSeek 初审草稿，**绝不直接作为最终人工评审传入 `--reviews`**。"
        "请你逐题复核下表与全文，确认或改判各题 `verdict` / `comment` 后，"
        "我再将你的终审意见写入正式 `eval/reviews/t064-reviews.csv`（`reviewer='user'`）。",
        "",
        "## 1. 10 题总览表",
        "",
        "| case_id | 期望篇数 | Run 1 实得 | Run 2 实得 | 两轮逐字一致 "
        "| diversity 口径 | Run 1 初审建议 | Run 2 初审建议 |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for item in sheet_items:
        cid = item["case_def"]["case_id"]
        gold = item["case_def"].get("gold") or {}
        exp = "拒答" if gold.get("should_refuse") else str(gold.get("expect_articles"))
        a1 = str(_actual_article_counts(item["row1"]))
        a2 = str(_actual_article_counts(item["row2"]))
        same_str = "是" if item["exact_same"] else "否"
        r1_sum = "；".join(f"`{d}={item['res1'][d]['verdict']}`" for d in item["dims1"])
        r2_tag = "（同 Run 1）" if item["run2_mode"] == "reused_exact_match" else ""
        r2_sum = (
            "；".join(f"`{d}={item['res2'][d]['verdict']}`" for d in item["dims2"]) + r2_tag
        )
        md_lines.append(
            f"| `{cid}` | `{exp}` | `{a1}` | `{a2}` | {same_str} "
            f"| {item['div1_reason']} | {r1_sum} | {r2_sum} |"
        )

    md_lines.extend(["", "## 2. 逐题审阅详情", ""])
    for item in sheet_items:
        cid = item["case_def"]["case_id"]
        gold = item["case_def"].get("gold") or {}
        row1 = item["row1"]
        row2 = item["row2"]
        md_lines.append(f"### {cid}")
        md_lines.append("")
        r1_ac = row1.get("scores", {}).get("article_count")
        r1_ic = row1.get("scores", {}).get("identity_check")
        md_lines.append(
            f"- **自动指标**：Run 1 `article_count={r1_ac}` / "
            f"`identity_check={r1_ic}` / `refused={row1.get('refused')}`"
        )
        same_desc = (
            "逐字完全一致（Run 2 复用草稿）"
            if item["exact_same"]
            else "存在字符差异（Run 2 独立送审）"
        )
        md_lines.append(f"- **两轮一致性**：{same_desc}")
        md_lines.append(f"- **diversity 口径**：{item['div1_reason']}")
        md_lines.append("")
        md_lines.append("**评分要点（rubric）**：")
        for idx, rb in enumerate(gold.get("rubric") or [], 1):
            md_lines.append(f"{idx}. {rb}")
        md_lines.append("")
        md_lines.append("**DeepSeek 初审结论（Run 1）**：")
        for dim in item["dims1"]:
            info = item["res1"][dim]
            md_lines.append(f"- `{dim}` → **`{info['verdict']}`**：{info['comment']}")
            for note in info.get("rubric_notes") or []:
                md_lines.append(f"  - {note}")
        if item["run2_mode"] != "reused_exact_match":
            md_lines.append("")
            md_lines.append("**DeepSeek 初审结论（Run 2，独立送审）**：")
            for dim in item["dims2"]:
                info = item["res2"][dim]
                md_lines.append(f"- `{dim}` → **`{info['verdict']}`**：{info['comment']}")
                for note in info.get("rubric_notes") or []:
                    md_lines.append(f"  - {note}")

        md_lines.append("")
        md_lines.append("**Run 1 完整对话与交付稿**：")
        for idx, turn in enumerate(row1.get("turns") or [], 1):
            md_lines.append(f"\n> **第 {idx} 轮用户输入**：{turn.get('user', '')}\n")
            md_lines.append("```markdown")
            md_lines.append(str(turn.get("content") or ""))
            md_lines.append("```")

        if not item["exact_same"]:
            md_lines.append("")
            md_lines.append("**Run 2 完整对话与交付稿（与 Run 1 有差异）**：")
            for idx, turn in enumerate(row2.get("turns") or [], 1):
                md_lines.append(f"\n> **第 {idx} 轮用户输入**：{turn.get('user', '')}\n")
                md_lines.append("```markdown")
                md_lines.append(str(turn.get("content") or ""))
                md_lines.append("```")

        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    out_md = Path(args.out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"完成：{out_csv}（Run1={len(r1_loaded)} 行, Run2={len(r2_loaded)} 行），{out_md}")
    print(f"DeepSeek 用量：{json.dumps(llm.meta(), ensure_ascii=False)}")


if __name__ == "__main__":
    main()
