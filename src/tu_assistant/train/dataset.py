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

from ..chat.prompts import PROMPT_VERSION, build_system_prompt
from ..citation.verify import verify_output
from ..manifest import write_manifest

# 旧版/新版 SYSTEM_TEMPLATE 中追问上限的句式（"每轮最多提 N 个问题"）
_MAX_QUESTIONS_RE = re.compile(r"最多提\s*(\d+)\s*个问题")


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
    seen: set[str] = set()
    root = Path(dataset_dir)
    for split in ("train", "valid"):
        path = root / f"{split}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            messages = json.loads(line)["messages"]
            # train.jsonl 含 train_oversample 的精确副本；复用时去重，
            # 否则同一对话会被重复计数并可能泄漏进 valid。
            key = json.dumps(messages, ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
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
    # 意图样本是 system + 多轮对话；写库时给单轮样本补的 system 只有 3 条消息，
    # 用消息数区分，避免复用时把补过 system 的单轮样本误判为 intent。
    if (
        messages
        and messages[0].get("role") == "system"
        and len(messages) > 3
    ):
        sample_type = "intent"
    elif "暂不支持" in assistant_text or "超出了我的知识范围" in assistant_text:
        sample_type = "refusal"
    elif "违法行为认定" in assistant_text:
        sample_type = "consult"
    elif "以案说法" in assistant_text and "普法提示" in assistant_text:
        sample_type = "article"
    elif "〔" not in assistant_text:
        # 无任何引用标记：knowledge 样本必然带〔〕块（check 强制），
        # 剩下的只能是 general（或措辞变体的 refusal）。
        sample_type = "general"
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


def thin_knowledge(
    samples: list[dict], max_n: int, *, seed: int = 42
) -> tuple[list[dict], dict]:
    """knowledge 样本按条款覆盖抽稀到 ``max_n``（E001 尝试 4）。

    第一轮：按主条款（``meta.clause_ids[0]``，meta 缺失时由
    ``_infer_meta`` 在加载侧补齐）分组，每组保 1 条；再补上仅以从属
    条款出现的 clause_id 的覆盖。第二轮：剩余名额在 leftover 中随机补足。
    与 ``balance_by_doc`` 兼容（抽稀在其后执行，占比上限只会更低）。

    返回 ``(抽稀后的 samples, 统计 dict)``；knowledge 不足 ``max_n`` 时原样返回。
    """
    knowledge = [
        s for s in samples if s.get("meta", {}).get("type") == "knowledge"
    ]
    all_clauses = {
        c for s in knowledge for c in (s.get("meta", {}).get("clause_ids") or [])
    }
    stats = {
        "knowledge_max": max_n,
        "knowledge_before": len(knowledge),
        "clause_coverage_before": len(all_clauses),
    }
    if len(knowledge) <= max_n:
        stats["knowledge_after"] = len(knowledge)
        stats["clause_coverage_after"] = len(all_clauses)
        return samples, stats

    rng = random.Random(seed)
    groups: dict[Any, list[dict]] = defaultdict(list)
    for i, s in enumerate(knowledge):
        cids = s.get("meta", {}).get("clause_ids") or []
        # 无 clause_ids 的样本各占一组（保住它们）
        groups[cids[0] if cids else ("_no_clause_", i)].append(s)

    kept: list[dict] = []
    kept_ids: set[int] = set()
    for g in groups.values():
        rng.shuffle(g)
        kept.append(g[0])
        kept_ids.add(id(g[0]))

    # 仅以从属条款出现的 clause_id 也要保覆盖
    covered = {
        c for s in kept for c in (s.get("meta", {}).get("clause_ids") or [])
    }
    leftover = [s for s in knowledge if id(s) not in kept_ids]
    for cid in sorted(all_clauses - covered):
        for s in leftover:
            if cid in (s.get("meta", {}).get("clause_ids") or []):
                kept.append(s)
                kept_ids.add(id(s))
                covered.add(cid)
                break
    leftover = [s for s in leftover if id(s) not in kept_ids]

    rng.shuffle(leftover)
    kept.extend(leftover[: max(0, max_n - len(kept))])

    others = [
        s for s in samples if s.get("meta", {}).get("type") != "knowledge"
    ]
    out = others + kept
    rng.shuffle(out)
    stats["knowledge_after"] = len(kept)
    stats["clause_coverage_after"] = len(covered)
    return out, stats


def unify_system_prompts(samples: list[dict], *, seed: int = 42) -> dict:
    """把全数据集的 system 消息统一为当前 ``build_system_prompt`` 模板。

    - 已有 system 且文本含"最多提 N 个问题"→ 用新模板重建并保持同一个 N；
    - 已有 system 但提取不到 N → 随机 N；
    - 无 system → 插入新模板，N 在 2–6 随机（FR-011）。
    """
    rng = random.Random(seed)
    added = replaced = 0
    for s in samples:
        messages = s.get("messages", [])
        if messages and messages[0].get("role") == "system":
            m = _MAX_QUESTIONS_RE.search(messages[0].get("content") or "")
            n = int(m.group(1)) if m else rng.randint(2, 6)
            messages[0] = {
                "role": "system",
                "content": build_system_prompt(max_questions=n),
            }
            replaced += 1
        else:
            messages.insert(
                0,
                {
                    "role": "system",
                    "content": build_system_prompt(
                        max_questions=rng.randint(2, 6)
                    ),
                },
            )
            added += 1
    return {"added": added, "replaced": replaced}


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
    add_system_prompt: bool = False,
    knowledge_max: int | None = None,
) -> dict:
    """写 train.jsonl / valid.jsonl / manifest.json，返回汇总。"""
    out = Path(out_dir) / dataset_id
    out.mkdir(parents=True, exist_ok=True)
    thin_stats: dict = {}
    if knowledge_max:
        samples, thin_stats = thin_knowledge(samples, knowledge_max, seed=seed)
    prompt_stats = (
        unify_system_prompts(samples, seed=seed) if add_system_prompt else {}
    )
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
        config={
            **generator,
            "train_oversample": train_oversample or {},
            "add_system_prompt": add_system_prompt,
            "knowledge_max": knowledge_max,
        },
        seed=seed,
        extra={
            "stage": "sft",
            "prompt_version": PROMPT_VERSION,
            "system_prompt_chars": len(build_system_prompt()),
            "system_prompt": prompt_stats or None,
            **({"knowledge_thin": thin_stats} if thin_stats else {}),
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
