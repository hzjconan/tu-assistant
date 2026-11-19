# 条款关联确认指南（T019 / T077）

`tu kb relations extract` 从条款原文中用规则抽出的**候选**关联，需要逐条人工确认后，才会进入训练数据、编排层关联补全兜底与 SC-005 评测指标。

> 历史基线 KB（已被数据集或评测 run 引用的版本）禁止原地修改；修改关系前须先用 `tu kb derive <旧版本>` 派生新 KB，再向新版本导入审阅差异。
>
> **版本管理约定：人工审阅文件入库，KB 不入库。** 审定后的审阅清单统一归档在受版本控制的 `data/relation-reviews/` 目录（只含 `clause_id`、决策与十余字触发片段），`artifacts/kb/` 下的 SQLite 知识库保持不入库、按需重建（完整复现链：`inputs/ → tu kb import → tu kb derive → tu kb relations confirm`）。

## 每行的含义

```json
{
  "from_clause_id": "<doc_id>:a10:p2",
  "to_clause_id": "<doc_id>:a38:p1",
  "relation_type": "liability_for",
  "origin": "rule",
  "decision": "pending",
  "confirmed": false,
  "evidence": "违反本条例第十条第二款",
  "scope": "explicit_paragraph"
}
```

- `relation_type`：
  - `liability_for`：`to` 条款是违反 `from` 条款时适用的法律责任；
  - `references`：`to` 条款引用 / 依照 `from` 条款；
  - `exception_of`：`to` 条款是 `from` 条款的例外情形。
- `scope`：`explicit_paragraph`（明指款）/ `explicit_item`（明指项）/ `single_paragraph_article`（单款条文）/ `whole_article_expanded`（整条引用多款条文后按款展开，需逐款判断该款是否属于实质义务/禁止性条款）。
- `evidence`：`to` 条款中触发该候选的原文引用片段，供核对款号与项号是否对齐。
- `decision`（四态，同时向后兼容旧版仅写布尔 `confirmed` 的文件）：
  - `confirm`：确认有效，写入新 KB（`confirmed=1`）；
  - `revoke`：撤销新 KB 中已存在的错误旧边（删除该行）；
  - `reject`：拒绝候选，不入库（不影响文件中未列出的已有已确认边）；
  - `pending`：待查，暂不入库（同样不影响未列出的已有边）。

`clause_id` 读法：`a10` = 第 10 条，`p2` = 第 2 款，`i1` = 第 1 项。

## 核对与导入步骤

1. 在新派生的 KB 上抽取候选：

   ```bash
   uv run tu kb relations extract --kb-version <新版本>
   ```

2. 交互核对（自动展示含子项的完整原文、被引条总款数与触发片段）：

   ```bash
   uv run tu kb relations review <pending.jsonl> --kb-version <新版本>
   ```

   交互按键：`回车 / y` = `confirm`，`n` = `reject`，`p / s` = `pending`（待查），`r` = `revoke`（撤销旧边）。也可配合 `uv run tu kb lookup "<clause_id>" --kb-version <新版本>` 随时抽查。

3. 事务化差异导入（必须显式指定 `--kb-version`，拒绝写入历史/只读版本；任一行格式错误或端点不存在则整批回滚）：

   ```bash
   uv run tu kb relations confirm <review.jsonl> --kb-version <新版本> --batch batch1-liability
   ```

   同一批次文件重复导入幂等；每次导入的批次、文件 SHA-256 与统计会记入新 KB 的 `manifest.json`。

## 判断技巧

- **核对款号与项号**：`evidence` 明指“第X条第Y款”时，确认 `from_clause_id` 精确落在 `pY`，不要误认到 `p1`；
- **整条展开逐款取舍**：`scope=whole_article_expanded` 时，剔除纯定义、宣示性或与该责任无关的款；
- **真关联 vs 假关联**：只提及编号（如“载明本法第X条所列事项”“第X条所称……是指……”）不是法律责任关系，应标 `reject`；
- **拿不准先标 `pending` 或 `reject`**：错的关系比漏的危害大（兜底会补错条款，训练会学错映射）。
