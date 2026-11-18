"""T036: 指标计算的单元测试。"""

from tu_assistant.citation.models import Citation
from tu_assistant.eval.metrics import (
    citation_accuracy,
    citation_completeness,
    clause_recall_precision,
    intent_score,
    multi_violation_score,
    refusal_correct,
)


class TestRecallPrecision:
    def test_perfect(self):
        r, p = clause_recall_precision({"a", "b"}, {"a", "b"})
        assert r == 1.0 and p == 1.0

    def test_partial(self):
        r, p = clause_recall_precision({"a", "c"}, {"a", "b"})
        assert r == 0.5 and p == 0.5

    def test_none(self):
        r, p = clause_recall_precision(set(), {"a"})
        assert r == 0.0 and p is None
        r, p = clause_recall_precision({"a"}, set())
        assert r is None and p == 0.0


class TestCitationCompleteness:
    def test_all_marked(self):
        text = "〔《示例工会法》（2020）第四条〕\n> 原文。"
        complete, total = citation_completeness(text)
        assert complete == 1 and total == 1

    def test_bare_counts_against(self):
        text = "〔《示例工会法》（2020）第四条〕\n另外第八条规定。"
        complete, total = citation_completeness(text)
        assert complete == 1 and total == 2


class TestCitationAccuracy:
    def _c(self, verdict):
        return Citation(raw="", title="t", verdict=verdict)

    def test_pre_post(self):
        cs = [self._c("ok"), self._c("corrected"), self._c("not_found")]
        acc = citation_accuracy(cs)
        assert acc["pre"] == 1 / 3
        assert acc["post"] == 2 / 3

    def test_incomplete_excluded(self):
        cs = [self._c("ok"), self._c("incomplete")]
        acc = citation_accuracy(cs)
        assert acc["n"] == 1 and acc["pre"] == 1.0


class TestBehaviorMetrics:
    def test_multi_violation_hits_any_gold_clause(self):
        gold = [
            {"actor": "用人单位", "clauses": ["d:a1", "d:a2"]},
            {"actor": "工会", "clauses": ["d:a8"]},
            {"actor": "个人", "clauses": ["d:a9"]},
        ]
        score = multi_violation_score({"d:a2", "d:a8", "d:x"}, gold)
        assert score == 2 / 3

    def test_refusal_correct_both_directions(self):
        assert refusal_correct("抱歉，这超出了我的知识范围。", True)
        assert not refusal_correct("可以回答，条款如下。", True)
        assert not refusal_correct("抱歉，我无法回答。", False)
        assert refusal_correct("可以回答，条款如下。", False)
        assert refusal_correct("用人单位不在规定时间内支付工资的，应承担责任。", False)
        assert refusal_correct("用人单位无法提供工资条。〔《劳动法》第五十条〕", False)
        assert refusal_correct("提到第三条，但这个主题我无法回答。", True)

    def test_intent_within_three_turns(self):
        turns = [
            {"intent": None},
            {"intent": "consult"},
            {"intent": "article"},
        ]
        assert intent_score(turns, {"intent": "consult"}) == 1.0
        assert intent_score(turns[:1], {"intent": "consult"}) == 0.0
        assert intent_score(turns, {"intent": "missing"}) == 0.0
