"""T036: 指标计算的单元测试。"""

from tu_assistant.citation.models import Citation
from tu_assistant.eval.metrics import (
    citation_accuracy,
    citation_completeness,
    clause_recall_precision,
    intent_score,
    multi_violation_score,
    refusal_correct,
    relation_completion_score,
)
from tu_assistant.kb.models import ClauseRelation
from tu_assistant.kb.store import create_kb, insert_relation


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


class TestRelationCompletionScore:
    def test_deduplicates_shared_liability_target(self):
        conn = create_kb(":memory:")
        # 整条展开：a21:p1 与 a21:p2 都指向同一个责任条款 a40:p1；另有一条 a3:p1 -> a51:p1
        insert_relation(conn, ClauseRelation("d:a21:p1", "d:a40:p1", "liability_for", "rule", True))
        insert_relation(conn, ClauseRelation("d:a21:p2", "d:a40:p1", "liability_for", "rule", True))
        insert_relation(conn, ClauseRelation("d:a3:p1", "d:a51:p1", "liability_for", "rule", True))
        # references 不计入 SC-005
        insert_relation(conn, ClauseRelation("d:a21:p1", "d:a99:p1", "references", "rule", True))
        conn.commit()

        # 同时引用 a21:p1、a21:p2 且只补全了 a40:p1，未补全 a51:p1：
        # 去重后责任条款集合为 {a40:p1, a51:p1} → 1/2 = 0.5（而非按边算 2/3）
        score = relation_completion_score({"d:a21:p1", "d:a21:p2", "d:a3:p1", "d:a40:p1"}, conn)
        assert score == 0.5

        # 只引用 a21:p1 与 a21:p2 且补全 a40:p1 → 1/1 = 1.0
        assert relation_completion_score({"d:a21:p1", "d:a21:p2", "d:a40:p1"}, conn) == 1.0
        # 无触发责任关系 → None
        assert relation_completion_score({"d:a1:p1"}, conn) is None
        conn.close()
