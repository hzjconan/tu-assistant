import json
import re

from tu_assistant.train.dataset import (
    load_message_samples,
    oversample_train,
    thin_knowledge,
    unify_system_prompts,
    write_dataset,
)


def _sample(sample_type: str, text: str, role: str = "user") -> dict:
    return {
        "messages": [
            {"role": role, "content": text},
            {"role": "assistant", "content": "回答"},
        ],
        "meta": {"type": sample_type},
    }


def test_oversample_train_repeats_only_selected_types():
    samples = [
        _sample("knowledge", "条款问题"),
        _sample("knowledge", "另一个条款问题"),
        _sample("consult", "案情咨询"),
    ]

    out = oversample_train(samples, {"consult": 4}, seed=1)

    assert len(out) == 6
    assert sum(1 for s in out if s["meta"]["type"] == "consult") == 4
    assert sum(1 for s in out if s["meta"]["type"] == "knowledge") == 2


def test_write_dataset_records_base_and_boosted_train_sizes(tmp_path):
    samples = [_sample("knowledge", f"条款问题{i}") for i in range(9)]
    samples.append(_sample("consult", "案情咨询"))

    result = write_dataset(
        samples,
        "ds-test",
        tmp_path,
        kb_version="kb-test",
        generator={"provider": "test"},
        seed=3,
        train_oversample={"consult": 4},
    )
    manifest = json.loads((tmp_path / "ds-test" / "manifest.json").read_text())

    assert manifest["train_size"] == result["train"]
    assert manifest["base_train_size"] <= manifest["train_size"]
    assert manifest["train_counts"]["consult"] in (0, 4)


def test_unify_system_prompts_replaces_and_preserves_n():
    old_prompt = (
        "你是工会法律服务助手，面向工会工作人员。"
        "每轮追问最多提 4 个问题，优先问对结论影响最大的事实。"
    )
    samples = [
        _sample("knowledge", "条款问题"),
        _sample("consult", "案情咨询"),
        {
            "messages": [
                {"role": "system", "content": old_prompt},
                {"role": "user", "content": "含糊开场"},
                {"role": "assistant", "content": "先追问"},
            ],
            "meta": {"type": "intent"},
        },
        {
            "messages": [
                {"role": "system", "content": "无关系统提示"},
                {"role": "user", "content": "案情"},
                {"role": "assistant", "content": "回答"},
            ],
            "meta": {"type": "knowledge"},
        },
    ]

    stats = unify_system_prompts(samples, seed=7)

    assert stats == {"added": 2, "replaced": 2}
    for s in samples:
        first = s["messages"][0]
        assert first["role"] == "system"
        assert "工会法律服务助手" in first["content"]
    # 已有 system 且含 N 的样本保持同一个 N
    assert "每轮最多提 4 个问题" in samples[2]["messages"][0]["content"]
    # 提取不到 N 的旧 system → 随机 N ∈ [2,6]
    m = re.search(r"最多提 (\d+) 个问题", samples[3]["messages"][0]["content"])
    assert m and 2 <= int(m.group(1)) <= 6
    assert len(samples[2]["messages"]) == 3


def _knowledge_sample(text: str, clause_ids: list[str]) -> dict:
    return {
        "messages": [
            {"role": "user", "content": text},
            {"role": "assistant", "content": "回答"},
        ],
        "meta": {
            "type": "knowledge",
            "doc_id": clause_ids[0].split(":", 1)[0],
            "clause_ids": clause_ids,
        },
    }


