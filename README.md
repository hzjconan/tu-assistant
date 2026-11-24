# tu-assistant

工会法律条款智能助手（POC）：将项目方提供的 **24 篇公开法律文档**（3,809 条记录）通过 QLoRA 微调“训进”自有本地模型，提供**多轮对话法律条款咨询（识别条款 + 引用出处）**与**以案说法普法文章生成**；**运行时完全私有化本地执行、零外部 API 调用**，条款原文与身份脱敏由确定性校验层兜底。

> **当前阶段：POC 开发与全量验证已收官**（本机 Apple Silicon M1 Pro / 32GB 验证通过）。详见 [需求规格](./specs/001-legal-clause-assistant/spec.md)、[现场演示剧本](./docs/demo-scenarios.md) 与 [全项目复盘终章](./docs/learning/08-lessons-and-next.md)。

---

## POC 状态与核心基线

| 维度 | 活跃基线 / 实测结果 | 详细记录 |
|---|---|---|
| **语料与活跃知识库** | `kb-20261119-045641`（24 篇法规 / 3,809 条记录 / 67 条已确认关联：`liability_for` 26 + `references` 41） | [第 3 章 知识库](./docs/learning/03-knowledge-base.md) |
| **冻结 7B 演示模型** | `exp-20261116-resume500`（`Qwen2.5-7B-Instruct-4bit`，Apache 2.0，LoRA `77 MB`；1.5B 流程验证 `exp-20261114-120250`） | [POC 训练总结](./docs/experiments/poc-training-summary.md) |
| **SFT 有效性验证（`SC-016`）** | **PASS**（60 题条级 `1/60 → 17/60`，款级 `9/60 = 15.0%`，基座未知文件子集 `0/30 → 21/30`） | [POC 训练总结](./docs/experiments/poc-training-summary.md) |
| **重复评测稳定性（`SC-015`）** | **PASS**（`eval/cases/v1/` 全 7 类 98 题两轮独立冷启动最大波动 **`0.0 pp`**） | [T064 重复评测](./docs/experiments/T064-eval-repeatability.md) |
| **端到端验收（`quickstart.md`）** | **V1–V7 + US4 全 8 场景 PASS**（含 7B + Gradio UI 10 分钟黄金主线与脱敏/零外连核查） | [T071 验证记录](./docs/experiments/T071-quickstart-verification.md) |
| **确定性自动化测试** | `uv run --offline --no-sync pytest` **462 passed, 6 xfailed**，`ruff check src tests` 全绿 | [T071 验证记录](./docs/experiments/T071-quickstart-verification.md) |

**客观边界声明（详阅 [第 8 章 复盘](./docs/learning/08-lessons-and-next.md)）**：
1. **不以精选演示题冒充全库召回，不外推至 1,000 篇**：98 题全量实测 `SC-002 = 0.121`、`SC-003 = 0.188`，引用准确率校验前 `0.405` → 校验后 `0.669`（已定位引用 `0.589 → 0.973`）；1,000 篇规模曲线（`SC-012`）与 RAG 对照留待正式阶段。
2. **功能边界（路线 A 与主动追问）**：按 [T075 实验结论](./docs/experiments/T075-article-training.md)，冻结演示模型未合入文章续训权重，普法文章限于给定案情与核准条款的预审单篇演示；主动追问能力（`intent` 首轮反问）尚未学会。
3. **已知缺陷 `T078`**：《上海市工伤保险实施办法》（63/63 条）括号条旨误切为第 1 款导致款号顺延 `+1`，POC 阶段保持 KB 与基线不动，已建档移至正式阶段修复。

---

## 环境与前置条件

