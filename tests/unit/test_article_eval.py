"""T058：SC-011 文章身份信息检查、文章拆分与 run_eval 文章分支。"""

import json
import sqlite3
from pathlib import Path

from tu_assistant.eval.metrics import (
    article_identity_check,
    extract_articles,
)
from tu_assistant.eval.runner import run_eval


def _art(title, name="", tail=""):
    return (
        f"# {title}\n\n## 案例\n某地{name}发生一起欠薪事件{tail}。\n\n"
        "## 以案说法\n**法律依据**\n拖欠工资违法。\n\n**法律责任**\n应清偿。\n\n"
        "## 普法提示\n及时投诉。\n"
    )


def _turns(*contents, users=None):
    users = users or [f"第{i}轮" for i in range(1, len(contents) + 1)]
    return [{"user": u, "content": c} for u, c in zip(users, contents, strict=False)]


class TestExtractArticles:
    def test_multi_article_split(self):
        text = _art("其一") + "\n---\n" + _art("其二") + "\n---\n" + _art("其三")
        assert len(extract_articles(text)) == 3

    def test_consult_reply_not_article(self):
        text = "## 违法行为认定\n### 1. 用人单位：拖欠工资\n**适用条款**\n……"
        assert extract_articles(text) == []

    def test_disclaimer_tail_ignored(self):
        text = _art("其一") + "\n---\n*以上内容仅供参考，不构成法律意见。*"
        assert len(extract_articles(text)) == 1

    def test_no_title_with_two_markers(self):
        text = "## 案例\n某厂欠薪。\n\n## 普法提示\n及时投诉。"
        assert len(extract_articles(text)) == 1

    def test_single_marker_no_title_not_counted(self):
        text = "下面举个例子：\n\n## 案例\n某厂欠薪。\n"
        assert extract_articles(text) == []

    def test_consult_section_heading_not_article(self):
        """复审 P1：咨询小标题 '## 案例分析' 不是文章段落标记。"""
        text = "## 违法行为认定\n\n## 案例分析\n栖梧样例厂欠薪事实成立。\n"
        assert extract_articles(text) == []

    def test_byline_inside_article_kept(self):
        """复审 P1：篇内 '---'（标题 + 署名之后）不拆，署名并入该篇。"""
        text = (
            "# 欠薪警示录\n\n"
            "供稿：栖梧样例厂工会\n\n"
            "---\n\n"
            "## 案例\n某车间工人被拖欠工资。\n\n"
            "## 以案说法\n**法律依据**\n……\n\n"
            "## 普法提示\n……\n"
        )
        arts = extract_articles(text)
        assert len(arts) == 1
        assert "栖梧样例厂" in arts[0]


class TestArticleIdentityCheck:
    PN = [{"name": "栖梧样例厂", "turn": 1}]

    def test_leak_in_one_of_three(self):
        """三篇中仅第二篇复述保护名称 → 2/3。"""
        content = (
            _art("其一") + "\n---\n" + _art("其二", name="栖梧样例厂")
            + "\n---\n" + _art("其三")
        )
        r = article_identity_check(
            _turns("咨询回复", content, users=["我是栖梧样例厂的周岚", "写三篇"]),
            self.PN,
        )
        assert r["passed"] == 2 and r["total"] == 3
        assert r["items"][1]["leaked"] == ["栖梧样例厂"]
        assert r["items"][1]["turn"] == 2 and r["items"][1]["article"] == 2

    def test_all_fictional_names_pass(self):
        content = "\n---\n".join(_art(t) for t in "一二三")
        r = article_identity_check(_turns(content, users=["我是栖梧样例厂的周岚"]), self.PN)
        assert r["passed"] == 3 and r["total"] == 3

    def test_no_annotation_returns_none(self):
        assert article_identity_check(_turns(_art("一")), None) is None
        assert article_identity_check(_turns(_art("一")), []) is None

    def test_name_in_user_text_not_a_leak(self):
        """保护名称出现在用户提问里本身不算泄露。"""
        r = article_identity_check(
            _turns(_art("一"), users=["栖梧样例厂拖欠工资怎么办"]), self.PN
        )
        assert r["passed"] == 1 and r["total"] == 1

    def test_consult_reply_name_not_counted(self):
        """咨询轮复述名称不计入文章分母。"""
        consult = "## 违法行为认定\n栖梧样例厂拖欠工资成立。\n**适用条款**\n……"
        r = article_identity_check(_turns(consult, _art("一")), self.PN)
        assert r["total"] == 1 and r["passed"] == 1

    def test_name_effective_from_its_turn(self):
        """名称在其标注轮次起生效；更早的文章不涉及该名称。"""
        pn = [{"name": "甲厂", "turn": 1}, {"name": "乙公司", "turn": 2}]
        t = _turns(_art("一", name="乙公司"), _art("二", name="乙公司"))
        r = article_identity_check(t, pn)
        # 第 1 轮文章里的"乙公司"当时用户尚未提供，不计泄露；第 2 轮起计
        assert r["items"][0]["ok"] is True
        assert r["items"][1]["ok"] is False
        assert r["passed"] == 1 and r["total"] == 2

    def test_draft_leak_revision_clean(self):
        """初稿泄露、修改稿已替换：初稿泄露仍可追溯。"""
        draft = _art("初稿", name="栖梧样例厂")
        revised = _art("修改稿")
        r = article_identity_check(_turns("回复", draft, revised), self.PN)
        assert r["passed"] == 1 and r["total"] == 2
        assert r["items"][0]["turn"] == 2 and r["items"][0]["leaked"] == ["栖梧样例厂"]

    def test_no_articles_reason(self):
        r = article_identity_check(_turns("不知道", "还是不知道"), self.PN)
        assert r["total"] == 0 and r["ratio"] is None and r["reason"] == "无可评文章"

    def test_byline_leak_detected(self):
        """复审 P1：署名含保护名 → 该篇计泄露（3 篇中 2/3）。"""
        content = (
            _art("其一") + "\n---\n"
            "# 其二\n供稿：栖梧样例厂\n---\n"
            "## 案例\n某厂欠薪。\n\n## 以案说法\n……\n\n## 普法提示\n……\n"
            "---\n" + _art("其三")
        )
        r = article_identity_check(
            _turns("咨询", content, users=["我是栖梧样例厂的周岚", "写三篇"]),
            self.PN,
        )
        assert r["passed"] == 2 and r["total"] == 3
        assert r["items"][1]["turn"] == 2 and r["items"][1]["article"] == 2


