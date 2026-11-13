"""数据集构建（T031）：messages JSONL、9:1 划分、均衡抽样、评测集去重。

输入样本格式::

    {"messages": [{"role": ..., "content": ...}, ...],
     "meta": {"type": "knowledge|intent|consult|refusal|article|general",
              "doc_id": "...", "clause_ids": [...]}}

输出 ``artifacts/datasets/<dataset_id>/`` 下的 train.jsonl / valid.jsonl
与 manifest.json（含 dedup_against）。
"""

from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..manifest import write_manifest


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text)


def dedup_against_eval(
    samples: list[dict], eval_questions: list[str], *, overlap: float = 0.8
) -> tuple[list[dict], list[dict]]:
    """与评测集去重：任一 user 消息与评测题问句高重合 → 剔除。

    用字符级 3-gram Jaccard 相似度，阈值 overlap。
    """
    def grams(s: str) -> set[str]:
        s = _norm(s)
        return {s[i : i + 3] for i in range(max(1, len(s) - 2))}

    eval_grams = [grams(q) for q in eval_questions]
    kept, dropped = [], []
    for s in samples:
        user_texts = " ".join(
            m["content"] for m in s["messages"] if m["role"] == "user"
        )
        g = grams(user_texts)
        dup = any(
            eg and len(g & eg) / len(g | eg) >= overlap for eg in eval_grams
        )
        (dropped if dup else kept).append(s)
    return kept, dropped


def balance_by_doc(
    samples: list[dict], *, max_ratio: float = 0.2, seed: int = 42
) -> list[dict]:
    """按文件均衡：任一 doc_id 的样本占比不超过 max_ratio（默认 20%）。

    防止最大文件主导训练数据（AGENTS.md / T031）。
    """
    rng = random.Random(seed)
    by_doc: dict[str, list[dict]] = defaultdict(list)
    no_doc: list[dict] = []
    for s in samples:
        doc = s.get("meta", {}).get("doc_id")
        (by_doc[doc].append if doc else no_doc.append)(s)
    if not by_doc:
        return samples
    n = len(samples)
    cap = max(1, int(n * max_ratio))
    out = list(no_doc)
    for doc_samples in by_doc.values():
        rng.shuffle(doc_samples)
        out.extend(doc_samples[:cap])
    rng.shuffle(out)
    return out


def split_train_valid(
    samples: list[dict], *, valid_ratio: float = 0.1, seed: int = 42
) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    idx = list(range(len(samples)))
    rng.shuffle(idx)
    n_valid = max(1, int(len(samples) * valid_ratio))
    valid = [samples[i] for i in idx[:n_valid]]
    train = [samples[i] for i in idx[n_valid:]]
    return train, valid


def write_dataset(
    samples: list[dict],
    dataset_id: str,
    out_dir: str | Path,
    *,
    kb_version: str,
    generator: dict[str, Any],
    eval_set_version: str | None = None,
    seed: int = 42,
) -> dict:
    """写 train.jsonl / valid.jsonl / manifest.json，返回汇总。"""
    out = Path(out_dir) / dataset_id
    out.mkdir(parents=True, exist_ok=True)
    train, valid = split_train_valid(samples, seed=seed)

    for name, rows in (("train", train), ("valid", valid)):
        with (out / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for s in rows:
                f.write(json.dumps({"messages": s["messages"]}, ensure_ascii=False) + "\n")

    counts: dict[str, int] = defaultdict(int)
    for s in samples:
        counts[s.get("meta", {}).get("type", "unknown")] += 1

    write_manifest(
        out,
        artifact_id=dataset_id,
        artifact_type="dataset",
        inputs={"kb_version": kb_version},
        config=generator,
        seed=seed,
        extra={
            "stage": "sft",
            "counts": dict(counts),
            "train_size": len(train),
            "valid_size": len(valid),
            "dedup_against": eval_set_version,
        },
    )
    return {
        "dataset_id": dataset_id,
        "dir": str(out),
        "train": len(train),
        "valid": len(valid),
        "counts": dict(counts),
    }
