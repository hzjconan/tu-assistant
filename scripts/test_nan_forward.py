"""对 iter 51-100 的 50 个候选样本逐个跑前向 loss，检查是否有 inf/nan。"""

from __future__ import annotations

import json

import mlx.core as mx
import mlx.nn as nn
import numpy as np
from mlx_lm.utils import load

MODEL = "mlx-community/Qwen2.5-7B-Instruct-4bit"

model, tok = load(MODEL)

with open(
    "artifacts/datasets/ds-kb-20261113-093057-16741/train.jsonl",
    encoding="utf-8",
) as f:
    rows = [json.loads(line)["messages"] for line in f if line.strip()]
np.random.seed(42)
perm = np.random.permutation(len(rows))

for it_i, sample_i in enumerate(perm[50:100], start=51):
    msgs = rows[sample_i]
    tokens = tok.apply_chat_template(msgs, return_dict=False)
    prompt = tok.apply_chat_template(
        msgs[:-1], add_generation_prompt=True, return_dict=False
    )
    x = mx.array(tokens)[None, :]
    inputs, targets = x[:, :-1], x[:, 1:]
    logits = model(inputs)
    steps = mx.arange(1, targets.shape[1] + 1)
    mask = mx.logical_and(steps >= len(prompt), steps <= len(tokens))
    ce = nn.losses.cross_entropy(logits, targets) * mask
    ntoks = mask.sum()
    loss = ce.astype(mx.float32).sum() / ntoks
    mx.eval(loss)
    flag = "" if mx.isfinite(loss) else "  <<< NON-FINITE"
    print(
        f"iter {it_i} sample {sample_i}: loss={float(loss):.3f} "
        f"ntoks={int(ntoks)} logits_max={float(logits.abs().max()):.1f}{flag}"
    )
