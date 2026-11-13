"""T008: 中文数字转换的单元测试。"""

from tu_assistant.kb.numbers import chinese_to_int, parse_clause_number


class TestChineseToInt:
    def test_digits(self):
        assert chinese_to_int("一") == 1
        assert chinese_to_int("九") == 9
        assert chinese_to_int("零") == 0

    def test_ten_boundaries(self):
        assert chinese_to_int("十") == 10
        assert chinese_to_int("十一") == 11
        assert chinese_to_int("十九") == 19
        assert chinese_to_int("二十") == 20
        assert chinese_to_int("二十一") == 21
        assert chinese_to_int("九十九") == 99

    def test_hundreds(self):
        assert chinese_to_int("一百") == 100
        assert chinese_to_int("一百零一") == 101
        assert chinese_to_int("一百一十") == 110
        assert chinese_to_int("一百一十一") == 111
        assert chinese_to_int("一百二十三") == 123
        assert chinese_to_int("二百五十") == 250

    def test_thousands(self):
        assert chinese_to_int("一千") == 1000
        assert chinese_to_int("一千零一") == 1001
        assert chinese_to_int("二千三百四十五") == 2345

    def test_arabic_and_mixed(self):
        assert chinese_to_int("51") == 51
        assert chinese_to_int("7") == 7

    def test_invalid(self):
        assert chinese_to_int("") is None
        assert chinese_to_int("abc") is None
        assert chinese_to_int("五十一abc") is None
        assert chinese_to_int("万") is None


class TestParseClauseNumber:
    def test_wrapped(self):
        assert parse_clause_number("第五十一条") == 51
        assert parse_clause_number("第51条") == 51
        assert parse_clause_number("（三）") == 3
        assert parse_clause_number("(十)") == 10
        assert parse_clause_number("第一款") == 1
        assert parse_clause_number("第（二）项") == 2

    def test_whitespace(self):
        assert parse_clause_number("  第五十一条  ") == 51

    def test_invalid(self):
        assert parse_clause_number("章节") is None
        assert parse_clause_number("第一条之二") is None
