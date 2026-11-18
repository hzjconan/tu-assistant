"""复现 mlx_lm lora 的 batch 顺序，定位 iter 51-100 的可疑样本。

iterate_batches: idx 按 len(dataset[i]) 排序（CacheDataset.itemlen 是
len(dict)=1，稳定排序即原顺序）；batch_size=1 → batch_idx=[[0],[1],...]；
np.random.seed(seed) 后每轮 np.random.permutation 决定 batch 顺序。
"""

from __future__ import annotations

import json

import numpy as np
from transformers import AutoTokenizer

MODEL = "mlx-community/Qwen2.5-7B-Instruct-4bit"
SEED = 42

with open(
    "artifacts/datasets/ds-kb-20261113-093057-16741/train.jsonl",
    encoding="utf-8",
) as f:
    rows = [json.loads(line)["messages"] for line in f if line.strip()]
n = len(rows)

np.random.seed(SEED)
perm = np.random.permutation(n)

tok = AutoTokenizer.from_pretrained(MODEL)

suspects = perm[50:100]
stats = []
for it_i, sample_i in enumerate(suspects, start=51):
    msgs = rows[sample_i]
    full = tok.apply_chat_template(msgs, return_dict=False)
    prompt = tok.apply_chat_template(
        msgs[:-1], add_generation_prompt=True, return_dict=False
    )
    stats.append(
        (it_i, sample_i, len(full), len(prompt), len(full) - len(prompt))
    )

stats.sort(key=lambda x: x[4])
print("iter, sample_idx, full_tokens, prompt_tokens, unmasked")
for s in stats[:12]:
    print(s)
print("...")
for s in stats[-5:]:
    print(s)
