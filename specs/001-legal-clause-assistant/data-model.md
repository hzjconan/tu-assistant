# Data Model: 工会法律条款智能助手

**Feature**: `001-legal-clause-assistant` | **Date**: 2026-11-10 | **Plan**: [plan.md](./plan.md)

存储约定：
- **知识库**（LegalDocument / Clause / ClauseRelation）存于 SQLite（`artifacts/kb/<kb_version>.sqlite`），
  每次入库变更生成新的知识库版本；训练与评测都引用具体的 `kb_version`。
- **评测集**（EvalCase）以 JSONL 存于仓库 `eval/cases/`，随代码版本化提交（内容全部来自公开资料或合成）。
- **训练数据、模型适配器、评测报告、实验记录**存于 `artifacts/`（不提交 git），每个产物带一份清单（manifest）。
- **会话**只在内存中存在，不落盘（FR-009、FR-033）。

---

## 1. 知识库

### LegalDocument（法律文件）

| 字段 | 类型 | 说明 |
|---|---|---|
| `doc_id` | str | 稳定 ID：文件全称 + 版本的哈希 |
| `title` | str | 文件全称，如《中华人民共和国工会法》 |
| `issuer` | str? | 发布机关 |
| `level` | str? | 层级（法律 / 行政法规 / 部门规章 / 其他），以项目方提供为准，不预设 |
| `version_label` | str | 版本标识，如"2021年修正" |
| `promulgated_on` | date? | 发布或修正日期 |
| `status` | enum | `current` / `amended` / `repealed` |
| `source_file` | str | 原始文件名与 SHA-256 |
| `corpus` | enum | `project`（项目方提供）；正式阶段增加 `scaling`（规模扩展用公开文档） |

**校验规则**：同一 `title` 至多一个 `status=current`；正式阶段 `corpus=scaling` 的文件不进入正式知识库版本（宪章"数据与合规约束"）。

### Clause（条款）

| 字段 | 类型 | 说明 |
|---|---|---|
| `clause_id` | str | `doc_id` + 条/款/项编号 |
| `doc_id` | str | 所属文件 |
| `article_no` | int | 条号（整数） |
| `paragraph_no` | int? | 款号（条内第几款），无则为空 |
| `item_no` | int? | 项号（（一）→1），无则为空 |
| `number_text` | str | 原始编号写法，如"第五十一条第一款" |
| `heading_path` | list[str] | 所在编 / 章 / 节标题 |
| `text` | str | 原文（逐字） |
| `clause_type` | enum | `obligation` / `prohibition` / `right` / `liability` / `other` |
| `parse_warnings` | list[str] | 入库校验发现的问题（编号缺失、重复等） |

**校验规则**：同一文件内 (`article_no`, `paragraph_no`, `item_no`) 唯一；条号连续性缺口记入 `parse_warnings`（FR-005）。

### ClauseRelation（条款关联）

| 字段 | 类型 | 说明 |
|---|---|---|
| `from_clause_id` | str | 起点条款 |
| `to_clause_id` | str | 终点条款 |
| `relation_type` | enum | `liability_for`（违反后适用的法律责任）/ `references`（引用）/ `exception_of`（例外） |
| `origin` | enum | `rule`（规则抽取）/ `llm`（模型辅助）/ `manual`（人工） |
| `confirmed` | bool | 是否经人工确认；只有确认过的关联用于训练数据和关联补全指标 |

### Citation（出处）

模型输出中的一处条款引用，解析自引用标记（见 [contracts/citation-format.md](./contracts/citation-format.md)）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `raw` | str | 原始标记文本 |
| `title` / `version_label` | str | 解析出的文件名与版本 |
| `article_no` / `paragraph_no` / `item_no` | int? | 解析出的编号 |
| `quoted_text` | str? | 模型给出的原文 |
| `resolved_clause_id` | str? | 在知识库中找到的条款 |
| `verdict` | enum | `ok` / `corrected`（原文被替换）/ `not_found`（已删除）/ `incomplete`（裸引用） |

---

## 2. 对话

### Session（会话，仅内存）

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | str | 随机 ID |
| `messages` | list[Turn] | 各轮消息 |
| `intent` | enum? | `consult` / `article` / 未确认为空 |
| `user_entities` | set[str] | 从用户消息中抽取的候选身份信息，用于 FR-030 检查 |
| `config` | dict | 本会话生效的配置（`max_questions_per_turn` 等） |

