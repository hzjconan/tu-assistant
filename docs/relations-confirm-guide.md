# 条款关联确认指南（T019）

`tu kb relations extract` 从条款原文中用规则抽出的**候选**关联，需要你逐条
确认后才会被训练数据和"关联补全兜底"使用。

## 文件位置

`artifacts/kb/<kb_version>-relations_pending.jsonl`（当前：
`kb-20261113-071600-relations_pending.jsonl`，共 68 条）

## 每行的含义

```json
{
  "from_clause_id": "<doc_id>:a4:p1",       // 被引用的条款（如被违反的义务条款）
  "to_clause_id": "<doc_id>:a50:p1",        // 含有该引用的条款（如法律责任条款）
  "relation_type": "liability_for",          // 关系类型
  "origin": "rule",                          // 抽取方式（rule=规则）
  "confirmed": false                         // ← 你要改的字段
}
```

- `liability_for`：to 条款是"违反 from 条款"时适用的法律责任；
- `references`：to 条款引用/依照 from 条款；
- `exception_of`：to 条款是 from 条款的例外情形。

`clause_id` 的读法：`a4` = 第 4 条，`p1` = 第 1 款，`i2` = 第 2 项。

## 怎么确认

1. 用 `tu kb lookup` 直接按 `clause_id` 查条款原文核对，例如：

   ```bash
   uv run tu kb lookup "3296db5b22b8ea1d:a24:p1"
   ```

   输出含文件全称、版本、条款号和原文。

   （`doc_id` 是"标题+版本"的哈希，看不出文件名；`tu kb list` 可对照全部文件，
   也可用 `tu kb show <文件全称> 4 -p 1` 按标题查。）

2. 把每行的 `confirmed` 改成：
   - `true`：关系真实成立；
   - `false`：只是碰巧提到编号，或关系类型不对。

3. 如果你发现规则**漏抽**了某条关联，也可以手动在文件末尾加一行
   （`origin` 改成 `"manual"`，`confirmed: true`）。

4. 全部确认完后导入：

   ```bash
   uv run tu kb relations confirm artifacts/kb/kb-20261113-071400-relations_pending.jsonl
   ```

## 判断技巧

- 真关联：to 条款里的"第X条"指向**另一条款的实质内容**（违反它、依照它、排除它）；
- 假关联：只是提及编号（如"本法第X条所称的'工会'是指……"——这是解释名词）；
- 拿不准的宁可标 `false`：错的关系比漏的危害大（兜底会补错条款）。
