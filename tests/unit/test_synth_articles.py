"""T052 从生成入口检验训练原稿，数据库和模型回复全部使用虚构材料。"""

import json
from types import SimpleNamespace

import pytest

from tu_assistant.chat.orchestrator import DISCLAIMER
from tu_assistant.kb.models import Clause, ClauseRelation, DocumentMeta
from tu_assistant.kb.store import create_kb, insert_clause, insert_document, insert_relation
from tu_assistant.synth.articles import (
    ARTICLE_USER_PROMPTS,
    CASE_USER_PROMPTS,
    REVISION_USER_PROMPTS,
    ArticleStats,
    draft_id,
    find_case_near_duplicates,
    generate,
    generate_from_case,
    generate_revisions,
    normalize_draft_markers,
)
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
        cn_num = {1: "一", 2: "两", 3: "三", 4: "四"}
        assert (
            any(k in sample["messages"][1]["content"] for k in (f"{mode}篇", f"{cn_num[mode]}篇"))
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
        ("tip_cit", "citation_in_tip", 2),
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
            "tip_cit": ("请查收记录。", f"请查收记录。\n**法律依据**\n{act['依据']}"),
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
        generate(conn, None, {}, request_modes=(5,), eval_cases=folder)


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


# ---- T053: 多轮修改样本测试 ----


class RevisionFixtureClient:
    def __init__(self, transform=None):
        self.transform = transform
        self.calls = []

    def chat(self, messages, *, input_source, max_tokens, reject_truncated):
        assert (input_source, max_tokens, reject_truncated) == ("kb_clause", 4096, True)
        prompt = messages[0]["content"]
        rtype = "plainer" if "修改要求（更通俗）" in prompt else "swap_subject"
        draft = prompt.split("\n原初稿\n", 1)[1]
        self.calls.append((rtype, prompt))
        if rtype == "plainer":
            revised = draft.replace("未办理", "压根没办").replace("请查收记录。", "工友记得留好凭证。")
        else:
            revised = (
                draft.replace("虚构厂", "明达物流公司")
                .replace("未办理", "拖着不办")
                .replace("该厂", "该公司")
            )
        if self.transform:
            revised = self.transform(revised, rtype, draft)
        return revised


def _make_drafts(inputs, modes=(1, 2)):
    conn, folder = inputs
    client = FixtureClient(lambda *_: None)
    samples = generate(
        conn,
        client,
        {"seed": 42},
        n_requests=len(modes),
        request_modes=modes,
        count_tokens=lambda _: 200,
        eval_cases=folder,
    )
    for idx, s in enumerate(samples, 1):
        s["meta"]["source_batch"] = "unit-drafts"
        s["meta"]["request"] = idx
    return samples


def test_revisions_plainer_and_swap_subject_positive(inputs):
    conn, folder = inputs
    # 新增一条未被初稿引用的 references 目标条款，验证历史轮按 process_turn 回填“相关条款（系统补充）”
    insert_clause(conn, Clause("demo", 5, 1, None, "第5条", text="补充关联条款。"))
    insert_relation(conn, ClauseRelation("demo:a1:p1", "demo:a5:p1", "references", "manual", True))
    insert_relation(conn, ClauseRelation("demo:a2:p1", "demo:a5:p1", "references", "manual", True))
    drafts = _make_drafts(inputs, modes=(1, 2))
    stats = ArticleStats()
    client = RevisionFixtureClient()

    def count(messages):
        return 600 if len(messages) == 3 else 1300

    revisions = generate_revisions(
        conn,
        client,
        {"seed": 42},
        drafts,
        stats=stats,
        count_tokens=count,
        eval_cases=folder,
    )
    assert (stats.total, stats.kept, stats.dropped) == (4, 4, 0)
    assert len(client.calls) == 4
    kinds = [s["meta"]["kind"] for s in revisions]
    assert kinds == ["revise_plainer", "revise_swap_subject", "revise_plainer", "revise_swap_subject"]
    assert [s["meta"]["parent"] for s in revisions] == [
        "unit-drafts:req1",
        "unit-drafts:req1",
        "unit-drafts:req2",
        "unit-drafts:req2",
    ]

    for rev in revisions:
        msgs = rev["messages"]
        assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user", "assistant"]
        assert msgs[2]["content"].endswith(DISCLAIMER)
        assert "**相关条款（系统补充）**" in msgs[2]["content"]
        assert "补充关联条款。" in msgs[2]["content"]
        assert DISCLAIMER.strip() not in msgs[4]["content"]
        assert rev["meta"]["type"] == "article"
        assert rev["meta"]["tokens"] == 1300


def test_normalize_draft_markers_adds_explicit_paragraph(inputs):
    conn, _ = inputs
    # 把第 1 条变为多款条文，KB 里的 number_text 更新为“第一条第1款”
    conn.execute("UPDATE clauses SET number_text='第一条第1款' WHERE clause_id='demo:a1:p1'")
    insert_clause(conn, Clause("demo", 1, 2, None, "第一条第2款", text="补充要求。"))
    draft = {
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "写文章"},
            {
                "role": "assistant",
                "content": "〔《演练规则》（示例版）第1条〕\n> 应当登记。",
            },
        ],
        "meta": {"type": "article"},
    }
    normalized = normalize_draft_markers(draft, conn)
    assert "〔《演练规则》（示例版）第一条第1款〕" in normalized["messages"][2]["content"]
    # 原对象不被原地修改
    assert "〔《演练规则》（示例版）第1条〕" in draft["messages"][2]["content"]


