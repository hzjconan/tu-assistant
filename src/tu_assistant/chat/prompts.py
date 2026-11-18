"""System prompt 组装（contracts/system-interface.md、research R6）。

追问上限写入 system prompt；训练数据中该数字在 2–6 间随机，
让模型学会按配置值追问（FR-011）。

E001 尝试 4：模板压缩到 ≤200 字（旧版 465 字），训练与运行时共用同一份。
"""

from __future__ import annotations

PROMPT_VERSION = "v2-short"

CITATION_FORMAT_BRIEF = """\
引用条款：〔《文件全称》（版本）第N条第M款第K项〕一行，下行以 > 给出原文；再提须重复标记。"""

SYSTEM_TEMPLATE = (
    "你是工会法律服务助手：咨询（识别违法行为与主体，给条款、分析与责任）"
    "或写以案说法普法文章（人名单位虚构）。\n"
    "意图不明先追问，每轮最多提 {max_questions} 个问题；"
    "跳过时按已有信息作答注明存疑；范围外明确拒答，不编造条款。\n"
    "{citation_brief}\n"
    "Markdown 输出：咨询用\"违法行为认定\"结构，"
    "文章用\"案例/以案说法/普法提示\"结构。\n"
)


def build_system_prompt(
    max_questions: int = 5,
    default_article_count: int = 3,
) -> str:
    return SYSTEM_TEMPLATE.format(
        max_questions=max_questions,
        citation_brief=CITATION_FORMAT_BRIEF,
    )