**状态流转**：`intent=空`（追问意图）→ `consult` 或 `article`；用户可在会话中途改变意图（FR-013）。会话结束即销毁。

### Turn（一轮消息）

| 字段 | 类型 | 说明 |
|---|---|---|
| `role` | enum | `user` / `assistant` |
| `content` | str | 交付给用户的内容（Markdown，已经过校验层） |
| `raw_content` | str? | 模型原始输出（校验前），仅评测时保留 |
| `citations` | list[Citation] | 本轮输出中的引用及校验结果 |
| `question_count` | int? | 本轮追问的问题数（FR-011 指标） |

### ViolationFinding（违法行为认定）

从咨询回答或普法文章中解析出的结构化结果，用于评测打分。

| 字段 | 类型 | 说明 |
|---|---|---|
| `actor` | str | 违法主体（不预设类型，FR-017） |
| `conduct` | str | 行为事实 |
| `applicable` | list[Citation] | 适用条款 |
| `liability` | list[Citation] | 法律责任条款 |

---

## 3. 评测

### EvalCase（评测用例，`eval/cases/*.jsonl`）

| 字段 | 类型 | 说明 |
|---|---|---|
| `case_id` | str | 稳定 ID |
| `category` | enum | `clause_id` / `multi_violation` / `exception` / `refusal` / `false_refusal` / `intent` / `article` |
| `input` | object | 单轮：`{"message": str}`；多轮：`{"script": [str, ...]}`（固定对话脚本，预先写好用户每轮说的话） |
| `gold` | object | 标准答案：`clauses`（应引用的条款 ID 集合）、`violations`（主体 + 条款）、`intent`、`should_refuse`、评分要点 `rubric` |
| `source` | enum | `public_case` / `manual` / `synthetic_reviewed` |
| `eval_set_version` | str | 所属评测集版本 |

**校验规则**：`gold.clauses` 中的条款必须存在于对应知识库版本；`source=synthetic_reviewed` 须有人工校验记录；
任何用例不得来自真实用户对话（宪章原则 III）。

### EvalRun（一次评测）

| 字段 | 类型 | 说明 |
|---|---|---|
| `run_id` | str | |
| `system` | object | 被测系统：基座、适配器 ID（`exp_id`）、配置哈希 |
| `kb_version` / `eval_set_version` | str | |
| `kb_scale` | int | 知识库文档数（POC 为 30–50；正式阶段用于规模曲线） |
| `results` | list[CaseResult] | 逐条结果：输出（校验前 / 后）、解析出的引用与认定、各指标得分 |
| `metrics` | dict | SC-001 ~ SC-011 汇总值；引用准确率分校验前 / 后 |

### ReviewComment（人工评审意见，FR-037；POC 用表格记录，列与下表一致）

| 字段 | 类型 | 说明 |
|---|---|---|
| `run_id` / `case_id` | str | 关联到具体输出 |
| `reviewer` | str | 评审人（项目方 / 法律专业人员） |
| `verdict` | enum | `pass` / `minor_issue` / `fail` |
| `comment` | str | 意见 |
| `created_at` | datetime | |

只对评测输出做评审，不评审真实用户会话。

---

## 4. 训练与实验

### TrainingSample（训练样本，JSONL）

格式见 [contracts/datasets.md](./contracts/datasets.md)。每个数据集带清单：

| 字段 | 说明 |
|---|---|
| `dataset_id` | |
| `stage` | POC 仅 `sft`；正式阶段增加 `cpt` / `dpo` |
| `kb_version` | 生成所依据的知识库版本 |
| `generator` | 合成所用提供方、模型名、提示词版本、随机种子 |
| `counts` | 各样本类型条数与 token 数 |
| `dedup_against` | 已与之去重的评测集版本 |

### ExperimentRun（一次训练实验）

| 字段 | 说明 |
|---|---|
| `exp_id` | |
| `base_model` | 基座名称与版本（含许可证） |
| `datasets` | 使用的 `dataset_id` 列表与混合比例 |
| `method` | POC 为 `mlx_qlora`（正式阶段可为 `lora_bf16` / `full`）及超参（rank、学习率、轮数、序列长度、梯度检查点） |
| `hardware` | 机器型号与内存（POC 为本机 M1 Pro / 32GB） |
| `seed` | 随机种子 |
| `outputs` | 适配器路径、训练日志、耗时、峰值显存 / 内存 |
| `eval_runs` | 关联的 `run_id`（宪章原则 V：影响模型行为的变更须附回归评测） |
