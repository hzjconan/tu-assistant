# Contract: 数据集格式

POC 只有一个 SFT 数据集，知识类与行为类样本混合（research R3），供本机 mlx-lm 训练使用。
格式采用通用的 `messages` JSONL，正式阶段可直接用于 LLaMA-Factory 等 GPU 训练工具。

## SFT

知识类样本：

```json
{
  "messages": [
    {"role": "user", "content": "《中华人民共和国工会法》第五十一条第一款是怎么规定的？"},
    {"role": "assistant", "content": "〔《中华人民共和国工会法》（2021年修正）第五十一条第一款〕\n> ……"}
  ],
  "meta": {"kind": "recite|lookup|paraphrase_qa|relation", "clause_ids": ["..."]}
}
```

行为类样本：

```json
{
  "messages": [
    {"role": "system", "content": "……每轮最多追问 4 个问题……"},
    {"role": "user", "content": "我们单位领导不让搞工会"},
    {"role": "assistant", "content": "为了准确判断，请补充以下信息：\n1. ……？"}
  ],
  "meta": {"kind": "intent|consult|multi_violation|exception|refusal|article|revision|general", "clause_ids": ["..."], "max_questions": 4}
}
```

- 助手消息遵守 [citation-format.md](./citation-format.md)。
- `max_questions` 在 2–6 之间随机，并写入 system prompt（research R6）。
- 普法文章样本中的人物与单位一律为虚构名称。
- 数据集按 9:1 划分训练集与验证集（mlx-lm 需要 `train.jsonl`、`valid.jsonl`）。

## 去重要求

每个数据集清单记录 `dedup_against`（评测集版本）。生成时按条款与问句相似度剔除与评测用例过于接近的样本（宪章原则 V）。

## 正式阶段新增（POC 不实现）

- CPT 语料：`{"text": "...", "meta": {"clause_id": "...", "kind": "verbatim|paraphrase|bidirectional|relation|general"}}`
- DPO 样本：`{"messages": [...], "chosen": "...", "rejected": "...", "meta": {"error_type": "wrong_number|wrong_text|should_refuse"}}`
