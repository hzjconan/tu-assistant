"""T054 / T055 / T056 身份信息检查单元测试与入口集成测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tu_assistant.chat.anonymize import (
    CITATION_CONFLICT_NOTICE,
    AnonymizeState,
    anonymize_article_text,
    classify_turn_intent,
    extract_user_entities,
    sanitize_citations,
)
from tu_assistant.chat.assistant import SessionConfig, TrainedAssistant
from tu_assistant.citation.models import Citation
from tu_assistant.citation.verify import verify_output
from tu_assistant.eval.metrics import (
    detect_refusal,
    extract_articles,
    intent_score,
)
from tu_assistant.eval.runner import run_eval
from tu_assistant.kb.models import Clause, ClauseRelation, DocumentMeta
from tu_assistant.kb.store import (
    create_kb,
    doc_id_for,
    insert_clause,
    insert_document,
    insert_relation,
)
from tu_assistant.runtime.client import ChatResponse

REPO_ROOT = Path(__file__).resolve().parents[2]


def _extract_names(text: str) -> list[tuple[str, str]]:
    state = AnonymizeState()
    extract_user_entities(text, state)
    return [(e.name, e.kind) for e in state.entities]


def _make_memory_kb(
    *,
    doc_title: str = "劳动权益示例法",
    version_label: str = "2026",
    clause1_text: str = "用人单位应当依法按时足额支付劳动者工资。",
    clause2_text: str = "违反第一条规定的，由劳动行政部门责令限期支付。",
    with_relation: bool = False,
):
    conn = create_kb(":memory:")
    meta = DocumentMeta(title=doc_title, version_label=version_label)
    meta.doc_id = doc_id_for(meta.title, meta.version_label)
    insert_document(conn, meta)
    d = meta.doc_id
    insert_clause(conn, Clause(d, 1, 1, None, "第一条", text=clause1_text))
    insert_clause(conn, Clause(d, 2, 1, None, "第二条", text=clause2_text))
    if with_relation:
        insert_relation(
            conn,
            ClauseRelation(f"{d}:a1:p1", f"{d}:a2:p1", "liability_for", "rule", True),
        )
    conn.commit()
    return conn


class _SeqClient:
    """按顺序返回固定回复并记录每轮请求 messages 的假客户端。"""

    def __init__(self, replies: list[str]) -> None:
        self._replies = iter(replies)
        self.recorded_messages: list[list[dict]] = []

    def chat(self, messages, temperature=0.7, max_tokens=4096):
        self.recorded_messages.append([dict(m) for m in messages])
        return ChatResponse(content=next(self._replies))


# ---------- 1. 候选实体抽取 ----------


class TestEntityExtraction:
    def test_person_self_intro_and_title_contexts(self):
        assert _extract_names("我叫林川，想问问加班费怎么算。") == [("林川", "person")]
        assert _extract_names("我是青砾建筑公司的工会主席许明哲，反映欠薪问题。") == [
            ("青砾建筑公司", "org"),
            ("许明哲", "person"),
        ]
        assert _extract_names("车间主任韩松安排连续加班不给调休。") == [("韩松", "person")]
        assert _extract_names("姓名：陆远，在松涛机械厂干了三年。") == [
            ("陆远", "person"),
            ("松涛机械厂", "org"),
        ]
        # Round 1 B2 回归：2 字姓名紧跟"说/称/问"及标点、3 字名第 3 字为单字后接词
        assert _extract_names("工会主席周岚说，我们车间被欠薪了。") == [("周岚", "person")]
        assert _extract_names("车间主任韩松说：必须加班。") == [("韩松", "person")]
        assert _extract_names("厂长韩松称，公司没钱。") == [("韩松", "person")]
        assert _extract_names("我叫林川说，公司欠薪。") == [("林川", "person")]
        assert _extract_names("我叫李明正准备维权。") == [("李明正", "person")]

    @pytest.mark.parametrize(
        "phrase",
        [
            "工会主席任期内可以调整岗位吗？",
            "工会主席安排职工代表参加协商合法吗？",
            "工会主席应当履行哪些职责？",
            "工会主席管理工会经费有什么规定？",
            "工会主席向职工反映情况需要审批吗？",
            "工会主席要钱用于活动支出合理吗？",
            "这家门店长白班不给加班费怎么办？",
            "公司把文件汇总监管起来了。",
            "工头常年拖欠农民工工资。",
            "车间主任常年安排加班不给调休。",
        ],
    )
    def test_title_ordinary_phrases_zero_candidates(self, phrase):
        assert _extract_names(phrase) == []

    @pytest.mark.parametrize(
        ("sentence", "expected"),
        [
            ("我在青砾建筑公司做施工。", [("青砾建筑公司", "org")]),
            ("我在松涛机械厂做质检。", [("松涛机械厂", "org")]),
            ("他是盛华实业集团的老员工。", [("盛华实业集团", "org")]),
            ("我是云杉中心医院的护士长沈宁。", [("云杉中心医院", "org"), ("沈宁", "person")]),
            ("我在明德实验学校任教。", [("明德实验学校", "org")]),
            # Round 1 B3 回归：右侧业务语境与左侧字号常用字
            ("青砾建筑公司法定代表人韩松不发工资。", [("青砾建筑公司", "org"), ("韩松", "person")]),
            ("青砾建筑公司制定了霸王条款。", [("青砾建筑公司", "org")]),
            ("青砾建筑公司章程规定加班不给钱。", [("青砾建筑公司", "org")]),
            ("我在松涛机械厂办公室工作。", [("松涛机械厂", "org")]),
            ("我在松涛机械厂内部做质检。", [("松涛机械厂", "org")]),
            ("松涛机械厂规章制度不合理。", [("松涛机械厂", "org")]),
            ("我在明德实验学校制定教学计划。", [("明德实验学校", "org")]),
            ("我在云杉中心医院法定节假日加班。", [("云杉中心医院", "org")]),
            ("我在华为技术有限公司工作。", [("华为技术有限公司", "org")]),
            ("我在协和医院当护士。", [("协和医院", "org")]),
            ("我在仁和医院当医生。", [("仁和医院", "org")]),
            ("我在前进机械厂工作。", [("前进机械厂", "org")]),
            ("我在华能电力集团工作。", [("华能电力集团", "org")]),
            ("我在方正电子公司工作。", [("方正电子公司", "org")]),
            ("我在未来科技有限公司工作。", [("未来科技有限公司", "org")]),
            # Round 2 R2-B1 回归：强锚点之后仍有定语/介词（的/在/叫）时不黏连前缀
            ("我是外地人在启明电子厂做质检，厂里不发加班费。", [("启明电子厂", "org")]),
            ("我在老家的松涛机械厂上班。", [("松涛机械厂", "org")]),
            ("我在上海的华为技术有限公司工作。", [("华为技术有限公司", "org")]),
            ("我是北京的协和医院医生。", [("协和医院", "org")]),
            ("我在一家叫青砾建筑公司上班。", [("青砾建筑公司", "org")]),
            ("我是某市的青砾建筑公司职工。", [("青砾建筑公司", "org")]),
            ("我是干质检的在启明电子厂上班。", [("启明电子厂", "org")]),
            ("我是工会派驻在青砾建筑公司的干部。", [("青砾建筑公司", "org")]),
        ],
    )
    def test_five_org_suffixes_distinct_from_v1(self, sentence, expected):
        assert _extract_names(sentence) == expected

    @pytest.mark.parametrize(
        "sentence",
        [
            "某餐饮公司三个月没发工资。",
            "某厂不给员工签合同怎么办？",
            "建筑公司没有给工人发安全帽。",
            "有限责任公司和股份有限公司有什么区别？",
            "外国公司分支机构和分公司怎么管理？",
            "厂房漏水、厂区停电，厂长不让休息，公司法怎么规定？",
        ],
    )
    def test_generic_fictional_and_morpheme_orgs_filtered(self, sentence):
        assert _extract_names(sentence) == []

    def test_legal_material_stripped_while_preserving_surrounding_identity(self):
        msg = (
            "我叫林川，依据《中华人民共和国公司法》第三条和"
            "〔《云杉医院管理条例》（2025）第一条〕\n"
            "> 任何单位不得侵害职工合法权益。\n"
            "我在青砾建筑公司做质检，公司三个月没发工资。"
        )
        assert _extract_names(msg) == [
            ("林川", "person"),
            ("青砾建筑公司", "org"),
        ]
        msg2 = (
            "我叫陈实，依据《公司法》第三条规定：“青砾建筑公司是企业法人。”"
            "我想问加班费。"
        )
        assert _extract_names(msg2) == [("陈实", "person")]

    def test_official_68_negative_controls_and_009_010(self):
        """正式 60 题 + article-001..008 共 68 题 69 条用户消息零候选；009/010 合计 4 全称。"""
        reviewed = [
            json.loads(line)
            for line in (REPO_ROOT / "eval/cases/v1/reviewed.jsonl").read_text("utf-8").splitlines()
            if line.strip()
        ]
        articles = [
            json.loads(line)
            for line in (REPO_ROOT / "eval/cases/v1/articles.jsonl").read_text("utf-8").splitlines()
            if line.strip()
        ]
        neg_cases = reviewed + [
            c for c in articles if c["case_id"] not in {"article-009", "article-010"}
        ]
        assert len(neg_cases) == 68
        msg_count = 0
        for case in neg_cases:
            state = AnonymizeState()
            msgs = (
                case["input"]["script"]
                if "script" in case["input"]
                else [case["input"]["message"]]
            )
            for m in msgs:
                msg_count += 1
                extract_user_entities(m, state)
            assert state.entities == [], f"{case['case_id']} 误抽: {state.entities}"
        assert msg_count == 69

        for cid, expected_turn1 in (
            ("article-009", [("栖梧样例厂", "org"), ("周岚", "person")]),
            ("article-010", [("陈实", "person"), ("启明电子厂", "org")]),
        ):
            case = next(c for c in articles if c["case_id"] == cid)
            state = AnonymizeState()
            turns = case["input"]["script"]
            extract_user_entities(turns[0], state)
            assert [(e.name, e.kind) for e in state.entities] == expected_turn1
            for extra_msg in turns[1:]:
                before = list(state.entities)
                extract_user_entities(extra_msg, state)
                assert state.entities == before


# ---------- 2. 意图判定与续改状态 ----------


class TestIntentClassification:
    @pytest.mark.parametrize(
        "prompt",
        [
            (
                "写一篇给工厂新职工看的普法短文。虚构案例：签完劳动合同，两份都被车间收走了，"
                "新职工想自己留一份。请用“案例、以案说法、普法提示”三个小节，只讲谁应当持有合同文本。"
                "依据《中华人民共和国劳动合同法》第十六条第二款“劳动合同文本由用人单位和劳动者各执一份”。"
                "不要扩写处罚或赔偿。"
            ),
            (
                "请把以下工会宣传栏素材整理成一篇简短的普法案例，保留“案例、以案说法、普法提示”三个小节。"
                "案例：某企业的技术人员收到一份写着三年的竞业限制协议，签字前想核对期限。"
                "法律依据：〔《中华人民共和国劳动合同法》（2012-12-28）第二十四条第2款〕规定，竞业限制期限不得超过二年。"
                "提示：发现约定三年，可以先指出期限超出上限，请对方核对。文章到这里结束，只使用给定的事实和依据。"
            ),
            (
                "写一篇工会宣传栏短文，分“案例、以案说法、普法提示”三段。虚构案情：某门店招用一名新职工，"
                "办好入职手续后还要扣着他的身份证原件。请只讲这个问题。"
                "依据〔《中华人民共和国劳动合同法》（2012-12-28）第九条〕：用人单位招用劳动者，"
                "不得扣押劳动者的居民身份证和其他证件。结尾提醒职工核对后领回原件。"
            ),
        ],
    )
    def test_t075_rehearsal_prompts_classified_as_article(self, prompt):
        intent, active, should_check = classify_turn_intent(
            prompt,
            "非标准回复正文",
            has_citation=False,
            article_task_active=False,
            current_intent=None,
        )
        assert (intent, active, should_check) == ("article", True, True)
        # 三条彩排提示词均不含真实身份，应零候选
        assert _extract_names(prompt) == []

    @pytest.mark.parametrize(
        "consult_msg",
        [
            "不要写文章，只问这个案例怎么处理",
            "这篇文章引用的条款适用吗",
            "单位不让发普法文章合法吗？",
            "单位不让写普法文章合法吗？",
            "我们单位最近在配合上面修改一个跟职工切身利益直接相关的规章，"
            "我想问下，这种起草或者修改的时候，是不是必须得听取我们工会的意见啊？",
        ],
    )
    def test_consult_counterexamples_clear_article_task(self, consult_msg):
        intent, active, should_check = classify_turn_intent(
            consult_msg,
            "单说一个案例：应当依法处理。",
            has_citation=False,
            article_task_active=True,
            current_intent="article",
        )
        assert (intent, active, should_check) == ("consult", False, False)

    @pytest.mark.parametrize("revise_msg", ["再通俗一点", "换一个违法主体", "换个违法主体"])
    def test_elliptical_revision_continues_article_task(self, revise_msg):
        intent, active, should_check = classify_turn_intent(
            revise_msg,
            "无标题改稿正文。",
            has_citation=False,
            article_task_active=True,
            current_intent="article",
        )
        assert (intent, active, should_check) == ("article", True, True)

    def test_single_case_word_not_article_and_intent_score_compatible(self):
        # 模糊开场 → 追问（保持 None）→ 整理成一篇普法案例 → article → intent_score == 1.0
        i1, a1, c1 = classify_turn_intent(
            "我想问个事",
            "请问您想咨询哪方面问题？\n1. 工资问题？",
            has_citation=False,
            article_task_active=False,
            current_intent=None,
        )
        assert (i1, a1, c1) == (None, False, False)
        i2, a2, c2 = classify_turn_intent(
            "请把宣传栏素材整理成一篇普法案例",
            "案例：拖欠工资……",
            has_citation=False,
            article_task_active=a1,
            current_intent=i1,
        )
        assert (i2, a2, c2) == ("article", True, True)
        assert intent_score([{"intent": i1}, {"intent": i2}], {"intent": "article"}) == 1.0

        # 咨询场景的 intent_score，含满 3 轮与超 3 轮断言
        ci1, ca1, _ = classify_turn_intent(
            "不要写文章，只问这个案例怎么处理",
            "案例说明如下。",
            has_citation=False,
            article_task_active=True,
            current_intent="article",
        )
        assert ci1 == "consult" and ca1 is False
        assert intent_score([{"intent": ci1}], {"intent": "consult"}) == 1.0
        assert (
            intent_score(
                [{"intent": None}, {"intent": None}, {"intent": "article"}],
                {"intent": "article"},
            )
            == 1.0
        )
        assert (
            intent_score(
                [
                    {"intent": None},
                    {"intent": None},
                    {"intent": None},
                    {"intent": "article"},
                ],
                {"intent": "article"},
            )
            == 0.0
        )

    def test_untitled_draft_then_elliptical_revision_then_consult(self):
        conn = _make_memory_kb()
        client = _SeqClient(
            [
                "没有标题的初稿：职工林川在青砾建筑公司被欠薪。",
                "更通俗的版本：职工林川还是在青砾建筑公司干活被欠薪。",
                "咨询回答：林川可以向青砾建筑公司主张欠薪。",
            ]
        )
        assistant = TrainedAssistant(client, conn, temperature=0.0)
        sid = assistant.new_session(SessionConfig())

        r1 = assistant.send(sid, "我叫林川，在青砾建筑公司上班。请帮我写一篇普法短文。")
        assert r1.intent == "article"
        assert "林川" not in r1.content and "青砾建筑公司" not in r1.content
        assert "职工甲某" in r1.content and "甲单位" in r1.content

        r2 = assistant.send(sid, "再通俗一点")
        assert r2.intent == "article"
        assert "林川" not in r2.content and "青砾建筑公司" not in r2.content
        assert "职工甲某" in r2.content and "甲单位" in r2.content

        r3 = assistant.send(sid, "不要写文章，只问这个案例怎么处理")
        assert r3.intent == "consult"
        # 切回咨询后不替换咨询回复中的用户称呼
        assert "林川" in r3.content and "青砾建筑公司" in r3.content
        conn.close()


# ---------- 3. 代称分配与替换规则 ----------


class TestAliasAllocationAndReplacement:
    def test_multi_entities_cross_turn_collision_pool_exhaustion_and_idempotency(self):
        state = AnonymizeState()
        extract_user_entities("我叫林川，同事厂长韩松，在青砾建筑公司和松涛机械厂干过。", state)

        # 当前稿中已有角色“甲某”和“甲单位”，首次分配应避开
        draft = "案例：甲某和职工林川、韩松在甲单位、青砾建筑公司、松涛机械厂发生纠纷，老张和小王围观。"
        res1 = anonymize_article_text(draft, state)
        assert not res1.blocked
        assert res1.person_replacements == 2 and res1.org_replacements == 2
        assert state.aliases["林川"] == "乙某"
        assert state.aliases["韩松"] == "丙某"
        assert state.aliases["青砾建筑公司"] == "乙单位"
        assert state.aliases["松涛机械厂"] == "丙单位"
        assert "职工乙某" in res1.text
        assert "老张" in res1.text and "小王" in res1.text

        # 幂等性：再次处理结果逐字不变
        res_idem = anonymize_article_text(res1.text, state)
        assert res_idem.text == res1.text
        assert res_idem.person_replacements == 0 and res_idem.org_replacements == 0

        # 后续稿同时出现“旧代称 + 原名”继续复用旧代称
        draft2 = "改稿：乙某（即林川）在乙单位（青砾建筑公司）维权。"
        res2 = anonymize_article_text(draft2, state)
        assert res2.text == "改稿：乙某（即乙某）在乙单位（乙单位）维权。"

    def test_pool_exhaustion_continues_with_numbered_aliases(self):
        state = AnonymizeState()
        surnames = ["王", "李", "张", "刘", "陈", "杨", "黄", "赵", "周", "吴", "徐", "孙"]
        names = [f"{s}远" for s in surnames]
        for n in names:
            state.register(n, "person")
        text = "、".join(names)
        res = anonymize_article_text(text, state)
        assert res.person_replacements == 12
        assert state.aliases[names[0]] == "甲某"
        assert state.aliases[names[9]] == "癸某"
        assert state.aliases[names[10]] == "人员1"
        assert state.aliases[names[11]] == "人员2"

        # 单位池耗尽同样按类别加序号继续
        org_state = AnonymizeState()
        orgs = [f"示例第{i}电子厂" for i in range(1, 13)]
        for o in orgs:
            org_state.register(o, "org")
        org_res = anonymize_article_text("、".join(orgs), org_state)
        assert org_res.org_replacements == 12
        assert org_state.aliases[orgs[0]] == "甲单位"
        assert org_state.aliases[orgs[9]] == "癸单位"
        assert org_state.aliases[orgs[10]] == "单位1"
        assert org_state.aliases[orgs[11]] == "单位2"

    def test_later_disclosure_reclaims_old_alias_while_normal_reference_reuses(self):
        state = AnonymizeState()
        extract_user_entities("我叫林川，在青砾建筑公司上班。", state)
        r1 = anonymize_article_text("林川在青砾建筑公司讨薪。", state)
        assert r1.text == "甲某在甲单位讨薪。"

        # 仅引用上一轮虚构角色 → 继续复用
        extract_user_entities("把甲某改成工地工人，甲单位换成餐饮店。", state)
        assert state.aliases["林川"] == "甲某"
        assert state.aliases["青砾建筑公司"] == "甲单位"

        # 后披露身份明确占用旧代称 → 解除旧映射并保护新披露身份
        extract_user_entities("其实另一个同事本人叫甲某。", state)
        assert "甲某" in state.known_names()
        assert "林川" not in state.aliases
        r2 = anonymize_article_text("林川和甲某在青砾建筑公司一起讨薪。", state)
        assert "林川" not in r2.text and "甲某" not in r2.text
        assert state.aliases["林川"] != state.aliases["甲某"]
        assert state.aliases["青砾建筑公司"] == "甲单位"

    def test_overlapping_names_longest_first_single_pass(self):
        state = AnonymizeState()
        state.register("青砾", "org")
        state.register("青砾建筑公司", "org")
        res = anonymize_article_text("青砾建筑公司和青砾都欠薪。", state)
        assert res.org_replacements == 2
        assert "青砾" not in res.text
        assert state.aliases["青砾建筑公司"] in res.text
        assert state.aliases["青砾"] in res.text


# ---------- 4. 核准法条区间与引文冲突 ----------


class TestCitationProtectedSpansAndConflict:
    def test_inline_trailing_text_after_inserted_quote_anonymized_while_kb_verbatim(self):
        """缺引文插入后正文粘连在同一 > 行末尾：KB 原文逐字保留，行末解释已替换。"""
        conn = _make_memory_kb(clause1_text="用人单位应当依法按时足额支付劳动者工资。")
        client = _SeqClient(
            [
                "# 欠薪警示\n\n## 案例\n职工林川在青砾建筑公司被欠薪。\n\n"
                "## 以案说法\n〔《劳动权益示例法》（2026）第一条〕林川所在的青砾建筑公司明显违法。\n\n"
                "## 普法提示\n及时维权。"
            ]
        )
        assistant = TrainedAssistant(client, conn, temperature=0.0)
        sid = assistant.new_session(SessionConfig())
        reply = assistant.send(sid, "我叫林川，在青砾建筑公司上班。请写一篇普法文章。")
        assert not assistant._last_turn_anonymize_info(sid)["blocked"]
        assert "> 用人单位应当依法按时足额支付劳动者工资。" in reply.content
        assert "林川" not in reply.content and "青砾建筑公司" not in reply.content
        assert "甲某所在的甲单位明显违法。" in reply.content
        conn.close()

    def test_repeated_kb_sentence_in_body_and_system_related_clause_protected(self):
        """同一句 KB 原文在正文重现 + 多标记同一行 + 系统补条前正文变长。"""
        conn = _make_memory_kb(
            clause1_text="用人单位应当依法支付工资。",
            clause2_text="违反第一条的依法处罚。",
            with_relation=True,
        )
        raw = (
            "# 普法短文\n\n## 案例\n林川在青砾建筑公司被欠薪，用人单位应当依法支付工资。\n\n"
            "## 以案说法\n"
            "〔《劳动权益示例法》（2025）第一条〕〔《劳动权益示例法》（2026）第一条〕\n"
            "> 错误的引文内容，提到林川。\n\n"
            "## 普法提示\n林川应保留证据。"
        )
        # 先验证 verify_output 保留原稿 Citation.span/quote_span 坐标且生成精确 protected_spans
        vr = verify_output(raw, conn)
        assert len(vr.protected_spans) >= 4
        m0_s, m0_e = vr.citations[0].span
        assert raw[m0_s:m0_e] == "〔《劳动权益示例法》（2025）第一条〕"
        for s, e in vr.protected_spans:
            seg = vr.text[s:e]
            assert seg.startswith(("〔《", "> "))

        client = _SeqClient([raw])
        assistant = TrainedAssistant(client, conn, temperature=0.0)
        sid = assistant.new_session(SessionConfig())
        reply = assistant.send(sid, "我叫林川，在青砾建筑公司上班。写一篇普法文章。")
        assert "林川" not in reply.content and "青砾建筑公司" not in reply.content
        assert "**相关条款（系统补充）**" in reply.content
        assert "> 违反第一条的依法处罚。" in reply.content
        # Reply.citations 中被修正前的原始 quoted_text 也不得泄露原名
        for c in reply.citations:
            assert "林川" not in (c.raw or "")
            assert "林川" not in (c.quoted_text or "")
        conn.close()

    @pytest.mark.parametrize("conflict_where", ["marker_title", "kb_quote", "related_clause"])
    def test_conflict_in_verified_citation_blocks_delivery(self, conflict_where):
        if conflict_where == "marker_title":
            conn = _make_memory_kb(doc_title="青砾建筑公司章程条例", with_relation=False)
            raw = (
                "# 标题\n\n## 案例\n欠薪。\n\n## 以案说法\n"
                "〔《青砾建筑公司章程条例》（2026）第一条〕\n\n## 普法提示\n维权。"
            )
        elif conflict_where == "kb_quote":
            conn = _make_memory_kb(
                clause1_text="青砾建筑公司应当依法支付工资。", with_relation=False
            )
            raw = (
                "# 标题\n\n## 案例\n欠薪。\n\n## 以案说法\n"
                "〔《劳动权益示例法》（2026）第一条〕\n\n## 普法提示\n维权。"
            )
        else:
            conn = _make_memory_kb(
                clause1_text="用人单位应当支付工资。",
                clause2_text="青砾建筑公司违反第一条应受处罚。",
                with_relation=True,
            )
            raw = (
                "# 标题\n\n## 案例\n欠薪。\n\n## 以案说法\n"
                "〔《劳动权益示例法》（2026）第一条〕\n\n## 普法提示\n维权。"
            )

        client = _SeqClient([raw])
        assistant = TrainedAssistant(client, conn, temperature=0.0)
        sid = assistant.new_session(SessionConfig())
        reply = assistant.send(sid, "我在青砾建筑公司上班，请写一篇普法文章。")
        info = assistant._last_turn_anonymize_info(sid)

        assert info["blocked"] is True
        assert reply.content == CITATION_CONFLICT_NOTICE
        assert "青砾建筑公司" not in reply.content
        assert "以上内容仅供参考" not in reply.content
        assert "〔《" not in reply.content
        assert reply.citations == []
        assert reply.question_count == 0
        assert extract_articles(reply.content) == []
        assert detect_refusal(reply.content)["refused"] is False
        conn.close()

    def test_unverified_quote_and_not_found_citations_can_be_anonymized(self):
        """普通引用、not_found、incomplete 与裸引用不享有核准豁免，保护名可正常替换。"""
        conn = _make_memory_kb()
        raw = (
            "# 普法案例\n\n## 案例\n> 职工林川在青砾建筑公司说：“已经欠薪三个月。”\n\n"
            "## 以案说法\n依据第一条，〔《青砾建筑公司内部办法》（2026）第九条〕\n"
            "> 林川应当拿到工资。\n\n## 普法提示\n及时投诉。"
        )
        client = _SeqClient([raw])
        assistant = TrainedAssistant(client, conn, temperature=0.0)
        sid = assistant.new_session(SessionConfig())
        reply = assistant.send(sid, "我叫林川，在青砾建筑公司上班。写一篇普法文章。")
        assert not assistant._last_turn_anonymize_info(sid)["blocked"]
        assert "林川" not in reply.content and "青砾建筑公司" not in reply.content
        assert "〔此处引用未通过校验，已删除〕" in reply.content
        for c in reply.citations:
            for field_val in (c.raw, c.title, c.version_label, c.quoted_text):
                assert "林川" not in (field_val or "")
                assert "青砾建筑公司" not in (field_val or "")
        conn.close()


# ---------- 5. 入口、导出、会话隔离与评测报告 ----------


class TestEntryExportIsolationAndEvalReport:
    def test_assistant_history_export_and_session_isolation(self):
        conn = _make_memory_kb()
        client = _SeqClient(
            [
                "# 初稿\n\n## 案例\n林川在青砾建筑公司被欠薪。\n\n"
                "## 以案说法\n违法。\n\n## 普法提示\n投诉。",
                "# 改稿\n\n## 案例\n林川在青砾建筑公司再次讨薪。\n\n"
                "## 以案说法\n违法。\n\n## 普法提示\n投诉。",
                "# 新会话稿\n\n## 案例\n林川在青砾建筑公司被欠薪。\n\n"
                "## 以案说法\n违法。\n\n## 普法提示\n投诉。",
            ]
        )
        assistant = TrainedAssistant(client, conn, temperature=0.0)
        sid1 = assistant.new_session(SessionConfig())
        r1 = assistant.send(sid1, "我叫林川，在青砾建筑公司上班，写一篇普法文章。")
        r2 = assistant.send(sid1, "再通俗一点")

        # 下一轮发给模型的助手历史已脱敏且与 Reply.content / export_markdown 同源
        sent_history = client.recorded_messages[1]
        assistant_hist = [m["content"] for m in sent_history if m["role"] == "assistant"]
        assert assistant_hist == [r1.content]
        assert assistant.export_markdown(sid1, 0) == r1.content
        assert assistant.export_markdown(sid1, 1) == r2.content
        assert "林川" not in r1.content and "林川" not in r2.content

        # 普通模式 raw_content 应为空，且 Session.user_entities 保持兼容语义
        assert r1.raw_content is None and r2.raw_content is None
        assert assistant._sessions[sid1].user_entities == {"林川", "青砾建筑公司"}

        assistant.close(sid1)
        sid2 = assistant.new_session(SessionConfig())
        # 新会话不携带旧会话的实体映射
        r3 = assistant.send(sid2, "写一篇普法文章。")
        assert "林川" in r3.content and "青砾建筑公司" in r3.content
        conn.close()

    def test_multiline_ok_quote_protected_and_incomplete_ambiguous_allowed(self):
        """verdict=ok 的多行 > 引文受保护；多款歧义 incomplete 标记及引语允许替换。"""
        conn = create_kb(":memory:")
        meta = DocumentMeta(title="多款示例法", version_label="2026")
        meta.doc_id = doc_id_for(meta.title, meta.version_label)
        insert_document(conn, meta)
        d = meta.doc_id
        insert_clause(
            conn,
            Clause(d, 1, 1, None, "第一条第1款", text="第一行原文\n第二行含青砾建筑公司。"),
        )
        insert_clause(
            conn,
            Clause(d, 2, 1, None, "第二条第1款", text="第二条第一款原文。"),
        )
        insert_clause(
            conn,
            Clause(d, 2, 2, None, "第二条第2款", text="第二条第二款原文。"),
        )
        conn.commit()

        # 1. ok 多行引文含保护名 → 触发暂缓交稿
        raw_ok_multi = (
            "# 标题\n\n## 案例\n欠薪。\n\n## 以案说法\n"
            "〔《多款示例法》（2026）第一条第1款〕\n"
            "> 第一行原文\n> 第二行含青砾建筑公司。\n\n## 普法提示\n维权。"
        )
        vr = verify_output(raw_ok_multi, conn)
        assert vr.citations[0].verdict == "ok"
        assert len(vr.protected_spans) == 2
        c1 = _SeqClient([raw_ok_multi])
        a1 = TrainedAssistant(c1, conn, temperature=0.0)
        s1 = a1.new_session(SessionConfig())
        r1 = a1.send(s1, "我在青砾建筑公司上班，写一篇普法文章。")
        assert a1._last_turn_anonymize_info(s1)["blocked"] is True
        assert r1.content == CITATION_CONFLICT_NOTICE

        # 2. 多款歧义 incomplete 标记及引语含保护名 → 允许替换，不触发暂缓
        raw_incomplete = (
            "# 标题\n\n## 案例\n青砾建筑公司欠薪。\n\n## 以案说法\n"
            "〔《多款示例法》（2026）第二条〕\n"
            "> 青砾建筑公司应当按时发工资。\n\n## 普法提示\n维权。"
        )
        vr2 = verify_output(raw_incomplete, conn)
        assert vr2.citations[0].verdict == "incomplete"
        assert vr2.protected_spans == []
        c2 = _SeqClient([raw_incomplete])
        a2 = TrainedAssistant(c2, conn, temperature=0.0)
        s2 = a2.new_session(SessionConfig())
        r2 = a2.send(s2, "我在青砾建筑公司上班，写一篇普法文章。")
        assert a2._last_turn_anonymize_info(s2)["blocked"] is False
        assert "青砾建筑公司" not in r2.content
        assert "甲单位" in r2.content
        conn.close()

    def test_sanitize_citations_avoids_draft_alias_collision(self):
        """正文含虚构角色甲某、实体仅在 Citation 元数据出现时，分配代称避开甲某。"""
        state = AnonymizeState()
        state.register("林川", "person")
        cits = [
            Citation(
                raw="〔《A法》（2026）第一条〕",
                title="A法",
                version_label="2026",
                quoted_text="错误引文含林川",
                verdict="corrected",
                article_no=1,
                resolved_clause_id="d:a1:p1",
            )
        ]
        cleaned = sanitize_citations(cits, state, draft_text="正文已有虚构角色甲某。")
        assert state.aliases["林川"] == "乙某"
        assert cleaned[0].quoted_text == "错误引文含乙某"

    def test_sanitize_citations_all_four_verdicts(self):
        state = AnonymizeState()
        state.register("林川", "person")
        state.register("青砾建筑公司", "org")
        cits = [
            Citation(
                raw="〔《青砾建筑公司法》（2026）第一条〕",
                title="青砾建筑公司法",
                version_label="林川版",
                quoted_text="林川原文",
                verdict="ok",
                article_no=1,
                resolved_clause_id="d:a1:p1",
            ),
            Citation(
                raw="〔《A法》（2026）第一条〕",
                title="A法",
                version_label="2026",
                quoted_text="错误引文含林川",
                verdict="corrected",
                article_no=1,
                resolved_clause_id="d:a1:p1",
            ),
            Citation(
                raw="〔《青砾建筑公司规定》（2026）第九条〕",
                title="青砾建筑公司规定",
                version_label="2026",
                quoted_text="含林川",
                verdict="not_found",
                article_no=9,
            ),
            Citation(
                raw="林川第一条",
                title="",
                version_label="",
                quoted_text=None,
                verdict="incomplete",
                article_no=1,
            ),
        ]
        cleaned = sanitize_citations(cits, state)
        assert len(cleaned) == 4
        for orig, san in zip(cits, cleaned, strict=True):
            assert san.verdict == orig.verdict
            assert san.article_no == orig.article_no
            assert san.resolved_clause_id == orig.resolved_clause_id
            for val in (san.raw, san.title, san.version_label, san.quoted_text):
                assert "林川" not in (val or "")
                assert "青砾建筑公司" not in (val or "")

    def test_run_eval_reports_citation_conflict_blocked_turn(self, tmp_path, monkeypatch):
        kb_path = tmp_path / "kb" / "kb-conflict.sqlite"
        kb_path.parent.mkdir(parents=True, exist_ok=True)
        conn = create_kb(kb_path)
        meta = DocumentMeta(title="劳动权益示例法", version_label="2026")
        meta.doc_id = doc_id_for(meta.title, meta.version_label)
        insert_document(conn, meta)
        insert_clause(
            conn,
            Clause(meta.doc_id, 1, 1, None, "第一条", text="青砾建筑公司应当依法支付工资。"),
        )
        conn.commit()
        conn.close()

        case = {
            "case_id": "article-conflict-1",
            "category": "article",
            "input": {"message": "我在青砾建筑公司上班，请写一篇普法文章。"},
            "gold": {
                "expect_articles": [1],
                "protected_names": [{"name": "青砾建筑公司", "turn": 1}],
            },
            "source": "manual",
        }
        cases_path = tmp_path / "cases.jsonl"
        cases_path.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")

        class _FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                body = (
                    "# 标题\n\n## 案例\n欠薪。\n\n## 以案说法\n"
                    "〔《劳动权益示例法》（2026）第一条〕\n\n## 普法提示\n维权。"
                )
                return {"choices": [{"message": {"content": body}}], "usage": {}}

        class _FakeClient:
            def __init__(self, timeout=None):
                pass

            def post(self, url, json=None):
                return _FakeResp()

        monkeypatch.setattr("httpx.Client", _FakeClient)
        out = run_eval(
            cases_path=cases_path,
            kb_path=kb_path,
            endpoint="http://127.0.0.1:8080/v1",
            allowed_hosts=["127.0.0.1"],
            artifacts_dir=tmp_path / "artifacts",
            exp_id="exp-conflict",
        )
        results = [
            json.loads(line)
            for line in (Path(out["dir"]) / "results.jsonl").read_text("utf-8").splitlines()
        ]
        r0 = results[0]
        assert r0["turns"][0]["anonymize"]["blocked"] is True
        assert r0["scores"]["identity_check"]["total"] == 0
        assert r0["scores"]["identity_check"]["passed"] == 0
        assert r0["scores"]["refusal_evidence"]["refused"] is False
        report = (Path(out["dir"]) / "report.md").read_text("utf-8")
        assert "引用冲突暂缓交稿" in report
        assert "article-conflict-1 第1轮" in report
