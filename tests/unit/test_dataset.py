import json
import re

from tu_assistant.train.dataset import (
    dedup_against_eval,
    load_message_samples,
    oversample_train,
    split_train_valid,
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
                {"role": "user", "content": "另一案情"},
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
    assert all(s["meta"]["split"] == "train" for s in loaded)


def test_infer_meta_multi_turn_article_vs_intent_switch_and_relations(tmp_path):
    rows = [
        # 1) 5 消息 T053 修改稿（更早助手轮与末轮均含 以案说法+普法提示）→ article
        {
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "写1篇普法文章"},
                {"role": "assistant", "content": "## 案例\n甲\n## 以案说法\n分析\n## 普法提示\n提示"},
                {"role": "user", "content": "语言再通俗些"},
                {"role": "assistant", "content": "## 案例\n甲\n## 以案说法\n通俗分析\n## 普法提示\n通俗提示"},
            ]
        },
        # 2) 5 消息 intent 中途变卦写文章（首轮助手只是追问，末轮才是文章）→ 保持 intent
        {
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "单位扣工资怎么办"},
                {"role": "assistant", "content": "请问您是想咨询维权还是写普法文章？"},
                {"role": "user", "content": "写成普法文章吧"},
                {"role": "assistant", "content": "## 案例\n甲\n## 以案说法\n分析\n## 普法提示\n提示"},
            ]
        },
        # 3) 单轮初稿 → article
        {
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "写普法文章"},
                {"role": "assistant", "content": "## 案例\n甲\n## 以案说法\n分析\n## 普法提示\n提示"},
            ]
        },
        # 4) 关系问答样本 → knowledge + kind=relation_liability_for
        {
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "违反《演练规则》第1条要承担什么法律责任？"},
                {"role": "assistant", "content": "〔《演练规则》（示例版）第3条〕\n> 责令改正。"},
            ]
        },
        # 5) references 关系问答 → knowledge + kind=relation_references
        {
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "哪些条款引用了《演练规则》第1条？"},
                {"role": "assistant", "content": "〔《演练规则》（示例版）第2条〕\n> 依照第1条。"},
            ]
        },
    ]
    (tmp_path / "train.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )
    loaded = load_message_samples(tmp_path)
    assert [s["meta"]["type"] for s in loaded] == [
        "article", "intent", "article", "knowledge", "knowledge",
    ]
    assert loaded[3]["meta"]["kind"] == "relation_liability_for"
    assert loaded[4]["meta"]["kind"] == "relation_references"


def test_split_preserves_reuse_split_and_groups_article_families():
    reused_train = [
        {
            "messages": [{"role": "user", "content": f"old_t_{i}"}, {"role": "assistant", "content": "a"}],
            "meta": {"type": "knowledge", "split": "train"},
        }
        for i in range(18)
    ]
    reused_valid = [
        {
            "messages": [{"role": "user", "content": f"old_v_{i}"}, {"role": "assistant", "content": "a"}],
            "meta": {"type": "knowledge", "split": "valid"},
        }
        for i in range(2)
    ]
    # 新增 4 个文章家族（每个家族 1 初稿 + 2 修改稿）
    articles = []
    for f in range(4):
        did = f"batch:req{f}"
        articles.append(
            {
                "messages": [{"role": "user", "content": f"d{f}"}, {"role": "assistant", "content": f"a{f}"}],
                "meta": {"type": "article", "sample_id": did},
            }
        )
        for r in range(2):
            articles.append(
                {
                    "messages": [
                        {"role": "user", "content": f"r{f}_{r}"},
                        {"role": "assistant", "content": f"ra{f}"},
                    ],
                    "meta": {"type": "article", "parent": did},
                }
            )

    for seed in (1, 7, 42, 99):
        train, valid = split_train_valid(
            reused_train + reused_valid + articles, valid_ratio=0.25, seed=seed, preserve_split=True
        )
        valid_users = {s["messages"][0]["content"] for s in valid}
        old_train_users = {s["messages"][0]["content"] for s in reused_train}
        assert not (valid_users & old_train_users)
        assert {s["messages"][0]["content"] for s in reused_valid}.issubset(valid_users)

        train_fams = {
            s["meta"].get("parent") or s["meta"].get("sample_id")
            for s in train
            if s["meta"]["type"] == "article"
        }
        valid_fams = {
            s["meta"].get("parent") or s["meta"].get("sample_id")
            for s in valid
            if s["meta"]["type"] == "article"
        }
        assert train_fams and valid_fams
        assert not (train_fams & valid_fams)


def test_thin_knowledge_pins_relations_and_protects_valid_split():
    # 5 条 relation_* + 5 条共享同一条款的 valid 普通样本 + 10 条同条款 train 普通样本，抽稀到 12 条。
    # 因 5 条 valid 共享同一 clause_id，第一轮最多只选 1 条，其余 4 条必须进入第二轮 valid_left 分支。
    rels = [
        {
            "messages": [{"role": "user", "content": f"rel{i}"}, {"role": "assistant", "content": "a"}],
            "meta": {"type": "knowledge", "kind": "relation_liability_for", "clause_ids": [f"d:a{i}"]},
        }
        for i in range(5)
    ]
    val_k = [
        {
            "messages": [{"role": "user", "content": f"val{i}"}, {"role": "assistant", "content": "a"}],
            "meta": {"type": "knowledge", "split": "valid", "clause_ids": ["d:shared"]},
        }
        for i in range(5)
    ]
    tr_k = [
        {
            "messages": [{"role": "user", "content": f"tr{i}"}, {"role": "assistant", "content": "a"}],
            "meta": {"type": "knowledge", "split": "train", "clause_ids": ["d:shared"]},
        }
        for i in range(10)
    ]
    out, stats = thin_knowledge(rels + val_k + tr_k, 12, seed=42)
    assert stats["pinned_relations"] == 5
    assert stats["knowledge_after"] == 12
    kept_users = {s["messages"][0]["content"] for s in out}
    # 全部 5 条 relation_* 和全部 5 条共享条款的 valid 样本都保住，仅从 train 侧裁减
    assert all(f"rel{i}" in kept_users for i in range(5))
    assert all(f"val{i}" in kept_users for i in range(5))
    assert sum(1 for u in kept_users if u.startswith("tr")) == 2


def test_thin_knowledge_subordinate_clauses_no_duplicate_append():
    # 一条 leftover 样本同时包含 2 个未覆盖从属条款（d:sub1, d:sub2），只能入选 1 次
    samples = [
        _knowledge_sample("main0", ["d:0"]),
        _knowledge_sample("main1", ["d:1"]),
        _knowledge_sample("multi_sub", ["d:0", "d:sub1", "d:sub2"]),
        _knowledge_sample("extra0", ["d:0"]),
        _knowledge_sample("extra1", ["d:0"]),
    ]
    out, stats = thin_knowledge(samples, 4, seed=1)
    users = [s["messages"][0]["content"] for s in out]
    assert len(users) == len(set(users)) == 4
    assert users.count("multi_sub") == 1
    assert stats["clause_coverage_after"] == 4


def test_load_message_samples_cross_split_dedup_prefers_train(tmp_path):
    train_rows = [
        {
            "messages": [
                {"role": "system", "content": "每轮最多提 3 个问题"},
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好！"},
            ]
        }
    ]
    valid_rows = [
        # 仅 system 不同的重复样本：train 优先，应被去重不留在 valid
        {
            "messages": [
                {"role": "system", "content": "每轮最多提 5 个问题"},
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好！"},
            ]
        },
        # 独立 valid 样本：应保留且标记 split="valid"
        {
            "messages": [
                {"role": "system", "content": "每轮最多提 4 个问题"},
                {"role": "user", "content": "帮我润色"},
                {"role": "assistant", "content": "好的。"},
            ]
        },
    ]
    (tmp_path / "train.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in train_rows), encoding="utf-8"
    )
    (tmp_path / "valid.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in valid_rows), encoding="utf-8"
    )
    loaded = load_message_samples(tmp_path)
    assert len(loaded) == 2
    by_user = {s["messages"][1]["content"]: s["meta"]["split"] for s in loaded}
    assert by_user == {"你好": "train", "帮我润色": "valid"}


def test_dedup_against_eval_catches_single_turn_in_multiturn():
    sample = {
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "帮我写一篇完全无关主题的普法文章。"},
            {"role": "assistant", "content": "初稿"},
            {"role": "user", "content": "文章里把电子厂背景换成建筑工地再发我一版。"},
            {"role": "assistant", "content": "修改稿"},
        ],
        "meta": {"type": "article"},
    }
    kept, dropped = dedup_against_eval([sample], ["文章里把电子厂背景换成建筑工地再发我一版。"])
    assert not kept and len(dropped) == 1


def test_write_dataset_extra_manifest_fields(tmp_path):
    samples = [_sample("knowledge", f"条款问题{i}") for i in range(10)]
    write_dataset(
        samples,
        "ds-extra",
        tmp_path,
        kb_version="kb-test",
        generator={"provider": "test"},
        extra_manifest={
            "known_issues": [{"id": "T078", "summary": "测试"}],
            "article_stats": {"total": 0},
        },
    )
    manifest = json.loads((tmp_path / "ds-extra" / "manifest.json").read_text())
    assert manifest["known_issues"][0]["id"] == "T078"
    assert manifest["article_stats"]["total"] == 0
