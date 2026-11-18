"""统计数据集中在 mask_prompt 下会被全掩码的样本（prompt 段 >= max_seq_length）。

mask_prompt 的 loss 只算最后一个 assistant 段；若序列被 max_seq_length
截断后 prompt 已占满全部长度，mask 全零 → loss=NaN（E001 尝试 3 的坑）。
"""

from __future__ import annotations

import json

from transformers import AutoTokenizer

MODEL = "mlx-community/Qwen2.5-7B-Instruct-4bit"
MAX_SEQ = 2048

tok = AutoTokenizer.from_pretrained(MODEL)

for split in ("train", "valid"):
    path = f"artifacts/datasets/ds-kb-20261113-093057-16741/{split}.jsonl"
    bad = over = total = 0
    bad_rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            total += 1
            msgs = json.loads(line)["messages"]
            full = tok.apply_chat_template(msgs, return_dict=False)
            prompt = tok.apply_chat_template(
                msgs[:-1], add_generation_prompt=True, return_dict=False
            )
            if len(full) > MAX_SEQ:
                over += 1
            if len(prompt) >= MAX_SEQ:
                bad += 1
                bad_rows.append((i, len(prompt), len(full)))
    print(f"{split}: total={total} over_{MAX_SEQ}={over} fully_masked={bad}")
    for i, p, f in bad_rows[:20]:
        print(f"  row {i}: prompt={p} full={f}")
