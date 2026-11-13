"""T036: 指标计算的单元测试。"""

from tu_assistant.citation.models import Citation
from tu_assistant.eval.metrics import (
    citation_accuracy,
    citation_completeness,
    clause_recall_precision,
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