def test_revisions_reject_3_article_and_long_drafts(inputs):
    conn, folder = inputs
    draft3 = _make_drafts(inputs, modes=(3,))
    draft1 = _make_drafts(inputs, modes=(1,))

    stats3 = ArticleStats()
    client3 = RevisionFixtureClient()
    res3 = generate_revisions(
        conn,
        client3,
        {"seed": 42},
        draft3,
        n_requests=1,
        stats=stats3,
        count_tokens=lambda _: 200,
        eval_cases=folder,
    )
    assert not res3 and stats3.reasons == {"unsupported_article_count": 1}
    assert not client3.calls

    stats_long_draft = ArticleStats()
    client_ld = RevisionFixtureClient()
    res_ld = generate_revisions(
        conn,
        client_ld,
        {"seed": 42},
        draft1,
        n_requests=1,
        stats=stats_long_draft,
        count_tokens=lambda msgs: 1051 if len(msgs) == 3 else 1500,
        eval_cases=folder,
    )
    assert not res_ld and stats_long_draft.reasons == {"draft_too_long": 1}
    assert not client_ld.calls

    stats_too_long = ArticleStats()
    res_tl = generate_revisions(
        conn,
        RevisionFixtureClient(),
        {"seed": 42},
        draft1,
        n_requests=1,
        stats=stats_too_long,
        count_tokens=lambda msgs: 800 if len(msgs) == 3 else 2049,
        eval_cases=folder,
    )
    assert not res_tl and stats_too_long.reasons == {"too_long": 1}


@pytest.mark.parametrize(
    ("rtype", "bad", "expected_reason"),
    [
        ("plainer", "unchanged", "revision_unchanged"),
        ("plainer", "actor_changed", "actor_changed"),
        ("plainer", "citation_altered", "citation_not_found"),
        ("swap_subject", "actor_unchanged", "actor_unchanged"),
        ("swap_subject", "citation_swapped", "liability_basis_swapped"),
    ],
)
def test_revisions_negative_validation(inputs, rtype, bad, expected_reason):
    conn, folder = inputs
    drafts = _make_drafts(inputs, modes=(2,))

    def transform(revised, _rt, draft):
        if bad == "unchanged":
            return draft
        if bad == "actor_changed":
            return revised.replace("### 虚构厂：", "### 别的厂：", 1)
        if bad == "citation_altered":
            return revised.replace("《演练规则》", "《不存在法》", 1)
        if bad == "actor_unchanged":
            return revised.replace("明达物流公司", "虚构厂")
        if bad == "citation_swapped":
            return revised.replace("第1条〕\n> 应当登记。", "第3条〕\n> 登记遗漏责令改正。", 1).replace(
                "第2条〕\n> 应当通知。", "第4条〕\n> 漏发通知应补发。", 1
            )
        return revised

    stats = ArticleStats()
    res = generate_revisions(
        conn,
        RevisionFixtureClient(transform),
        {"seed": 42},
        drafts,
        revision_types=(rtype,),
        n_requests=1,
        stats=stats,
        count_tokens=lambda msgs: 600 if len(msgs) == 3 else 1300,
        eval_cases=folder,
    )
    assert not res and stats.reasons == {expected_reason: 1}