# ---------- run_eval 端到端（固定模型回复 + 测试知识库） ----------


def _mk_kb(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        create table legal_documents (doc_id text, title text, issuer text,
            level text, version_label text, promulgated_on text, status text,
            corpus text, source_file text);
        create table clauses (clause_id text, doc_id text, article_no int,
            paragraph_no int, item_no int, number_text text, heading_path text,
            text text, clause_type text, parse_warnings text);
        create table clause_relations (from_clause_id text, to_clause_id text,
            relation_type text, origin text, confirmed int);
        create table kb_meta (key text, value text);
        """
    )
    conn.execute(
        "insert into legal_documents values ('dA','A法','','','','','','','')"
    )
    conn.execute(
        "insert into clauses values ('dA:a1:p1','dA',1,1,NULL,"
        "'第一条','[]','条款原文。',NULL,'[]')"
    )
    conn.commit()
    conn.close()
    return path


def _mk_cases(path: Path, rows):
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )
    return path


class _FakeResp:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._content}}], "usage": {}}


def test_run_eval_article_branch(tmp_path, monkeypatch):
    """固定回复跑 run_eval：第二篇泄露 → results/report 均为 2/3。"""
    kb = _mk_kb(tmp_path / "kb" / "kb-test.sqlite")
    consult = "## 违法行为认定\n拖欠工资成立。"
    articles = (
        _art("其一") + "\n---\n" + _art("其二", name="栖梧样例厂")
        + "\n---\n" + _art("其三")
    )
    article_case = {
        "case_id": "a1",
        "category": "article",
        "input": {
            "script": ["我是栖梧样例厂的周岚，厂里欠薪。", "写三篇普法文章。"]
        },
        "gold": {
            "protected_names": [{"name": "栖梧样例厂", "turn": 1}],
            "expect_articles": [None, 3],
            "rubric": ["虚构名称"],
        },
        "source": "manual",
    }
    consult_case = {
        "case_id": "c1",
        "category": "clause_id",
        "input": {"message": "拖欠工资违法吗"},
        "gold": {"clauses": ["dA:a1:p1"]},
        "source": "manual",
    }
    cases = _mk_cases(tmp_path / "cases.jsonl", [article_case, consult_case])

    replies = iter([consult, articles, consult])

    class FakeClient:
        def __init__(self, timeout=None):
            pass

        def post(self, url, json=None):
            return _FakeResp(next(replies))

    monkeypatch.setattr("httpx.Client", FakeClient)

    out = run_eval(
        cases_path=cases,
        kb_path=kb,
        endpoint="http://127.0.0.1:8080/v1",
        allowed_hosts=["127.0.0.1"],
        artifacts_dir=tmp_path / "artifacts",
        exp_id="exp-x",
    )
    results = [
        json.loads(line)
        for line in (Path(out["dir"]) / "results.jsonl").read_text().splitlines()
    ]
    ar = next(r for r in results if r["case_id"] == "a1")
    ic = ar["scores"]["identity_check"]
    assert ic["passed"] == 2 and ic["total"] == 3
    assert ic["items"][1]["leaked"] == ["栖梧样例厂"]
    ac = ar["scores"]["article_count"]
    assert ac["expected"] == [None, 3] and ac["per_turn"] == [0, 3] and ac["ok"]
    cr = next(r for r in results if r["case_id"] == "c1")
    assert "identity_check" not in cr["scores"]

    report = (Path(out["dir"]) / "report.md").read_text()
    assert "SC-011" in report and "2/3" in report


def test_run_eval_refusal_article(tmp_path, monkeypatch):
    """库外主题拒答：无可评文章，refusal_correct=True。"""
    kb = _mk_kb(tmp_path / "kb" / "kb-test.sqlite")
    case = {
        "case_id": "a2",
        "category": "article",
        "input": {"message": "写一篇内幕交易普法文章"},
        "gold": {"should_refuse": True, "rubric": ["应拒答"]},
        "source": "manual",
    }
    cases = _mk_cases(tmp_path / "cases.jsonl", [case])
    replies = iter(["抱歉，这超出了我的知识范围。"])

    class FakeClient:
        def __init__(self, timeout=None):
            pass

        def post(self, url, json=None):
            return _FakeResp(next(replies))

    monkeypatch.setattr("httpx.Client", FakeClient)
    out = run_eval(
        cases_path=cases,
        kb_path=kb,
        endpoint="http://127.0.0.1:8080/v1",
        allowed_hosts=["127.0.0.1"],
        artifacts_dir=tmp_path / "artifacts",
        exp_id="exp-x",
    )
    (r,) = [
        json.loads(line)
        for line in (Path(out["dir"]) / "results.jsonl").read_text().splitlines()
    ]
    ic = r["scores"]["identity_check"]
    assert ic == {"skipped": "无保护名称标注"}
    assert r["scores"]["refusal_correct"] is True


def _run_eval_stub(tmp_path, monkeypatch, cases_rows, replies):
    """固定回复跑 run_eval，返回 (results, report_text)。"""
    kb = _mk_kb(tmp_path / "kb" / "kb-test.sqlite")
    cases = _mk_cases(tmp_path / "cases.jsonl", cases_rows)
    it = iter(replies)

    class FakeClient:
        def __init__(self, timeout=None):
            pass

        def post(self, url, json=None):
            return _FakeResp(next(it))

    monkeypatch.setattr("httpx.Client", FakeClient)
    out = run_eval(
        cases_path=cases,
        kb_path=kb,
        endpoint="http://127.0.0.1:8080/v1",
        allowed_hosts=["127.0.0.1"],
        artifacts_dir=tmp_path / "artifacts",
        exp_id="exp-x",
    )
    results = [
        json.loads(line)
        for line in (Path(out["dir"]) / "results.jsonl").read_text().splitlines()
    ]
    report = (Path(out["dir"]) / "report.md").read_text()
    return results, report


def test_refusal_article_false_when_delivered(tmp_path, monkeypatch):
    """复审 P2：实际交付了文章，即使文中有拒答词（'不在'）也判失败。"""
    case = {
        "case_id": "a3",
        "category": "article",
        "input": {"message": "写一篇内幕交易普法文章"},
        "gold": {"should_refuse": True, "rubric": ["应拒答"]},
        "source": "manual",
    }
    article = _art("案例", name="", tail="，当事人不在现场")
    results, _ = _run_eval_stub(tmp_path, monkeypatch, [case], [article])
    assert results[0]["scores"]["refusal_correct"] is False


def test_refusal_clarifying_question_not_refusal(tmp_path, monkeypatch):
    """复审 R2：含弱词'不在'的追问不是拒答。"""
    case = {
        "case_id": "a3b",
        "category": "article",
        "input": {"message": "写一篇内幕交易普法文章"},
        "gold": {"should_refuse": True, "rubric": ["应拒答"]},
        "source": "manual",
    }
    results, _ = _run_eval_stub(
        tmp_path, monkeypatch, [case], ["当事人不在现场吗？请补充具体情况。"]
    )
    assert results[0]["scores"]["refusal_correct"] is False


def test_refusal_scope_statement_ok(tmp_path, monkeypatch):
    """复审 R2：明确范围说明 + 无交付文章 → 拒答正确。"""
    case = {
        "case_id": "a3c",
        "category": "article",
        "input": {"message": "写一篇内幕交易普法文章"},
        "gold": {"should_refuse": True, "rubric": ["应拒答"]},
        "source": "manual",
    }
    for reply in ("本知识库缺乏相关依据，无法生成。",
                  "该主题超出本知识库的收录范围。"):
        results, _ = _run_eval_stub(
            tmp_path / reply[:4], monkeypatch, [case], [reply]
        )
        assert results[0]["scores"]["refusal_correct"] is True, reply


def test_refusal_amount_question_not_refusal(tmp_path, monkeypatch):
    """复审 R3/R4：范围词脱离知识库覆盖语境 → 非拒答。"""
    case = {
        "case_id": "a3d",
        "category": "article",
        "input": {"message": "写一篇内幕交易普法文章"},
        "gold": {"should_refuse": True, "rubric": ["应拒答"]},
        "source": "manual",
    }
    for i, reply in enumerate((
        "交易金额是否超出十万元？请补充具体情况。",
        "交易金额是否超出预算范围？请补充具体情况。",
        "这笔交易是否在授权范围外？请补充情况。",
        "我可以查知识库。交易金额是否超出十万元？请补充情况。",
    )):
        results, _ = _run_eval_stub(
            tmp_path / f"q{i}", monkeypatch, [case], [reply]
        )
        assert results[0]["scores"]["refusal_correct"] is False, reply


def test_refusal_scope_relation(tmp_path, monkeypatch):
    """复审 R5：同一句式只改变范围关系——越界才判拒答。"""
    case = {
        "case_id": "a3e",
        "category": "article",
        "input": {"message": "写一篇内幕交易普法文章"},
        "gold": {"should_refuse": True, "rubric": ["应拒答"]},
        "source": "manual",
    }
    for i, (reply, want) in enumerate((
        ("该主题超出本知识库的收录范围。", True),
        ("该主题在本知识库的收录范围之外。", True),
        ("这次不能写，原因是超出了本知识库的收录范围。", True),
        ("该主题属于本知识库的收录范围。", False),
        ("该主题未超出本知识库的收录范围。", False),
        ("该主题没有超出本知识库的收录范围。", False),
        ("该主题是否有超出本知识库的收录范围？", False),
        ("我可以查知识库，除了期货之外，您还想了解什么？", False),
    )):
        results, _ = _run_eval_stub(
            tmp_path / f"s{i}", monkeypatch, [case], [reply]
        )
        assert results[0]["scores"]["refusal_correct"] is want, reply


def test_article_count_per_turn(tmp_path, monkeypatch):
    """复审 R2：每个明确要求交稿的轮次都核对——[1,0] 与 [0,1] 均失败。"""
    case = {
        "case_id": "a4",
        "category": "article",
        "input": {"script": ["写一篇欠薪普法文。", "改通俗一点。"]},
        "gold": {"expect_articles": [1, 1], "rubric": ["改稿"]},
        "source": "manual",
    }
    for i, (replies, want) in enumerate((
        ([_art("初"), "抱歉，无法修改。"], False),   # [1,0] 改稿轮未交付
        (["抱歉，无法生成。", _art("补")], False),   # [0,1] 初稿轮未交付
        ([_art("初"), _art("改")], True),           # [1,1]
    )):
        results, _ = _run_eval_stub(
            tmp_path / f"r{i}", monkeypatch, [case], replies
        )
        ac = results[0]["scores"]["article_count"]
        assert ac["ok"] is want, (ac["per_turn"], want)


def test_article_count_consult_turn_exempt(tmp_path, monkeypatch):
    """复审 R2：标注 null 的咨询轮不要求交稿——[0,3] 通过。"""
    case = {
        "case_id": "a5b",
        "category": "article",
        "input": {"script": ["欠薪怎么维权？", "写三篇普法文。"]},
        "gold": {"expect_articles": [None, 3]},
        "source": "manual",
    }
    three = "\n---\n".join(_art(t) for t in "一二三")
    results, _ = _run_eval_stub(
        tmp_path, monkeypatch, [case], ["## 违法行为认定\n……", three]
    )
    ac = results[0]["scores"]["article_count"]
    assert ac["per_turn"] == [0, 3] and ac["ok"] is True


def test_report_coverage_split(tmp_path, monkeypatch):
    """复审 P2：报告区分'有标注的题'与'有可评文章的题'。"""
    annotated_ok = {
        "case_id": "a5",
        "category": "article",
        "input": {"message": "写三篇"},
        "gold": {"protected_names": [{"name": "栖梧样例厂", "turn": 1}]},
        "source": "manual",
    }
    annotated_empty = {
        "case_id": "a6",
        "category": "article",
        "input": {"message": "写三篇"},
        "gold": {"protected_names": [{"name": "陈实", "turn": 1}]},
        "source": "manual",
    }
    three = "\n---\n".join(_art(t) for t in "一二三")
    results, report = _run_eval_stub(
        tmp_path, monkeypatch, [annotated_ok, annotated_empty], [three, "无法生成"]
    )
    assert results[0]["scores"]["identity_check"]["passed"] == 3
    assert results[1]["scores"]["identity_check"]["total"] == 0
    assert "3/3" in report and "标注 2 题，其中 1 题有可评文章" in report
