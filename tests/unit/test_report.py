"""T061 + T063：评测报告聚合、人工评审 CSV 校验/汇总与只读 CLI 单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tu_assistant.cli import app
from tu_assistant.eval.report import (
    REQUIRED_REVIEW_COLUMNS,
    ReportError,
    extract_failures,
    extract_pending_articles,
    load_reviews,
    render_report,
    render_run_report,
    summarize_run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_row(
    case_id: str,
    category: str,
    *,
    gold: dict | None = None,
    turns: list[dict] | None = None,
    final_text: str = "正常回答。〔《A法》第一条〕",
    recall: float | None = 1.0,
    precision: float | None = 1.0,
    citation_complete: int = 1,
    citation_total: int = 1,
    counts: dict[str, int] | None = None,
    relation_completion: float | None = None,
    refused: bool = False,
    refusal_correct: bool = True,
    omit_refusal_fields: bool = False,
    multi_violation: float | None = None,
    intent: float | None = None,
    article_count: dict | None = None,
    identity_check: dict | None = None,
) -> dict:
    c = {"ok": 1, "corrected": 0, "not_found": 0, "incomplete": 0}
    if counts is not None:
        c = {k: counts.get(k, 0) for k in ("ok", "corrected", "not_found", "incomplete")}
    scores: dict = {
        "recall": recall,
        "precision": precision,
        "citation_complete": citation_complete,
        "citation_total": citation_total,
        "citation_acc": {"counts": c},
        "cited_clause_ids": [],
        "relation_completion": relation_completion,
    }
    if not omit_refusal_fields:
        scores["refusal_evidence"] = {
            "refused": refused,
            "evidence": "无法回答" if refused else None,
            "blocked_by": None,
        }
        scores["refusal_correct"] = refusal_correct
    if multi_violation is not None:
        scores["multi_violation"] = multi_violation
    if intent is not None:
        scores["intent"] = intent
    if article_count is not None:
        scores["article_count"] = article_count
    if identity_check is not None:
        scores["identity_check"] = identity_check

    return {
        "case_id": case_id,
        "category": category,
        "turns": turns if turns is not None else [{"user": "q", "content": final_text}],
        "final_raw": final_text,
        "final_text": final_text,
        "gold": gold if gold is not None else {},
        "scores": scores,
    }


def _write_run(
    artifacts_dir: Path,
    run_id: str,
    rows: list[dict],
    *,
    manifest: dict | None = None,
    existing_report: str | None = None,
) -> Path:
    run_dir = artifacts_dir / "eval" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    m = manifest or {
        "id": run_id,
        "type": "eval_run",
        "inputs": {
            "cases": "eval/cases/v1",
            "kb": "artifacts/kb/kb-20261119-045641.sqlite",
            "exp_id": "exp-test",
        },
        "config": {"exp": "exp-test", "temperature": 0.0},
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(m, ensure_ascii=False), encoding="utf-8"
    )
    (run_dir / "results.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )
    if existing_report is not None:
        (run_dir / "report.md").write_text(existing_report, encoding="utf-8")
    return run_dir


class TestSummarizeAllMetrics:
    def test_all_seven_categories_exact_math(self):
        rows = [
            _make_row(
                "c-01",
                "clause_id",
                recall=1.0,
                precision=0.5,
                citation_complete=2,
                citation_total=2,
                counts={"ok": 1, "corrected": 1, "not_found": 0, "incomplete": 0},
                relation_completion=1.0,
            ),
            _make_row(
                "e-01",
                "exception",
                recall=0.5,
                precision=1.0,
                citation_complete=1,
                citation_total=2,
                counts={"ok": 1, "corrected": 0, "not_found": 1, "incomplete": 1},
                relation_completion=0.5,
            ),
            _make_row(
                "mv-01",
                "multi_violation",
                recall=0.5,
                precision=1.0,
                citation_complete=1,
                citation_total=1,
                counts={"ok": 1, "corrected": 0, "not_found": 0, "incomplete": 0},
                multi_violation=0.5,
            ),
            _make_row(
                "in-01",
                "intent",
                recall=None,
                precision=None,
                citation_complete=0,
                citation_total=0,
                counts={"ok": 0, "corrected": 0, "not_found": 0, "incomplete": 0},
                intent=1.0,
            ),
            _make_row(
                "in-02",
                "intent",
                recall=None,
                precision=None,
                citation_complete=0,
                citation_total=0,
                counts={"ok": 0, "corrected": 0, "not_found": 0, "incomplete": 0},
                intent=0.0,
            ),
            _make_row(
                "ref-01",
                "refusal",
                gold={"should_refuse": True},
                recall=None,
                precision=None,
                citation_complete=0,
                citation_total=0,
                counts={"ok": 0, "corrected": 0, "not_found": 0, "incomplete": 0},
                refused=True,
                refusal_correct=True,
            ),
            _make_row(
                "fr-01",
                "false_refusal",
                gold={"should_refuse": False},
                recall=None,
                precision=None,
                citation_complete=0,
                citation_total=0,
                counts={"ok": 0, "corrected": 0, "not_found": 0, "incomplete": 0},
                refused=True,
                refusal_correct=False,
            ),
            _make_row(
                "art-01",
                "article",
                gold={"expect_articles": [None, 3], "rubric": ["要点1", "要点2"]},
                turns=[
                    {"user": "咨询", "content": "答复"},
                    {
                        "user": "写3篇",
                        "content": "# 1\n## 案例\n甲\n",
                        "anonymize": {"blocked": False},
                    },
                ],
                recall=None,
                precision=None,
                citation_complete=1,
                citation_total=1,
                counts={"ok": 0, "corrected": 1, "not_found": 0, "incomplete": 1},
                article_count={"expected": [None, 3], "per_turn": [0, 3], "ok": True},
                identity_check={"passed": 2, "total": 3, "unparsed_leaks": []},
            ),
        ]

        s = summarize_run(rows, run_id="run-all")
        assert s["case_count"] == 8
        assert s["sc001"] == {"value": 0.5, "hits": 1, "total": 2}
        assert s["sc002"]["n"] == 3
        assert s["sc002"]["value"] == pytest.approx((1.0 + 0.5 + 0.5) / 3)
        assert s["sc003"]["n"] == 3
        assert s["sc003"]["value"] == pytest.approx((0.5 + 1.0 + 1.0) / 3)
        assert s["sc004"] == {"value": 0.5, "n": 1}
        assert s["sc005"] == {"value": 0.75, "n": 2}
        assert s["sc006"] == {"value": pytest.approx(5 / 6), "complete": 5, "total": 6}
        # counts: ok=3, corrected=2, not_found=1, incomplete=2 → total=8, resolved=6
        assert s["sc007"]["counts"] == {
            "ok": 3,
            "corrected": 2,
            "not_found": 1,
            "incomplete": 2,
        }
        assert s["sc007"]["total"] == 8
        assert s["sc007"]["pre"] == pytest.approx(3 / 8)
        assert s["sc007"]["post"] == pytest.approx(5 / 8)
        assert s["sc007"]["resolved_total"] == 6
        assert s["sc007"]["resolved_pre"] == pytest.approx(3 / 6)
        assert s["sc007"]["resolved_post"] == pytest.approx(5 / 6)
        assert s["sc008"]["outside_hits"] == 1 and s["sc008"]["outside_total"] == 1
        assert s["sc008"]["special_hits"] == 1 and s["sc008"]["special_total"] == 1
        assert s["sc008"]["regular_hits"] == 0 and s["sc008"]["regular_total"] == 6
        assert s["sc008"]["false_refusal_rate"] == pytest.approx(1 / 7)
        assert s["sc011"]["passed"] == 2 and s["sc011"]["total"] == 3
        assert s["auxiliary"]["article_count_ok"] == 1
        assert s["auxiliary"]["article_count_total"] == 1

        md = render_report(
            "run-all", "exp-1", rows, kb_version="kb-v1", cases_path="eval/cases/v1"
        )
        for code in [f"SC-{i:03d}" for i in range(1, 12)]:
            assert code in md
        assert "POC 目标值（仅供参考）" in md
        assert "不作为验收条件" in md
        assert "严格全分母（主口径）" in md
        assert "已定位引用（对照）" in md
        assert "0.833（5/6）" in md
        assert "0.375" in md and "0.625" in md  # 3/8, 5/8
        assert "0.500" in md and "0.833" in md  # 3/6, 5/6

    def test_empty_and_zero_citations_boundaries(self):
        s = summarize_run([], run_id="run-empty")
        assert s["case_count"] == 0
        assert s["sc001"]["value"] is None
        assert s["sc002"]["value"] is None
        assert s["sc006"]["value"] is None
        assert s["sc007"]["pre"] is None and s["sc007"]["post"] is None
        assert s["sc008"]["outside_rate"] is None
        assert s["sc008"]["false_refusal_rate"] is None
        md = render_report("run-empty", None, [])
        assert "无失败用例。" in md
        assert "本评测集无普法文章用例。" in md


class TestFailureExtraction:
    def test_all_ten_deterministic_failure_triggers(self, tmp_path):
        rows = [
            _make_row("f01-recall", "clause_id", recall=0.5),
            _make_row("f02-precision", "clause_id", precision=0.5),
            _make_row(
                "f03-citation",
                "clause_id",
                citation_complete=1,
                citation_total=2,
                counts={"ok": 1, "corrected": 0, "not_found": 1, "incomplete": 1},
            ),
            _make_row(
                "f04-missed-refusal",
                "refusal",
                gold={"should_refuse": True},
                recall=None,
                precision=None,
                citation_complete=0,
                citation_total=0,
                counts={},
                refused=False,
                refusal_correct=False,
            ),
            _make_row(
                "f05-false-refusal",
                "clause_id",
                refused=True,
                refusal_correct=False,
            ),
            _make_row("f06-relation", "clause_id", relation_completion=0.5),
            _make_row("f07-mv", "multi_violation", multi_violation=0.5),
            _make_row(
                "f08-intent",
                "intent",
                recall=None,
                precision=None,
                citation_complete=0,
                citation_total=0,
                counts={},
                intent=0.0,
            ),
            _make_row(
                "f09-article-count",
                "article",
                gold={"expect_articles": 3},
                recall=None,
                precision=None,
                citation_complete=0,
                citation_total=0,
                counts={},
                article_count={"expected": 3, "per_turn": [1], "ok": False},
            ),
            _make_row(
                "f10-identity-and-block",
                "article",
                gold={"expect_articles": 2},
                turns=[
                    {"user": "u", "content": "c", "anonymize": {"blocked": True}},
                ],
                recall=None,
                precision=None,
                citation_complete=0,
                citation_total=0,
                counts={},
                identity_check={
                    "passed": 1,
                    "total": 2,
                    "unparsed_leaks": [{"turn": 1, "leaked": ["某厂"]}],
                },
            ),
            _make_row(
                "f11-manual-fail",
                "article",
                gold={"expect_articles": 1},
                recall=None,
                precision=None,
                citation_complete=0,
                citation_total=0,
                counts={},
            ),
            _make_row("p00-clean", "clause_id"),
        ]
        csv_path = tmp_path / "reviews.csv"
        csv_path.write_text(
            "run_id,case_id,reviewer,verdict,comment,created_at,dimension\n"
            "r1,f11-manual-fail,法律顾问,fail,构成要件错误,2026-11-22T10:00:00Z,correctness\n",
            encoding="utf-8",
        )
        reviews = load_reviews(csv_path, run_id="r1", results=rows)
        failures = extract_failures(rows, reviews=reviews)
        by_id = {f["case_id"]: "；".join(f["reasons"]) for f in failures}

        assert "p00-clean" not in by_id
        assert [f["case_id"] for f in failures] == sorted(by_id)
        assert "recall=0.500" in by_id["f01-recall"]
        assert "precision=0.500" in by_id["f02-precision"]
        assert "not_found=1" in by_id["f03-citation"]
        assert "incomplete=1" in by_id["f03-citation"]
        assert "未标明出处=1" in by_id["f03-citation"]
        assert "范围外未拒答" in by_id["f04-missed-refusal"]
        assert "范围内误拒" in by_id["f05-false-refusal"]
        assert "关联条款未全补" in by_id["f06-relation"]
        assert "多违法行为未全识别" in by_id["f07-mv"]
        assert "意图未在 3 轮内确认" in by_id["f08-intent"]
        assert "文章篇数不符" in by_id["f09-article-count"]
        assert "文章身份信息泄露" in by_id["f10-identity-and-block"]
        assert "未拆篇轮次含保护名称" in by_id["f10-identity-and-block"]
        assert "引用冲突暂缓交稿" in by_id["f10-identity-and-block"]
        assert "人工评审未通过（correctness/法律顾问）" in by_id["f11-manual-fail"]

    def test_all_passing_shows_no_failures(self):
        rows = [_make_row("c-ok", "clause_id")]
        assert extract_failures(rows) == []
        md = render_report("r-ok", "exp-1", rows)
        assert "无失败用例。" in md


class TestReviewsTemplateAndValidation:
    def _sample_article_rows(self) -> list[dict]:
        return [
            _make_row(
                "article-001",
                "article",
                gold={"expect_articles": 3, "rubric": ["多篇要点"]},
                recall=None,
                precision=None,
                citation_complete=0,
                citation_total=0,
                counts={},
                article_count={"expected": 3, "per_turn": [3], "ok": True},
            ),
            _make_row(
                "article-005",
                "article",
                gold={"expect_articles": [1, 1], "rubric": ["单篇改稿"]},
                recall=None,
                precision=None,
                citation_complete=0,
                citation_total=0,
                counts={},
                article_count={"expected": [1, 1], "per_turn": [1, 1], "ok": True},
            ),
            _make_row(
                "article-007",
                "article",
                gold={"should_refuse": True, "rubric": ["范围外应拒答"]},
                recall=None,
                precision=None,
                citation_complete=0,
                citation_total=0,
                counts={},
                refused=True,
                refusal_correct=True,
            ),
            _make_row("clause-001", "clause_id"),
        ]

    def test_repo_review_template_valid_and_loadable(self):
        tpl = REPO_ROOT / "eval" / "review-template.csv"
        assert tpl.exists()
        header = tpl.read_text(encoding="utf-8").splitlines()[0].split(",")
        for col in REQUIRED_REVIEW_COLUMNS:
            assert col in header
        assert header[-1] == "dimension"
        entries = load_reviews(tpl, run_id="run-x", results=self._sample_article_rows())
        assert entries == []

    def test_load_reviews_normal_multi_reviewer_dedup_and_ignore_other_runs(self, tmp_path):
        rows = self._sample_article_rows()
        csv_path = tmp_path / "r.csv"
        # UTF-8 BOM + 多 run 混存 + 同评审人追加修订（按 created_at 与行号取新） + 多评审人
        csv_path.write_text(
            "\ufeffrun_id,case_id,reviewer,verdict,comment,created_at,dimension\n"
            "other-run,unknown-id,甲,invalid_verdict,忽略其他run,2026-11-22T01:00:00Z,bad\n"
            "r1,article-001,项目方,fail,初评误判,2026-11-22T09:00:00Z,correctness\n"
            "r1,article-001,项目方,PASS,复评通过,2026-11-22T10:00:00Z,correctness\n"
            "r1,article-001,法律顾问,minor_issue,措辞可优化,2026-11-22T10:30:00Z,correctness\n"
            "r1,article-005,项目方,fail,首评不通过,2026-11-22T10:00:00Z,correctness\n"
            "r1,article-005,项目方,pass,同行时间戳靠后覆盖,2026-11-22T10:00:00Z,correctness\n"
            "r1,article-001,项目方,fail,三篇高度雷同,2026-11-22T11:00:00Z,diversity\n"
            "r1,article-001,法律顾问,pass,场景差异明显,2026-11-22T11:30:00Z,diversity\n"
            "r1,article-007,项目方,pass,拒答理由充分,2026-11-22T12:00:00Z,other\n",
            encoding="utf-8",
        )
        entries = load_reviews(csv_path, run_id="r1", results=rows)
        assert len(entries) == 6
        a5 = next(e for e in entries if e.case_id == "article-005")
        assert a5.verdict == "pass" and a5.comment == "同行时间戳靠后覆盖"
        s = summarize_run(rows, reviews=entries, run_id="r1")
        # SC-009: article-001(项目方=pass, 法律顾问=minor_issue) + article-005(项目方=pass) → 2/3
        assert s["sc009"]["status"] == "scored"
        assert s["sc009"]["counts"] == {"pass": 2, "minor_issue": 1, "fail": 0}
        assert s["sc009"]["total"] == 3
        assert s["sc009"]["covered_cases"] == 2
        assert s["sc009"]["eligible_cases"] == 2
        assert s["sc009"]["value"] == pytest.approx(2 / 3)
        # SC-010: article-001(项目方=fail, 法律顾问=pass) → 实质重复率 fail/total = 1/2
        assert s["sc010"]["status"] == "scored"
        assert s["sc010"]["counts"] == {"pass": 1, "minor_issue": 0, "fail": 1}
        assert s["sc010"]["total"] == 2
        assert s["sc010"]["covered_cases"] == 1
        assert s["sc010"]["eligible_cases"] == 1
        assert s["sc010"]["value"] == pytest.approx(0.5)

        pending = extract_pending_articles(rows, run_id="r1", reviews=entries)
        assert [p["case_id"] for p in pending] == ["article-001", "article-005", "article-007"]
        assert pending[0]["status"].startswith("已评（")
        assert pending[1]["status"].startswith("已评（")
        assert pending[2]["status"].startswith("已评（")

    def test_six_column_backward_compatibility(self, tmp_path):
        rows = self._sample_article_rows()
        csv_path = tmp_path / "six_col.csv"
        csv_path.write_text(
            "run_id,case_id,reviewer,verdict,comment,created_at\n"
            "r1,article-001,项目方,pass,构成要件准确,2026-11-22T10:00:00Z\n"
            "r1,article-007,项目方,pass,拒答正常,2026-11-22T10:05:00Z\n",
            encoding="utf-8",
        )
        entries = load_reviews(csv_path, run_id="r1", results=rows)
        assert {(e.case_id, e.dimension) for e in entries} == {
            ("article-001", "correctness"),
            ("article-007", "other"),
        }
        md = render_report("r1", "exp-1", rows, reviews=entries, reviews_path=csv_path)
        assert "1.000（pass=1, minor_issue=0, fail=0；覆盖 1/2 题，共 1 条）" in md
        assert "缺少 diversity 维度标注" in md
        assert "diversity 待评审" in md

    @pytest.mark.parametrize(
        ("content", "err_substr"),
        [
            ("", "缺少表头"),
            ("run_id,case_id,reviewer,verdict,comment\nr1,article-001,甲,pass,ok\n", "created_at"),
            (
                "run_id,case_id,reviewer,verdict,comment,created_at,dimension\n"
                "r1,no-such-case,甲,pass,ok,2026-11-22,correctness\n",
                "第 2 行",
            ),
            (
                "run_id,case_id,reviewer,verdict,comment,created_at,dimension\n"
                "r1,article-001,甲,good,ok,2026-11-22,correctness\n",
                "verdict",
            ),
            (
                "run_id,case_id,reviewer,verdict,comment,created_at,dimension\n"
                "r1,article-001,,pass,ok,2026-11-22,correctness\n",
                "reviewer",
            ),
            (
                "run_id,case_id,reviewer,verdict,comment,created_at,dimension\n"
                "r1,article-001,甲,pass,ok,2026-11-22,style\n",
                "dimension",
            ),
            (
                "run_id,case_id,reviewer,verdict,comment,created_at,dimension\n"
                "r1,clause-001,甲,pass,ok,2026-11-22,correctness\n",
                "不是普法文章用例",
            ),
            (
                "run_id,case_id,reviewer,verdict,comment,created_at,dimension\n"
                "r1,article-007,甲,pass,ok,2026-11-22,correctness\n",
                "should_refuse=true",
            ),
            (
                "run_id,case_id,reviewer,verdict,comment,created_at,dimension\n"
                "r1,article-005,甲,pass,ok,2026-11-22,diversity\n",
                "不是多篇生成题",
            ),
        ],
    )
    def test_invalid_reviews_fail_fast(self, tmp_path, content, err_substr):
        csv_path = tmp_path / "bad.csv"
        csv_path.write_text(content, encoding="utf-8")
        with pytest.raises(ReportError, match=err_substr):
            load_reviews(csv_path, run_id="r1", results=self._sample_article_rows())

    def test_csv_multiline_quotes_physical_line_num_extra_cols_and_encoding(self, tmp_path):
        rows = self._sample_article_rows()

        # 1. 带引号多行评审意见保留换行，且空时间戳追加修订按行号覆盖前一条带时间戳记录
        ok_csv = tmp_path / "multiline.csv"
        ok_csv.write_text(
            "run_id,case_id,reviewer,verdict,comment,created_at,dimension\n"
            'r1,article-001,甲,fail,"第一点\n第二点",2026-11-22T09:00:00Z,correctness\n'
            'r1,article-001,甲,pass,"修订后\n通过",,correctness\n',
            encoding="utf-8",
        )
        entries = load_reviews(ok_csv, run_id="r1", results=rows)
        assert len(entries) == 1
        assert entries[0].verdict == "pass"
        assert entries[0].comment == "修订后\n通过"

        # 2. 空行之后报错给出真实物理行号（第 4 行而非第 2 行）
        blank_csv = tmp_path / "blank_lines.csv"
        blank_csv.write_text(
            "run_id,case_id,reviewer,verdict,comment,created_at,dimension\n"
            "\n"
            "\n"
            "r1,article-001,甲,bad_verdict,ok,2026-11-22,correctness\n",
            encoding="utf-8",
        )
        with pytest.raises(ReportError, match="第 4 行"):
            load_reviews(blank_csv, run_id="r1", results=rows)

        # 3. 未加引号逗号导致多余列：拒绝静默错位
        extra_csv = tmp_path / "extra_cols.csv"
        extra_csv.write_text(
            "run_id,case_id,reviewer,verdict,comment,created_at\n"
            "r1,article-001,甲,pass,条款准确,建议保留,2026-11-22T10:00:00Z\n",
            encoding="utf-8",
        )
        with pytest.raises(ReportError, match="列数超出表头"):
            load_reviews(extra_csv, run_id="r1", results=rows)

        # 4. 非 UTF-8（GBK）编码：转为 ReportError
        gbk_csv = tmp_path / "gbk.csv"
        gbk_csv.write_bytes(
            "run_id,case_id,reviewer,verdict,comment,created_at\n"
            "r1,article-001,甲,pass,中文GBK,2026-11-22\n".encode("gbk")
        )
        with pytest.raises(ReportError, match="UTF-8"):
            load_reviews(gbk_csv, run_id="r1", results=rows)

    def test_mixed_iso_timestamps_blank_dimension_duplicate_headers_and_empty_run_id(
        self, tmp_path
    ):
        rows = self._sample_article_rows()

        # 1. 混用带时区 ISO 与空格分隔无时区时间：不因空格 < 'T' 误选旧 fail，后行 pass 胜出
        #    同为带时区 ISO：按 UTC 统一比较（02:00Z = 10:00+08:00 > 09:00+08:00）
        ts_csv = tmp_path / "mixed_ts.csv"
        ts_csv.write_text(
            "run_id,case_id,reviewer,verdict,comment,created_at,dimension\n"
            "r1,article-001,甲,fail,旧记录,2026-11-22T09:00:00+08:00,correctness\n"
            "r1,article-001,甲,pass,新记录空格格式,2026-11-22 10:00,correctness\n"
            "r1,article-005,乙,fail,早UTC,2026-11-22T02:00:00Z,\n"
            "r1,article-005,乙,pass,晚东八区,2026-11-22T11:00:00+08:00,\n"
            "r1,article-007,乙,pass,拒答题留空归other,2026-11-22T11:00:00+08:00,\n",
            encoding="utf-8",
        )
        entries = load_reviews(ts_csv, run_id="r1", results=rows)
        by_key = {(e.case_id, e.reviewer): e for e in entries}
        assert by_key[("article-001", "甲")].verdict == "pass"
        assert by_key[("article-005", "乙")].verdict == "pass"
        # 7 列模板 dimension 留空：普通文章默认 correctness，拒答题归 other
        assert by_key[("article-005", "乙")].dimension == "correctness"
        assert by_key[("article-007", "乙")].dimension == "other"

        # 2. 表头重复列名：报错
        dup_csv = tmp_path / "dup_header.csv"
        dup_csv.write_text(
            "run_id,case_id,reviewer,verdict,comment,created_at,verdict\n"
            "r1,article-001,甲,pass,ok,2026-11-22,fail\n",
            encoding="utf-8",
        )
        with pytest.raises(ReportError, match="重复列名"):
            load_reviews(dup_csv, run_id="r1", results=rows)

        # 3. 非空行缺少 run_id：报错而非静默跳过
        no_run_csv = tmp_path / "empty_run.csv"
        no_run_csv.write_text(
            "run_id,case_id,reviewer,verdict,comment,created_at,dimension\n"
            ",article-001,甲,pass,忘填run_id,2026-11-22,correctness\n",
            encoding="utf-8",
        )
        with pytest.raises(ReportError, match="run_id 不能为空"):
            load_reviews(no_run_csv, run_id="r1", results=rows)

        # 4. 实得 0 篇的普通文章题在待评审清单中标明“待评审（实得 0 篇）”
        zero_row = _make_row(
            "article-000",
            "article",
            gold={"expect_articles": 3, "rubric": ["三篇"]},
            recall=None,
            precision=None,
            citation_complete=0,
            citation_total=0,
            counts={},
            article_count={"expected": 3, "per_turn": [0], "ok": False},
        )
        pending = extract_pending_articles([zero_row, rows[2]], run_id="r1")
        assert pending[0]["status"] == "待评审（实得 0 篇）"
        assert pending[1]["status"] == "待评审"


class TestHistoricalCompatAndCliProtection:
    def test_legacy_schema_without_refusal_evidence_recomputed(self, tmp_path):
        rows = [
            _make_row(
                "legacy-1",
                "clause_id",
                final_text="抱歉，这超出了我的知识范围。",
                omit_refusal_fields=True,
            ),
            _make_row(
                "legacy-2",
                "clause_id",
                final_text="依据〔《A法》第一条〕应当支付工资。",
                omit_refusal_fields=True,
            ),
        ]
        # 复现 B1：缺少 refusal_evidence 但含旧版 refusal_correct=True（与当前 detect_refusal 冲突）
        conflict_row = _make_row(
            "legacy-conflict",
            "refusal",
            gold={"should_refuse": True},
            final_text="这是一个普通回答，没有拒答短语。",
            recall=None,
            precision=None,
            citation_complete=0,
            citation_total=0,
            counts={},
            omit_refusal_fields=True,
        )
        conflict_row["scores"]["refusal_correct"] = True
        rows.append(conflict_row)

        _write_run(tmp_path, "run-legacy", rows)
        md = render_run_report(tmp_path, "run-legacy")
        assert "缺少 `refusal_evidence`" in md
        assert "范围外正确拒答 0.000（0/1）" in md
        assert "范围内误拒 0.500（1/2）" in md
        assert "| refusal | 1 | 1 |" in md
        assert "legacy-1" in md and "范围内误拒" in md
        assert "legacy-conflict" in md and "范围外未拒答" in md

    def test_cli_report_stdout_out_reviews_and_overwrite_guard(self, tmp_path):
        runner = CliRunner()
        rows = [
            _make_row("c1", "clause_id"),
            _make_row(
                "a1",
                "article",
                gold={"expect_articles": 2, "rubric": ["多篇"]},
                recall=None,
                precision=None,
                citation_complete=0,
                citation_total=0,
                counts={},
                article_count={"expected": 2, "per_turn": [2], "ok": True},
            ),
        ]
        original_text = "HISTORICAL LOCKED REPORT\n"
        run_dir = _write_run(
            tmp_path, "run-locked", rows, existing_report=original_text
        )
        other_dir = _write_run(
            tmp_path, "run-other", rows, existing_report=original_text
        )
        locked_report = run_dir / "report.md"
        other_report = other_dir / "report.md"

        # 1. 不传 --out：输出到 stdout，原 report.md 字节不变
        res = runner.invoke(
            app, ["eval", "report", "run-locked", "--artifacts", str(tmp_path)]
        )
        assert res.exit_code == 0, res.output
        assert "# 评测报告 run-locked" in res.output
        assert locked_report.read_text(encoding="utf-8") == original_text

        # 2. --out 指向已有历史 run 目录内任意路径（含已有产物、跨 run、符号链接、新建文件）：均拒绝，退出码 2
        symlink_to_locked = tmp_path / "link_report.md"
        symlink_to_locked.symlink_to(locked_report)
        for protected in (
            locked_report,
            other_report,
            symlink_to_locked,
            run_dir / "manifest.json",
            run_dir / "new_report.md",
        ):
            res_guard = runner.invoke(
                app,
                [
                    "eval",
                    "report",
                    "run-locked",
                    "--artifacts",
                    str(tmp_path),
                    "--out",
                    str(protected),
                ],
            )
            assert res_guard.exit_code == 2
        assert locked_report.read_text(encoding="utf-8") == original_text
        assert other_report.read_text(encoding="utf-8") == original_text

        # 3. --out 指向目录：捕获 OSError 返回退出码 2
        res_dir = runner.invoke(
            app,
            [
                "eval",
                "report",
                "run-locked",
                "--artifacts",
                str(tmp_path),
                "--out",
                str(tmp_path),
            ],
        )
        assert res_dir.exit_code == 2

        # 4. --reviews 合法与非法（含退出码 2）
        good_csv = tmp_path / "good_reviews.csv"
        good_csv.write_text(
            "run_id,case_id,reviewer,verdict,comment,created_at,dimension\n"
            "run-locked,a1,项目方,pass,准确,2026-11-22T10:00:00Z,correctness\n"
            "run-locked,a1,项目方,pass,多样,2026-11-22T10:05:00Z,diversity\n",
            encoding="utf-8",
        )
        out_file = tmp_path / "exported" / "report_with_reviews.md"
        res_out = runner.invoke(
            app,
            [
                "eval",
                "report",
                "run-locked",
                "--reviews",
                str(good_csv),
                "--artifacts",
                str(tmp_path),
                "--out",
                str(out_file),
            ],
        )
        assert res_out.exit_code == 0, res_out.output
        out_text = out_file.read_text(encoding="utf-8")
        assert "1.000（pass=1, minor_issue=0, fail=0；覆盖 1/1 题，共 1 条）" in out_text
        assert "0.000（pass=1, minor_issue=0, fail=0；覆盖 1/1 题，共 1 条）" in out_text

        bad_csv = tmp_path / "bad_reviews.csv"
        bad_csv.write_text("run_id,case_id\n", encoding="utf-8")
        res_bad_csv = runner.invoke(
            app,
            [
                "eval",
                "report",
                "run-locked",
                "--reviews",
                str(bad_csv),
                "--artifacts",
                str(tmp_path),
            ],
        )
        assert res_bad_csv.exit_code == 2

        # 5. 非法 run_id（含 "." / ".." / 逃逸 / 空白）与缺失目录：退出码 2
        for bad_id in (".", "..", "../escape", " run-locked "):
            res_bad = runner.invoke(
                app, ["eval", "report", bad_id, "--artifacts", str(tmp_path)]
            )
            assert res_bad.exit_code == 2, bad_id
        res_missing = runner.invoke(
            app, ["eval", "report", "run-missing", "--artifacts", str(tmp_path)]
        )
        assert res_missing.exit_code == 2