def test_revisions_partial_swap_partial_unchanged_and_dirty_draft(inputs):
    conn, folder = inputs
    # 1) 单篇双行为 swap_subject：只换了第 1 个 ### 主体，第 2 个仍与初稿相同 -> 必须拒收
    draft1 = _make_drafts(inputs, modes=(1,))

    def only_swap_first(revised, _rt, _draft):
        # RevisionFixtureClient 把两个 ### 虚构厂 都换成了 ### 明达物流公司，这里把第二个还原
        head, sep, tail = revised.rpartition("### 明达物流公司：")
        assert sep
        return f"{head}### 虚构厂：{tail}"

    stats_partial_swap = ArticleStats()
    res1 = generate_revisions(
        conn,
        RevisionFixtureClient(only_swap_first),
        {"seed": 42},
        draft1,
        revision_types=("swap_subject",),
        n_requests=1,
        stats=stats_partial_swap,
        count_tokens=lambda msgs: 500 if len(msgs) == 3 else 1100,
        eval_cases=folder,
    )
    assert not res1
    assert stats_partial_swap.drops == [{"request": 1, "reason": "actor_unchanged", "article": 1}]

    # 2) 两篇 plainer：仅改第 1 篇、第 2 篇逐字照搬 -> 按篇序报错 article=2
    draft2 = _make_drafts(inputs, modes=(2,))

    def keep_second_verbatim(revised, _rt, draft):
        rev_first = revised.split("\n---\n", 1)[0]
        orig_second = draft.split("\n---\n", 1)[1]
        return f"{rev_first}\n---\n{orig_second}"

    stats_partial_same = ArticleStats()
    res2 = generate_revisions(
        conn,
        RevisionFixtureClient(keep_second_verbatim),
        {"seed": 42},
        draft2,
        revision_types=("plainer",),
        n_requests=1,
        stats=stats_partial_same,
        count_tokens=lambda msgs: 500 if len(msgs) == 3 else 1100,
        eval_cases=folder,
    )
    assert not res2
    assert stats_partial_same.drops == [{"request": 1, "reason": "revision_unchanged", "article": 2}]

    # 3) 损坏初稿（文本篇数与 meta.plan 不一致）在调外部模型前即判 invalid_draft
    dirty = _make_drafts(inputs, modes=(2,))
    dirty[0]["messages"][2]["content"] = "# 仅剩一篇\n## 案例\n无。"
    client_dirty = RevisionFixtureClient()
    stats_dirty = ArticleStats()
    res3 = generate_revisions(
        conn,
        client_dirty,
        {"seed": 42},
        dirty,
        revision_types=("plainer",),
        n_requests=1,
        stats=stats_dirty,
        count_tokens=lambda _: 200,
        eval_cases=folder,
    )
    assert not res3 and stats_dirty.reasons == {"invalid_draft": 1}
    assert not client_dirty.calls

    # 4) swap_subject 改了 ### 标题，但案例正文里残留了初稿主体名 -> actor_residual
    def leave_residual_in_case(revised, _rt, _draft):
        return revised.replace("明达物流公司拖着不办", "虚构厂拖着不办", 1)

    stats_residual = ArticleStats()
    res4 = generate_revisions(
        conn,
        RevisionFixtureClient(leave_residual_in_case),
        {"seed": 42},
        draft1,
        revision_types=("swap_subject",),
        n_requests=1,
        stats=stats_residual,
        count_tokens=lambda msgs: 500 if len(msgs) == 3 else 1100,
        eval_cases=folder,
    )
    assert not res4
    assert stats_residual.drops == [{"request": 1, "reason": "actor_residual", "article": 1}]


def test_revisions_per_turn_eval_overlap_and_truncation(inputs, monkeypatch):
    conn, folder = inputs
    drafts = _make_drafts(inputs, modes=(1,))

    # 仅在第二轮修改问句命中评测集，第一轮完全无关 -> 逐轮去重仍应拦截
    eval_row = {
        "case_id": "art-rev",
        "category": "article",
        "input": {"script": ["写一篇完全不相关的文章。", REVISION_USER_PROMPTS["plainer"][0]]},
    }
    (folder / "cases.jsonl").write_text(json.dumps(eval_row, ensure_ascii=False))
    monkeypatch.setattr(
        "tu_assistant.synth.articles.REVISION_USER_PROMPTS",
        {
            "plainer": (REVISION_USER_PROMPTS["plainer"][0],),
            "swap_subject": REVISION_USER_PROMPTS["swap_subject"],
        },
    )
    stats_dup = ArticleStats()
    res_dup = generate_revisions(
        conn,
        RevisionFixtureClient(),
        {"seed": 42},
        drafts,
        revision_types=("plainer",),
        n_requests=1,
        stats=stats_dup,
        count_tokens=lambda msgs: 500 if len(msgs) == 3 else 1000,
        eval_cases=folder,
    )
    assert not res_dup and stats_dup.reasons == {"eval_overlap": 1}

    # 截断反例
    monkeypatch.setenv("TU_EXTERNAL_LLM_API_KEY", "unit-test")
    llm = ExternalLLM("http://localhost", "fake")
    trunc_resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="半截"), finish_reason="length")],
        usage=None,
    )
    llm._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: trunc_resp))
    )
    stats_trunc = ArticleStats()
    (folder / "cases.jsonl").unlink()
    res_trunc = generate_revisions(
        conn,
        llm,
        {"seed": 42},
        drafts,
        revision_types=("plainer",),
        n_requests=1,
        stats=stats_trunc,
        count_tokens=lambda msgs: 500 if len(msgs) == 3 else 1000,
        eval_cases=folder,
    )
    assert not res_trunc and stats_trunc.reasons == {"llm_truncated": 1}


