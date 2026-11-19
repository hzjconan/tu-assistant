"""可复现地整理并校验 T053 初稿池与修改稿保留候选（candidates.jsonl）。

从以下只读原始产物出发，应用全部经用户确认的筛选与最小人工校订，
重算 Qwen tokenizer 长度并用当前校验逻辑逐条复验：
  1. artifacts/synth/articles/t052-implementation-review/candidates.jsonl（取 1–2 篇并规范化第1款）
  2. artifacts/synth/articles/t053-new-drafts/samples.jsonl（保留 Req 1, 2, 5, 6, 8）
  3. artifacts/synth/articles/t053-revisions-trial/samples.jsonl（保留 Req 1–5, 7–13）
"""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

from tu_assistant.chat.orchestrator import DISCLAIMER
from tu_assistant.config import load_yaml
from tu_assistant.eval.cases import eval_questions, load_cases
from tu_assistant.synth.articles import (
    MAX_DRAFT_TOKENS,
    TRAIN_CONFIG,
    ArticleStats,
    _eval_overlap_any_turn,
    _history_assistant_text,
    _materials,
    _validate,
    _validate_revision,
    draft_id,
    normalize_draft_markers,
    training_token_counter,
)

KB_PATH = Path("artifacts/kb/kb-20261119-045641.sqlite")
T052_CANDIDATES = Path("artifacts/synth/articles/t052-implementation-review/candidates.jsonl")
NEW_DRAFTS_RAW = Path("artifacts/synth/articles/t053-new-drafts/samples.jsonl")
NEW_DRAFTS_OUT = Path("artifacts/synth/articles/t053-new-drafts/candidates.jsonl")
REVISIONS_RAW = Path("artifacts/synth/articles/t053-revisions-trial/samples.jsonl")
REVISIONS_OUT = Path("artifacts/synth/articles/t053-revisions-trial/candidates.jsonl")
EVAL_CASES = Path("eval/cases/v1")

KEPT_NEW_DRAFT_REQS = (1, 2, 5, 6, 8)
KEPT_REVISION_REQS = (1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13)


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _replace_once(text: str, old: str, new: str) -> str:
    assert old in text, f"预期替换串不存在：{old!r}"
    return text.replace(old, new, 1)


