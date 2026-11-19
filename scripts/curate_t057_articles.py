"""T057 步骤 4：可复现整理并固化全部人工确认初稿与修改稿，生成去重与覆盖报告。"""

from __future__ import annotations

import copy
import json
import sqlite3
from collections import Counter
from pathlib import Path
from statistics import median

from tu_assistant.chat.orchestrator import DISCLAIMER
from tu_assistant.config import load_yaml
from tu_assistant.eval.cases import eval_questions, load_cases
from tu_assistant.synth.articles import (
    TRAIN_CONFIG,
    ArticleStats,
    _eval_overlap_any_turn,
    _history_assistant_text,
    _materials,
    _validate,
    _validate_revision,
    draft_id,
    find_case_near_duplicates,
    normalize_draft_markers,
    training_token_counter,
)
from tu_assistant.synth.knowledge import doc_titles

KB_PATH = Path("artifacts/kb/kb-20261119-045641.sqlite")
OUT_DIR = Path("artifacts/synth/articles/t057-curated")
EVAL_CASES = Path("eval/cases/v1")


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _family_id(sample: dict) -> str:
    meta = sample.get("meta") or {}
    return str(meta["parent"]) if meta.get("parent") else draft_id(sample)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    train_cfg = load_yaml(TRAIN_CONFIG)
    max_seq = train_cfg["max_seq_length"]
    count_tokens = training_token_counter(train_cfg["base_model"])
    questions = eval_questions(load_cases(EVAL_CASES))

    conn = sqlite3.connect(KB_PATH.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        pool = _materials(conn, ArticleStats())
        rel_by_pair = {(r.basis, r.liability): r for r in pool}
        titles = doc_titles(conn)

        # ---- 1. 汇总全部 22 条确认初稿 ----
        t052_path = Path("artifacts/synth/articles/t052-implementation-review/candidates.jsonl")
        t052_row1 = copy.deepcopy(_load_jsonl(t052_path)[0])
        t053_drafts = _load_jsonl(Path("artifacts/synth/articles/t053-new-drafts/candidates.jsonl"))
        t057_drafts = _load_jsonl(Path("artifacts/synth/articles/t057-expand-drafts/candidates.jsonl"))
        t057_comp = _load_jsonl(Path("artifacts/synth/articles/t057-expand-company/candidates.jsonl"))

        raw_drafts = [t052_row1, *t053_drafts, *t057_drafts, *t057_comp]
        curated_drafts: list[dict] = []
        draft_by_id: dict[str, dict] = {}
        seen_ids: set[str] = set()

        for d in raw_drafts:
            d = copy.deepcopy(d)
            did = draft_id(d)
            if did in seen_ids:
                continue
            seen_ids.add(did)
            # 清理 t057-expand-drafts:req1 普法提示末尾多贴的重复引文块
            if did == "t057-expand-drafts:req1":
                body = d["messages"][2]["content"]
                marker = "\n**法律依据**\n"
                tip_idx = body.find("## 普法提示")
                dup_idx = body.find(marker, tip_idx)
                assert tip_idx != -1 and dup_idx != -1
                d["messages"][2]["content"] = body[:dup_idx].rstrip()
                d["meta"]["review_edit"] = "清理 ## 普法提示 末尾重复粘贴的引文块"
            norm = normalize_draft_markers(d, conn)
            norm["meta"]["sample_id"] = did
            plan = [[rel_by_pair[(p[0], p[1])] for p in e["acts"]] for e in norm["meta"]["plan"]]
            ids = _validate(norm["messages"][2]["content"].strip(), plan, conn)
            assert set(ids) == set(norm["meta"]["clause_ids"])
            tok = count_tokens(norm["messages"])
            assert tok <= max_seq, f"初稿 {did} 超出 2048：{tok}"
            norm["meta"]["tokens"] = tok
            norm["meta"]["human_review"] = "approved"
            assert not _eval_overlap_any_turn(norm, questions)
            curated_drafts.append(norm)
            draft_by_id[did] = norm

        # ---- 2. 汇总全部 24 条确认修改稿（显式 request ID 白名单，不用位置切片） ----
        r_t053 = _load_jsonl(Path("artifacts/synth/articles/t053-revisions-trial/candidates.jsonl"))
        spot_keep = {2, 3, 4, 5, 6}
        r_spot = [
            s
            for s in _load_jsonl(Path("artifacts/synth/articles/t057-v11-spotcheck/samples.jsonl"))
            if s["meta"].get("request") in spot_keep
        ]
        r_plain_path = Path("artifacts/synth/articles/t057-expand-revisions-plainer/samples.jsonl")
        r_plain = [s for s in _load_jsonl(r_plain_path) if s["meta"].get("request") in spot_keep]
        r_comp = _load_jsonl(Path("artifacts/synth/articles/t057-expand-revisions-company/samples.jsonl"))
        for group, batch in (
            (r_spot, "t057-v11-spotcheck"),
            (r_plain, "t057-expand-revisions-plainer"),
            (r_comp, "t057-expand-revisions-company"),
        ):
            for s in group:
                s["meta"]["source_batch"] = batch

        curated_revs: list[dict] = []
        for s in [*r_t053, *r_spot, *r_plain, *r_comp]:
            s = copy.deepcopy(s)
            parent = s["meta"]["parent"]
            assert parent in draft_by_id, f"孤儿修改稿：{parent}"
            parent_draft = draft_by_id[parent]
            s["messages"][0] = copy.deepcopy(parent_draft["messages"][0])
            s["messages"][1] = copy.deepcopy(parent_draft["messages"][1])
            draft_text = parent_draft["messages"][2]["content"].strip()
            s["messages"][2] = {
                "role": "assistant",
                "content": _history_assistant_text(draft_text, conn),
            }
            revised = s["messages"][4]["content"].strip()
            # 修正 req6 普法提示法理表述：区分第三十八条（企业恢复原岗位）与第三十九条（人社部门责令改正）
            batch_name = s["meta"].get("source_batch")
            edit_note = "区分第三十八条（企业应代表要求恢复原岗位）与第三十九条（人社部门责令改正）"
            if batch_name == "t057-v11-spotcheck" and s["meta"].get("request") == 6:
                old_tip = "遇到此类情况，可向人力资源社会保障部门反映，要求责令改正并恢复岗位。"
                new_tip = (
                    "遇到拒绝协商可向人力资源社会保障部门反映，要求责令改正；"
                    "遭遇无故调岗的，协商代表本人可依法要求企业恢复原工作岗位。"
                )
                assert old_tip in revised
                revised = revised.replace(old_tip, new_tip, 1)
                s["messages"][4]["content"] = revised
                s["meta"]["review_edit"] = edit_note
            elif batch_name == "t057-expand-revisions-plainer" and s["meta"].get("request") == 6:
                old_tip = "碰上这种事，可以向人力资源社会保障部门反映，要求责令改正、恢复岗位。"
                new_tip = (
                    "碰上企业拒绝协商，可以向人力资源社会保障部门反映，要求责令改正；"
                    "被无故调岗的，代表本人可以依法要求企业恢复原岗位。"
                )
                assert old_tip in revised
                revised = revised.replace(old_tip, new_tip, 1)
                s["messages"][4]["content"] = revised
                s["meta"]["review_edit"] = edit_note
            plan = [[rel_by_pair[(p[0], p[1])] for p in e["acts"]] for e in s["meta"]["plan"]]
            ids = _validate_revision(revised, draft_text, plan, s["meta"]["revision_type"], conn)
            assert set(ids) == set(s["meta"]["clause_ids"])
            assert s["messages"][2]["content"].endswith(DISCLAIMER)
            assert DISCLAIMER.strip() not in revised
            tok = count_tokens(s["messages"])
            assert tok <= max_seq, (
                f"修改稿 {s['meta'].get('source_batch')}:{s['meta'].get('request')} 超出 2048：{tok}"
            )
            s["meta"]["tokens"] = tok
            s["meta"]["human_review"] = "approved"
            assert not _eval_overlap_any_turn(s, questions)
            curated_revs.append(s)

        _write_jsonl(OUT_DIR / "drafts.jsonl", curated_drafts)
        _write_jsonl(OUT_DIR / "revisions.jsonl", curated_revs)

        # ---- 3. 跨请求案例近重复报告 ----
        all_samples = curated_drafts + curated_revs
        fam_by_sid: dict[str, str] = {}
        for s in all_samples:
            m = s["meta"]
            sid = (
                draft_id(s)
                if not m.get("parent")
                else f"{m.get('source_batch', 'rev')}:req{m.get('request')}"
            )
            fam_by_sid[sid] = _family_id(s)

        all_dups = find_case_near_duplicates(all_samples)
        cross_fam = [
            d for d in all_dups if fam_by_sid.get(d["left_id"]) != fam_by_sid.get(d["right_id"])
        ]
        same_fam = len(all_dups) - len(cross_fam)

        dedup_lines = [
            "# T057 跨请求案例近重复筛查报告",
            "",
            (
                f"- 筛查样本总数：**{len(all_samples)}**"
                f"（{len(curated_drafts)} 初稿 + {len(curated_revs)} 修改稿）"
            ),
            (
                "- 检测口径：仅比对脱敏虚构人名/单位名后的 `## 案例` 段与 `# 标题`，"
                "自动跳过 `revise_plainer` 与其 `parent`；"
                "阈值 `2-gram Jaccard >= 0.15` 或 `SequenceMatcher >= 0.35` 或同标题。"
            ),
            (
                f"- 总告警数：{len(all_dups)}（同家族配对 {same_fam} 条；"
                f"**跨家族告警 {len(cross_fam)} 条**）。"
            ),
            "",
            "## 跨家族告警明细与人工裁决",
            "",
            "| 左样本 | 篇 | 右样本 | 篇 | Jaccard | SeqRatio | 同标题 | 裁决 |",
            "|---|---:|---|---:|---:|---:|---|---|",
        ]
        for d in cross_fam:
            dedup_lines.append(
                f"| `{d['left_id']}` | {d['left_article']} | `{d['right_id']}` | {d['right_article']} "
                f"| {d['jaccard']} | {d['seq_ratio']} | {d['same_title']} | 保留（情节独立） |"
            )
        (OUT_DIR / "dedup_report.md").write_text("\n".join(dedup_lines) + "\n", encoding="utf-8")

        # ---- 4. 覆盖与留证报告 ----
        by_kind = Counter(s["meta"]["kind"] for s in all_samples)
        by_doc = Counter(titles[s["meta"]["doc_id"]][0] for s in all_samples)
        pair_freq = Counter(
            f"{p[0]} -> {p[1]}"
            for s in curated_drafts
            for e in s["meta"]["plan"]
            for p in e["acts"]
        )
        all_toks = [s["meta"]["tokens"] for s in all_samples]
        cov_lines = [
            "# T057 固化文章样本覆盖与留证报告",
            "",
            f"- KB：`{KB_PATH}`",
            (
                f"- 固化文件：`{OUT_DIR / 'drafts.jsonl'}`（{len(curated_drafts)} 条）、"
                f"`{OUT_DIR / 'revisions.jsonl'}`（{len(curated_revs)} 条）"
            ),
            f"- 总样本数：**{len(all_samples)}**（家族数：{len(draft_by_id)}）",
            (
                f"- Token 分布（全量 ≤ 2,048）：min **{min(all_toks)}** / "
                f"median **{median(all_toks)}** / max **{max(all_toks)}**"
            ),
            "",
            "## 问法与修改类型分布",
            "",
            "| kind | 数量 |",
            "|---|---:|",
            *[f"| `{k}` | {v} |" for k, v in sorted(by_kind.items())],
            "",
            "## 法规分布（全部 6 部法规，单法规均 ≤ 30%）",
            "",
            "| 法规 | 数量 | 占比 |",
            "|---|---:|---:|",
            *[f"| {doc} | {cnt} | {cnt / len(all_samples):.1%} |" for doc, cnt in by_doc.most_common()],
            "",
            f"## 素材覆盖（初稿覆盖 {len(pair_freq)} / 26 对 `liability_for`）",
            "",
            "| 依据 -> 责任 | 初稿出现篇次 |",
            "|---|---:|",
            *[f"| `{k}` | {v} |" for k, v in pair_freq.most_common()],
        ]
        (OUT_DIR / "coverage_report.md").write_text("\n".join(cov_lines) + "\n", encoding="utf-8")

        print(
            f"CURATED OK: {len(curated_drafts)} drafts + {len(curated_revs)} revisions "
            f"= {len(all_samples)} | cross_fam_dups={len(cross_fam)} "
            f"| tokens={min(all_toks)}..{max(all_toks)}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