def test_draft_id_fallback_deterministic():
    d = {"messages": [{"role": "user", "content": "a"}], "meta": {}}
    assert draft_id(d) == draft_id(d)
    assert draft_id(d).startswith("draft-")
    d2 = {"messages": [], "meta": {"sample_id": "custom-1"}}
    assert draft_id(d2) == "custom-1"


def test_revision_user_prompts_do_not_overlap_v1_eval():
    from pathlib import Path

    from tu_assistant.eval.cases import eval_questions, load_cases
    from tu_assistant.train.dataset import dedup_against_eval

    v1 = Path("eval/cases/v1")
    if not v1.exists():
        pytest.skip("eval/cases/v1 不存在")
    questions = eval_questions(load_cases(v1))
    samples = [
        {"messages": [{"role": "user", "content": p}]}
        for prompts in REVISION_USER_PROMPTS.values()
        for p in prompts
    ]
    _, dropped = dedup_against_eval(samples, questions)
    assert not dropped


# ---- T057: 自然问法池、n4、n1_case 与跨请求案例近重复测试 ----


def test_t057_n4_vague_modes_and_prompt_bank_no_eval_overlap(inputs):
    from pathlib import Path

    from tu_assistant.eval.cases import eval_questions, load_cases
    from tu_assistant.train.dataset import dedup_against_eval

    conn, folder = inputs
    stats = ArticleStats()
    samples = generate(
        conn,
        FixtureClient(lambda *_: None),
        {"seed": 42},
        n_requests=2,
        request_modes=("vague", 4),
        count_tokens=lambda _: 400,
        eval_cases=folder,
        stats=stats,
    )
    assert len(samples) == 2
    assert samples[0]["meta"]["kind"] == "n3_vague"
    assert samples[0]["meta"]["n_requested"] == 3
    assert "几篇" in samples[0]["messages"][1]["content"]
    assert samples[1]["meta"]["kind"] == "n4"
    assert samples[1]["meta"]["n_requested"] == 4

    v1 = Path("eval/cases/v1")
    if v1.exists():
        questions = eval_questions(load_cases(v1))
        prompt_samples = [
            {"messages": [{"role": "user", "content": tpl.format(topic="单位漏办手续")}]}
            for group in ARTICLE_USER_PROMPTS.values()
            for tpl in group
        ] + [
            {"messages": [{"role": "user", "content": tpl.format(case_brief="某机械厂一直没给工人办手续")}]}
            for tpl in CASE_USER_PROMPTS
        ]
        _, dropped = dedup_against_eval(prompt_samples, questions)
        assert not dropped


