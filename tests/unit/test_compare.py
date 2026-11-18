"""eval.compare：SC-016 判定的单元测试（T076，含首轮返工 8.1–8.4）。"""

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tu_assistant.cli import app
from tu_assistant.eval.compare import (
    CompareError,
    align_cases,
    comparability_issues,
    fisher_exact_two_sided,
    load_run,
    role_issues,
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
    assert r3.exit_code == 2 and "T062" in r3.output
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
