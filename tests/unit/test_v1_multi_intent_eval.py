"""T049 评测集 v1 扩充（multi_violation / intent / boundaries）与 CLI 增强确定性测试。"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from tu_assistant.chat.anonymize import classify_user_intent_signals
from tu_assistant.cli import app
from tu_assistant.eval.cases import eval_questions, load_cases, validate_gold_clauses
from tu_assistant.eval.compare import compare_runs, evaluate_sc015, load_run
from tu_assistant.eval.report import summarize_run
from tu_assistant.eval.runner import run_eval
from tu_assistant.kb.store import get_clause_by_id, get_document, open_kb
from tu_assistant.train.dataset import dedup_against_eval

KB_PATH = Path("artifacts/kb/kb-20261119-045641.sqlite")
V1_DIR = Path("eval/cases/v1")
CAND_DIR = Path("eval/cases/candidates")
NEW_FILES = ("multi_violation.jsonl", "intent.jsonl", "boundaries.jsonl")
T078_DOC_ID = "9fc301cd90566af9"


def _load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _format_citation(conn: sqlite3.Connection, cid: str) -> str:
    clause = get_clause_by_id(conn, cid)
    assert clause is not None
    doc = get_document(conn, clause.doc_id)
    assert doc is not None
    return f"〔《{doc.title}》（{doc.version_label}）{clause.number_text}〕\n> {clause.text}"


# ---- 1. 正式 v1 用例 schema、KB 完整性与候选一致性 ----


def test_v1_full_schema_kb_and_candidate_parity():
    cases = load_cases(V1_DIR)
    assert len(cases) == 98

    case_ids = [c.case_id for c in cases]
    assert len(case_ids) == len(set(case_ids)), "存在重复 case_id"
    assert all(c.source != "train_probe" for c in cases)

    # 校验新增正式文件与已审定候选文件全量一致（全部 confirmed=True，扣除 confirmed 后逐条相等）
    for name in NEW_FILES:
        v1_rows = _load_jsonl(V1_DIR / name)
        cand_rows = _load_jsonl(CAND_DIR / name)
        assert len(cand_rows) == len(v1_rows), f"{name} 候选与正式题数不一致"
        assert all(r.get("confirmed") is True for r in cand_rows), (
            f"{name} 存在未确认候选条目"
        )
        confirmed_cands = [
            {k: v for k, v in row.items() if k != "confirmed"} for row in cand_rows
        ]
        assert v1_rows == confirmed_cands, f"{name} 正式文件与已审定候选不一致"
        assert all(r["source"] == "manual" for r in v1_rows)
        assert all(r.get("eval_set_version") == "v1" for r in v1_rows)

    if not KB_PATH.exists():
        pytest.skip(f"{KB_PATH} 不存在")
    conn = open_kb(KB_PATH)
    try:
        assert validate_gold_clauses(cases, conn) == []
        for name in NEW_FILES:
            for c in load_cases(V1_DIR / name):
                cids = list(c.gold.get("clauses", []))
                for v in c.gold.get("violations", []):
                    cids.extend(v.get("clauses", []))
                    cids.extend(v.get("liability", []))
                for cid in cids:
                    assert not cid.startswith(f"{T078_DOC_ID}:"), (
                        f"{c.case_id} 引用了 T078 已知缺陷文件 {cid}"
                    )
    finally:
        conn.close()


# ---- 2. multi_violation、intent 与 boundaries 专项结构及防伪确认信号校验 ----


def test_multi_violation_structure_and_relations():
    mv_cases = load_cases(V1_DIR / "multi_violation.jsonl")
    assert len(mv_cases) == 10

    actors: set[str] = set()
    for c in mv_cases:
        assert c.category == "multi_violation"
        vs = c.gold.get("violations", [])
        assert len(vs) >= 2, f"{c.case_id} violations 少于 2 条"
        union_ids: set[str] = set()
        for v in vs:
            assert v.get("actor"), f"{c.case_id} 缺少 actor"
            assert v.get("clauses"), f"{c.case_id} 缺少 violation clauses"
            actors.add(v["actor"])
            union_ids.update(v["clauses"])
            union_ids.update(v.get("liability", []))
        assert set(c.gold.get("clauses", [])) == union_ids, (
            f"{c.case_id} gold.clauses 须等于所有 violation clauses ∪ liability"
        )
        assert c.gold.get("rubric"), f"{c.case_id} 缺少 rubric"

    assert len(actors) >= 4
    assert any(
        any(k in a for k in ("工会", "从业人员", "高级管理人员", "分包", "派遣"))
        for a in actors
    )

    if KB_PATH.exists():
        conn = open_kb(KB_PATH)
        try:
            rels = conn.execute(
                "SELECT from_clause_id, to_clause_id FROM clause_relations "
                "WHERE confirmed=1 AND relation_type='liability_for'"
            ).fetchall()
            liab_pairs = {(r[0], r[1]) for r in rels}
            hit_count = sum(
                1
                for c in mv_cases
                if any(
                    (sc, lc) in liab_pairs
                    for v in c.gold.get("violations", [])
                    for sc in v.get("clauses", [])
                    for lc in v.get("liability", [])
                )
            )
            assert hit_count >= 5
        finally:
            conn.close()


def test_intent_scripts_zero_false_confirmation_signals():
    intent_cases = load_cases(V1_DIR / "intent.jsonl")
    assert len(intent_cases) == 10

    for c in intent_cases:
        assert c.category == "intent"
        script = c.input.get("script", [])
        assert 2 <= len(script) <= 3, f"{c.case_id} script 轮数不在 2-3"
        assert c.gold.get("intent") in {"consult", "article"}
        assert c.gold.get("rubric"), f"{c.case_id} 缺少 rubric"

        # 所有第 1 轮模糊开场 5 项用户信号必须全 False
        sig1 = classify_user_intent_signals(script[0], article_task_active=False)
        assert not any(sig1.__dict__.values()), (
            f"{c.case_id} 第1轮触发了意图信号: {sig1}"
        )

        # 咨询收敛题第 2/3 轮不得触发任何用户侧意图信号（避免正则伪确认）
        if c.gold["intent"] == "consult":
            for turn_idx, turn in enumerate(script[1:], 2):
                sig = classify_user_intent_signals(turn, article_task_active=False)
                assert not any(sig.__dict__.values()), (
                    f"{c.case_id} 第{turn_idx}轮触发了用户意图信号: {sig}"
                )


def test_boundaries_structure_and_signals():
    b_cases = load_cases(V1_DIR / "boundaries.jsonl")
    assert len(b_cases) == 8

    refusals = [c for c in b_cases if c.category == "refusal"]
    false_refusals = [c for c in b_cases if c.category == "false_refusal"]
    exceptions = [c for c in b_cases if c.category == "exception"]
    assert (len(refusals), len(false_refusals), len(exceptions)) == (3, 2, 3)

    for c in refusals:
        assert c.gold.get("should_refuse") is True
        assert c.gold.get("rubric")
    ref003 = next(c for c in refusals if c.case_id == "refusal-003")
    assert len(ref003.input.get("script", [])) == 2
    sig1 = classify_user_intent_signals(ref003.input["script"][0], article_task_active=False)
    assert not any(sig1.__dict__.values())

    for c in false_refusals + exceptions:
        assert not c.gold.get("should_refuse")
        assert c.gold.get("clauses")
        assert c.gold.get("rubric")


def test_new_cases_do_not_overlap_existing_v1():
    existing_qs = eval_questions(
        load_cases(V1_DIR / "reviewed.jsonl") + load_cases(V1_DIR / "articles.jsonl")
    )
    new_cases = []
    for name in NEW_FILES:
        new_cases.extend(load_cases(V1_DIR / name))
    new_qs = eval_questions(new_cases)
    existing_samples = [{"messages": [{"role": "user", "content": q}]} for q in existing_qs]
    _, dropped = dedup_against_eval(existing_samples, new_qs, overlap=0.8)
    assert not dropped


# ---- 3. 固定回复端到端运行器 / 报告 / 对比确定性验证 ----


def test_e2e_runner_report_compare_on_t049_cases(tmp_path: Path, monkeypatch):
    if not KB_PATH.exists():
        pytest.skip(f"{KB_PATH} 不存在")

    conn = open_kb(KB_PATH)
    try:
        mv_cases = load_cases(V1_DIR / "multi_violation.jsonl")
        intent_cases = load_cases(V1_DIR / "intent.jsonl")
        boundary_cases = load_cases(V1_DIR / "boundaries.jsonl")
        article_cases = load_cases(V1_DIR / "articles.jsonl")

        # 代表性 17 题子集，全面覆盖 SC-001 ~ SC-008 与 SC-011（含 2 轮与 3 轮 intent 边界）：
        # - mv: mv-001 (全中), mv-003 (半中), mv-007 (零中)
        # - intent 2 轮: intent-001 (T2 确认 consult), intent-008 (T2 确认 article), intent-002 (未确认)
        # - intent 3 轮: intent-004 (T3 确认 consult), intent-005 (3 轮均未确认)
        # - boundaries: 全 8 题 (3 refusal + 2 false_refusal + 3 exception)
        # - article: article-009 (带 protected_names，验证 SC-011 渲染无缺项)
        selected_ids = {
            "mv-001", "mv-003", "mv-007",
            "intent-001", "intent-008", "intent-002",
            "intent-004", "intent-005",
        }
        art009 = next(c for c in article_cases if c.case_id == "article-009")
        subset = (
            [c for c in mv_cases + intent_cases if c.case_id in selected_ids]
            + boundary_cases
            + [art009]
        )
        cases_file = tmp_path / "subset.jsonl"
        cases_file.write_text(
            "".join(
                json.dumps(
                    {
                        "case_id": c.case_id,
                        "category": c.category,
                        "input": c.input,
                        "gold": c.gold,
                        "source": c.source,
                        "eval_set_version": c.eval_set_version,
                    },
                    ensure_ascii=False,
                )
                + "\n"
                for c in subset
            ),
            encoding="utf-8",
        )

        mv001 = next(c for c in mv_cases if c.case_id == "mv-001")
        mv003 = next(c for c in mv_cases if c.case_id == "mv-003")
        mv007 = next(c for c in mv_cases if c.case_id == "mv-007")
        int001 = next(c for c in intent_cases if c.case_id == "intent-001")
        int002 = next(c for c in intent_cases if c.case_id == "intent-002")
        int004 = next(c for c in intent_cases if c.case_id == "intent-004")
        int005 = next(c for c in intent_cases if c.case_id == "intent-005")
        int008 = next(c for c in intent_cases if c.case_id == "intent-008")
        ref001 = next(c for c in boundary_cases if c.case_id == "refusal-001")
        ref002 = next(c for c in boundary_cases if c.case_id == "refusal-002")
        ref003 = next(c for c in boundary_cases if c.case_id == "refusal-003")
        fr001 = next(c for c in boundary_cases if c.case_id == "false-refusal-001")
        fr002 = next(c for c in boundary_cases if c.case_id == "false-refusal-002")
        exc001 = next(c for c in boundary_cases if c.case_id == "exc-001")
        exc002 = next(c for c in boundary_cases if c.case_id == "exc-002")
        exc003 = next(c for c in boundary_cases if c.case_id == "exc-003")

        def cite_all(cids: list[str]) -> str:
            return "\n\n".join(_format_citation(conn, cid) for cid in cids)

        art009_citations = cite_all(art009.gold["clauses"])
        art009_reply = (
            "# 普法案例一：按月领薪不能拖\n\n## 案例\n某制造企业拖欠员工小赵两个月工资。\n\n"
            f"## 以案说法\n{art009_citations}\n\n## 普法提示\n企业应按月足额发放工资。\n\n"
            "# 普法案例二：车间欠薪工会撑腰\n\n## 案例\n某食品厂克扣员工小钱报酬。\n\n"
            f"## 以案说法\n{art009_citations}\n\n## 普法提示\n工会应依法要求企业改正。\n\n"
            "# 普法案例三：维权渠道要记牢\n\n## 案例\n某物流站拖欠员工小孙薪资。\n\n"
            f"## 以案说法\n{art009_citations}\n\n## 普法提示\n劳动者可及时向工会反映。"
        )

        reply_by_user: dict[str, str] = {
            # mv-001: 全中（2/2 violations，4/4 clauses，命中 liability_for）
            mv001.input["message"]: "违法行为认定如下：\n\n" + cite_all(mv001.gold["clauses"]),
            # mv-003: 半中（仅引第1个 violation 实体+责任，1/2 violations，2/4 clauses）
            mv003.input["message"]: "违法行为认定如下：\n\n"
            + cite_all(
                mv003.gold["violations"][0]["clauses"]
                + mv003.gold["violations"][0]["liability"]
            ),
            # mv-007: 零中（无引用）
            mv007.input["message"]: "该情况需要进一步核实具体财务凭证。",
            # intent-001 (2 轮确认 consult)
            int001.input["script"][0]: "请问您主要是想了解相关法律规定，还是需要撰写普法材料？",
            int001.input["script"][1]: "适用条款与法律责任如下：\n\n"
            + cite_all(int001.gold["clauses"]),
            # intent-008 (2 轮确认 article)
            int008.input["script"][0]: "请问您希望咨询具体条文，还是需要普法宣传短文？",
            int008.input["script"][1]: (
                "# 哺乳期权益保护\n\n## 案例\n某企业安排哺乳期女职工小周加班。\n\n"
                "## 以案说法\n违反相关规定。\n\n## 普法提示\n企业应依法保护哺乳期女职工。"
            ),
            # intent-002 (2 轮均未确认 -> SC-001=0.0)
            int002.input["script"][0]: "能再说说具体情况吗？",
            int002.input["script"][1]: "好的，请问还有其他补充信息吗？",
            # intent-004 (3 轮脚本：前 2 轮追问保持 None，第 3 轮确认 consult -> SC-001=1.0)
            int004.input["script"][0]: "请问您平时接触哪些作业环境，目前打算怎么安排？",
            int004.input["script"][1]: "公司近期是否安排过离岗前的职业健康检查？",
            int004.input["script"][2]: "适用条款如下：\n\n" + cite_all(int004.gold["clauses"]),
            # intent-005 (3 轮脚本：3 轮均未确认 -> SC-001=0.0)
            int005.input["script"][0]: "能介绍一下贵单位的基本情况吗？",
            int005.input["script"][1]: "这次调整大概涉及哪些方面的内容？",
            int005.input["script"][2]: "了解，后续如有进一步资料可以再告诉我。",
            # boundaries: refusal 3 题明确拒答
            ref001.input["message"]: "抱歉，个人所得税问题不在本知识库范围内，建议咨询税务部门。",
            ref002.input["message"]: "抱歉，民间借贷纠纷超出了本知识库范围，暂不支持回答。",
            ref003.input["script"][0]: "请问您是想了解辞退相关的法律规定吗？",
            ref003.input["script"][1]: (
                "抱歉，暂不支持代写或起草劳动仲裁申请书等法律文书，建议联系工会法律援助机构。"
            ),
            # false_refusal 2 题正常引用回答
            fr001.input["message"]: "适用条款如下：\n\n" + cite_all(fr001.gold["clauses"]),
            fr002.input["message"]: "适用条款如下：\n\n" + cite_all(fr002.gold["clauses"]),
            # exception 3 题正常引用回答
            exc001.input["message"]: "适用条款如下：\n\n" + cite_all(exc001.gold["clauses"]),
            exc002.input["message"]: "适用条款如下：\n\n" + cite_all(exc002.gold["clauses"]),
            exc003.input["message"]: "适用条款如下：\n\n" + cite_all(exc003.gold["clauses"]),
            # article-009: 第1轮澄清，第2轮输出3篇无身份泄露文章
            art009.input["script"][0]: "请问您是希望了解欠薪维权条款，还是需要普法宣传稿件？",
            art009.input["script"][1]: art009_reply,
        }
    finally:
        conn.close()

    class FakeModelClient:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, messages, temperature=0.0, max_tokens=2048):
            last_user = next(m["content"] for m in reversed(messages) if m["role"] == "user")
            return SimpleNamespace(content=reply_by_user[last_user])

    monkeypatch.setattr("tu_assistant.eval.runner.ModelClient", FakeModelClient)

    artifacts_dir = tmp_path / "artifacts"
    meta1 = run_eval(
        cases_path=cases_file,
        kb_path=KB_PATH,
        endpoint="http://127.0.0.1:8080/v1",
        allowed_hosts=["127.0.0.1"],
        artifacts_dir=artifacts_dir,
        exp_id="exp-mock-t049",
    )
    run_dir1 = artifacts_dir / "eval" / meta1["run_id"]
    results1 = _load_jsonl(run_dir1 / "results.jsonl")
    by_id = {r["case_id"]: r for r in results1}

    # 验证 multi_violation 全中 / 半中 / 零中精确手算值
    assert by_id["mv-001"]["scores"]["multi_violation"] == pytest.approx(1.0)
    assert by_id["mv-001"]["scores"]["recall"] == pytest.approx(1.0)
    assert by_id["mv-001"]["scores"]["precision"] == pytest.approx(1.0)
    assert by_id["mv-001"]["scores"]["relation_completion"] == pytest.approx(1.0)

    assert by_id["mv-003"]["scores"]["multi_violation"] == pytest.approx(0.5)
    assert by_id["mv-003"]["scores"]["recall"] == pytest.approx(0.5)
    assert by_id["mv-003"]["scores"]["precision"] == pytest.approx(1.0)
    assert by_id["mv-003"]["scores"]["relation_completion"] == pytest.approx(1.0)

    assert by_id["mv-007"]["scores"]["multi_violation"] == pytest.approx(0.0)
    assert by_id["mv-007"]["scores"]["recall"] == pytest.approx(0.0)

    # 验证 2 轮与 3 轮 intent：第 1 轮均保持 None；第 2/3 轮确认 = 1.0；2/3 轮均未确认 = 0.0
    assert [t["intent"] for t in by_id["intent-001"]["turns"]] == [None, "consult"]
    assert by_id["intent-001"]["scores"]["intent"] == pytest.approx(1.0)

    assert [t["intent"] for t in by_id["intent-008"]["turns"]] == [None, "article"]
    assert by_id["intent-008"]["scores"]["intent"] == pytest.approx(1.0)

    assert [t["intent"] for t in by_id["intent-002"]["turns"]] == [None, None]
    assert by_id["intent-002"]["scores"]["intent"] == pytest.approx(0.0)

    assert [t["intent"] for t in by_id["intent-004"]["turns"]] == [None, None, "consult"]
    assert by_id["intent-004"]["scores"]["intent"] == pytest.approx(1.0)

    assert [t["intent"] for t in by_id["intent-005"]["turns"]] == [None, None, None]
    assert by_id["intent-005"]["scores"]["intent"] == pytest.approx(0.0)

    # 验证汇总统计精确手算值（覆盖 SC-001 ~ SC-008 与 SC-011）
    summary = summarize_run(results1)
    assert summary["sc001"]["value"] == pytest.approx(3 / 5)
    assert summary["sc001"]["hits"] == 3
    assert summary["sc001"]["total"] == 5
    # SC-002: 13 题带 gold.clauses，总分 1+0.5+0+1+0+1+0+1+1+1+1+1+1 = 9.5
    assert summary["sc002"]["n"] == 13
    assert summary["sc002"]["value"] == pytest.approx(9.5 / 13)
    # SC-003: 10 题有效引用且带 gold.clauses，全部 1.0
    assert summary["sc003"]["n"] == 10
    assert summary["sc003"]["value"] == pytest.approx(1.0)
    assert summary["sc004"]["value"] == pytest.approx(0.5)
    assert summary["sc004"]["n"] == 3
    assert summary["sc005"]["value"] == pytest.approx(1.0)
    assert summary["sc006"]["value"] == pytest.approx(1.0)
    assert summary["sc007"]["pre"] == pytest.approx(1.0)
    assert summary["sc007"]["post"] == pytest.approx(1.0)
    assert summary["sc008"]["outside_rate"] == pytest.approx(1.0)
    assert summary["sc008"]["outside_total"] == 3
    assert summary["sc008"]["special_hits"] == 0
    assert summary["sc008"]["special_total"] == 2
    assert summary["sc008"]["regular_hits"] == 0
    assert summary["sc008"]["regular_total"] == 12
    assert summary["sc008"]["false_refusal_rate"] == pytest.approx(0.0)
    assert summary["sc008"]["false_refusal_total"] == 14
    assert summary["sc011"]["ratio"] == pytest.approx(1.0)
    assert summary["sc011"]["passed"] == 3
    assert summary["sc011"]["total"] == 3

    # 验证 report.md 渲染完整且除 SC-009/SC-010（待人工评审）外所有 SC 指标行均无 '-' 缺项
    report_md = (run_dir1 / "report.md").read_text(encoding="utf-8")
    assert "3/5" in report_md
    assert "3/3" in report_md
    assert "0/2" in report_md
    assert "0/12" in report_md
    sc_rows = [
        line
        for line in report_md.splitlines()
        if line.startswith("| SC-")
    ]
    assert len(sc_rows) == 11
    for row in sc_rows:
        if row.startswith(("| SC-009", "| SC-010")):
            continue
        cols = [col.strip() for col in row.strip("|").split("|")]
        assert not cols[2].startswith("-"), f"报告指标行出现缺项 '-': {row}"

    # 验证同模型二次运行经 compare_runs 后 SC-015 零波动 PASS
    class _NextSecDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz or UTC) + timedelta(seconds=2)

    monkeypatch.setattr("tu_assistant.eval.runner.datetime", _NextSecDatetime)
    meta2 = run_eval(
        cases_path=cases_file,
        kb_path=KB_PATH,
        endpoint="http://127.0.0.1:8080/v1",
        allowed_hosts=["127.0.0.1"],
        artifacts_dir=artifacts_dir,
        exp_id="exp-mock-t049",
    )
    assert meta2["run_id"] != meta1["run_id"]
    run1 = load_run(artifacts_dir, meta1["run_id"])
    run2 = load_run(artifacts_dir, meta2["run_id"])
    cmp = compare_runs([run1, run2])
    sc015 = evaluate_sc015(cmp)
    assert sc015.passed is True


# ---- 4. CLI `tu eval cases review / promote` 轻量增强单元测试 ----


def test_cli_eval_cases_review_and_promote_preserve_source(tmp_path: Path):
    if not KB_PATH.exists():
        pytest.skip(f"{KB_PATH} 不存在")

    cand_file = tmp_path / "cand.jsonl"
    rows = [
        {
            "case_id": "mv-demo",
            "category": "multi_violation",
            "input": {"message": "测试多违法行为"},
            "gold": {
                "clauses": ["4b6c1f293f717293:a3:p1", "4b6c1f293f717293:a51:p1"],
                "violations": [
                    {
                        "actor": "用人单位",
                        "conduct": "阻挠建会",
                        "clauses": ["4b6c1f293f717293:a3:p1"],
                        "liability": ["4b6c1f293f717293:a51:p1", "missing:a999:p1"],
                    }
                ],
                "rubric": ["要点1"],
            },
            "source": "manual",
            "eval_set_version": "v1",
            "confirmed": False,
        },
        {
            "case_id": "int-demo",
            "category": "intent",
            "input": {"script": ["第一轮", "第二轮"]},
            "gold": {"intent": "consult", "rubric": ["要点2"]},
            "source": "public_case",
            "eval_set_version": "v1",
            "confirmed": True,
        },
        {
            "case_id": "syn-demo",
            "category": "clause_id",
            "input": {"message": "合成题"},
            "gold": {"clauses": ["4b6c1f293f717293:a3:p1"]},
            "source": "synthetic",
            "eval_set_version": "v1",
            "confirmed": True,
        },
        {
            "case_id": "syn-rev-demo",
            "category": "clause_id",
            "input": {"message": "已审合成题"},
            "gold": {"clauses": ["4b6c1f293f717293:a3:p1"]},
            "source": "synthetic_reviewed",
            "eval_set_version": "v1",
            "confirmed": True,
        },
        {
            "case_id": "no-source-demo",
            "category": "clause_id",
            "input": {"message": "缺 source 字段题"},
            "gold": {"clauses": ["4b6c1f293f717293:a3:p1"]},
            "eval_set_version": "v1",
            "confirmed": True,
        },
        {
            "case_id": "drop-false-demo",
            "category": "clause_id",
            "input": {"message": "显式未确认题"},
            "gold": {"clauses": ["4b6c1f293f717293:a3:p1"]},
            "source": "manual",
            "eval_set_version": "v1",
            "confirmed": False,
        },
        {
            "case_id": "drop-missing-demo",
            "category": "clause_id",
            "input": {"message": "缺 confirmed 键题"},
            "gold": {"clauses": ["4b6c1f293f717293:a3:p1"]},
            "source": "manual",
            "eval_set_version": "v1",
        },
    ]
    cand_file.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )

    runner = CliRunner()
    # 测试 review 展示 source / violations / 适用条款 / 法律责任 / 不存在条款兜底 / intent / 缺 source 兜底
    res_review = runner.invoke(
        app,
        [
            "eval",
            "cases",
            "review",
            str(cand_file),
            "--kb-version",
            "kb-20261119-045641",
        ],
        input="1 t\n2 s\n5 s\nq\n",
    )
    assert res_review.exit_code == 0, res_review.output
    assert "source=manual" in res_review.output
    assert "违法行为[1] 主体=用人单位｜行为=阻挠建会" in res_review.output
    assert "适用条款: 中华人民共和国工会法（2021-12-24）第三条第1款" in res_review.output
    assert "法律责任: 中华人民共和国工会法（2021-12-24）第五十一条" in res_review.output
    assert "missing:a999:p1（未在库中找到）" in res_review.output
    assert "预期意图: consult" in res_review.output
    assert "source=public_case" in res_review.output
    assert "no-source-demo clause_id（source=manual" in res_review.output

    # 测试 promote：保留 manual/public_case/synthetic_reviewed，
    # 将 synthetic 与缺 source 转为 synthetic_reviewed，并过滤未确认条目
    out_file = tmp_path / "promoted.jsonl"
    res_promote = runner.invoke(
        app,
        ["eval", "cases", "promote", str(cand_file), "--out", str(out_file)],
    )
    assert res_promote.exit_code == 0, res_promote.output
    promoted = _load_jsonl(out_file)
    assert [r["case_id"] for r in promoted] == [
        "mv-demo",
        "int-demo",
        "syn-demo",
        "syn-rev-demo",
        "no-source-demo",
    ]
    assert {r["case_id"]: r["source"] for r in promoted} == {
        "mv-demo": "manual",
        "int-demo": "public_case",
        "syn-demo": "synthetic_reviewed",
        "syn-rev-demo": "synthetic_reviewed",
        "no-source-demo": "synthetic_reviewed",
    }
    assert all("confirmed" not in r for r in promoted)