def test_t057_generate_from_case_positive_and_negative(inputs):
    conn, folder = inputs

    class CaseClient:
        def __init__(self, brief: str):
            self.brief = brief

        def chat(self, messages, *, input_source, max_tokens, reject_truncated):
            assert (input_source, max_tokens, reject_truncated) == ("kb_clause", 4096, True)
            mats = json.loads(messages[0]["content"].split("\n行为素材\n", 1)[1])
            lines = ["# 漏办手续的后果", "## 案例", "某机械厂漏办了工人登记手续。", "## 以案说法"]
            for m in mats:
                lines.extend(
                    [
                        "### 某机械厂：漏办手续",
                        "事实清楚，符合条款适用条件。",
                        "**法律依据**",
                        m["依据"],
                        "**法律责任**",
                        m["责任"],
                    ]
                )
            lines.extend(["## 普法提示", "工友可留存凭证向主管部门反映。"])
            return f"用户案情：{self.brief}\n" + "\n".join(lines)

    ok_stats = ArticleStats()
    ok = generate_from_case(
        conn,
        CaseClient("某机械厂一直不给车间工人办登记，大家准备去反映。"),
        {"seed": 42},
        n_requests=1,
        stats=ok_stats,
        count_tokens=lambda _: 500,
        eval_cases=folder,
    )
    assert len(ok) == 1 and ok[0]["meta"]["kind"] == "n1_case"

    for bad_brief in ("违反《演练规则》第一条的情况", "按第1条规定公司没办手续", ""):
        bad_stats = ArticleStats()
        bad = generate_from_case(
            conn,
            CaseClient(bad_brief),
            {"seed": 42},
            n_requests=1,
            stats=bad_stats,
            count_tokens=lambda _: 500,
            eval_cases=folder,
        )
        assert not bad and bad_stats.reasons == {"invalid_case_brief": 1}


def test_t057_find_case_near_duplicates():
    # 1) 换标题、换人名、换单位名但情节高度相似 → 应检出
    a = {
        "messages": [
            {
                "role": "assistant",
                "content": (
                    "# 标题甲\n## 案例\n某快捷酒店前台赵某值班时发现男子用他人身份证为意识不清女子开房，"
                    "经理钱某让只登记不报警。\n## 以案说法\n分析\n## 普法提示\n提示"
                ),
            }
        ],
        "meta": {"type": "article", "sample_id": "d1"},
    }
    b = {
        "messages": [
            {
                "role": "assistant",
                "content": (
                    "# 标题乙\n## 案例\n某商务宾馆前台孙某值班时发现男子用他人身份证为意识不清女子开房，"
                    "经理李某让只登记不报警。\n## 以案说法\n分析\n## 普法提示\n提示"
                ),
            }
        ],
        "meta": {"type": "article", "sample_id": "d2"},
    }
    # 2) 不同情节 → 不误报
    c = {
        "messages": [
            {
                "role": "assistant",
                "content": (
                    "# 标题丙\n## 案例\n某物流公司仓库管理员王某加班三个月未拿到加班费，"
                    "向工会反映后公司仍拖延。\n## 以案说法\n分析\n## 普法提示\n提示"
                ),
            }
        ],
        "meta": {"type": "article", "sample_id": "d3"},
    }
    # 3) plainer 修改稿与其 parent → 自动跳过
    p = {
        "messages": [{"role": "assistant", "content": a["messages"][0]["content"]}],
        "meta": {
            "type": "article",
            "kind": "revise_plainer",
            "parent": "d1",
            "source_batch": "rev",
            "request": 1,
        },
    }
    matches = find_case_near_duplicates([a, b, c, p])
    pairs = {(m["left_id"], m["right_id"]) for m in matches}
    assert ("d1", "d2") in pairs
    assert ("d1", "rev:req1") not in pairs
    assert ("d1", "d3") not in pairs and ("d2", "d3") not in pairs


