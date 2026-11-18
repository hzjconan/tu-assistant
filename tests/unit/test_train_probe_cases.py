"""Training probes are separately tagged and cannot be mistaken for reviewed cases."""

import json

import pytest

from tu_assistant.eval.cases import load_cases


def test_train_probe_source_loads(tmp_path):
    path = tmp_path / "probes.jsonl"
    case = {
        "case_id": "p1-0001", "category": "clause_id",
        "input": {"message": "假设问题"},
        "gold": {"clauses": ["doc:a1:p1"]},
        "source": "train_probe", "eval_set_version": "train-probe-v1",
        "note": "train.jsonl:12",
    }
    path.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
    loaded = load_cases(path)
    assert len(loaded) == 1
    assert loaded[0].source == "train_probe"
    assert loaded[0].gold["clauses"] == ["doc:a1:p1"]
    case["source"] = "unreviewed"
    path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="未知 source"):
        load_cases(path)
