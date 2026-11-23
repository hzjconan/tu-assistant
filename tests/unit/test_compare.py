"""eval.compare：SC-016、通用多 run 对比（T062）与 SC-015 稳定性判定的单元测试。"""

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tu_assistant.cli import app
from tu_assistant.eval.compare import (
    CompareError,
    align_cases,
    align_general_cases,
    check_general_comparable,
    comparability_issues,
    compare_runs,
    evaluate_sc015,
    fisher_exact_two_sided,
    load_run,
    render_compare_markdown,
    role_issues,
    same_system_issues,
    save_compare_artifact,
    sc016,
    score_case,
)

DOCS = [
    ("dA", "中华人民共和国A法"),
    ("dB", "B条例"),
    ("dC", "C规定"),
]
KB_PATH = "artifacts/kb/x.sqlite"
CASES_PATH = "eval/cases/v1/reviewed.jsonl"


def _row(case_id, gold, raw="", cited=None, user="问题", category="clause_id",
         _has_scores=True, _has_raw=True):
    row = {
        "case_id": case_id,
        "category": category,
        "turns": [{"user": user}],
        "gold": {"clauses": gold},
    }
    if _has_raw:
        row["final_raw"] = raw
    if _has_scores:
        row["scores"] = {"cited_clause_ids": cited if cited is not None else []}
    elif cited is not None:
        row["scores"] = cited
    return row


