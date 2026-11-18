"""T058：SC-011 文章身份信息检查、文章拆分与 run_eval 文章分支。"""

import json
import sqlite3
from pathlib import Path

import pytest

from tu_assistant.eval.metrics import (
    article_identity_check,
    detect_refusal,
    extract_articles,
)
from tu_assistant.eval.runner import run_eval
from tu_assistant.synth.refusal import REFUSAL_ANSWERS


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
        "insert into legal_documents values ('dA','A法','','','','','current','','')"
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


def _published_article(case_id):
    path = Path(__file__).resolve().parents[2] / "eval/cases/v1/articles.jsonl"
    return next(c for c in map(json.loads, path.read_text().splitlines()) if c["case_id"] == case_id)


# 固定回复、结构门槛、证据短语
REFUSAL_REPLIES = [
    # A. 已交稿或正在追问
    (_art("案例", tail="，当事人不在现场"), "article", None),
    ("当事人不在现场吗？请补充具体情况。", "follow_up", None),
    ("交易金额是否超出十万元？请补充具体情况。", "follow_up", None),
    ("交易金额是否超出预算范围？请补充具体情况。", "follow_up", None),
    ("这笔交易是否在授权范围外？请补充情况。", "follow_up", None),
    ("我可以查知识库。交易金额是否超出十万元？请补充情况。", "follow_up", None),
    ("信息不足时我无法生成准确的文章，请补充：\n1. 涉及哪个行业？", "follow_up", None),
    ("信息不足时我无法生成准确的文章。\n1. 涉及哪个行业？", "follow_up", None),
    # B. 无证据
    ("该主题属于本知识库的收录范围。", None, None),
    ("该主题未超出本知识库的收录范围。", None, None),
    ("该主题没有超出本知识库的收录范围。", None, None),
    ("该主题是否超出本知识库的收录范围？", None, None),
    ("该主题是否有超出本知识库的收录范围？", None, None),
    ("我可以查知识库，除了期货之外，您还想了解什么？", None, None),
    ("如果超出本知识库的收录范围，我会直接告诉您。请问您想了解哪方面？", None, None),
    ("这个主题超出知识库范围了吗？您能再说具体些吗？", None, None),
    ("如果单位无法提供工资条，您手里还有其他证据吗？", None, None),
    # C. 拒答，含引导转向其他主题的问句
    ("本知识库缺乏相关依据，无法生成。", None, "无法生成"),
    ("该主题超出本知识库的收录范围。", None, "超出本知识库"),
    ("该主题在本知识库的收录范围之外。", None, "收录范围之外"),
    ("这次不能写，原因是超出了本知识库的收录范围。", None, "不能写"),
    ("原因是超出了本知识库的收录范围。", None, "超出了本知识库"),
    ("抱歉，这超出了我的知识范围。", None, "超出了我的知识范围"),
    (REFUSAL_ANSWERS["out_of_scope"], None, "超出了我的知识范围"),
    (REFUSAL_ANSWERS["unsupported_feature"], None, "暂不支持"),
    ("抱歉，证券期货内幕交易不属于我能处理的领域，这篇文章我写不了。", None, "写不了"),
    ("现有资料里找不到证券期货方面的规定，这篇普法文章没法写。", None, "没法写"),
    ("对不起，我只能就劳动和工会相关法律写文章，内幕交易罪这个题目我帮不上忙。", None, "帮不上忙"),
    ("抱歉，库内没有证券期货方面的法律依据，无法生成这篇文章。需要我改写一篇劳动法方面的普法文章吗？",
     None, "无法生成"),
    ("抱歉，该主题超出本知识库的收录范围。您可以换个劳动法主题，例如：\n"
     "1. 拖欠工资怎么维权？\n2. 加班费怎么算？", None, "超出本知识库"),
    ("抱歉，库内没有证券期货方面的法律依据，无法生成。如有劳动法方面的需求，请补充说明。",
     None, "库内没有"),
]


@pytest.mark.parametrize(("reply", "blocked_by", "evidence"), REFUSAL_REPLIES)
def test_article_refusal(tmp_path, monkeypatch, reply, blocked_by, evidence):
    results, report = _run_eval_stub(tmp_path, monkeypatch, [_published_article("article-007")], [reply])
    scores = results[0]["scores"]
    refused = evidence is not None
    assert scores["refusal_correct"] is refused
    assert scores["refusal_evidence"] == {"refused": refused, "evidence": evidence, "blocked_by": blocked_by}
    assert scores["identity_check"] == {"skipped": "无保护名称标注"}
    assert f"范围外正确拒答 {float(refused):.3f}（{int(refused)}/1）" in report
    assert "范围内误拒 无样本（0/0）" in report
    assert "常规题 无样本（0/0）" in report
    assert "专设误拒题 无样本（0/0）" in report
    assert "SC-008（自动初筛，依据见 results.jsonl 的 refusal_evidence）" in report


