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

from ..citation.verify import verify_output
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


def load_message_samples(dataset_dir: str | Path, kb_conn=None) -> list[dict]:
    """读取已写出的 messages JSONL，并重建生成侧 meta（用于数据增补）。

    写出的数据集不含 meta；增补时根据会话结构与助手文本推断类型，
    并通过出处校验层把引用解析回 clause_id/doc_id。
    """
    samples: list[dict] = []
    root = Path(dataset_dir)
    for split in ("train", "valid"):
        path = root / f"{split}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            messages = json.loads(line)["messages"]
            samples.append(
                {"messages": messages,
                 "meta": _infer_meta(messages, kb_conn)}
            )
    return samples


def _infer_meta(messages: list[dict], kb_conn=None) -> dict:
    assistant_text = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "assistant"),
        "",
    )
    if messages and messages[0].get("role") == "system":
        sample_type = "intent"
    elif "暂不支持" in assistant_text or "超出了我的知识范围" in assistant_text:
        sample_type = "refusal"
    elif "违法行为认定" in assistant_text:
        sample_type = "consult"
    elif "以案说法" in assistant_text and "普法提示" in assistant_text:
        sample_type = "article"
    else:
        sample_type = "knowledge"

    clause_ids: list[str] = []
    if kb_conn is not None and assistant_text:
        clause_ids = [
            c.resolved_clause_id for c in verify_output(assistant_text, kb_conn).citations
            if c.resolved_clause_id
        ]
    return {
        "type": sample_type,
        "doc_id": clause_ids[0].split(":", 1)[0] if clause_ids else None,
        "clause_ids": clause_ids,
    }


def oversample_train(
    samples: list[dict], factors: dict[str, int], *, seed: int = 42
) -> list[dict]:
    """只在训练侧重复少数类型样本；验证集保持真实分布。"""
    if not factors:
        return samples
    out: list[dict] = []
    for s in samples:
        factor = factors.get(s.get("meta", {}).get("type"), 1)
        out.extend([s] * max(1, int(factor)))
    rng = random.Random(seed)
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
    train_oversample: dict[str, int] | None = None,
) -> dict:
    """写 train.jsonl / valid.jsonl / manifest.json，返回汇总。"""
    out = Path(out_dir) / dataset_id
    out.mkdir(parents=True, exist_ok=True)
    train, valid = split_train_valid(samples, seed=seed)
    base_train_size = len(train)
    train = oversample_train(train, train_oversample or {}, seed=seed)

    for name, rows in (("train", train), ("valid", valid)):
        with (out / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for s in rows:
                f.write(json.dumps({"messages": s["messages"]}, ensure_ascii=False) + "\n")

    counts: dict[str, int] = defaultdict(int)
    train_counts: dict[str, int] = defaultdict(int)
    for s in samples:
        counts[s.get("meta", {}).get("type", "unknown")] += 1
    for s in train:
        train_counts[s.get("meta", {}).get("type", "unknown")] += 1

    write_manifest(
        out,
        artifact_id=dataset_id,
        artifact_type="dataset",
        inputs={"kb_version": kb_version},
        config={**generator, "train_oversample": train_oversample or {}},
        seed=seed,
        extra={
            "stage": "sft",
            "counts": dict(counts),
            "train_counts": dict(train_counts),
            "base_train_size": base_train_size,
            "train_size": len(train),
            "valid_size": len(valid),
            "dedup_against": eval_set_version,
        },
    )

    latest = Path(out_dir) / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(out.name)
    return {
        "dataset_id": dataset_id,
        "dir": str(out),
        "train": len(train),
        "valid": len(valid),
        "counts": dict(counts),
    }
