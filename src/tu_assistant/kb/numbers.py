"""中文数字与编号转换。

支持法律文本中的编号写法："第五十一条" → 51、"（三）" → 3、阿拉伯数字原样解析。
只处理 0–9999（法律条号不会超出）。解析失败返回 None，不抛异常。
"""

from __future__ import annotations

_DIGITS = {
    "零": 0, "〇": 0, "○": 0,
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9,
}
_UNITS = {"十": 10, "百": 100, "千": 1000}


def chinese_to_int(text: str) -> int | None:
    """把中文数字串转成整数，如 "五十一"→51、"一百一十"→110、"十"→10。"""
    text = text.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total = 0
    num = 0
    seen = False
    for ch in text:
        if ch in _DIGITS:
            num = _DIGITS[ch]
            seen = True
        elif ch in _UNITS:
            unit = _UNITS[ch]
            total += (num or 1) * unit  # "十" 开头的 "十五" = 1*10+5
            num = 0
            seen = True
        else:
            return None
    if not seen:
        return None
    result = total + num
    return result if 0 <= result <= 9999 else None


def parse_clause_number(text: str) -> int | None:
    """解析条款编号："第五十一条" / "51" / "（三）" → 整数。

    去掉首尾常见的包装字符（第、条、款、项、括号、空白）后再解析，
    但要求去掉后整个剩余串是合法数字，防止误解析。
    """
    t = text.strip()
    for ch in "第条款项()（）【】[] 　":
        t = t.replace(ch, "")
    return chinese_to_int(t)


def normalize_number_text(text: str) -> str:
    """保留原始编号写法（如"第五十一条第一款"），仅去除空白。"""
    return "".join(text.split())