@pytest.mark.parametrize(("reply", "expected"), [
    pytest.param("这个主题不会超出知识库范围。", False,
                 marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason="不会超出被识别为越界")),
    pytest.param("资料里找不到相关规定，这篇稿子恕难执笔。", True,
                 marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason="委婉拒答未命中短语")),
    pytest.param("这个主题未必超出知识库范围，请补充具体情况。", False,
                 marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason="未必超出被识别为越界")),
    pytest.param("现有资料里找不到证券期货方面的规定，没法据此写普法文章。", True,
                 marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason="插入据此后未命中短语")),
    pytest.param("若干问题超出知识库范围，无法生成。", True,
                 marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason="若干被当作条件句前缀")),
    pytest.param("用人单位无法提供考勤记录的，应承担不利后果（劳动合同法第三十条）。", False,
                 marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason="裸引用不阻断能力短语")),
])
def test_refusal_known_limitations(reply, expected):
    assert detect_refusal(reply)["refused"] is expected


@pytest.mark.parametrize(("reply", "blocked_by"), [
    (_art("文章") + "\n该主题超出本知识库。请补充说明。", "article"),
    ("该主题超出本知识库。〔《A法》第一条〕\n1. 需要劳动法主题吗？", "citation"),
])
def test_refusal_structure_priority(reply, blocked_by):
    assert detect_refusal(reply) == {"refused": False, "evidence": None, "blocked_by": blocked_by}


def test_consult_refusal_report(tmp_path, monkeypatch):
    cases = [
        {"case_id": str(i), "category": category, "gold": {"should_refuse": expected},
         "input": {"message": "咨询"}, "source": "manual"}
        for i, (category, expected) in enumerate([("refusal", True), ("false_refusal", False),
                                                  ("false_refusal", False)])
    ]
    replies = ["无法回答。", "无法回答。", "单位无法提供凭证。〔《A法》第一条〕"]
    results, report = _run_eval_stub(tmp_path, monkeypatch, cases, replies)
    assert [r["scores"]["refusal_correct"] for r in results] == [True, False, True]
    assert results[1]["scores"]["refusal_evidence"]["evidence"] == "无法回答"
    assert results[2]["scores"]["refusal_evidence"]["blocked_by"] == "citation"
    assert "范围外正确拒答 1.000（1/1）" in report
    assert "范围内误拒 0.500（1/2）" in report
    assert "常规题 无样本（0/0）" in report
    assert "专设误拒题 1/2" in report


def test_regular_refusal_report(tmp_path, monkeypatch):
    cases = [
        {"case_id": str(i), "category": category, "gold": {},
         "input": {"message": "咨询或生成文章"}, "source": "manual"}
        for i, category in enumerate(["clause_id", "clause_id", "article", "false_refusal"])
    ]
    replies = [
        "单位无法提供凭证。〔《A法》第一条〕", "抱歉，这个问题我无法回答。",
        _art("欠薪普法"), "抱歉，这个问题我无法回答。",
    ]
    results, report = _run_eval_stub(tmp_path, monkeypatch, cases, replies)
    assert [r["scores"]["refusal_correct"] for r in results] == [True, False, True, False]
    detections = [r["scores"]["refusal_evidence"] for r in results]
    assert [d["blocked_by"] for d in detections] == ["citation", None, "article", None]
    assert detections[1]["evidence"] == detections[3]["evidence"] == "无法回答"
    assert "范围外正确拒答 无样本（0/0）" in report
    assert "范围内误拒 0.500（2/4）" in report
    assert "常规题 1/3" in report
    assert "专设误拒题 1/1" in report


def test_unparsed_article_leak(tmp_path, monkeypatch):
    case = _published_article("article-009")
    text = "\n---\n".join(
        f"# {title}\n**案例**\n{name}发生欠薪。\n**以案说法**\n……\n**普法提示**\n……"
        for title, name in [("其一", "甲厂"), ("其二", "栖梧样例厂"), ("其三", "乙厂")]
    )
    results, report = _run_eval_stub(tmp_path, monkeypatch, [case], ["周岚提到欠薪。", text])
    check = results[0]["scores"]["identity_check"]
    assert check["total"] == check["passed"] == 0
    assert check["reason"] == "未识别出文章结构"
    assert check["unparsed_leaks"] == [{"turn": 2, "leaked": ["栖梧样例厂"]}]
    assert "另有 1 轮未识别出文章结构但含保护名称" in report
    assert results[0]["scores"]["article_count"]["ok"] is False


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