- **硬件**：macOS（Apple Silicon）。**训练建议 ≥32GB 统一内存**（MLX 4bit QLoRA 开启 `grad_checkpoint: true` 峰值约 `11.5–13.5 GB`）；**仅运行演示建议 ≥16GB（推荐 32GB）**。
- **软件**：Python `3.12` + [uv](https://docs.astral.sh/uv/)（`uv sync` 按 `uv.lock` 精确还原 `mlx-lm 0.32.2`、`gradio 6.31.0` 等依赖）。
- **外部大模型 API Key（仅离线数据合成需要）**：在仓库根目录创建 `.env`（已被 `.gitignore` 忽略）写入 `TU_EXTERNAL_LLM_API_KEY=sk-...`，默认对接 DeepSeek（见 [configs/synth.yaml](./configs/synth.yaml)）；**运行时推理、对话、UI、评测均零外部服务调用**。
- **Hugging Face 国内加速与离线模式**：首次拉取基座模型必设 `export HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1`；基座进入本机缓存后可配合 `HF_HUB_OFFLINE=1` 与 `uv run --offline --no-sync` 完全断网运行。

---

## 快速开始（按场景选择）

### 场景 A：已有演示产物 / 换机直接运行（约 5 分钟）

`artifacts/` 不在 Git 中。若已有最小演示产物包（**4 个文件、共约 79 MB**：`manifest.json`、`adapters/adapters.safetensors`、`adapters/adapter_config.json`、`kb-20261119-045641.sqlite`），按 [换机迁移指南](./docs/demo-scenarios.md#9-换机器演示与最小产物迁移指南) 解压到仓库根目录，运行 `uv sync` 后开**两个终端**：

**终端 1：启动本地模型服务（仅监听 `127.0.0.1:8080`）**

```bash
# 首次运行需下载 7B 4bit 基座（约 4.4 GB）；已缓存后可改用 HF_HUB_OFFLINE=1 断网启动
HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1 \
  uv run tu serve model --exp exp-20261116-resume500
```

等待终端出现 `Starting httpd at 127.0.0.1 on port 8080...`。

**终端 2：启动本地 Gradio 演示界面（仅监听 `127.0.0.1:7860`）**

```bash
# 推荐：--temperature 0.0 与 SC-015 零波动评测基线一致；如需轻微措辞变化可省略（默认 0.7）
uv run tu ui --temperature 0.0 --inbrowser
```

浏览器打开 `http://127.0.0.1:7860` 即可演示（支持多轮对话、「新会话」释放内存、「保存当前回复为 Markdown」、严禁公网共享、未开终端 1 时提供中文引导，演示完双终端 `Ctrl+C` 停止）。建议按 [docs/demo-scenarios.md](./docs/demo-scenarios.md) 的 10 分钟黄金主线演练；命令行备选：`uv run tu chat`（内置 `/new`、`/save <路径.md>`、`/quit`）。

### 场景 B：从零复现全流程

**步骤 0：还原环境与跑通测试**

```bash
uv sync
uv run --offline --no-sync pytest
uv run --offline --no-sync ruff check src tests
uv run --offline --no-sync tu version
```

**步骤 1：语料入库与知识库维护**

```bash
# 预期：24 篇法规 / 3,809 条记录 / 问题 24 个（缺显式版本标签）
uv run tu kb import inputs/project/001
uv run tu kb list
uv run tu kb show "中华人民共和国劳动法" 24
uv run tu kb diff <old_ver> <new_ver> --summary-only
uv run tu kb derive <source_kb>   # 派生新库补齐多款条文第 1 款显式款号（不动旧库）
```

> **防劫持提示**：[configs/app.yaml](./configs/app.yaml) 默认 `kb.version: null`（自动加载最新 SQLite），且新导入库的已确认关联为 `0` 条。在已有活跃库机器上仅测试入库时，务必加 `--artifacts /tmp/kb-test` 隔离，或在 `configs/app.yaml` 中显式锁定 `kb.version: "kb-20261119-045641"`。

**步骤 2：条款关联抽取 → 人工审阅 → 差异导入**

```bash
uv run tu kb relations extract --kb-version <ver>
uv run tu kb relations review artifacts/kb/<ver>-relations_pending.jsonl --kb-version <ver>
uv run tu kb relations confirm artifacts/kb/<ver>-relations_pending.jsonl --kb-version <ver>   # --kb-version 必填
```

审定清单归档在 `data/relation-reviews/`，详细规则见 [docs/relations-confirm-guide.md](./docs/relations-confirm-guide.md)。

**步骤 3：外部大模型合成 SFT 训练数据（需 `.env` API Key）**

```bash
set -a && source .env && set +a
uv run tu synth sft   # 产出 artifacts/datasets/ds-<kb>-<N>/；调试可加 --skip-llm
```

增量重建可组合 `--reuse-dataset`、`--reuse-only`、`--refresh-relations`、`--articles-file` 与 `--preserve-split`。

**步骤 4：本机 QLoRA 训练（1.5B 调试 / 7B 演示）**

> **硬件互斥提醒**：M1 Pro 32GB 下**训练前务必停止 `tu serve model` 与 `tu ui`**，否则统一内存叠加至 `22.5–28.5+ GB` 极易卡顿或 OOM。

```bash
export HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1
uv run tu train --config configs/train/debug-1.5b.yaml   # 实测约 2–4 小时 / 2 epoch（历史基线约 4 小时），流程验证
uv run tu train --config configs/train/demo-7b.yaml      # 已默认 grad_checkpoint: true，约 12–14 h/epoch
```

**步骤 5：评测、报告与版本对比**（先启动终端 1 `tu serve model`）

```bash
uv run tu eval run --exp exp-20261116-resume500 --cases eval/cases/smoke
uv run tu eval run --exp exp-20261116-resume500 --cases eval/cases/v1
uv run tu eval report <run_id> --reviews eval/reviews/t064-reviews.csv
uv run tu eval compare <run1> <run2> --sc015 --reviews eval/reviews/t064-reviews.csv --save
uv run tu eval compare --sc016 <base_run> <trained_run>   # 恰好 2 个 run ID，不可与 --sc015/--out/--save/--reviews 混用
```

全部 V1–V7 + US4 验证步骤见 [specs/001-legal-clause-assistant/quickstart.md](./specs/001-legal-clause-assistant/quickstart.md)。

---

## 常用命令速查（`tu` CLI）

下表覆盖 `src/tu_assistant/cli.py` 全部 **21 个注册子命令**（详细参数以 `uv run tu <子命令> --help` 为准）：

| 分组 | 命令与必选 / 高频参数 | 说明 |
|---|---|---|
| **基础与知识库** | `tu version` | 输出版本号（`tu-assistant 0.1.0`） |
| | `tu kb import <dir> [--artifacts]` | 批量导入法规文档生成新版本 SQLite 与 `parse_report.md` |
| | `tu kb derive <source_kb> [--kb-version] [--artifacts]` | 从历史 KB 派生新版本，补齐多款条文第 1 款显式款号（原文与原有关联不变，不动旧库） |
| | `tu kb list [--kb-version] [--artifacts]` | 列出知识库中的法律文档清单与条款统计 |
| | `tu kb show <title> <article_no> [-p] [-i] [--kb-version]` | 按书名与条/款/项号查询条款原文 |
| | `tu kb lookup <clause_id> [--kb-version]` | 按内部 `clause_id` 精确查询单条记录 |
| | `tu kb diff <v1> <v2> [--summary-only] [--artifacts]` | 对比两版 KB 的新增/删除/修订条款（零条文正文泄漏） |
| **条款关联** | `tu kb relations extract [--kb-version] [--out]` | 基于规则抽取显式条款引用候选到 JSONL |
| | `tu kb relations review <file> [--kb-version]` | 终端交互式审阅关联候选（四态标注） |
| | `tu kb relations confirm <file> --kb-version <ver> [--batch]` | 事务化差异导入已确认关联（`--kb-version` 必填） |
| **合成与训练** | `tu synth evalcases [--kb-version] [--n] [--synth-config]` | 用独立提示词生成评测候选用例 |
| | `tu synth sft [--kb-version] [--skip-llm] [--reuse-dataset] ...` | 合成 SFT 样本、质检、去重并构建 train/valid 数据集 |
| | `tu train --config <yaml> [--artifacts]` | 封装 `mlx_lm lora` 训练并写入 `manifest.json` |
| **服务与交互** | `tu serve model --exp <exp_id> [--host] [--port]` | 动态挂载 LoRA 启动 `mlx_lm.server`（限 `127.0.0.1`/`localhost`） |
| | `tu chat [--config] [--kb-version] [--artifacts]` | 命令行多轮对话（`/new`、`/save <path>`、`/quit`） |
| | `tu ui [--temperature <float>] [--port 7860] [--inbrowser]` | 启动本地 Gradio 演示界面（`--host` 仅允许 `127.0.0.1`；默认温度 `0.7`，演示推荐 `0.0`） |
| **评测与审核** | `tu eval cases review <file> [--kb-version]` | 终端交互式人工核对候选用例：查看问题与 `gold` 条款并标记 `confirmed`（原地回写 JSONL） |
| | `tu eval cases promote <file> [--out]` | 将审定通过的候选用例晋升写入正式评测集 |
| | `tu eval run --cases <path> [--exp] [--kb-version] [--no-system-prompt]` | 运行单轮或固定脚本评测并输出 `results.jsonl` / `report.md` |
| | `tu eval report <run_id> [--reviews] [--out]` | 只读重渲染指定 run 报告（可叠加人工评审 CSV） |
| | `tu eval compare <run1> <run2>... [--sc015\|--sc016] [--reviews] [--save]` | 同口径多版本对比、`SC-015` 稳定性或 `SC-016` 验收判定 |

---

## 仓库结构

| 路径 | 内容说明 |
|---|---|
| `src/tu_assistant/` | 主源码：`kb/`、`citation/`、`chat/`、`runtime/`、`synth/`、`train/`、`eval/`、`ui/`、`cli.py`、`config.py`、`manifest.py` |
| `configs/` | [app.yaml](./configs/app.yaml)（运行时与 KB 配置）、[synth.yaml](./configs/synth.yaml)（外部合成配置）、`train/`（1.5B / 7B 训练配置） |
| `inputs/` | `inputs/project/001/`（24 篇公开法律语料，已入库 Git）；`inputs/excluded/`（4 篇评估排除文件） |
| `data/relation-reviews/` | 人工审定并归档的三份条款关联审阅清单 |
| `eval/` | `cases/smoke/`（2 题）、`cases/v1/`（98 题全 7 类）、`review-template.csv`、`reviews/t064-reviews.csv`、`diagnostics/` |
| `tests/` | 确定性单元测试与集成测试（基线 `462 passed, 6 xfailed`） |
| `scripts/` | 数据整理、训练守护与实验诊断脚本 |
| `docs/` | 演示剧本、条款关联指南、实验记录、学习文档（00–08 完结版）、任务执行单 |
| `specs/001-legal-clause-assistant/` | SDD 规格、实施计划、技术决策、数据模型、接口契约、任务清单与验证步骤 |
| `.specify/memory/constitution.md`、`AGENTS.md` | 项目核心原则（宪章）与开发/安全约定 |

**不入 Git 的本地文件**：`artifacts/`（知识库 SQLite、数据集、LoRA 适配器、评测输出与日志，可按场景 B 重建或通过 4 文件 79 MB 最小包迁移）与 `.env`（外部大模型 API Key）。

---

## 常见问题与注意事项

1. **`kb.version: null` 防劫持与知识更新需重训**：本地测试重导请加 `--artifacts /tmp/<dir>` 隔离或在 [configs/app.yaml](./configs/app.yaml) 显式锁定 `kb.version`；仅切库只更新校验层原文，新增或实质修订条款须重抽关联并重训模型（见 [quickstart.md](./specs/001-legal-clause-assistant/quickstart.md)）。
2. **训练与演示不可同开**：M1 Pro 32GB 同时运行 `tu train` 与 `tu serve model` / `tu ui` 会叠加内存至 `22.5–28.5+ GB` 导致卡顿或 OOM，须严格串行（原理见 [L7.6](./docs/learning/07-serving-demo.md#l76-为什么训练与演示不能在-m1-pro32gb上同时进行)）。
3. **HF 下载极慢或断网离线运行**：拉取基座必设 `HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1`；基座进入本机缓存后可设 `HF_HUB_OFFLINE=1` 并配合 `uv run --offline --no-sync` 完全离线运行。
4. **长样本训练显存与防休眠**：7B 训练配置已默认开启 `grad_checkpoint: true`（峰值约 23 GB → 11.5 GB）；长时间合成或训练可用 `caffeinate -is -w <PID>` 防休眠。
5. **代理导致 `git push` 返回 503**：若系统 HTTP/HTTPS 代理干扰 Git 推送，可临时取消代理变量：`env -u http_proxy -u https_proxy git push`。
6. **`tu ui` 提示无法连接模型服务或端口占用**：确认终端 1 的 `tu serve model` 已就绪（`127.0.0.1:8080`），若 `7860` 被占用可传 `--port 7861`；演示切场景前务必先点「新会话」。

---

## 文档索引

### 1. 演示、操作与验收指南

| 文档 | 说明 |
|---|---|
| [docs/demo-scenarios.md](./docs/demo-scenarios.md) | 10 分钟现场黄金主线、5 大场景库、汇报边界与 4 文件 79 MB 换机迁移指南 |
| [docs/experiments/T071-quickstart-verification.md](./docs/experiments/T071-quickstart-verification.md) | `quickstart.md` V1–V7 + US4 全 8 场景端到端验收记录 |
| [docs/relations-confirm-guide.md](./docs/relations-confirm-guide.md) | 条款关联四态审阅与事务化差异导入指南 |
| [specs/001-legal-clause-assistant/quickstart.md](./specs/001-legal-clause-assistant/quickstart.md) | POC 全部验证场景步骤与知识更新操作说明 |

### 2. 实验诊断与评测报告

| 文档 | 说明 |
|---|---|
| [docs/experiments/README.md](./docs/experiments/README.md) | 实验记录总目录与编号规范 |
| [docs/experiments/poc-training-summary.md](./docs/experiments/poc-training-summary.md) | POC 训练目标达成结论、`SC-016` 判定与正式阶段路线判断 |
| [docs/experiments/T064-eval-repeatability.md](./docs/experiments/T064-eval-repeatability.md) | 冻结 7B 98 题两轮冷启动重复评测与 `SC-015`（`0.0 pp`）报告 |
| [docs/experiments/T075-article-training.md](./docs/experiments/T075-article-training.md) | 文章样本续训实验、回归门槛判定与路线 A 决策 |
| [E001](./docs/experiments/E001-1.5b-citation-failure.md) · [E002](./docs/experiments/E002-eval-served-base-model.md) · [E003](./docs/experiments/E003-memorization-vs-exposure.md) | 7B NaN 修复、误测基座事故排查、曝光与泛化实验 |

### 3. 配套学习文档（00–08 全套完结，按 `[L章.节]` 编号）

- 总目录与阅读顺序：[docs/learning/README.md](./docs/learning/README.md)
- 基础与数据：[00 术语表](./docs/learning/00-glossary.md) · [01 全局视角](./docs/learning/01-big-picture.md) · [02 硬件与环境](./docs/learning/02-hardware.md) · [03 知识库与出处校验](./docs/learning/03-knowledge-base.md) · [附录A 工具](./docs/learning/appendix-tools.md)
- 训练到收官：[04 训练数据](./docs/learning/04-training-data.md) · [05 模型训练](./docs/learning/05-training.md) · [06 质量评测](./docs/learning/06-evaluation.md) · [07 推理与演示](./docs/learning/07-serving-demo.md) · [08 复盘与演进](./docs/learning/08-lessons-and-next.md)

### 4. 规格、契约与项目约定（SDD）

- 项目原则与约定：[项目宪章（constitution.md）](./.specify/memory/constitution.md) · [开发与安全约定（AGENTS.md）](./AGENTS.md)
- 需求与规划：[需求规格（spec.md）](./specs/001-legal-clause-assistant/spec.md) · [实施计划（plan.md）](./specs/001-legal-clause-assistant/plan.md) · [技术决策（research.md）](./specs/001-legal-clause-assistant/research.md) · [数据模型（data-model.md）](./specs/001-legal-clause-assistant/data-model.md) · [任务清单（tasks.md）](./specs/001-legal-clause-assistant/tasks.md)
- 接口契约：[CLI（contracts/cli.md）](./specs/001-legal-clause-assistant/contracts/cli.md) · [引用格式（citation-format.md）](./specs/001-legal-clause-assistant/contracts/citation-format.md) · [数据集格式（datasets.md）](./specs/001-legal-clause-assistant/contracts/datasets.md) · [系统接口（system-interface.md）](./specs/001-legal-clause-assistant/contracts/system-interface.md)
