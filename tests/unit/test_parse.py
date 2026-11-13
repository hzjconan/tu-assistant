"""T012: 条款切分的单元测试（fixtures 为自编文本，不取自 inputs/）。"""

from pathlib import Path

from tu_assistant.kb.parse import parse_clauses
from tu_assistant.kb.readers import read_document

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load(name: str) -> list[str]:
    return read_document(FIXTURES / name)


class TestArticleStyle:
    def setup_method(self):
        self.clauses, self.warnings = parse_clauses(load("law_sample.txt"), "doc1")

    def test_article_count(self):
        articles = {c.article_no for c in self.clauses}
        assert articles == {1, 2, 3, 4, 6, 8, 9}

    def test_missing_article_not_error_but_detectable(self):
        # 第5、7条缺失：由入库校验（T014）检查缺口，切分本身不报错
        present = sorted({c.article_no for c in self.clauses})
        assert 5 not in present and 7 not in present

    def test_paragraph_and_items(self):
        # 第三条：一段含（一）（二）两项 → 引言 + 2 项
        art3 = [c for c in self.clauses if c.article_no == 3]
        intro = [c for c in art3 if c.item_no is None]
        items = [c for c in art3 if c.item_no is not None]
        assert len(intro) == 1 and len(items) == 2
        assert items[0].item_no == 1 and items[1].item_no == 2
        assert intro[0].text.endswith("：")
        assert "二十五人以上" in items[0].text

    def test_multi_paragraph_article(self):
        # 第九条：引言 + （一）（二）项
        art9 = [c for c in self.clauses if c.article_no == 9]
        assert any(c.item_no == 1 for c in art9)
        assert any(c.item_no == 2 for c in art9)

    def test_heading_path(self):
        art4 = next(c for c in self.clauses if c.article_no == 4)
        assert any("第二章" in h for h in art4.heading_path)

    def test_number_text(self):
        c = next(c for c in self.clauses if c.article_no == 1)
        assert c.number_text == "第一条"

    def test_text_verbatim(self):
        c = next(c for c in self.clauses if c.article_no == 4)
        assert c.text == "用人单位不得阻挠职工依法参加和组织工会。"

    def test_clause_id(self):
        c = next(c for c in self.clauses if c.article_no == 3 and c.item_no == 1)
        assert c.clause_id == "doc1:a3:p1:i1"


class TestSectionStyle:
    def test_notice(self):
        clauses, warnings = parse_clauses(load("notice_sample.txt"), "doc2")
        assert not warnings
        sections = {c.article_no for c in clauses}
        assert sections == {1, 2, 3}
        # 第二段有（一）（二）项
        items = [c for c in clauses if c.article_no == 2 and c.item_no is not None]
        assert len(items) == 2

    def test_no_structure(self):
        clauses, warnings = parse_clauses(["随便一段文字", "另一段"], "doc3")
        assert clauses == [] or "no_clause_structure" in warnings

    def test_empty(self):
        clauses, warnings = parse_clauses([], "doc4")
        assert clauses == [] and "empty_document" in warnings


class TestDuplicateDetection:
    def test_duplicate_article_warning(self):
        lines = ["第一条 内容一。", "第一条 内容二。"]
        _, warnings = parse_clauses(lines, "doc5")
        assert any("duplicate_article" in w for w in warnings)

    def test_zhiyi_article(self):
        lines = ["第一条 内容。", "第一条之一 补充内容。"]
        clauses, warnings = parse_clauses(lines, "doc6")
        assert len([c for c in clauses if c.article_no == 1]) == 2
        assert not any("duplicate" in w for w in warnings)