def test_thin_knowledge_preserves_clause_coverage(tmp_path):
    # 5 个条款、8 条样本：c:1 有 4 条，其余各 1 条；s8 的从属条款 c:5
    samples = [
        _knowledge_sample(f"k{i}", [f"doc:{c}"])
        for i, c in enumerate(["1", "1", "1", "1", "2", "3", "4"])
    ]
    samples.append(_knowledge_sample("k8", ["doc:1", "doc:5"]))
    samples += [_sample("consult", "案情咨询"), _sample("intent", "开场")]

    out, stats = thin_knowledge(samples, 6, seed=42)

    knowledge = [s for s in out if s["meta"]["type"] == "knowledge"]
    assert len(knowledge) == 6
    covered = {
        c for s in knowledge for c in s["meta"]["clause_ids"]
    }
    assert covered == {"doc:1", "doc:2", "doc:3", "doc:4", "doc:5"}
    assert stats["knowledge_before"] == 8
    assert stats["knowledge_after"] == 6
    assert stats["clause_coverage_after"] == 5
    # 非 knowledge 样本不受影响
    assert sum(1 for s in out if s["meta"]["type"] != "knowledge") == 2

    # knowledge 不足 max_n 时原样返回
    out2, stats2 = thin_knowledge(samples, 100, seed=42)
    assert len(out2) == len(samples)
    assert stats2["knowledge_after"] == 8


def test_thin_knowledge_respects_doc_cap():
    # 单文件占比上限已由 balance_by_doc 保证；抽稀不应放大任一 doc 占比。
    samples = [
        _knowledge_sample(f"big{i}", [f"big:{i % 20}"]) for i in range(80)
    ]
    samples += [
        _knowledge_sample(f"small{i}", [f"small:{i}"]) for i in range(20)
    ]

    out, _ = thin_knowledge(samples, 50, seed=1)

    knowledge = [s for s in out if s["meta"]["type"] == "knowledge"]
    assert len(knowledge) <= 50
    big = sum(1 for s in knowledge if s["meta"]["doc_id"] == "big")
    assert big / len(knowledge) <= 0.8 + 1e-9  # 抽稀后占比不高于抽稀前


def test_write_dataset_records_system_prompt_flag(tmp_path):
    samples = [_sample("knowledge", f"条款问题{i}") for i in range(10)]

    write_dataset(
        samples,
        "ds-sysprompt",
        tmp_path,
        kb_version="kb-test",
        generator={"provider": "test"},
        seed=3,
        add_system_prompt=True,
    )
    manifest = json.loads(
        (tmp_path / "ds-sysprompt" / "manifest.json").read_text()
    )
    rows = [
        json.loads(line)
        for line in (tmp_path / "ds-sysprompt" / "train.jsonl")
        .read_text()
        .splitlines()
    ]

    assert manifest["config"]["add_system_prompt"] is True
    assert manifest["system_prompt"]["added"] == 10
    assert manifest["prompt_version"]
    assert all(r["messages"][0]["role"] == "system" for r in rows)


def test_load_message_samples_infers_sample_type(tmp_path):
    rows = [
        {
            "messages": [
                {"role": "system", "content": "系统提示"},
                {"role": "user", "content": "含糊开场"},
                {"role": "assistant", "content": "先追问"},
                {"role": "user", "content": "补充信息"},
                {"role": "assistant", "content": "咨询回答"},
            ]
        },
        {
            # 补过 system 的单轮样本不应误判为 intent
            "messages": [
                {"role": "system", "content": "系统提示"},
                {"role": "user", "content": "案情"},
                {"role": "assistant", "content": "## 违法行为认定\n分析"},
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "写起诉状"},
                {"role": "assistant", "content": "抱歉，本期我暂不支持这项功能。"},
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "案情"},
                {"role": "assistant", "content": "## 违法行为认定\n分析"},
            ]
        },
        {
            # 无引用标记 → general（不是 knowledge，避免被 check 误杀）
            "messages": [
                {"role": "user", "content": "帮我润色这句话"},
                {"role": "assistant", "content": "可以改为……"},
            ]
        },
    ]
    (tmp_path / "train.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )

    loaded = load_message_samples(tmp_path)

    assert [s["meta"]["type"] for s in loaded] == [
        "intent", "consult", "refusal", "consult", "general",
    ]
