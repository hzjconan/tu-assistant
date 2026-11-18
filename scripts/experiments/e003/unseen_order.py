"""Reconstruct first-epoch training indices using the installed mlx_lm version."""

import json
from pathlib import Path

import numpy as np

root = Path(__file__).resolve().parents[3]
data = root / "artifacts/datasets/latest/train.jsonl"
rows = [json.loads(line) for line in data.open(encoding="utf-8")]
# mlx_lm 0.32.2: CacheDataset.itemlen returns len(raw dict), not token count.
# Every JSONL row has only the "messages" key, so sorted() preserves file order.
assert len(rows) == 8921
assert {tuple(row) for row in rows} == {("messages",)}
np.random.seed(42)
order = np.random.permutation(len(rows)).tolist()
unseen = order[8421:]
result = {
    "dataset": str(data.relative_to(root)),
    "seed": 42,
    "first_segment": 500,
    "resume_segment": 8421,
    "unseen_line_numbers": [i + 1 for i in unseen],
}
path = root / "artifacts/logs/e003/unseen_ids.json"
path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print("rows:", len(rows), "first-segment overlap:", len(set(order[:500]) & set(order[:8421])))
print("unseen:", len(unseen), "unique:", len(set(unseen)), "saved:", path.relative_to(root))
