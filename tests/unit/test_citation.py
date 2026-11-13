"""T022: 出处校验的单元测试（基于内存知识库与自编条款）。"""

import pytest

from tu_assistant.citation.parse import parse_citations
from tu_assistant.citation.verify import NOT_FOUND_PLACEHOLDER, verify_output
from tu_assistant.kb.models import Clause, DocumentMeta
from tu_assistant.kb.store import create_kb, doc_id_for, insert_clause, insert_document

TITLE = "示例工会法"
VERSION = "2020"


@pytest.fixture()
def conn():
    c = create_kb(":memory:")
    meta = DocumentMeta(title=TITLE, version_label=VERSION)
    meta.doc_id = doc_id_for(TITLE, VERSION)
    insert_document(c, meta)
    clauses = [
        Clause(meta.doc_id, 4, 1, None, "第四条",
               text="用人单位不得阻挠职工依法参加和组织工会。"),
        Clause(meta.doc_id, 8, 1, None, "第八条",
               text="违反本法第四条规定的，由劳动行政部门责令其改正。"),
        Clause(meta.doc_id, 3, 1, None, "第三条",
               text="企业应当依法建立工会组织："),
        Clause(meta.doc_id, 3, 1, 1, "第三条第一项",
               text="（一）职工二十五人以上的，应当建立基层工会委员会；"),
        Clause(meta.doc_id, 3, 1, 2, "第三条第二项",
               text="（二）不足二十五人的，可以单独建立。"),
    ]
    for cl in clauses:
        insert_clause(c, cl)
    c.commit()
    return c


def mark(article: str, para: str | None = None, version: str = VERSION) -> str:
    s = f"〔《{TITLE}》（{version}）第{article}条"
    if para:
        s += f"第{para}款"
    return s + "〕"


class TestParse:
    def test_marker_and_quote(self):
        text = f"分析如下：\n{mark('四')}\n> 用人单位不得阻挠职工依法参加和组织工会。\n"
        cs = parse_citations(text)
        assert len(cs) == 1
        c = cs[0]
        assert c.article_no == 4 and c.title == TITLE and c.version_label == VERSION
        assert c.quoted_text == "用人单位不得阻挠职工依法参加和组织工会。"

    def test_arabic_numbers(self):
        cs = parse_citations(f"{mark('4')}\n")
        assert cs[0].article_no == 4

    def test_bare_reference(self):
        text = "根据第四条的规定，用人单位不得阻挠。"
        cs = parse_citations(text)
        assert len(cs) == 1 and cs[0].verdict == "incomplete"

    def test_marker_without_version(self):
        cs = parse_citations(f"〔《{TITLE}》第四条〕\n")
        assert cs[0].version_label == "" and cs[0].article_no == 4


class TestVerify:
    def test_ok(self, conn):
        text = f"{mark('四')}\n> 用人单位不得阻挠职工依法参加和组织工会。"
        r = verify_output(text, conn)
        assert r.citations[0].verdict == "ok"
        assert "阻挠" in r.text

    def test_corrected(self, conn):
        text = f"{mark('四')}\n> 用人单位可以阻挠职工参加工会。"
        r = verify_output(text, conn)
        assert r.citations[0].verdict == "corrected"
        assert "不得阻挠职工依法参加和组织工会。" in r.text
        assert "可以阻挠" not in r.text

    def test_not_found(self, conn):
        text = f"{mark('九十九')}\n> 任意原文。"
        r = verify_output(text, conn)
        assert r.citations[0].verdict == "not_found"
        assert NOT_FOUND_PLACEHOLDER in r.text
        assert "任意原文" not in r.text

    def test_autofill_quote(self, conn):
        text = f"依据{mark('四')}，单位做法违法。"
        r = verify_output(text, conn)
        assert r.citations[0].verdict == "ok"
        assert "> 用人单位不得阻挠职工依法参加和组织工会。" in r.text

    def test_bare_kept_but_incomplete(self, conn):
        text = "依据第四条处理。"
        r = verify_output(text, conn)
        assert r.citations[0].verdict == "incomplete"
        assert r.text == text

    def test_wrong_version_fixed(self, conn):
        text = f"{mark('四', version='1999')}\n> 用人单位不得阻挠职工依法参加和组织工会。"
        r = verify_output(text, conn)
        assert r.citations[0].verdict == "corrected"
        assert f"（{VERSION}）" in r.text

    def test_para_with_items(self, conn):
        # 引用第三条第一款：该款含两项，原文 = 引言 + 各项
        text = f"{mark('三', para='一')}\n"
        r = verify_output(text, conn)
        assert r.citations[0].verdict == "ok"
        assert "（一）" in r.text and "（二）" in r.text

    def test_item_precise(self, conn):
        m = f"〔《{TITLE}》（{VERSION}）第三条第一款第一项〕"
        text = f"{m}\n> （一）职工二十五人以上的，应当建立基层工会委员会；"
        r = verify_output(text, conn)
        assert r.citations[0].verdict == "ok"

    def test_multi_para_article_only_incomplete(self, conn):
        # 第三条有引言+两项 → 只写"第三条"无法唯一定位
        r = verify_output(f"{mark('三')}\n", conn)
        assert r.citations[0].verdict == "incomplete"