def test_t057_cli_synth_sft_rejects_orphan_revision_and_drops_old_articles(inputs, tmp_path):
    from typer.testing import CliRunner

    from tu_assistant.cli import app
    from tu_assistant.kb.store import create_kb, insert_clause, insert_document, insert_relation

    # 建临时磁盘 KB + 最小复用数据集 + 孤儿修改稿
    artifacts_dir = tmp_path / "artifacts"
    kb_dir = artifacts_dir / "kb"
    kb_dir.mkdir(parents=True)
    kb_file = kb_dir / "kb-test.sqlite"
    db = create_kb(kb_file)
    insert_document(db, DocumentMeta("演练规则", "示例版", doc_id="demo"))
    insert_clause(db, Clause("demo", 1, 1, None, "第1条", text="应当登记。"))
    insert_clause(db, Clause("demo", 3, 1, None, "第3条", text="登记遗漏责令改正。"))
    insert_relation(db, ClauseRelation("demo:a1:p1", "demo:a3:p1", "liability_for", "manual", True))
    db.commit()
    db.close()

    eval_dir = tmp_path / "eval_cases"
    eval_dir.mkdir()

    reuse_dir = artifacts_dir / "datasets" / "ds-old"
    reuse_dir.mkdir(parents=True)
    old_art_body = (
        "## 案例\n旧文章\n## 以案说法\n分析\n"
        "〔《演练规则》（示例版）第1条〕\n> 应当登记。\n## 普法提示\n提示"
    )
    old_rows = [
        {
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "写文章"},
                {"role": "assistant", "content": old_art_body},
            ]
        },
        {
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "帮我润色一句话"},
                {"role": "assistant", "content": "好的。"},
            ]
        },
        *[
            {
                "messages": [
                    {"role": "system", "content": "sys"},
                    {"role": "user", "content": f"帮我润色第{i}句话"},
                    {"role": "assistant", "content": f"好的第{i}句。"},
                ]
            }
            for i in range(15)
        ],
    ]
    (reuse_dir / "train.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in old_rows), encoding="utf-8"
    )
    (reuse_dir / "valid.jsonl").write_text("", encoding="utf-8")

    orphan_file = tmp_path / "orphan.jsonl"
    orphan_file.write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "system", "content": "sys"},
                    {"role": "user", "content": "改通俗"},
                    {"role": "assistant", "content": old_art_body},
                ],
                "meta": {"type": "article", "parent": "missing-draft"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    res = runner.invoke(
        app,
        [
            "synth",
            "sft",
            "--kb-version",
            "kb-test",
            "--artifacts",
            str(artifacts_dir),
            "--reuse-dataset",
            str(reuse_dir),
            "--reuse-only",
            "--skip-llm",
            "--eval-cases",
            str(eval_dir),
            "--articles-file",
            str(orphan_file),
        ],
    )
    assert res.exit_code != 0
    assert "孤儿修改稿" in res.output

    # 正例路径：传入合法初稿 + 修改稿 + --refresh-relations，旧文章应被剔除，新文章与 manifest 完整落盘
    new_draft_body = (
        "# 新初稿\n## 案例\n全新初稿案情\n## 以案说法\n分析\n"
        "〔《演练规则》（示例版）第1条〕\n> 应当登记。\n## 普法提示\n提示"
    )
    new_rev_body = (
        "# 新修改稿\n## 案例\n全新修改稿案情\n## 以案说法\n通俗分析\n"
        "〔《演练规则》（示例版）第1条〕\n> 应当登记。\n## 普法提示\n通俗提示"
    )
    valid_art_file = tmp_path / "valid_articles.jsonl"
    valid_art_file.write_text(
        "".join(
            json.dumps(r, ensure_ascii=False) + "\n"
            for r in (
                {
                    "messages": [
                        {"role": "system", "content": "sys"},
                        {"role": "user", "content": "写1篇新文章"},
                        {"role": "assistant", "content": new_draft_body},
                    ],
                    "meta": {
                        "type": "article",
                        "kind": "n1",
                        "sample_id": "d-new-1",
                        "doc_id": "demo",
                        "clause_ids": ["demo:a1:p1"],
                    },
                },
                {
                    "messages": [
                        {"role": "system", "content": "sys"},
                        {"role": "user", "content": "写1篇新文章"},
                        {"role": "assistant", "content": new_draft_body + DISCLAIMER},
                        {"role": "user", "content": "改通俗些"},
                        {"role": "assistant", "content": new_rev_body},
                    ],
                    "meta": {
                        "type": "article",
                        "kind": "revise_plainer",
                        "parent": "d-new-1",
                        "doc_id": "demo",
                        "clause_ids": ["demo:a1:p1"],
                    },
                },
            )
        ),
        encoding="utf-8",
    )

    res_ok = runner.invoke(
        app,
        [
            "synth",
            "sft",
            "--kb-version",
            "kb-test",
            "--artifacts",
            str(artifacts_dir),
            "--reuse-dataset",
            str(reuse_dir),
            "--reuse-only",
            "--refresh-relations",
            "--skip-llm",
            "--eval-cases",
            str(eval_dir),
            "--articles-file",
            str(valid_art_file),
        ],
    )
    assert res_ok.exit_code == 0, res_ok.output
    latest_dir = (artifacts_dir / "datasets" / "latest").resolve()
    all_text = (latest_dir / "train.jsonl").read_text(encoding="utf-8") + (
        latest_dir / "valid.jsonl"
    ).read_text(encoding="utf-8")
    assert "旧文章" not in all_text
    assert "全新初稿案情" in all_text and "全新修改稿案情" in all_text
    manifest = json.loads((latest_dir / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["known_issues"]) == 3
    assert manifest["relation_refresh"]["added_new"] == 1
    assert manifest["article_stats"]["total"] == 2
    assert manifest["article_stats"]["family_leakage"] == 0
    assert manifest["config"]["train_oversample"]["article"] == 6
    assert "dedup_eval_questions" in manifest["split_integrity"]
