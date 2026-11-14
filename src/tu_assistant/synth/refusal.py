"""拒答样本合成（T043，FR-014、FR-022）。

范围外问题 → 明确拒答或引导；多为模板化生成（确定性），
外部模型只负责把问题换个说法，降低模式化。
"""

from __future__ import annotations

import random

from .llm import ExternalLLM

# (问题, 拒答类型)
REFUSAL_ITEMS = [
    ("公司拖欠我三个月工资，帮我写一份劳动仲裁申请书。", "unsupported_feature"),
    ("帮我起草一份解除劳动合同通知书。", "unsupported_feature"),
    ("帮我写一份给法院的民事起诉状。", "unsupported_feature"),
    ("帮我做一份可以向劳动监察大队提交的投诉材料。", "unsupported_feature"),
    ("某某地方关于高温补贴的规定是什么？", "unsupported_feature"),
    ("帮我查一下某个区的集体合同示范文本。", "unsupported_feature"),
    ("我们区总工会的地址在哪里？", "out_of_scope"),
    ("交通事故对方全责不赔钱怎么办？", "out_of_scope"),
    ("个人所得税怎么算？", "out_of_scope"),
    ("帮我查查今天的天气。", "out_of_scope"),
    ("刑法里盗窃罪怎么判？", "out_of_scope"),
    ("离婚时孩子抚养权一般怎么判？", "out_of_scope"),
    ("房东不退押金怎么办？", "out_of_scope"),
    ("医疗事故可以赔多少钱？", "out_of_scope"),
    ("商标注册需要哪些材料？", "out_of_scope"),
    ("公司股权代持协议有没有法律效力？", "out_of_scope"),
]

REFUSAL_ANSWERS = {
    "unsupported_feature": (
        "抱歉，本期我暂不支持这项功能（如起草法律文书、查询地方性规定）。"
        "我可以帮你做两件事：解答工会相关法律条款的适用问题，"
        "或者生成普法宣传文章。需要的话告诉我。"
    ),
    "out_of_scope": (
        "抱歉，这个问题超出了我的知识范围。我的知识库只覆盖工会领域的"
        "法律法规，无法回答其他领域的问题，也不便推测作答。"
        "如果你有工会法律方面的问题，或需要生成普法文章，我可以帮忙。"
    ),
}

REWRITE_PROMPT = "把下面这句话换个更口语化的说法，意思不变，只输出改写后的句子：\n{q}"


def generate(llm: ExternalLLM | None, cfg: dict) -> list[dict]:
    samples = []
    rng = random.Random(cfg.get("seed", 42))
    rewrites = cfg.get("behavior", {}).get("refusal_rewrites", 1)
    progress_every = cfg.get("progress_every", 50)
    for idx, (q, kind) in enumerate(REFUSAL_ITEMS, 1):
        samples.append(_make(q, kind, "refusal"))
        if llm is not None:
            for _ in range(rewrites):
                out = llm.chat(
                    [{"role": "user", "content": REWRITE_PROMPT.format(q=q)}],
                    input_source="synthetic_template",
                    max_tokens=100,
                ).strip()
                if out and out != q:
                    samples.append(_make(out, kind, "refusal"))
        if progress_every and idx % progress_every == 0:
            print(f"refusal progress: {idx}/{len(REFUSAL_ITEMS)}")

    # 误拒对照：范围内问题不得拒答的负样本由 consult/knowledge 覆盖，
    # 这里再加几条"看似范围外实则范围内"的提示样本交由 check 过滤
    rng.shuffle(samples)
    return samples


def _make(q: str, kind: str, sample_type: str) -> dict:
    return {
        "messages": [
            {"role": "user", "content": q},
            {"role": "assistant", "content": REFUSAL_ANSWERS[kind]},
        ],
        "meta": {"type": sample_type, "kind": kind},
    }
