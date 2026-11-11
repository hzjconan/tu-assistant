# Contract: 命令行工具 `tu`

所有流程通过同一个命令行入口执行；正式阶段扩展到 1000 篇时沿用同一套命令（宪章原则 VI）。
每个命令把产物写入 `artifacts/` 并生成清单（manifest）；命令出错时返回非零退出码。

## 知识库

| 命令 | 说明 | 产物 |
|---|---|---|
| `tu kb import <dir>` | 导入目录下的文档，拆分条款，入库校验（POC 阶段整批重导） | 新的 `kb_version`；校验问题清单 `parse_report.md` |
| `tu kb relations extract` | 用规则抽取条款关联，待人工确认 | `relations_pending.jsonl` |
| `tu kb relations confirm <file>` | 导入人工确认结果 | 更新 `kb_version` |
| `tu kb show <title> <article_no>` | 查看某条款，便于人工核对 | — |

## 数据合成与训练

| 命令 | 说明 | 产物 |
|---|---|---|
| `tu synth sft --kb <ver>` | 生成训练样本（知识类 + 行为类，见 research R3） | `dataset_id` + manifest |
| `tu synth evalcases --kb <ver>` | 生成评测候选用例（需人工校验后才能进入评测集） | `eval/cases/candidates/*.jsonl` |
| `tu train --config configs/train/<name>.yaml` | 本机 MLX QLoRA 训练 | `exp_id` + 适配器 + 日志 |

## 运行

| 命令 | 说明 |
|---|---|
| `tu serve model --exp <exp_id>` | 启动本地模型端点（`mlx_lm.server`） |
| `tu chat` | 命令行多轮对话；`/save <path>` 保存最后一轮为 `.md` |
| `tu ui` | 启动本地网页演示界面 |

## 评测

| 命令 | 说明 | 产物 |
|---|---|---|
| `tu eval run --exp <exp_id> --kb <ver> --cases <eval_set_version>` | 运行评测（不调用外部服务） | `run_id`、`report.md`、`results.jsonl` |
| `tu eval compare <run_id>...` | 对比多次评测（同一评测集与口径），用于看数据调整前后的变化 | `compare.md` |

POC 阶段人工评审意见用表格记录（spec FR-037）。

## 正式阶段新增（POC 不实现）

`tu synth cpt`（继续预训练语料）、`tu kb import --corpus scaling`（规模扩展文档）、`tu chat --system b`（检索对照组）、
`tu eval curve`（规模曲线）、`tu eval review import`（系统内录入评审意见）。
