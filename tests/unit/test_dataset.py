import json

from tu_assistant.train.dataset import (
    load_message_samples,
    oversample_train,
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


def test_load_message_samples_infers_sample_type(tmp_path):
    rows = [
        {
            "messages": [
                {"role": "system", "content": "系统提示"},
                {"role": "user", "content": "含糊开场"},
                {"role": "assistant", "content": "先追问"},
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
    ]
    (tmp_path / "train.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )

    loaded = load_message_samples(tmp_path)

    assert [s["meta"]["type"] for s in loaded] == [
        "intent", "refusal", "consult",
    ]
