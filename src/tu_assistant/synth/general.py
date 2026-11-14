"""通用对话样本（T044，research R3）。

少量混入非法律任务，防止 SFT 后模型的基本指令跟随能力退化。
这些样本不需要引用条款，也不进知识库；外部模型只负责批量扩写表达。
"""

from __future__ import annotations

import json
import random
import re

from .llm import ExternalLLM

BASE_ITEMS = [
    (
        "你好。",
        "你好，我是工会法律服务助手。你可以描述劳动用工、工会工作中的法律问题，"
        "也可以让我生成普法宣传文章。",
    ),
    (
        "你能帮我做什么？",
        "我主要能处理两类事：一是根据工会法律知识库分析违法行为、适用条款和"
        "法律责任；二是生成以案说法的普法文章。",
    ),
    (
        "帮我把这段话改得更正式：这个问题你们自己解决。",
        "建议表述：请相关方依照规定程序协商处理该事项。",
    ),
    (
        "给我三个向职工说明情况的要点。",
        "1. 先说明已经掌握的事实；2. 再说明适用的规则和依据；"
        "3. 最后给出下一步建议与需要补充的材料。",
    ),
    ("把“要及时沟通”换成更正式的说法。", "可改为：应当及时开展沟通协商。"),
    (
        "帮我列一个会议通知提纲。",
        "可以包括：会议主题、时间地点、参加人员、议程、需准备的材料、"
        "联系人和注意事项。",
    ),
    (
        "把这段话总结成一句：公司没开会就直接改了排班，大家觉得不合理。",
        "公司未经协商程序单方调整排班，引发职工异议。",
    ),
    ("怎么开头比较礼貌？", "可以使用：您好，想向您咨询一个问题。"),
    (
        "帮我润色：这个事儿挺麻烦的。",
        "可改为：该事项涉及因素较多，处理时需要进一步核实相关情况。",
    ),
    (
        "用一句话解释“集体协商”。",
        "集体协商是职工一方与用人单位就劳动关系有关事项进行平等协商、"
        "形成集体合同或协议的过程。",
    ),
]

GENERAL_PROMPT = """\
编写 {batch_size} 组简短的通用对话样本，用于保持助手的通用指令跟随能力。
- 不涉及法律条文，不要求引用出处；
- 可以围绕问候、润色文字、概括、列清单、礼貌表达、解释常见概念；
- user 口语化，assistant 简洁直接；
- 只输出 JSON 数组：[{{"user": "...", "assistant": "..."}}]"""


def _parse_pairs(text: str) -> list[tuple[str, str]]:
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return [(d["user"], d["assistant"]) for d in arr
            if isinstance(d, dict) and "user" in d and "assistant" in d]


def _make(user: str, assistant: str) -> dict:
    return {
        "messages": [
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ],
        "meta": {"type": "general"},
    }


def generate(llm: ExternalLLM | None, cfg: dict, *, target: int = 50) -> list[dict]:
    samples = [_make(q, a) for q, a in BASE_ITEMS[: max(0, target)]]
    if llm is None or len(samples) >= target:
        return samples[:target]

    rng = random.Random(cfg.get("seed", 42))
    batch_size = max(1, cfg.get("general_batch_size", 10))
    progress_every = cfg.get("progress_every", 50)
    calls = 0
    while len(samples) < target:
        calls += 1
        out = llm.chat(
            [{"role": "user", "content": GENERAL_PROMPT.format(batch_size=batch_size)}],
            input_source="synthetic_template",
            temperature=0.9,
            max_tokens=2500,
        )
        for user, assistant in _parse_pairs(out):
            if len(samples) < target and (user, assistant) not in [
                (m[0]["content"], m[1]["content"]) for m in
                    (s["messages"] for s in samples[-50:])
            ]:
                samples.append(_make(user, assistant))
        if progress_every and calls % progress_every == 0:
            print(f"general progress: {len(samples)}/{target}")
    rng.shuffle(samples)
    return samples[:target]
