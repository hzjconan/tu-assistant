"""T052 从生成入口检验训练原稿，数据库和模型回复全部使用虚构材料。"""

import json
from types import SimpleNamespace

import pytest

from tu_assistant.kb.models import Clause, ClauseRelation, DocumentMeta
from tu_assistant.kb.store import create_kb, insert_clause, insert_document, insert_relation
from tu_assistant.synth.articles import ArticleStats, generate
from tu_assistant.synth.llm import (
    ExternalInputNotAllowedError,
    ExternalLLM,
)


@pytest.fixture
def inputs(tmp_path):
    db = create_kb(":memory:")
    insert_document(db, DocumentMeta("演练规则", "示例版", doc_id="demo"))
    for n, content in enumerate(["应当登记。", "应当通知。", "登记遗漏责令改正。", "漏发通知应补发。"], 1):
        insert_clause(db, Clause("demo", n, 1, None, f"第{n}条", text=content))
    for a, b in [(1, 3), (2, 4)]:
        insert_relation(db, ClauseRelation(f"demo:a{a}:p1", f"demo:a{b}:p1", "liability_for", "manual", True))
    # 其他关系种类和未确认关系不能入选。
    insert_relation(db, ClauseRelation("demo:a1:p1", "demo:a2:p1", "references", "manual", True))
    insert_relation(db, ClauseRelation("demo:a3:p1", "demo:a1:p1", "liability_for", "rule", False))
    yield db, tmp_path
    db.close()


class FixtureClient:
    def __init__(self, change):
        self.change = change
        self.calls = []

    def chat(self, messages, *, input_source, max_tokens, reject_truncated):
        assert (input_source, max_tokens, reject_truncated) == ("kb_clause", 4096, True)
        plan = json.loads(messages[0]["content"].split("\n篇计划\n")[1])
        self.calls.append(plan)
        articles = []
        for i, article in enumerate(plan, 1):
            lines = [f"# 故事{i}", "## 案例", f"虚构厂未办理第{i}笔记录。", "## 以案说法"]
            for material in article["行为素材"]:
                lines.extend(
                    [
                        "### 虚构厂：漏办手续",
                        "记录与该厂履职义务相符。",
                        "**法律依据**",
                        material["依据"],
                        "**法律责任**",
                        material["责任"],
                    ]
                )
            lines.extend(["## 普法提示", "请查收记录。"])
            articles.append("\n".join(lines))
        self.change(articles, plan)
        return "主题：办理手续要留心\n" + "\n---\n".join(articles)


def run(inputs, change=lambda articles, plan: None, *, n=1, length=200):
    conn, folder = inputs
    client = FixtureClient(change)
    stats = ArticleStats()

    def count(messages):
        assert [m["role"] for m in messages] == ["system", "user", "assistant"]
        return length

    samples = generate(
        conn, client, {"seed": 42}, n_requests=n, stats=stats, eval_cases=folder, count_tokens=count
    )
    return samples, stats, client


def test_request_modes_and_material_plan(inputs):
    samples, stats, client = run(inputs, n=4)
    assert (stats.total, stats.kept, stats.dropped) == (4, 4, 0)
    assert stats.materials == {"eligible": 2}
    for sample, plan, mode in zip(samples, client.calls, (None, 1, 2, 3), strict=True):
        m = sample["meta"]
        assert (m["type"], m["doc_id"], m["kind"]) == (
            "article",
            "demo",
            f"n{mode}" if mode else "n3_default",
        )
        assert len(plan) == m["n_requested"] == (mode or 3)
        assert len({p["focus"] for p in m["plan"]}) == len(plan)
        assert str(m["max_questions"]) in sample["messages"][0]["content"]
        assert 2 <= m["max_questions"] <= 6
        assert (
            (f"{mode}篇" in sample["messages"][1]["content"])
            if mode
            else ("篇" not in sample["messages"][1]["content"])
        )
        ids = {cid for p in m["plan"] for pair in p["acts"] for cid in pair}
        assert set(m["clause_ids"]) == ids
        assert len(m["plan"][0]["acts"]) == (2 if mode == 1 else 1)


@pytest.mark.parametrize(
    ("bad", "reason", "article"),
    [
        ("count", "article_count_mismatch", None),
        ("section", "article_section_missing", 2),
        ("liability", "liability_missing", 2),
        ("swapped", "liability_basis_swapped", 2),
        ("missing_quote", "quote_missing", 2),
        ("wrong_quote", "citation_text_wrong", 2),
        ("not_found", "citation_not_found", 2),
        ("actor", "actor_missing", 2),
        ("analysis", "analysis_missing", 2),
        ("bare", "citation_mismatch", 2),
    ],
)
def test_bad_drafts_reject_whole_request(inputs, bad, reason, article):
    def change(articles, plan):
        if bad == "count":
            articles.pop()
            return
        act = plan[1]["行为素材"][0]
        replacements = {
            "section": ("## 普法提示", "**普法提示**"),
            "liability": ("**法律责任**", "责任"),
            "swapped": (act["依据"], act["责任"]),
            "missing_quote": (act["依据"], act["依据"].splitlines()[0]),
            "wrong_quote": (act["依据"], act["依据"] + "错"),
            "not_found": ("《演练规则》", "《不存在文件》"),
            "actor": ("### 虚构厂：", "### 违法主体："),
            "analysis": ("记录与该厂履职义务相符。", ""),
            "bare": ("请查收记录。", "根据第一条请查收记录。"),
        }
        old, new = replacements[bad]
        articles[1] = articles[1].replace(old, new)

    samples, stats, _ = run(inputs, change)
    assert not samples and stats.reasons == {reason: 1}
    assert stats.drops == [{"request": 1, "reason": reason, "article": article}]