def _mk_run(art_dir: Path, run_id: str, rows, model="m", kb=KB_PATH,
            cases=CASES_PATH, extra_config=None, case_count=None):
    d = art_dir / "eval" / run_id
    d.mkdir(parents=True, exist_ok=True)
    config = {"temperature": 0.0, "model": model, "use_system_prompt": True}
    config.update(extra_config or {})
    (d / "manifest.json").write_text(json.dumps({
        "id": run_id, "type": "eval_run",
        "inputs": {"cases": cases, "kb": kb, "exp_id": "exp-x",
                   "endpoint": "http://127.0.0.1:8080/v1"},
        "config": config,
        "case_count": case_count if case_count is not None else len(rows),
        "gold_clause_issues": [],
    }), encoding="utf-8")
    (d / "results.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return load_run(art_dir, run_id)


def _mk_kb(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("create table legal_documents (doc_id text primary key, title text not null)")
    conn.executemany("insert into legal_documents values (?, ?)", DOCS)
    conn.commit()
    conn.close()
    return path


def _aligned(rows_base, rows_trained, tmp_path):
    b = _mk_run(tmp_path, "b", rows_base, model="base-model")
    t = _mk_run(tmp_path, "t", rows_trained, model="default_model",
                extra_config={"base_model": "base-model", "exp": "exp-x"})
    return align_cases(b, t)


def _tmp():
    import tempfile

    return Path(tempfile.mkdtemp(prefix="cmp-"))


# ---------- loose / score_case ----------

def test_loose_levels():
    row = _row("c1", ["dA:a3:p2"], raw="《A法》第三条第二款")
    h = score_case(row, DOCS)
    assert h.doc and h.article and not h.paragraph
    row2 = _row("c1", ["dA:a3:p2"], raw="《A法》第三条第二款", cited=["dA:a3:p2"])
    assert score_case(row2, DOCS).paragraph


def test_loose_doc_only_and_normalization():
    h = score_case(_row("c1", ["dA:a3:p2"], raw="依据《A法》有关规定"), DOCS)
    assert h.doc and not h.article
    h2 = score_case(_row("c1", ["dA:a3:p2"], raw="《中华人民共和国A法》第三条"), DOCS)
    assert h2.doc and h2.article
    h3 = score_case(_row("c1", ["dA:a24:p2"], raw="《A法》第二十四条"), DOCS)
    assert h3.article


def test_fisher_known_table():
    assert fisher_exact_two_sided(1, 4, 4, 1) == pytest.approx(52 / 252)


# ---------- sc016 三项条件 ----------

def _title(doc_id):
    return {"dA": "A法", "dB": "B条例", "dC": "C规定"}[doc_id]


def _cases_pair(n, art_hit_b=0, art_hit_t=0, para_t=0,
                doc_hit_b=0, doc_hit_t=0, files=None):
    files = files or ["dA"] * n
    br, tr = [], []
    for i in range(n):
        gold = [f"{files[i]}:a{i + 1}:p1"]
        b_raw = f"《{_title(files[i])}》第{i + 1}条" if i < max(art_hit_b, doc_hit_b) else "不知道"
        t_raw = f"《{_title(files[i])}》第{i + 1}条" if i < max(art_hit_t, doc_hit_t) else "无"
        br.append(_row(f"c{i}", gold, raw=b_raw))
        tr.append(_row(f"c{i}", gold, raw=t_raw, cited=gold if i < para_t else []))
    return br, tr


def test_sc016_pass_and_fail():
    br, tr = _cases_pair(10, art_hit_t=8, para_t=2, files=["dA"] * 5 + ["dB"] * 5)
    res = sc016(_aligned(br, tr, _tmp()), DOCS)
    assert res.n == 10 and res.cond1_base == 0 and res.cond1_trained == 8
    assert res.cond2_trained == 2 and res.cond2_ratio == pytest.approx(0.2)
    assert res.subset_n == 10 and res.cond3_trained == 8
    assert res.passed == (res.cond1_ok and res.cond2_ok and res.cond3_ok)

    br2, tr2 = _cases_pair(10, art_hit_b=8, art_hit_t=0, files=["dC"] * 10)
    res2 = sc016(_aligned(br2, tr2, _tmp()), DOCS)
    assert not res2.cond1_ok and not res2.passed

    br3, tr3 = _cases_pair(10, art_hit_t=8, para_t=0, files=["dB"] * 10)
    res3 = sc016(_aligned(br3, tr3, _tmp()), DOCS)
    assert not res3.cond2_ok and not res3.passed


def test_sc016_para_boundary_10pct():
    br, tr = _cases_pair(20, art_hit_t=15, para_t=2, files=["dA"] * 20)
    res = sc016(_aligned(br, tr, _tmp()), DOCS)
    assert res.cond2_ratio == pytest.approx(0.10) and res.cond2_ok


def test_sc016_subset_excludes_whole_file():
    br, tr = _cases_pair(3, doc_hit_b=1, doc_hit_t=3, files=["dA", "dA", "dB"])
    res = sc016(_aligned(br, tr, _tmp()), DOCS)
    assert res.subset_n == 1
    br2, tr2 = _cases_pair(3, doc_hit_b=3, doc_hit_t=3, files=["dA", "dB", "dC"])
    res2 = sc016(_aligned(br2, tr2, _tmp()), DOCS)
    assert res2.subset_n == 0 and res2.cond3_ok is None and not res2.passed


# ---------- 对齐与字段完整性（8.3）----------

def test_align_order_independent():
    br, tr = _cases_pair(4, art_hit_t=3, files=["dA"] * 4)
    aligned = _aligned(br, list(reversed(tr)), _tmp())
    assert [c[0] for c in aligned] == ["c0", "c1", "c2", "c3"]


def test_align_errors():
    with pytest.raises(CompareError, match="重复 case_id"):
        _aligned([_row("c0", ["dA:a1:p1"]), _row("c0", ["dA:a1:p1"])],
                 [_row("c0", ["dA:a1:p1"]), _row("c1", ["dA:a2:p1"])], _tmp())
    with pytest.raises(CompareError, match="用例集合不同"):
        _aligned([_row("c0", ["dA:a1:p1"]), _row("c9", ["dA:a2:p1"])],
                 [_row("c0", ["dA:a1:p1"]), _row("c1", ["dA:a2:p1"])], _tmp())
    with pytest.raises(CompareError, match="gold 不一致"):
        _aligned([_row("c0", ["dA:a1:p1"])], [_row("c0", ["dA:a9:p1"])], _tmp())
    with pytest.raises(CompareError, match="恰好一个 gold"):
        _aligned([_row("c0", ["dA:a1:p1", "dA:a2:p1"])],
                 [_row("c0", ["dA:a1:p1", "dA:a2:p1"])], _tmp())


def test_missing_fields_reported():
    # 基座行缺 final_raw → 报 run 与用例 ID，而不是计为未命中
    br, tr = _cases_pair(2, art_hit_t=2, files=["dA", "dA"])
    del br[0]["final_raw"]
    with pytest.raises(CompareError, match=r"b 用例 c0 缺失 final_raw"):
        _aligned(br, tr, _tmp())
    # 自训行缺 scores.cited_clause_ids → 报错；显式空列表合法
    br2, tr2 = _cases_pair(2, art_hit_t=2, files=["dA", "dA"])
    tr2[1]["scores"] = {}
    with pytest.raises(CompareError, match=r"t 用例 c1 缺失 scores.cited_clause_ids"):
        _aligned(br2, tr2, _tmp())
    # JSON null / 错误类型不是合法观测 → 输入错误
    br3, tr3 = _cases_pair(2, art_hit_t=2, files=["dA", "dA"])
    br3[0]["final_raw"] = None
    with pytest.raises(CompareError, match=r"b 用例 c0 final_raw 应为字符串"):
        _aligned(br3, tr3, _tmp())
    br4, tr4 = _cases_pair(2, art_hit_t=2, files=["dA", "dA"])
    tr4[1]["scores"]["cited_clause_ids"] = "dA:a2:p1"
    with pytest.raises(CompareError, match="应为字符串列表"):
        _aligned(br4, tr4, _tmp())
    # 显式空 final_raw 与空 cited 列表是合法观测，不报错
    empty = [_row("c0", ["dA:a1:p1"], raw="", cited=[])]
    aligned = _aligned(empty, [_row("c0", ["dA:a1:p1"], raw="", cited=[])], _tmp())
    assert len(aligned) == 1


def test_case_count_mismatch(tmp_path):
    rows = [_row(f"c{i}", ["dA:a1:p1"]) for i in range(3)]
    d = tmp_path / "eval" / "r1"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({
        "id": "r1", "inputs": {"cases": CASES_PATH, "kb": KB_PATH},
        "config": {"model": "m"}, "case_count": 10,
    }), encoding="utf-8")
    (d / "results.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    with pytest.raises(CompareError, match="case_count=10，实际 3 行"):
        load_run(tmp_path, "r1")


# ---------- 读取错误统一为 CompareError（8.4）----------

def test_read_errors(tmp_path):
    d = tmp_path / "eval" / "r1"
    d.mkdir(parents=True)
    (d / "results.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(CompareError, match="manifest.json"):
        load_run(tmp_path, "r1")

    (d / "manifest.json").write_text(json.dumps({"id": "r1", "inputs": {}, "config": {}}))
    (d / "results.jsonl").write_text('{"case_id": "c0"}\n{"case_id": "c1",\n', encoding="utf-8")
    with pytest.raises(CompareError, match=r"results\.jsonl 第 2 行"):
        load_run(tmp_path, "r1")

    # 一行是合法 JSON 值但不是对象（null）→ 同样报输入错误带行号
    (d / "results.jsonl").write_text('{"case_id": "c0"}\nnull\n', encoding="utf-8")
    with pytest.raises(CompareError, match=r"第 2 行不是 JSON 对象"):
        load_run(tmp_path, "r1")


# ---------- 可比性与模型角色（8.1）----------

def test_comparability_conflicts(tmp_path):
    b = _mk_run(tmp_path, "b", [], model="m", kb="artifacts/kb/k1.sqlite")
    t = _mk_run(tmp_path, "t", [], model="default_model", kb="artifacts/kb/k2.sqlite")
    with pytest.raises(CompareError, match="知识库不一致"):
        comparability_issues(b, t)
    t2 = _mk_run(tmp_path / "x", "t", [], model="default_model",
                 kb="artifacts/kb/k1.sqlite", cases="eval/cases/v1/other.jsonl")
    with pytest.raises(CompareError, match="评测集不一致"):
        comparability_issues(b, t2)
    t3 = _mk_run(tmp_path / "y", "t", [], model="default_model",
                 kb="artifacts/kb/k1.sqlite",
                 extra_config={"temperature": 0.7})
    with pytest.raises(CompareError, match="temperature"):
        comparability_issues(b, t3)


def test_comparability_missing_fields_inconclusive(tmp_path):
    # 缺失或 JSON null 的必要设置 → 返回"无法确认"原因（非零路径），而非静默 PASS
    b = _mk_run(tmp_path, "b", [], model="m", cases=None)
    t = _mk_run(tmp_path, "t", [], model="default_model", cases=None)
    t.manifest["config"]["use_system_prompt"] = None
    t.manifest["config"]["temperature"] = None
    reasons = comparability_issues(b, t)
    assert any("use_system_prompt" in r for r in reasons)
    assert any("temperature" in r for r in reasons)
    b.manifest["config"]["use_system_prompt"] = None
    t.manifest["config"]["use_system_prompt"] = None
    assert any("use_system_prompt" in r for r in comparability_issues(b, t))


def test_role_issues(tmp_path):
    # adapter 充当基座 → 已知冲突
    b_adapter = _mk_run(tmp_path, "b", [], model="default_model",
                        extra_config={"exp": "exp-x", "base_model": "m"})
    t = _mk_run(tmp_path, "t", [], model="default_model",
                extra_config={"base_model": "m", "exp": "exp-y"})
    with pytest.raises(CompareError, match="不是未训练基座"):
        role_issues(b_adapter, t)
    # 自训位置放未挂 adapter 的 run
    b = _mk_run(tmp_path / "x", "b", [], model="m")
    t_no_adapter = _mk_run(tmp_path / "x", "t", [], model="concrete-model")
    with pytest.raises(CompareError, match="不能放在自训位置"):
        role_issues(b, t_no_adapter)
    # 不同基座 → 已知冲突
    t_other_base = _mk_run(tmp_path / "y", "t", [], model="default_model",
                           extra_config={"base_model": "other-model"})
    with pytest.raises(CompareError, match="基座不一致"):
        role_issues(b, t_other_base)
    # 自训 run 缺 base_model / exp → 无法确认（返回原因，不抛错）
    t_no_bm = _mk_run(tmp_path / "z", "t", [], model="default_model",
                      extra_config={"exp": "exp-y"})
    assert role_issues(b, t_no_bm) == ["自训 run 缺少 config.base_model，无法确认它与基座 run 是同一底座"]
    t_no_exp = _mk_run(tmp_path / "z2", "t", [], model="default_model",
                       extra_config={"base_model": "m"})
    assert role_issues(b, t_no_exp) == ["自训 run 缺少 config.exp，无法确认 adapter 身份"]
    # 角色正确 → 空列表
    t_ok = _mk_run(tmp_path / "w", "t", [], model="default_model",
                   extra_config={"base_model": "m", "exp": "exp-y"})
    assert role_issues(b, t_ok) == []


# ---------- 诊断集（8.2）----------

def test_diagnostic_cases_rejected(tmp_path):
    b = _mk_run(tmp_path, "b", [], model="m",
                cases="eval/diagnostics/train-probe-v1.jsonl")
    t = _mk_run(tmp_path, "t", [], model="default_model",
                cases="eval/diagnostics/train-probe-v1.jsonl",
                extra_config={"base_model": "m"})
    with pytest.raises(CompareError, match="诊断集"):
        comparability_issues(b, t)
    # 路径不含 probe 字样，但文件里 source=train_probe → 同样拒绝
    diag = tmp_path / "eval" / "cases" / "custom.jsonl"
    diag.parent.mkdir(parents=True, exist_ok=True)
    diag.write_text(json.dumps({"case_id": "x", "source": "train_probe"}) + "\n",
                    encoding="utf-8")
    b2 = _mk_run(tmp_path / "z", "b", [], model="m", cases=str(diag))
    t2 = _mk_run(tmp_path / "z", "t", [], model="default_model",
                 cases=str(diag), extra_config={"base_model": "m"})
    with pytest.raises(CompareError, match="诊断"):
        comparability_issues(b2, t2)


def test_diagnostic_directory_and_unverifiable(tmp_path):
    """普通目录下的用例文件按实际加载内容识别诊断来源；无法核对的来源报无法确认。"""
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "cases.jsonl").write_text(
        json.dumps({"case_id": "x", "source": "train_probe"}) + "\n", encoding="utf-8")
    b = _mk_run(tmp_path, "b", [], model="m", cases=str(suite))
    t = _mk_run(tmp_path, "t", [], model="default_model",
                cases=str(suite), extra_config={"base_model": "m", "exp": "e"})
    with pytest.raises(CompareError, match="诊断"):
        comparability_issues(b, t)

    # 同样目录放手工用例且题号与结果一致 → 来源可核对且非诊断
    (suite / "cases.jsonl").write_text(
        json.dumps({"case_id": "x", "source": "manual"}) + "\n", encoding="utf-8")
    rows_x = [_row("x", ["dA:a1:p1"])]
    b2 = _mk_run(tmp_path / "y", "b", rows_x, model="m", cases=str(suite))
    t2 = _mk_run(tmp_path / "y", "t", rows_x, model="default_model",
                 cases=str(suite), extra_config={"base_model": "m", "exp": "e"})
    assert not any("评测集来源" in r or "诊断" in r for r in comparability_issues(b2, t2))

    # 不存在的路径 → 无法核对来源 → 无法判定（原因列表），不是 PASS
    gone = "eval/cases/v1/does-not-exist.jsonl"
    b3 = _mk_run(tmp_path / "w", "b", [], model="m", cases=gone)
    t3 = _mk_run(tmp_path / "w", "t", [], model="default_model",
                 cases=gone, extra_config={"base_model": "m", "exp": "e"})
    assert all("无法核对评测集来源" in r for r in comparability_issues(b3, t3)
               if "评测集" in r)


def test_cases_file_broken_json(tmp_path):
    """评测集文件一行不完整 JSON → 输入错误并带文件与行号。"""
    bad = tmp_path / "cases.jsonl"
    bad.write_text('{"case_id": "x"}\n{"case_id":\n', encoding="utf-8")
    b = _mk_run(tmp_path, "b", [], model="m", cases=str(bad))
    t = _mk_run(tmp_path, "t", [], model="default_model",
                cases=str(bad), extra_config={"base_model": "m", "exp": "e"})
    with pytest.raises(CompareError, match=r"第 2 行"):
        comparability_issues(b, t)


# ---------- CLI ----------

runner = CliRunner()


def _full_run(tmp_path, run_id, rows, model, kb_path, cases=CASES_PATH, extra_config=None):
    d = tmp_path / "eval" / run_id
    d.mkdir(parents=True, exist_ok=True)
    config = {"temperature": 0.0, "model": model, "use_system_prompt": True}
    config.update(extra_config or {})
    (d / "manifest.json").write_text(json.dumps({
        "id": run_id, "type": "eval_run",
        "inputs": {"cases": cases, "kb": str(kb_path), "exp_id": "exp-x", "endpoint": "e"},
        "config": config,
        "case_count": len(rows), "gold_clause_issues": [],
    }), encoding="utf-8")
    (d / "results.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _cli_args(tmp_path, *run_ids):
    return ["eval", "compare", "--sc016", *run_ids, "--artifacts", str(tmp_path)]


def _mk_cases(tmp_path: Path, rows, name="cases.jsonl") -> Path:
    """生成与结果题号一致的手工评测集文件。"""
    f = tmp_path / name
    f.write_text("".join(
        json.dumps({"case_id": r["case_id"], "source": "manual"}) + "\n" for r in rows
    ), encoding="utf-8")
    return f


def test_cli_sc016(tmp_path):
    kb = _mk_kb(tmp_path / "kb" / "kb-test.sqlite")
    br, tr = _cases_pair(10, art_hit_t=8, para_t=2, files=["dA"] * 5 + ["dB"] * 5)
    cf = _mk_cases(tmp_path, br)
    _full_run(tmp_path, "rb", br, "base-model", kb, cases=str(cf))
    _full_run(tmp_path, "rt", tr, "default_model", kb, cases=str(cf),
              extra_config={"base_model": "base-model", "exp": "exp-x"})

    r = runner.invoke(app, _cli_args(tmp_path, "rb", "rt"))
    assert r.exit_code == 0, r.output
    assert "总判定：PASS" in r.output and "① 条级命中" in r.output

    _full_run(tmp_path, "rt2", [_row(r2["case_id"], r2["gold"]["clauses"], raw="错")
                                for r2 in tr], "default_model", kb, cases=str(cf),
              extra_config={"base_model": "base-model", "exp": "exp-x"})
    r2 = runner.invoke(app, _cli_args(tmp_path, "rb", "rt2"))
    assert r2.exit_code == 1 and "总判定：FAIL" in r2.output

    r3 = runner.invoke(app, ["eval", "compare", "rb", "rt", "--artifacts", str(tmp_path)])
    assert r3.exit_code == 0 and "# 评测对比报告" in r3.output
    r3_single = runner.invoke(app, ["eval", "compare", "rb", "--artifacts", str(tmp_path)])
    assert r3_single.exit_code == 2
    r4 = runner.invoke(app, ["eval", "compare", "--sc016", "rb", "--artifacts", str(tmp_path)])
    assert r4.exit_code == 2
    r5 = runner.invoke(app, _cli_args(tmp_path, "rb", "nope"))
    assert r5.exit_code == 2 and "输入错误" in r5.output


def test_cli_cases_link(tmp_path):
    """第三轮复审：结果必须确实属于 manifest 指向的评测集。"""
    kb = _mk_kb(tmp_path / "kb" / "kb-test.sqlite")
    br, tr = _cases_pair(6, art_hit_t=5, para_t=1, files=["dA"] * 6)
    cf = _mk_cases(tmp_path, br)
    _full_run(tmp_path, "rb", br, "base-model", kb, cases=str(cf))
    _full_run(tmp_path, "rt", tr, "default_model", kb, cases=str(cf),
              extra_config={"base_model": "base-model", "exp": "exp-x"})

    # 对照：题号一致的手工评测集 → PASS
    r0 = runner.invoke(app, _cli_args(tmp_path, "rb", "rt"))
    assert r0.exit_code == 0, r0.output

    # 复审复现：清单指向的同一文件被清空 → 缺少来源证据 → 无法判定（1）
    cf.write_text("")
    r1 = runner.invoke(app, _cli_args(tmp_path, "rb", "rt"))
    assert r1.exit_code == 1 and "无法判定" in r1.output

    # 同一文件被替换成 ID 不相交的用例 → 输入错误（2）
    cf.write_text("".join(
        json.dumps({"case_id": f"other-{r['case_id']}", "source": "manual"}) + "\n"
        for r in br
    ), encoding="utf-8")
    r2 = runner.invoke(app, _cli_args(tmp_path, "rb", "rt"))
    assert r2.exit_code == 2 and "结果与评测集用例不一致" in r2.output


def test_cli_cross_base_and_adapter_as_base(tmp_path):
    """8.1 回归：跨基座对比、adapter 充当基座都必须是输入错误 2。"""
    kb = _mk_kb(tmp_path / "kb" / "kb-test.sqlite")
    br, tr = _cases_pair(10, art_hit_t=8, para_t=2, files=["dA"] * 5 + ["dB"] * 5)
    cf = _mk_cases(tmp_path, br)
    _full_run(tmp_path, "r15b", br, "model-1.5B", kb, cases=str(cf))          # 1.5B 基座
    _full_run(tmp_path, "rt", tr, "default_model", kb, cases=str(cf),
              extra_config={"base_model": "model-7B", "exp": "exp-7b"})      # 7B 自训
    _full_run(tmp_path, "rckpt", br, "default_model", kb, cases=str(cf),
              extra_config={"base_model": "model-7B", "exp": "exp-ckpt"})    # adapter 检查点
    _full_run(tmp_path, "r7b", br, "model-7B", kb, cases=str(cf))            # 真 7B 基座

    r1 = runner.invoke(app, _cli_args(tmp_path, "r15b", "rt"))
    assert r1.exit_code == 2 and "基座不一致" in r1.output
    r2 = runner.invoke(app, _cli_args(tmp_path, "rckpt", "rt"))
    assert r2.exit_code == 2 and "不是未训练基座" in r2.output
    # 自训 run 缺 base_model → 无法判定（1），不是 PASS
    _full_run(tmp_path, "rt3", tr, "default_model", kb, cases=str(cf),
              extra_config={"exp": "exp-7b"})
    r3 = runner.invoke(app, _cli_args(tmp_path, "r7b", "rt3"))
    assert r3.exit_code == 1 and "无法判定" in r3.output
    # 自训 run 缺 config.exp → 无法确认 adapter 身份 → 无法判定（1）
    _full_run(tmp_path, "rt4", tr, "default_model", kb, cases=str(cf),
              extra_config={"base_model": "model-7B"})
    r4 = runner.invoke(app, _cli_args(tmp_path, "r7b", "rt4"))
    assert r4.exit_code == 1 and "无法判定" in r4.output and "config.exp" in r4.output


def test_cli_diagnostic_rejected(tmp_path):
    """8.2：模型角色正确的两个 run 指向诊断集 → 退出 2，且不输出三项分数。"""
    kb = _mk_kb(tmp_path / "kb" / "kb-test.sqlite")
    diag = tmp_path / "eval" / "diagnostics" / "train-probe-v1.jsonl"
    diag.parent.mkdir(parents=True, exist_ok=True)
    diag.write_text(json.dumps({"case_id": "x", "source": "train_probe"}) + "\n",
                    encoding="utf-8")
    rows = [_row(f"c{i}", ["dA:a1:p1"]) for i in range(3)]
    _full_run(tmp_path, "rb", rows, "base-model", kb, cases=str(diag))
    _full_run(tmp_path, "rt", rows, "default_model", kb, cases=str(diag),
              extra_config={"base_model": "base-model", "exp": "exp-x"})
    r = runner.invoke(app, _cli_args(tmp_path, "rb", "rt"))
    assert r.exit_code == 2 and "诊断集" in r.output
    assert "① 条级命中" not in r.output


# ---------- T062：通用多 run 对比与 SC-015 稳定性校验 ----------


def _rich_row(
    case_id: str,
    category: str,
    *,
    gold: dict | None = None,
    scores: dict | None = None,
    final_text: str = "正常回答",
    turns: list[dict] | None = None,
    user: str = "问题",
) -> dict:
    return {
        "case_id": case_id,
        "category": category,
        "turns": turns if turns is not None else [{"user": user, "content": final_text}],
        "gold": gold if gold is not None else {},
        "final_text": final_text,
        "final_raw": final_text,
        "scores": scores if scores is not None else {},
    }


def _make_multi_category_run_rows(variant: str) -> list[dict]:
    """构造覆盖 6 类用例的确定性结果集，便于逐项手算断言。

    variant: "v1"（基准）、"v2"（中间版本）、"v3"（末轮）
    """
    # c1: clause_id — v1 失败(recall=0.5, corrected=1, not_found=1, cit_complete=1/2), v2/v3 通过
    c1_rec = 0.5 if variant == "v1" else 1.0
    c1_prec = 0.5 if variant == "v1" else 1.0
    c1_cit_comp = 1 if variant == "v1" else 2
    c1_acc = (
        {"ok": 0, "corrected": 1, "not_found": 1, "incomplete": 0}
        if variant == "v1"
        else {"ok": 2, "corrected": 0, "not_found": 0, "incomplete": 0}
    )

    # c2: multi_violation — v1 通过(1.0), v2 失败(0.5), v3 失败(0.5) => pass->fail
    c2_mv = 1.0 if variant == "v1" else 0.5
    c2_rel = 1.0 if variant == "v1" else 0.5

    # c3: intent — v1 通过(1.0), v2 失败(0.0), v3 通过(1.0) => 3-run 矩阵 PASS/FAIL/PASS
    c3_intent = 0.0 if variant == "v2" else 1.0

    # c4: refusal — v1 未拒答(fail), v2/v3 正确拒答(pass)
    c4_ref = variant != "v1"

    # c5: false_refusal — 全部正确不拒答(pass)
    c5_ref = False

    # c6: article — v1 身份泄露 1/2, v2 2/2, v3 2/2
    c6_id_pass = 1 if variant == "v1" else 2

    return [
        _rich_row(
            "c1",
            "clause_id",
            gold={"clauses": ["dA:a1:p1", "dA:a2:p1"]},
            scores={
                "recall": c1_rec,
                "precision": c1_prec,
                "citation_complete": c1_cit_comp,
                "citation_total": 2,
                "citation_acc": {"counts": c1_acc},
                "refusal_evidence": {"refused": False},
            },
        ),
        _rich_row(
            "c2",
            "multi_violation",
            gold={"clauses": ["dA:a3:p1"]},
            scores={
                "recall": 1.0,
                "precision": 1.0,
                "multi_violation": c2_mv,
                "relation_completion": c2_rel,
                "citation_complete": 1,
                "citation_total": 1,
                "citation_acc": {"counts": {"ok": 1, "corrected": 0, "not_found": 0, "incomplete": 0}},
                "refusal_evidence": {"refused": False},
            },
        ),
        _rich_row(
            "c3",
            "intent",
            gold={"expected_intent": "consult"},
            scores={
                "intent": c3_intent,
                "refusal_evidence": {"refused": False},
            },
        ),
        _rich_row(
            "c4",
            "refusal",
            gold={"should_refuse": True},
            scores={"refusal_evidence": {"refused": c4_ref}},
        ),
        _rich_row(
            "c5",
            "false_refusal",
            gold={"should_refuse": False},
            scores={"refusal_evidence": {"refused": c5_ref}},
        ),
        _rich_row(
            "c6",
            "article",
            gold={"expect_articles": 2, "protected_names": [{"name": "启明厂", "turn": 1}]},
            scores={
                "article_count": {"ok": True, "expected": 2, "per_turn": [2]},
                "identity_check": {"passed": c6_id_pass, "total": 2, "unparsed_leaks": []},
                "refusal_evidence": {"refused": False},
            },
        ),
    ]


def test_general_compare_2run_and_3run_exact_metrics_and_transitions(tmp_path):
    """验收项 1：2-run 与 3-run 通用对比聚合、差值(pp)、最大波动、逐题翻转与 3-run 状态矩阵。"""
    kb = _mk_kb(tmp_path / "kb" / "kb-test.sqlite")
    rows_v1 = _make_multi_category_run_rows("v1")
    rows_v2 = _make_multi_category_run_rows("v2")
    rows_v3 = _make_multi_category_run_rows("v3")
    cf = _mk_cases(tmp_path, rows_v1)

    _full_run(tmp_path, "r1", rows_v1, "default_model", kb, cases=str(cf),
              extra_config={"base_model": "m7b", "exp": "exp-1"})
    _full_run(tmp_path, "r2", rows_v2, "default_model", kb, cases=str(cf),
              extra_config={"base_model": "m7b", "exp": "exp-2"})
    _full_run(tmp_path, "r3", rows_v3, "default_model", kb, cases=str(cf),
              extra_config={"base_model": "m7b", "exp": "exp-3"})

    loaded = [load_run(tmp_path, rid) for rid in ("r1", "r2", "r3")]
    issues, notes = check_general_comparable(loaded)
    assert issues == [] and notes == []

    # 3-run 聚合核对
    cmp3 = compare_runs(loaded)
    by_code = {m.code: m for m in cmp3.metrics}
    # SC-001: v1=1.0, v2=0.0, v3=1.0 -> delta=0.0, spread=1.0
    assert by_code["SC-001"].values == (1.0, 0.0, 1.0)
    assert by_code["SC-001"].delta == pytest.approx(0.0)
    assert by_code["SC-001"].spread == pytest.approx(1.0)
    # SC-002: mean(c1_rec, c2_rec=1.0) -> v1=0.75, v2=1.0, v3=1.0 -> delta=+0.25, spread=0.25
    assert by_code["SC-002"].values == (0.75, 1.0, 1.0)
    assert by_code["SC-002"].delta == pytest.approx(0.25)
    assert by_code["SC-002"].spread == pytest.approx(0.25)
    # SC-003: mean(c1_prec, c2_prec=1.0) -> v1=0.75, v2=1.0, v3=1.0 -> delta=+0.25, spread=0.25
    assert by_code["SC-003"].values == (0.75, 1.0, 1.0)
    assert by_code["SC-003"].delta == pytest.approx(0.25)
    assert by_code["SC-003"].spread == pytest.approx(0.25)
    # SC-004: v1=1.0, v2=0.5, v3=0.5 -> delta=-0.5, spread=0.5
    assert by_code["SC-004"].values == (1.0, 0.5, 0.5)
    assert by_code["SC-004"].delta == pytest.approx(-0.5)
    assert by_code["SC-004"].spread == pytest.approx(0.5)
    # SC-005: v1=1.0, v2=0.5, v3=0.5
    assert by_code["SC-005"].values == (1.0, 0.5, 0.5)
    assert by_code["SC-005"].delta == pytest.approx(-0.5)
    # SC-006: v1=2/3 (c1:1/2 + c2:1/1), v2=3/3, v3=3/3 -> delta=+1/3
    assert by_code["SC-006"].values[0] == pytest.approx(2 / 3)
    assert by_code["SC-006"].values[2] == pytest.approx(1.0)
    assert by_code["SC-006"].delta == pytest.approx(1 / 3)
    # SC-007 pre vs post 明显分离：v1 ok=1, corrected=1, nf=1 (total=3) -> pre=1/3, post=2/3
    assert by_code["SC-007（校验前）"].values[0] == pytest.approx(1 / 3)
    assert by_code["SC-007（校验前）"].values[2] == pytest.approx(1.0)
    assert by_code["SC-007（校验前）"].delta == pytest.approx(2 / 3)
    assert by_code["SC-007（校验后）"].values[0] == pytest.approx(2 / 3)
    assert by_code["SC-007（校验后）"].values[2] == pytest.approx(1.0)
    assert by_code["SC-007（校验后）"].delta == pytest.approx(1 / 3)
    # SC-008 outside: v1=0/1, v2=1/1, v3=1/1; false_refusal: 0/5 all
    assert by_code["SC-008（范围外）"].values == (0.0, 1.0, 1.0)
    assert by_code["SC-008（误拒）"].values == (0.0, 0.0, 0.0)
    # SC-009 / SC-010: 无 --reviews 时均为 None
    assert by_code["SC-009"].values == (None, None, None)
    assert by_code["SC-010"].values == (None, None, None)
    # SC-011: v1=1/2, v2=2/2, v3=2/2
    assert by_code["SC-011"].values == (0.5, 1.0, 1.0)
    assert by_code["SC-011"].delta == pytest.approx(0.5)

    # 逐题状态变化（r1 -> r3）：c1/c4/c6 新通过，c2 退步，c3/c5 始终通过
    assert [t.case_id for t in cmp3.newly_passed] == ["c1", "c4", "c6"]
    assert [t.case_id for t in cmp3.regressed] == ["c2"]
    assert cmp3.always_passed == 2
    assert cmp3.always_failed == 0
    # 3-run 状态矩阵应包含 c3（PASS/FAIL/PASS）以及 c1/c2/c4/c6
    flip_map = {cid: states for cid, _, states in cmp3.flip_matrix}
    assert flip_map["c3"] == (True, False, True)
    assert flip_map["c1"] == (False, True, True)
    assert flip_map["c2"] == (True, False, False)

    md3 = render_compare_markdown(cmp3)
    assert "### 多轮状态切换矩阵" in md3
    assert "末轮相对基准" in md3
    assert "+0.250（+25.0 pp）" in md3
    assert "100.0 pp" in md3
    # 按类别失败数对比精确行核对
    assert "| article | 1 | 1 | 0 | 0 | -1 |" in md3
    assert "| clause_id | 1 | 1 | 0 | 0 | -1 |" in md3
    assert "| false_refusal | 1 | 0 | 0 | 0 | 0 |" in md3
    assert "| intent | 1 | 0 | 1 | 0 | 0 |" in md3
    assert "| multi_violation | 1 | 0 | 1 | 1 | +1 |" in md3
    assert "| refusal | 1 | 1 | 0 | 0 | -1 |" in md3

    # 2-run 报告不含多轮矩阵且列头为“差值（相对基准）”
    cmp2 = compare_runs(loaded[:2])
    md2 = render_compare_markdown(cmp2)
    assert "差值（相对基准）" in md2
    assert "### 多轮状态切换矩阵" not in md2


def test_sc015_boundaries_and_edge_cases(tmp_path):
    """验收项 2：SC-015 0.0pp/2.0pp/2.1pp、单侧 None、全空无法判定、跨模型与缺字段。"""
    kb = _mk_kb(tmp_path / "kb" / "kb-test.sqlite")

    def _run_pair(tag: str, r1_scores: dict, r2_scores: dict, category="clause_id", gold=None):
        g = gold if gold is not None else {"clauses": ["dA:a1:p1"]}
        rows1 = [_rich_row("c1", category, gold=g, scores=r1_scores)]
        rows2 = [_rich_row("c1", category, gold=g, scores=r2_scores)]
        cf = _mk_cases(tmp_path, rows1, name=f"cases_{tag}.jsonl")
        _full_run(tmp_path, f"{tag}_a", rows1, "default_model", kb, cases=str(cf),
                  extra_config={"base_model": "m7b", "exp": "exp-same"})
        _full_run(tmp_path, f"{tag}_b", rows2, "default_model", kb, cases=str(cf),
                  extra_config={"base_model": "m7b", "exp": "exp-same"})
        return [load_run(tmp_path, f"{tag}_a"), load_run(tmp_path, f"{tag}_b")]

    def _sc15(*rids: str):
        return runner.invoke(
            app, ["eval", "compare", "--sc015", *rids, "--artifacts", str(tmp_path)]
        )

    # ① 0.0 pp -> PASS (exit 0)
    _run_pair("zero", {"recall": 0.5, "refusal_evidence": {"refused": False}},
              {"recall": 0.5, "refusal_evidence": {"refused": False}})
    r_zero = _sc15("zero_a", "zero_b")
    assert r_zero.exit_code == 0 and "**总判定：PASS**" in r_zero.output

    # ② 浮点边界 0.15 vs 0.17 (0.17 - 0.15 = 0.020000000000000018) -> PASS (exit 0)
    _run_pair("edge", {"recall": 0.15, "refusal_evidence": {"refused": False}},
              {"recall": 0.17, "refusal_evidence": {"refused": False}})
    r_edge = _sc15("edge_a", "edge_b")
    assert r_edge.exit_code == 0 and "**总判定：PASS**" in r_edge.output

    # ③ 0.15 vs 0.171 (2.1 pp) -> FAIL (exit 1)
    _run_pair("over", {"recall": 0.15, "refusal_evidence": {"refused": False}},
              {"recall": 0.171, "refusal_evidence": {"refused": False}})
    r_over = _sc15("over_a", "over_b")
    assert r_over.exit_code == 1 and "**总判定：FAIL**" in r_over.output

    # ④ 单侧 None（一方有 citation_total=1，另一方 citation_total=0）-> FAIL (exit 1)
    _run_pair(
        "pnone",
        {"citation_complete": 1, "citation_total": 1, "refusal_evidence": {"refused": False}},
        {"citation_complete": 0, "citation_total": 0, "refusal_evidence": {"refused": False}},
    )
    r_pn = _sc15("pnone_a", "pnone_b")
    assert r_pn.exit_code == 1
    assert "部分 run 无有效分母" in r_pn.output
    assert "无法比较（部分无样本）" in r_pn.output

    # ⑤ 全部指标无样本 -> 无法判定 (exit 1)
    # 构造 0 有效指标的 ComparisonResult 直接测 evaluate_sc015
    loaded_zero = [load_run(tmp_path, "zero_a"), load_run(tmp_path, "zero_b")]
    cmp_zero = compare_runs(loaded_zero)
    empty_metrics = tuple(
        type(m)(
            code=m.code, name=m.name, values=(None, None), cells=("-", "-"),
            delta=None, spread=None, partial_none=False, poc_target=m.poc_target,
        )
        for m in cmp_zero.metrics
    )
    cmp_empty = type(cmp_zero)(**{**cmp_zero.__dict__, "metrics": empty_metrics})
    sc15_empty = evaluate_sc015(cmp_empty)
    assert sc15_empty.passed is None and sc15_empty.evaluated_count == 0

    # ⑥ 不同 exp / 不同 model / 不同 base_model -> 输入错误 (exit 2)
    rows_base = [_rich_row("c1", "clause_id", gold={"clauses": ["dA:a1:p1"]},
                           scores={"recall": 0.5, "refusal_evidence": {"refused": False}})]
    cf_sys = _mk_cases(tmp_path, rows_base, name="cases_sys.jsonl")
    _full_run(tmp_path, "sa", rows_base, "default_model", kb, cases=str(cf_sys),
              extra_config={"base_model": "m7b", "exp": "exp-1"})
    _full_run(tmp_path, "sb_exp", rows_base, "default_model", kb, cases=str(cf_sys),
              extra_config={"base_model": "m7b", "exp": "exp-2"})
    _full_run(tmp_path, "sb_base", rows_base, "default_model", kb, cases=str(cf_sys),
              extra_config={"base_model": "m15b", "exp": "exp-1"})
    _full_run(tmp_path, "sb_mod", rows_base, "raw-7b", kb, cases=str(cf_sys))
    for other in ("sb_exp", "sb_base", "sb_mod"):
        r_diff = runner.invoke(
            app, ["eval", "compare", "--sc015", "sa", other, "--artifacts", str(tmp_path)]
        )
        assert r_diff.exit_code == 2 and "同一系统版本" in r_diff.output

    # ⑦ default_model 缺 exp 或缺 base_model -> 无法判定 (exit 1)
    _full_run(tmp_path, "s_no_exp", rows_base, "default_model", kb, cases=str(cf_sys),
              extra_config={"base_model": "m7b"})
    _full_run(tmp_path, "s_no_base", rows_base, "default_model", kb, cases=str(cf_sys),
              extra_config={"exp": "exp-1"})
    for miss in ("s_no_exp", "s_no_base"):
        r_m = runner.invoke(
            app, ["eval", "compare", "--sc015", "sa", miss, "--artifacts", str(tmp_path)]
        )
        assert r_m.exit_code == 1 and "无法判定" in r_m.output


def test_general_comparability_safety_and_subset_expansion(tmp_path):
    """验收项 3：非法/重复 run_id、目录扩题放行与提示、磁盘无此题退 2、旧 schema 复算。"""
    kb = _mk_kb(tmp_path / "kb" / "kb-test.sqlite")
    # 非法 run_id 拦截（load_run 入口，同时保护 --sc016 与通用对比）
    for bad_id in ("", ".", "..", "../x", "a/b", "a\\b", " run1"):
        with pytest.raises(CompareError, match="非法的 run_id"):
            load_run(tmp_path, bad_id)

    # 构造目录型评测集（初始 2 题，后续扩到 3 题）
    cases_dir = tmp_path / "v1_dir"
    cases_dir.mkdir()
    # 无 refusal_evidence（模拟旧 schema）
    rows_old = [
        _rich_row("c1", "clause_id", gold={"clauses": ["dA:a1:p1"]},
                  scores={"recall": 1.0}, final_text="依据《A法》第一条……"),
        _rich_row("c2", "refusal", gold={"should_refuse": True},
                  scores={}, final_text="该问题超出知识库范围，无法回答。"),
    ]
    (cases_dir / "part1.jsonl").write_text(
        "".join(json.dumps({"case_id": r["case_id"], "source": "manual"}) + "\n" for r in rows_old),
        encoding="utf-8",
    )
    # 扩题到 3 题
    (cases_dir / "part2.jsonl").write_text(
        json.dumps({"case_id": "c3", "source": "manual"}) + "\n", encoding="utf-8"
    )
    _full_run(tmp_path, "old1", rows_old, "m7b", kb, cases=str(cases_dir))
    _full_run(tmp_path, "old2", rows_old, "m7b", kb, cases=str(cases_dir))

    # 重复 run_id -> 退出 2
    r_dup = runner.invoke(app, ["eval", "compare", "old1", "old1", "--artifacts", str(tmp_path)])
    assert r_dup.exit_code == 2 and "重复" in r_dup.output

    # 目录扩题真子集 -> 放行（退出 0），输出扩题提示，并自动复算旧 schema SC-008
    r_sub = runner.invoke(app, ["eval", "compare", "old1", "old2", "--artifacts", str(tmp_path)])
    assert r_sub.exit_code == 0, r_sub.output
    assert "后续扩题（当前磁盘共 3 题），本次仅按历史共有 2 题对比" in r_sub.output
    assert "SC-008 历史兼容复算" in r_sub.output
    assert "1.000（1/1）" in r_sub.output  # c2 经 detect_refusal 复算正确拒答

    # 结果包含磁盘不存在的 case_id -> 退出 2
    rows_ghost = [*rows_old, _rich_row("ghost", "clause_id", gold={"clauses": ["dA:a1:p1"]})]
    _full_run(tmp_path, "g1", rows_ghost, "m7b", kb, cases=str(cases_dir))
    _full_run(tmp_path, "g2", rows_ghost, "m7b", kb, cases=str(cases_dir))
    r_ghost = runner.invoke(app, ["eval", "compare", "g1", "g2", "--artifacts", str(tmp_path)])
    assert r_ghost.exit_code == 2 and "不存在的用例" in r_ghost.output

    # 磁盘路径缺失 -> 无法确认（退出 1）
    _full_run(tmp_path, "miss1", rows_old, "m7b", kb, cases=str(tmp_path / "missing_dir"))
    _full_run(tmp_path, "miss2", rows_old, "m7b", kb, cases=str(tmp_path / "missing_dir"))
    r_miss = runner.invoke(app, ["eval", "compare", "miss1", "miss2", "--artifacts", str(tmp_path)])
    assert r_miss.exit_code == 1 and "无法确认" in r_miss.output

    # 缺 temperature -> 退出 1；temperature 不一致 -> 退出 2
    _full_run(tmp_path, "t_none", rows_old, "m7b", kb, cases=str(cases_dir),
              extra_config={"temperature": None})
    r_tn = runner.invoke(app, ["eval", "compare", "old1", "t_none", "--artifacts", str(tmp_path)])
    assert r_tn.exit_code == 1 and "temperature" in r_tn.output
    _full_run(tmp_path, "t_hot", rows_old, "m7b", kb, cases=str(cases_dir),
              extra_config={"temperature": 0.7})
    r_th = runner.invoke(app, ["eval", "compare", "old1", "t_hot", "--artifacts", str(tmp_path)])
    assert r_th.exit_code == 2 and "temperature" in r_th.output

    # 同 ID 内容不一致（gold 不同）-> 退出 2
    rows_diff_gold = [
        _rich_row("c1", "clause_id", gold={"clauses": ["dB:a9:p1"]}, scores={"recall": 1.0}),
        rows_old[1],
    ]
    _full_run(tmp_path, "dg", rows_diff_gold, "m7b", kb, cases=str(cases_dir))
    with pytest.raises(CompareError, match="gold 不一致"):
        align_general_cases([load_run(tmp_path, "old1"), load_run(tmp_path, "dg")])

    # same_system_issues 缺失 model 返回 issues
    _full_run(tmp_path, "no_mod", rows_old, None, kb, cases=str(cases_dir))
    assert same_system_issues([load_run(tmp_path, "old1"), load_run(tmp_path, "no_mod")])


def test_reviews_save_out_protection_and_mutual_exclusion(tmp_path):
    """验收项 4：--reviews 对比、默认只读 stdout、--out 防覆盖、--save 落盘与防碰撞、互斥选项。"""
    kb = _mk_kb(tmp_path / "kb" / "kb-test.sqlite")
    rows = [
        _rich_row(
            "art-1",
            "article",
            gold={"expect_articles": 3},
            scores={
                "article_count": {"ok": True, "expected": 3, "per_turn": [3]},
                "refusal_evidence": {"refused": False},
            },
        ),
    ]
    cf = _mk_cases(tmp_path, rows)
    _full_run(tmp_path, "ra", rows, "default_model", kb, cases=str(cf),
              extra_config={"base_model": "m7b", "exp": "exp-a"})
    _full_run(tmp_path, "rb", rows, "default_model", kb, cases=str(cf),
              extra_config={"base_model": "m7b", "exp": "exp-b"})

    # 人工评审 CSV 同时含 ra 与 rb 的 correctness / diversity
    rev_csv = tmp_path / "reviews.csv"
    rev_csv.write_text(
        "run_id,case_id,reviewer,verdict,comment,created_at,dimension\n"
        "ra,art-1,u1,fail,要件漏写,2026-11-22T10:00:00Z,correctness\n"
        "ra,art-1,u1,fail,三篇雷同,2026-11-22T10:01:00Z,diversity\n"
        "rb,art-1,u1,pass,完整,2026-11-22T10:02:00Z,correctness\n"
        "rb,art-1,u1,pass,差异明显,2026-11-22T10:03:00Z,diversity\n",
        encoding="utf-8",
    )

    # ① --reviews 对比 SC-009 (0.0 -> 1.0, +100.0 pp) 与 SC-010 (1.0 -> 0.0, -100.0 pp)
    before_dirs = sorted(p.name for p in (tmp_path / "eval").iterdir())
    r_rev = runner.invoke(
        app,
        ["eval", "compare", "ra", "rb", "--reviews", str(rev_csv), "--artifacts", str(tmp_path)],
    )
    assert r_rev.exit_code == 0, r_rev.output
    assert "0.000（0/1）" in r_rev.output and "1.000（1/1）" in r_rev.output
    assert "+1.000（+100.0 pp）" in r_rev.output and "-1.000（-100.0 pp）" in r_rev.output
    # ② 默认只读 stdout，不创建任何新目录
    assert sorted(p.name for p in (tmp_path / "eval").iterdir()) == before_dirs

    # ③ --out 禁止写入已有历史目录 artifacts/eval/ra/... 且原文件字节不变
    orig_report = tmp_path / "eval" / "ra" / "report.md"
    orig_report.write_text("KEEP-ME", encoding="utf-8")
    r_blk = runner.invoke(
        app,
        ["eval", "compare", "ra", "rb", "--out", str(orig_report), "--artifacts", str(tmp_path)],
    )
    assert r_blk.exit_code == 2 and "拒绝写入" in r_blk.output
    assert orig_report.read_text(encoding="utf-8") == "KEEP-ME"

    # --out 写入外部路径成功
    ext_out = tmp_path / "external" / "my_compare.md"
    r_ext = runner.invoke(
        app,
        ["eval", "compare", "ra", "rb", "--out", str(ext_out), "--artifacts", str(tmp_path)],
    )
    assert r_ext.exit_code == 0 and ext_out.is_file()
    assert "# 评测对比报告" in ext_out.read_text(encoding="utf-8")

    # ④ --save 落盘至 artifacts/eval/compare-<ts>/ 含 compare.md + manifest.json，同秒不覆盖
    r_save = runner.invoke(
        app, ["eval", "compare", "ra", "rb", "--save", "--artifacts", str(tmp_path)]
    )
    assert r_save.exit_code == 0, r_save.output
    saved_dirs = [p for p in (tmp_path / "eval").iterdir() if p.name.startswith("compare-")]
    assert len(saved_dirs) == 1
    assert (saved_dirs[0] / "compare.md").is_file()
    manifest = json.loads((saved_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["type"] == "eval_compare"
    assert manifest["inputs"]["runs"] == ["ra", "rb"]
    assert manifest["case_count"] == 1

    # 同秒碰撞保护：传入相同 timestamp 连续保存两次
    loaded = [load_run(tmp_path, "ra"), load_run(tmp_path, "rb")]
    cmp_res = compare_runs(loaded)
    md = render_compare_markdown(cmp_res)
    d1 = save_compare_artifact(tmp_path, cmp_res, md, timestamp="20261122-220000")
    d2 = save_compare_artifact(tmp_path, cmp_res, md, timestamp="20261122-220000")
    assert d1.name == "compare-20261122-220000"
    assert d2.name == "compare-20261122-220000-2"

    # ⑤ 互斥选项全部退 2
    for bad_flags in (
        ["--sc016", "--sc015"],
        ["--sc016", "--save"],
        ["--sc016", "--out", str(tmp_path / "x.md")],
        ["--sc016", "--reviews", str(rev_csv)],
        ["--out", str(tmp_path / "x.md"), "--save"],
    ):
        r_bad = runner.invoke(
            app, ["eval", "compare", *bad_flags, "ra", "rb", "--artifacts", str(tmp_path)]
        )
        assert r_bad.exit_code == 2, f"flags={bad_flags} output={r_bad.output}"


def test_general_comparability_and_align_negative_cases(tmp_path):
    """补齐通用对比与对齐反例：KB/评测集/use_system_prompt/诊断集/case_id/category/user/空结果。"""
    kb1 = _mk_kb(tmp_path / "kb" / "kb-1.sqlite")
    kb2 = _mk_kb(tmp_path / "kb" / "kb-2.sqlite")
    rows = [
        _rich_row("c1", "clause_id", gold={"clauses": ["dA:a1:p1"]},
                  scores={"recall": 1.0, "refusal_evidence": {"refused": False}}),
    ]
    cf1 = _mk_cases(tmp_path, rows, name="v1.jsonl")
    cf2 = _mk_cases(tmp_path, rows, name="v2.jsonl")

    _full_run(tmp_path, "base", rows, "m7b", kb1, cases=str(cf1))
    _full_run(tmp_path, "diff_kb", rows, "m7b", kb2, cases=str(cf1))
    _full_run(tmp_path, "diff_cases", rows, "m7b", kb1, cases=str(cf2))
    _full_run(tmp_path, "sys_false", rows, "m7b", kb1, cases=str(cf1),
              extra_config={"use_system_prompt": False})
    _full_run(tmp_path, "sys_none", rows, "m7b", kb1, cases=str(cf1),
              extra_config={"use_system_prompt": None})

    # KB 不一致 -> 退出 2
    r_kb = runner.invoke(app, ["eval", "compare", "base", "diff_kb", "--artifacts", str(tmp_path)])
    assert r_kb.exit_code == 2 and "知识库不一致" in r_kb.output

    # 评测集名不一致 -> 退出 2
    r_cf = runner.invoke(app, ["eval", "compare", "base", "diff_cases", "--artifacts", str(tmp_path)])
    assert r_cf.exit_code == 2 and "评测集不一致" in r_cf.output

    # use_system_prompt 不一致 -> 退出 2；缺失 -> 退出 1
    r_sf = runner.invoke(app, ["eval", "compare", "base", "sys_false", "--artifacts", str(tmp_path)])
    assert r_sf.exit_code == 2 and "use_system_prompt" in r_sf.output
    r_sn = runner.invoke(app, ["eval", "compare", "base", "sys_none", "--artifacts", str(tmp_path)])
    assert r_sn.exit_code == 1 and "use_system_prompt" in r_sn.output

    # 诊断集：路径命中 probe 与内容命中 source=train_probe 均退 2
    diag_path = tmp_path / "train-probe.jsonl"
    diag_path.write_text(json.dumps({"case_id": "c1", "source": "manual"}) + "\n", encoding="utf-8")
    _full_run(tmp_path, "dp1", rows, "m7b", kb1, cases=str(diag_path))
    _full_run(tmp_path, "dp2", rows, "m7b", kb1, cases=str(diag_path))
    r_dp = runner.invoke(app, ["eval", "compare", "dp1", "dp2", "--artifacts", str(tmp_path)])
    assert r_dp.exit_code == 2 and "诊断集" in r_dp.output

    diag_src = tmp_path / "normal_name.jsonl"
    diag_src.write_text(
        json.dumps({"case_id": "c1", "source": "train_probe"}) + "\n", encoding="utf-8"
    )
    _full_run(tmp_path, "ds1", rows, "m7b", kb1, cases=str(diag_src))
    _full_run(tmp_path, "ds2", rows, "m7b", kb1, cases=str(diag_src))
    r_ds = runner.invoke(app, ["eval", "compare", "ds1", "ds2", "--artifacts", str(tmp_path)])
    assert r_ds.exit_code == 2 and "诊断来源" in r_ds.output

    # align_general_cases：case_id 集合不同、category 不一致、turns[].user 不一致、空结果集
    rows_other_id = [_rich_row("c2", "clause_id", gold={"clauses": ["dA:a1:p1"]})]
    rows_diff_cat = [_rich_row("c1", "refusal", gold={"clauses": ["dA:a1:p1"]})]
    rows_diff_user = [_rich_row("c1", "clause_id", gold={"clauses": ["dA:a1:p1"]}, user="另一个问题")]
    _full_run(tmp_path, "oid", rows_other_id, "m7b", kb1, cases=str(cf1))
    _full_run(tmp_path, "dcat", rows_diff_cat, "m7b", kb1, cases=str(cf1))
    _full_run(tmp_path, "dusr", rows_diff_user, "m7b", kb1, cases=str(cf1))
    _full_run(tmp_path, "emp1", [], "m7b", kb1, cases=str(cf1))
    _full_run(tmp_path, "emp2", [], "m7b", kb1, cases=str(cf1))

    base_run = load_run(tmp_path, "base")
    with pytest.raises(CompareError, match="用例集合不同"):
        align_general_cases([base_run, load_run(tmp_path, "oid")])
    with pytest.raises(CompareError, match="category 不一致"):
        align_general_cases([base_run, load_run(tmp_path, "dcat")])
    with pytest.raises(CompareError, match="用户提问不一致"):
        align_general_cases([base_run, load_run(tmp_path, "dusr")])
    with pytest.raises(CompareError, match="评测结果为空"):
        align_general_cases([load_run(tmp_path, "emp1"), load_run(tmp_path, "emp2")])


def test_sc015_save_and_boundary_precision(tmp_path):
    """--sc015 --save PASS/FAIL 落盘与 manifest 校验 + 2.04 pp 临界超限展示精度防歧义。"""
    kb = _mk_kb(tmp_path / "kb" / "kb-test.sqlite")
    # 1/49 ≈ 0.020408 -> 2.04 pp（> 2.0 pp 但 .1f 为 2.0 pp，应自动提升精度展示为 2.04 pp）
    rows_p1 = [_rich_row("c1", "clause_id", gold={"clauses": ["dA:a1:p1"]},
                         scores={"recall": 0.5, "refusal_evidence": {"refused": False}})]
    rows_p2 = [_rich_row("c1", "clause_id", gold={"clauses": ["dA:a1:p1"]},
                         scores={"recall": 0.5, "refusal_evidence": {"refused": False}})]
    rows_f = [_rich_row("c1", "clause_id", gold={"clauses": ["dA:a1:p1"]},
                        scores={"recall": 0.5 + 1 / 49, "refusal_evidence": {"refused": False}})]
    cf = _mk_cases(tmp_path, rows_p1, name="sc15_save.jsonl")
    cfg = {"base_model": "m7b", "exp": "exp-t064"}
    _full_run(tmp_path, "p1", rows_p1, "default_model", kb, cases=str(cf), extra_config=cfg)
    _full_run(tmp_path, "p2", rows_p2, "default_model", kb, cases=str(cf), extra_config=cfg)
    _full_run(tmp_path, "pf", rows_f, "default_model", kb, cases=str(cf), extra_config=cfg)

    # ① --sc015 --save PASS -> 退 0，落盘 manifest 含 mode="sc015"、threshold_pp=2.0、sc015_passed=True
    r_pass = runner.invoke(
        app, ["eval", "compare", "--sc015", "--save", "p1", "p2", "--artifacts", str(tmp_path)]
    )
    assert r_pass.exit_code == 0, r_pass.output
    assert "SC-015 总判定：PASS" in r_pass.output
    saved_pass = sorted(
        p for p in (tmp_path / "eval").iterdir() if p.name.startswith("compare-")
    )
    assert len(saved_pass) == 1
    m_pass = json.loads((saved_pass[0] / "manifest.json").read_text(encoding="utf-8"))
    assert m_pass["type"] == "eval_compare"
    assert m_pass["config"] == {"mode": "sc015", "threshold_pp": 2.0}
    assert m_pass["sc015_passed"] is True

    # ② --sc015 --save FAIL (2.04 pp) -> 退 1，仍落盘，manifest sc015_passed=False，展示 2.04 pp
    r_fail = runner.invoke(
        app, ["eval", "compare", "--sc015", "--save", "p1", "pf", "--artifacts", str(tmp_path)]
    )
    assert r_fail.exit_code == 1
    assert "SC-015 总判定：FAIL" in r_fail.output
    saved_all = sorted(
        p for p in (tmp_path / "eval").iterdir() if p.name.startswith("compare-")
    )
    assert len(saved_all) == 2
    fail_dir = [p for p in saved_all if p != saved_pass[0]][0]
    m_fail = json.loads((fail_dir / "manifest.json").read_text(encoding="utf-8"))
    assert m_fail["config"] == {"mode": "sc015", "threshold_pp": 2.0}
    assert m_fail["sc015_passed"] is False
    md_fail = (fail_dir / "compare.md").read_text(encoding="utf-8")
    assert "波动 2.04 pp > 2.0 pp" in md_fail
    assert "波动 2.0 pp > 2.0 pp" not in md_fail