def main() -> None:
    train_cfg = load_yaml(TRAIN_CONFIG)
    max_seq = train_cfg["max_seq_length"]
    count_tokens = training_token_counter(train_cfg["base_model"])
    questions = eval_questions(load_cases(EVAL_CASES))

    conn = sqlite3.connect(KB_PATH.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        pool = _materials(conn, ArticleStats())
        rel_by_pair = {(r.basis, r.liability): r for r in pool}

        # ---- 1. 整理 7 条确认初稿池 ----
        confirmed_drafts: list[dict] = []

        for d in _load_jsonl(T052_CANDIDATES):
            if len(d["meta"]["plan"]) not in (1, 2):
                continue
            norm = normalize_draft_markers(d, conn)
            norm["meta"]["markers_normalized_kb"] = KB_PATH.stem
            confirmed_drafts.append(norm)

        new_by_req = {s["meta"]["request"]: s for s in _load_jsonl(NEW_DRAFTS_RAW)}
        for req in KEPT_NEW_DRAFT_REQS:
            d = copy.deepcopy(new_by_req[req])
            d["meta"]["source_batch"] = "t053-new-drafts"
            if req == 1:
                text = d["messages"][2]["content"]
                assert "某劳务公司" in text and "该劳务公司" in text
                d["messages"][2]["content"] = text.replace("某劳务公司", "某人力资源服务公司").replace(
                    "该劳务公司", "该人力资源服务公司"
                )
                d["meta"]["review_edit"] = (
                    "主体称谓微调：某劳务公司→某人力资源服务公司（对齐第40条第4款“人力资源服务机构”委托主体）"
                )
            elif req == 5:
                d["messages"][1]["content"] = _replace_once(
                    d["messages"][1]["content"], "出差住店被降薪辞退", "出差住店被降薪停工"
                )
                d["messages"][2]["content"] = _replace_once(
                    d["messages"][2]["content"],
                    "# 出差住店被降薪辞退，当场发现怎么办",
                    "# 出差住店被降薪停工，当场发现怎么办",
                )
                d["meta"]["review_edit"] = (
                    "标题与问句微调：被降薪辞退→被降薪停工（案例仅交代降薪与停止工作安排，无辞退事实）"
                )
            elif req == 8:
                d["messages"][2]["content"] = _replace_once(
                    d["messages"][2]["content"],
                    "# 前台发现可疑情况不报告，酒店被罚",
                    "# 前台发现可疑情况不报告，酒店恐担责",
                )
                d["meta"]["review_edit"] = "第1篇标题微调：酒店被罚→酒店恐担责（避免标题表述为已处罚）"
            confirmed_drafts.append(d)

        draft_by_id: dict[str, dict] = {}
        for d in confirmed_drafts:
            plan = [[rel_by_pair[(p[0], p[1])] for p in e["acts"]] for e in d["meta"]["plan"]]
            ids = _validate(d["messages"][2]["content"].strip(), plan, conn)
            assert set(ids) == set(d["meta"]["clause_ids"])
            tok = count_tokens(d["messages"])
            assert tok <= MAX_DRAFT_TOKENS, f"{draft_id(d)} 超出初稿上限：{tok}"
            d["meta"]["tokens"] = tok
            assert not _eval_overlap_any_turn(d, questions)
            draft_by_id[draft_id(d)] = d

        _write_jsonl(NEW_DRAFTS_OUT, confirmed_drafts)
        print(
            f"初稿池：{len(confirmed_drafts)} 条写入 {NEW_DRAFTS_OUT}，"
            f"tokens={min(d['meta']['tokens'] for d in confirmed_drafts)}.."
            f"{max(d['meta']['tokens'] for d in confirmed_drafts)}"
        )

        # ---- 2. 整理 12 条确认修改样本 ----
        rev_by_req = {s["meta"]["request"]: s for s in _load_jsonl(REVISIONS_RAW)}
        confirmed_revs: list[dict] = []
        for req in KEPT_REVISION_REQS:
            s = copy.deepcopy(rev_by_req[req])
            parent = s["meta"]["parent"]
            parent_draft = draft_by_id[parent]
            # 历史轮严格同步自确认初稿（保证初稿校订后历史上下文零漂移）
            s["messages"][0] = copy.deepcopy(parent_draft["messages"][0])
            s["messages"][1] = copy.deepcopy(parent_draft["messages"][1])
            draft_text = parent_draft["messages"][2]["content"].strip()
            s["messages"][2] = {
                "role": "assistant",
                "content": _history_assistant_text(draft_text, conn),
            }

            revised = s["messages"][4]["content"].strip()
            if req == 4:
                revised = _replace_once(
                    revised,
                    "某民办职业技能培训学校以课时费为主要收入来源的教师赵某",
                    "某民办职业技能培训学校以工资收入为主要生活来源的专职教师赵某",
                )
                revised = _replace_once(
                    revised,
                    "赵某以课时费为主要生活来源，属于用人单位劳动者",
                    "赵某以工资收入为主要生活来源，属于用人单位劳动者",
                )
                s["meta"]["review_edit"] = (
                    "要件微调：以课时费为主要收入来源的教师→以工资收入为主要生活来源的专职教师"
                    "（对齐《工会法》第3条第1款法定要件）"
                )
            elif req in (9, 10):
                revised = _replace_once(
                    revised,
                    "# 出差住店被降薪辞退，当场发现怎么办",
                    "# 出差住店被降薪停工，当场发现怎么办",
                )
                s["meta"]["review_edit"] = (
                    "同步初稿 req5 标题微调：被降薪辞退→被降薪停工（与案例事实一致）"
                )

            s["messages"][4]["content"] = revised
            plan = [[rel_by_pair[(p[0], p[1])] for p in e["acts"]] for e in s["meta"]["plan"]]
            ids = _validate_revision(revised, draft_text, plan, s["meta"]["revision_type"], conn)
            assert set(ids) == set(s["meta"]["clause_ids"])
            assert s["messages"][2]["content"].endswith(DISCLAIMER)
            assert DISCLAIMER.strip() not in revised
            tok = count_tokens(s["messages"])
            assert tok <= max_seq, f"Req {req} 超出 2048：{tok}"
            s["meta"]["tokens"] = tok
            s["meta"]["source_batch"] = "t053-revisions-trial"
            s["meta"]["human_review"] = "approved"
            assert not _eval_overlap_any_turn(s, questions)
            confirmed_revs.append(s)

        _write_jsonl(REVISIONS_OUT, confirmed_revs)
        toks = [s["meta"]["tokens"] for s in confirmed_revs]
        by_type: dict[str, int] = {}
        for s in confirmed_revs:
            rt = s["meta"]["revision_type"]
            by_type[rt] = by_type.get(rt, 0) + 1
        print(
            f"修改稿：{len(confirmed_revs)} 条写入 {REVISIONS_OUT}，"
            f"分类型={by_type}，tokens={min(toks)}..{max(toks)}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