def test_cross_act_in_same_article(inputs):
    def change(articles, plan):
        if len(plan[0]["行为素材"]) == 2:
            first, second = plan[0]["行为素材"]
            articles[0] = articles[0].replace(first["依据"], second["依据"], 1)
            articles[0] += "\n" + first["依据"]  # 整篇仍然引齐四条

    samples, stats, _ = run(inputs, change, n=2)
    assert len(samples) == 1
    assert stats.drops == [{"request": 2, "reason": "citation_mismatch", "article": 1}]


def test_repeat_marker_and_number_spelling(inputs):
    def change(articles, plan):
        marker = plan[0]["行为素材"][0]["依据"].splitlines()[0]
        articles[0] += "\n" + marker
        articles[0] = articles[0].translate(str.maketrans("1234", "一二三四"))

    samples, _, _ = run(inputs, change)
    assert len(samples) == 1
    assert not samples[0]["messages"][-1]["content"].split("---")[0].strip().splitlines()[-1].startswith(">")


def test_length_and_eval_overlap(inputs):
    samples, _, _ = run(inputs, length=2048)
    assert samples[0]["meta"]["tokens"] == 2048
    assert run(inputs, length=2049)[1].reasons == {"too_long": 1}
    _, folder = inputs
    row = {
        "case_id": "held",
        "category": "article",
        "input": {"message": samples[0]["messages"][1]["content"]},
    }
    (folder / "cases.jsonl").write_text(json.dumps(row))
    assert run(inputs)[1].reasons == {"eval_overlap": 1}


def test_materials_missing_or_wrong_paragraph(inputs):
    conn, _ = inputs
    conn.execute("DELETE FROM clauses WHERE clause_id='demo:a3:p1'")
    conn.execute("UPDATE clauses SET text='违反本规定第二条第二款。' WHERE clause_id='demo:a4:p1'")
    samples, stats, client = run(inputs)
    assert not samples and not client.calls
    assert stats.materials == {"eligible": 0, "material_unresolved": 1, "paragraph_mismatch": 1}


def test_length_finish_reason_keeps_usage_and_default_behavior(inputs, monkeypatch):
    monkeypatch.setenv("TU_EXTERNAL_LLM_API_KEY", "unit-test")
    llm = ExternalLLM("http://localhost", "fake")
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="片段"), finish_reason="length")], usage=None
    )
    llm._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: response))
    )
    assert llm.chat([], input_source="kb_clause") == "片段"
    db, folder = inputs
    stats = ArticleStats()
    assert not generate(db, llm, {}, n_requests=1, stats=stats, count_tokens=lambda _: 0, eval_cases=folder)
    assert stats.reasons == {"llm_truncated": 1} and llm.usage.calls == 2
    with pytest.raises(ExternalInputNotAllowedError):
        llm.chat([], input_source="user_chat", reject_truncated=True)
    assert llm.usage.calls == 2


def test_identical_cases_different_titles(inputs):
    def duplicate(articles, plan):
        articles[1] = articles[0].replace("# 故事1", "# 另一个标题", 1)

    samples, stats, _ = run(inputs, duplicate)
    assert not samples
    assert stats.drops == [{"request": 1, "reason": "duplicate_case", "article": 2}]


def test_explicit_modes_and_no_multi_material(inputs):
    conn, folder = inputs
    conn.execute("DELETE FROM clause_relations WHERE to_clause_id='demo:a4:p1'")
    stats = ArticleStats()
    samples = generate(
        conn,
        FixtureClient(lambda *_: None),
        {},
        n_requests=1,
        request_modes=(1,),
        count_tokens=lambda _: 200,
        eval_cases=folder,
        stats=stats,
    )
    assert samples[0]["meta"]["n_requested"] == 1
    assert stats.materials == {"eligible": 1, "no_multi_pair": 1}
    with pytest.raises(ValueError, match="训练篇数"):
        generate(conn, None, {}, request_modes=(4,), eval_cases=folder)


def test_child_items_in_basis_quote(inputs):
    conn, _ = inputs
    conn.execute("DELETE FROM clause_relations WHERE from_clause_id='demo:a2:p1'")
    insert_clause(conn, Clause("demo", 1, 1, 1, "第1条第一项", text="（一）登记时间。"))
    samples, stats, _ = run(inputs)
    assert stats.kept == 1
    assert "> 应当登记。（一）登记时间。" in samples[0]["messages"][-1]["content"]


@pytest.mark.parametrize("topic", ["请写十篇通知", "了解演练规则", "有关第十二条的规定"])
def test_topic_without_answer_or_explicit_count(inputs, topic):
    class Client(FixtureClient):
        def chat(self, *args, **kwargs):
            return super().chat(*args, **kwargs).replace("办理手续要留心", topic, 1)

    conn, folder = inputs
    stats = ArticleStats()
    samples = generate(
        conn,
        Client(lambda *_: None),
        {},
        n_requests=1,
        stats=stats,
        count_tokens=lambda _: 100,
        eval_cases=folder,
    )
    assert not samples and stats.reasons == {"invalid_topic": 1}
