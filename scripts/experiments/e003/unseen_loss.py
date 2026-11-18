"""Compare masked assistant-token loss for reconstructed seen/unseen rows."""

import json
from pathlib import Path

import numpy as np
from mlx_lm.tuner.datasets import CacheDataset, ChatDataset
from mlx_lm.tuner.trainer import evaluate
from mlx_lm.utils import load

root = Path(__file__).resolve().parents[3]
rows = [
    json.loads(line)
    for line in (root / "artifacts/datasets/latest/train.jsonl").open(encoding="utf-8")
]
unseen = set(json.loads(
    (root / "artifacts/logs/e003/unseen_ids.json").read_text(encoding="utf-8")
)["unseen_line_numbers"])
seen = [i for i in range(1, len(rows) + 1) if i not in unseen]
seen_sample = np.random.default_rng(43).choice(seen, size=500, replace=False).tolist()
model, tokenizer = load(
    "mlx-community/Qwen2.5-7B-Instruct-4bit",
    adapter_path=str(root / "artifacts/train/exp-20261116-resume500/adapters"),
)
for name, ids in [("seen", seen_sample), ("unseen", sorted(unseen))]:
    dataset = CacheDataset(ChatDataset([rows[i - 1] for i in ids], tokenizer, mask_prompt=True))
    loss = evaluate(
        model, dataset, batch_size=1, num_batches=-1, max_seq_length=2048
    )
    print(f"{name}: count={len(ids)} assistant-token-weighted loss={loss:.6f}", flush=True)
