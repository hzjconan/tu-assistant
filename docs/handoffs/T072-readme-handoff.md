# T072 执行单 · 更新根目录 `README.md`（POC 最终收官）

- **状态**：已完成并验收（2026-11-24，内部 2 轮独立只读复审通过，用户确认提交；POC 阶段正式收官）— 按方案 **`1A 2A 3A`** 实施
- **对应任务**：`specs/001-legal-clause-assistant/tasks.md` Phase 7 — **`T072`**（POC 阶段最后 1 项未完成任务；完成后 POC 阶段 `T001`–`T077` 全部清零，仅余已移出 POC 的正式阶段任务 `T078`）
- **Git 基线**：`814c4c6`（`main`，工作区干净；`T074` 已验收提交）
- **活跃产物与环境基线（本轮只读实测核验）**：
  - **运行环境**：Python `3.12.14`（`pyproject.toml` 要求 `>=3.12,<3.13`）、`mlx-lm 0.32.2`、`gradio 6.31.0`、`typer 0.29.1`、`pytest 9.2.0`、`ruff 0.17.4`、`tu-assistant 0.1.0`
  - **冻结 7B 演示模型**：`exp-20261116-resume500`（基座 `mlx-community/Qwen2.5-7B-Instruct-4bit`，Apache 2.0，约 `4.4 GB`；LoRA 适配器 `77.04 MB`，SHA-256 前缀 `b62a7d0e86f4`；从 iter-500 续训 `8,421` 步零 NaN，耗时 `49,593 s`，val loss `0.472`）
  - **1.5B 流程验证模型**：`exp-20261114-120250`（基座 `mlx-community/Qwen2.5-1.5B-Instruct-4bit`，`20.15 MB`）
  - **活跃知识库**：`artifacts/kb/kb-20261119-045641.sqlite`（24 篇法规 / 3,809 条记录 / 67 条已确认关联：`liability_for` 26 + `references` 41；SHA-256 `40d4ea70333404ccd9724fccddc09c51311de0123ea9416a37549fd7742f13bb`）
  - **活跃数据集**：`artifacts/datasets/ds-kb-20261119-045641-8247/`（去重 8,247 条，`train 8,962 / valid 820`，max `2,015 ≤ 2,048` token）
  - **评测集与验收基线**：`eval/cases/v1/` 98 题全 7 类（`reviewed.jsonl` 60 + `articles.jsonl` 10 + `multi_violation.jsonl` 10 + `intent.jsonl` 10 + `boundaries.jsonl` 8）+ `eval/cases/smoke/smoke.jsonl` 2 题；`SC-016` PASS（条级 `1/60 → 17/60`、`p=4.45e-05`；款级 `9/60 = 15.0%`；未知文件子集 `0/30 → 21/30`、`p=3.58e-09`）；`SC-015` PASS（T064 两轮冷启动 98 题波动 **`0.0 pp`**）；T071 `quickstart.md` V1–V7 + US4 全 8 场景 PASS
  - **当前服务元数据**：`artifacts/serve/current.json` 指向 `exp-20261116-resume500`（`model="default_model"`，`endpoint="http://127.0.0.1:8080/v1"`）
  - **自动化与只读门禁**：`uv run --offline --no-sync pytest` **462 passed, 6 xfailed**，`uv run --offline --no-sync ruff check src tests` 全绿，`shasum -a 256 -c artifacts/logs/t075/01/output.sha256` **25/25 OK**
- **不可逾越的红线**：
  1. **严禁读取 `inputs/` 目录下任何文件**（包括直接读取、grep 或运行任何输出其内容的脚本）；
  2. **纯文档边界**：本任务仅修改根目录 `README.md`（验收收尾时在本执行单末尾追加实施与复审记录；允许在 `.gitignore` 忽略的 `artifacts/logs/t072/` 下存放本地只读核查脚本，不入 Git）；**严禁改动 `src/`、`tests/`、`configs/`、`eval/`、`data/`、`specs/`、`docs/learning/`、`docs/experiments/`、`docs/demo-scenarios.md`、`AGENTS.md` 或任何历史产物**；
  3. **运行时零侵入**：不启动或触碰模型服务/UI，不改动 `artifacts/serve/current.json`、4 份历史 KB SQLite 与 T075 `output.sha256` 覆盖的 25 项文件；
  4. **验收门禁前不落账**：完成独立只读复审闭环并获用户明确确认前，不得勾选 `tasks.md` 中的 `T072`，不得执行 `git commit` 或 `git push`。

---

## 上篇：面向用户决策

### 1. 推荐任务编号与选择理由

**推荐推进 POC 阶段最后 1 项收官任务 `T072`（更新根目录 `README.md`：项目简介、环境准备、常用命令、文档索引）。**

| 维度 | 说明 |
|---|---|
| **为什么是最后压轴项** | `specs/001-legal-clause-assistant/tasks.md` 中 POC 阶段 77 项任务（`T001`–`T077`）已完成 76 项，仅剩 **`T072`**（`T078` 已明确标为 `[Post-POC / 正式阶段]` 移出 POC）。此前有意将 `T072` 压在 `T070`（演示剧本）、`T071`（全量验证）、`T073`（第 7 章）与 `T074`（第 8 章及术语表收口）全部验收提交之后，就是为了让全仓对外总入口 `README.md` 一次性定稿，做到零返工、零断链。 |
| **现有 `README.md` 摸底发现的 5 大关键缺口/隐患** | 现行 `README.md`（160 行，最后更新于 `3b944c9`）已明显落后于 Phase 7 定稿成果，直接照跑甚至会踩坑：<br>1. **POC 状态与边界过时**：仍写“目标是跑通全流程”，未体现全 8 场景验收通过、`SC-016` / `SC-015` 实测基线、冻结 7B 路线 A 限制与 `T078` 登记；<br>2. **三大高危操作隐患缺失预警**：① 直接运行 `tu kb import inputs/project/001` 会在默认 `kb.version: null` 下**静默劫持活跃库并让 67 条已确认关联归零**（缺 `--artifacts /tmp/...` 隔离与 `kb.version` 锁定提醒）；② 未提示 M1 Pro 32GB 上**训练与演示不可同时运行**（内存叠加 `22.5–28.5+ GB` 易 OOM/卡顿）；③ 缺现场演示推荐启动参数 `tu ui --temperature 0.0 --inbrowser`、4 文件（约 79 MB）换机迁移入口及 `HF_HUB_OFFLINE=1` 离线运行方式；<br>3. **CLI 常用命令覆盖不全**：`src/tu_assistant/cli.py` 实际注册 **21 个叶子命令**，现行 README 漏掉 `tu kb derive`、`tu kb lookup`、`tu kb diff --summary-only`、`tu synth evalcases`、`tu eval cases review/promote`、`tu version`，且未标注 `tu kb relations confirm` 的 `--kb-version` 为必填项、`--sc016` 仅接受 2 个 run ID 且与 `--sc015`/`--out`/`--save`/`--reviews` 互斥；<br>4. **文档索引严重残缺且不可点击**：现仅 5 行反引号纯文本，漏掉 `docs/demo-scenarios.md`、`docs/experiments/README.md`、`T071`、`T064`、`T075`、`poc-training-summary.md`、`docs/relations-confirm-guide.md`、已完结的 `docs/learning/00`–`08` 与 `appendix-tools.md`、以及 `specs/` 核心文档与 `.specify/memory/constitution.md`；<br>5. **仓库结构与个人杂项待打磨**：`仓库内容` 漏列 `tests/`、`scripts/`、`eval/reviews/`、`.specify/`；常见问题中写死了私人本机代理端口 `127.0.0.1:8002`。 |

---

### 2. 待用户拍板的决策清单

请审阅以下 3 项取舍并直接回复选择（例如 `1A 2A 3A`）：

1. **决策 1：`README.md` 的内容组织模式与篇幅定位**
   - **1A（推荐）：「场景分流 + 精炼全貌」架构（约 220–280 行）**
     - 结构：项目简介与 POC 验收基线看板 → **快速开始（场景 A：已有权重/换机约 5 分钟直接演示 vs 场景 B：从零全流程复现 0–5 步）** → 环境与前置条件 → **常用命令速查表（覆盖 `cli.py` 全部 21 个真实子命令）** → 仓库结构 → 常见问题与注意事项 → **分层可点击文档索引**（演示与验证 / 实验报告 / 学习文档 00–08 完结版 / 规格与宪章）。
     - *理由*：同时服务评审人、拿权重直接上台的演示者与从零复现的开发者；长篇细节全部下沉链接，避免重复维护，且弥补 `contracts/cli.md` 未收录后期子命令的不足。
   - **1B：「极简总目录」架构（约 150–180 行）**
     - 保留现有单线性步骤 0–6 骨架，只补上 POC 状态、三大安全预警、推荐演示参数与可点击文档索引；命令速查只列最常用 10 条，其余请用户自行执行 `tu --help`。
     - *理由*：更短更轻，但拿权重直接演示的读者需翻到中后段，且命令查漏需依赖终端 `--help`。

2. **决策 2：POC 实测基线与边界说明在 `README.md` 中的披露尺度**
   - **2A（推荐）：客观透明「成果 + 边界」精简看板**
     - 用 1 张 6 行基线表列出核心核验事实（活跃 KB `24 篇 / 3,809 条 / 67 关联`、冻结 7B `exp-20261116-resume500`、`SC-016` PASS［条级 `1→17/60`、款级 `9/60`、未知文件 `0→21/30`］、`SC-015` PASS［98 题 `0.0 pp` 波动］、`Quickstart V1–V7 + US4` PASS / `462 passed, 6 xfailed`），并紧接 3 条简明边界声明（① 全 98 题 `SC-002=0.121 / SC-003=0.188`，不以精选演示题冒充整体召回且不可外推至 1,000 篇；② 普法文章限于路线 A 预审单篇、主动追问尚未学会；③ `T078`《上海市工伤保险实施办法》括号条旨问题留待正式阶段修复），引向 `docs/learning/08-lessons-and-next.md`。
     - *理由*：严格呼应宪章原则 V“评测驱动决策”与第 8 章实事求是口径，让外部读者第一眼看到真实交付水平且不被误导。
   - **2B：仅写高层次里程碑结论（不展开具体指标小数）**
     - 只写 `SC-016 / SC-015 / V1–V7 + US4` 通过及冻结模型/知识库 ID，具体指标与边界全部外链到 `T071` 和 `08-lessons-and-next.md`。
     - *理由*：后续正式阶段迭代时无需频繁更新首页指标，但首屏说服力弱于 2A。

3. **决策 3：常见问题中私人本机代理端口（`127.0.0.1:8002`）的处理方式**
   - **3A（推荐）：泛化为通用代理排障提示**
     - 将原句改为通用表述：“若系统 HTTP/HTTPS 代理导致 `git push` 返回 503，可临时取消代理环境变量：`env -u http_proxy -u https_proxy git push`。”
     - *理由*：`README.md` 是全仓通用入口，去掉开发者单机特定端口更专业、便于交接与换机。
   - **3B：原样保留 `127.0.0.1:8002` 备忘**
     - 方便本机原样查阅，但对其他环境无参考价值。

---

## 下篇：面向实施方（便宜模型）的零歧义施工图

> 若用户拍板选择非推荐项，待定稿折叠清除落选分支后再开工；以下按推荐项 **`1A 2A 3A`** 展开精确施工口径。

### 3. 现状锚点与文档/环境陷阱预警

#### 3.1 关键源码、配置与文档锚点（全部经本轮只读实测核验）

| 类别 | 精确路径与锚点 | 实测事实要点（严禁凭记忆改写） |
|---|---|---|
| **CLI 全部 21 个注册子命令（单源真相）** | `src/tu_assistant/cli.py:21-1459` | 经 `typer.main.get_command(app)` 实测枚举：<br>1. `tu version`（输出 `tu-assistant 0.1.0`）<br>2. `tu kb import <directory> [--artifacts]`<br>3. `tu kb derive <source_kb> [--kb-version] [--artifacts]`<br>4. `tu kb list [--kb-version] [--artifacts]`<br>5. `tu kb show <title> <article_no> [-p/--paragraph] [-i/--item] [--kb-version] [--artifacts]`<br>6. `tu kb lookup <clause_id> [--kb-version] [--artifacts]`<br>7. `tu kb diff <v1> <v2> [--summary-only] [--artifacts]`<br>8. `tu kb relations extract [--kb-version] [--out] [--artifacts]`<br>9. `tu kb relations review <file> [--kb-version] [--artifacts]`<br>10. `tu kb relations confirm <file> --kb-version <ver> [--batch] [--artifacts]`（`--kb-version` 必填）<br>11. `tu synth evalcases [--kb-version] [--n] [--artifacts] [--synth-config]`<br>12. `tu synth sft [--kb-version] [--artifacts] [--synth-config] [--eval-cases] [--skip-llm] [--reuse-dataset] [--reuse-only] [--refresh-relations] [--articles-file] [--preserve-split/--no-preserve-split]`<br>13. `tu train --config <yaml> [--artifacts]`<br>14. `tu serve model --exp <exp_id> [--host] [--port] [--artifacts]`<br>15. `tu chat [--config] [--artifacts] [--kb-version]`（内置 `/save <path>`、`/new`、`/quit`、`/exit`）<br>16. `tu ui [--config] [--artifacts] [--kb-version] [--host] [--port] [--temperature] [--inbrowser/--no-inbrowser]`（`--host` 仅允许 `127.0.0.1`，默认端口 `7860`，默认温度 `0.7`）<br>17. `tu eval cases review <file> [--kb-version] [--artifacts]`<br>18. `tu eval cases promote <file> [--out]`<br>19. `tu eval run --cases <path> [--kb-version] [--exp] [--no-system-prompt] [--config] [--artifacts]`（`--cases` 必填）<br>20. `tu eval report <run_id> [--reviews] [--out] [--artifacts]`<br>21. `tu eval compare <run1> <run2>... [--sc016] [--sc015] [--reviews] [--out] [--save] [--artifacts]` |
| **配置文件与默认值** | `configs/app.yaml:1-25`<br>`configs/synth.yaml:1-59`<br>`configs/train/debug-1.5b.yaml`<br>`configs/train/demo-7b.yaml` | `app.yaml`：`model_endpoint="http://127.0.0.1:8080/v1"`、`allowed_hosts=["127.0.0.1", "localhost"]`、`model_name="default"`、`max_questions_per_turn: 5`、`default_article_count: 3`、`max_article_count: 10`、`kb.version: null`（自动取最新 SQLite）。`synth.yaml`：默认 DeepSeek（`TU_EXTERNAL_LLM_API_KEY` 仅来自环境变量）。`demo-7b.yaml`：已默认 `grad_checkpoint: true`、`save_every: 500`、`num_layers: -1`。 |
| **演示与迁移指南** | `docs/demo-scenarios.md:1-52,282-344` | 推荐现场启动：`uv run tu ui --temperature 0.0 --inbrowser`；10 分钟 6 步黄金主线；第 9 节（`#9-换机器演示与最小产物迁移指南`）含 **4 个文件 / 约 79 MB** 打包迁移命令与 `HF_HUB_OFFLINE=1` 断网演示说明。 |
| **全量验证与复盘终章** | `docs/experiments/T071-quickstart-verification.md:1-134`<br>`docs/learning/08-lessons-and-next.md:1-100` | T071 V1–V7 + US4 全 8 场景 PASS；`462 passed, 6 xfailed`；T064 两轮冷启动 98 题 `SC-015 = 0.0 pp` PASS；全 98 题 `SC-002=0.121`、`SC-003=0.188`、`SC-007` `0.405 → 0.669`（已定位 `0.589 → 0.973`）；`SC-011=2/2`；`T078` 影响《上海市工伤保险实施办法》63/63 条。 |
| **已完结文档体系（39 个目标路径全部实测存在）** | `docs/learning/{README,00..08,appendix-tools}.md`<br>`docs/experiments/{README,poc-training-summary,T064-*,T071-*,T075-*,E001-*,E002-*,E003-*}.md`<br>`docs/relations-confirm-guide.md`<br>`.specify/memory/constitution.md`<br>`specs/001-legal-clause-assistant/{spec,plan,research,data-model,tasks,quickstart}.md`<br>`specs/001-legal-clause-assistant/contracts/{cli,citation-format,datasets,system-interface}.md` | `docs/learning/01`–`08` 全部已标 `✅` 收口；根目录 `README.md` 目前**无任何站内入链锚点**，可放心重排章节结构。 |

#### 3.2 摸底发现的 6 处陷阱与必须采用的写法

1. **严禁向 `.gitignore` 忽略的 `artifacts/` 或 `.env` 写相对 Markdown 链接**：
   - `artifacts/` 与 `.env` 不在 Git 仓库中，克隆后相对链接必断 → 正文提及 `artifacts/...`、`.env` 时**一律用行内代码反引号**（如 `` `artifacts/kb/kb-20261119-045641.sqlite` ``），**严禁写成 `[...](./artifacts/...)` 或 `file://` 绝对路径**。
2. **以 `src/tu_assistant/cli.py` 为唯一命令真相，绝不盲抄历史 `contracts/cli.md`**：
   - `contracts/cli.md` 较早定稿，未包含 `version`、`kb derive`、`kb list`、`kb lookup`、`kb relations review`、`eval report`、`--sc015`、`--sc016`、`--temperature` 等后期命令与参数。
   - **必填项与互斥项不可写错**：
     - `tu kb relations confirm <file> --kb-version <ver>` 必须带 `--kb-version`；
     - `tu eval run --cases <path>` 必须带 `--cases`；
     - `tu eval compare --sc016 <base_run> <trained_run>` 恰好接受 2 个 run ID，且不可与 `--sc015`、`--out`、`--save`、`--reviews` 同用；
     - `tu ui` 仅允许 `--host 127.0.0.1`（非 `localhost`）且强制 `share=False`。
3. **`kb.version: null` 防劫持预警与知识更新重训提醒必须醒目**：
   - 在步骤 1（入库）和常见问题中均明确写清：`configs/app.yaml` 默认 `kb.version: null`（自动指向最新 SQLite），而 `tu kb import` 新生成的库已确认关联为 `0` 条；在已有活跃库环境下仅测试/复验入库时，必须加 `--artifacts /tmp/<dir>` 隔离，或先将 `configs/app.yaml` 的 `kb.version` 显式锁定为 `"kb-20261119-045641"`。
   - 同时在 KB 更新处简明提示：切换 `kb.version` 会立即更新出处校验层原文，但新增/实质修订条款仍需重抽关联并重训模型（详见 `specs/001-legal-clause-assistant/quickstart.md`）。
4. **单机训练与演示互斥预警不可遗漏**：
   - M1 Pro 32GB 统一内存下，`tu train` 与 `tu serve model` / `tu ui` 同时运行会将内存推高至 `22.5–28.5+ GB` 并争抢带宽导致卡顿或 OOM → 必须在训练步骤与常见问题中明确写出“**训练前停止本地模型服务与 UI，演示前确认无训练进程**”。
5. **所有数字与路径严守单一事实源（绝不四舍五入错位或写虚构示例）**：
   - 语料：`24 篇法规`（`inputs/project/001/`，另有 `4 篇`排除文件位于 `inputs/excluded/`），`3,809 条记录`，`67 条已确认关联（liability_for 26 + references 41）`；
   - 评测集：`eval/cases/v1/` `98 题`（全 7 类）+ `eval/cases/smoke/` `2 题`；人工评审归档 `eval/reviews/t064-reviews.csv`；
   - 演示/迁移：`exp-20261116-resume500`、`kb-20261119-045641`、`4 个文件 / 约 79 MB`（`adapters.safetensors` `77 MB`）；
   - 评测/验收数字：`SC-016`（`1/60 → 17/60`、`9/60 = 15.0%`、`0/30 → 21/30`）、`SC-015`（`0.0 pp`）、全 98 题 `SC-002 = 0.121`、`SC-003 = 0.188`、`SC-007` `0.405 → 0.669`（已定位 `0.589 → 0.973`）、`462 passed, 6 xfailed`。
6. **`inputs/` 禁读红线与无私有端口**：
   - 全文仅提及 `inputs/project/001/` 与 `inputs/excluded/` 路径和篇数统计，**严禁粘贴任何法条原文片段**；
   - 按决策 3A 清除私人端口 `127.0.0.1:8002`，改为通用代理排障提示。

---

### 4. 改动范围表与明确不做清单（Non-Goals）

#### 4.1 文件改动表

| 文件路径 | 操作 | 精确职责 |
|---|---|---|
| `README.md` | **修改（结构化重写）** | 按 §5 契约全面更新项目简介、POC 验收基线与边界、场景 A/B 快速开始、环境与前置条件、`tu` CLI 21 子命令速查表、仓库结构、常见问题与分层可点击文档索引 |
| `artifacts/logs/t072/verify_t072.py` | **新增（本地忽略产物，不入 Git）** | 纯只读确定性核查脚本，动态验证 Markdown 链接与 GFM 锚点、`cli.py` 全部 21 个叶子命令覆盖、核心文档索引完整性、POC 基线数字与预警关键词、零 `file://` / 零 `artifacts/` 相对链接及变更边界 |
| `docs/handoffs/T072-readme-handoff.md` | **验收收尾时追加** | 独立只读复审通过后，仅在末尾追加实施结果与复审记录 |

#### 4.2 明确不做清单（Non-Goals）

- **严禁改动任何代码、测试与配置**：不触碰 `src/`、`tests/`、`configs/`、`pyproject.toml`、`uv.lock`；
- **严禁改动规格与历史文档**：不触碰 `specs/001-legal-clause-assistant/*`（含 `contracts/cli.md` 与 `tasks.md`）、`.specify/`、`docs/learning/*`、`docs/experiments/*`（含 `docs/experiments/README.md`）、`docs/demo-scenarios.md`、`docs/relations-confirm-guide.md`、`AGENTS.md`；
- **严禁改动任何历史产物或运行时状态**：不触碰 4 份历史 KB SQLite、冻结权重、`artifacts/serve/current.json` 与 T075 `output.sha256` 覆盖的 25 项文件；
- **严禁读取 `inputs/` 目录**或粘贴法律条文正文；
- **未获用户明确确认前，不勾选 `tasks.md` 中的 `T072`，不执行 `git commit` / `git push`**。

---

### 5. 文档结构与事实口径契约（施工核心，不留猜想空间）

根目录 `README.md` 必须严格采用以下 **7 个顶级二级章节**（按顺序组织，总篇幅控制在约 **220–280 行**，信息密度高且无冗余长段落）：

#### 5.1 标题与顶部简介
- 标题：`# tu-assistant`
- 一段 3–4 行精炼简介：工会法律条款智能助手（POC），将项目方提供的 24 篇公开法律文档通过 QLoRA 微调“训进”自有本地模型，提供**多轮对话法律条款咨询（识别条款 + 引用出处）**与**以案说法普法文章生成**；**运行时完全私有化本地执行、零外部 API 调用**，条款原文与身份脱敏由确定性校验层兜底。
- 一条醒目引用块标注当前阶段：**POC 阶段开发与全量验证已收官**（M1 Pro / 32GB 本机运行），并链接到 [需求规格](./specs/001-legal-clause-assistant/spec.md)、[现场演示剧本](./docs/demo-scenarios.md) 与 [全项目复盘](./docs/learning/08-lessons-and-next.md)。

#### 5.2 `## POC 状态与核心基线`
- **1 张 6 行基线总览表**（维度 | 活跃基线 / 实测结果 | 详细记录）：
  1. **语料与活跃知识库**：`kb-20261119-045641`（24 篇法规 / 3,809 条记录 / 67 条已确认关联：`liability_for` 26 + `references` 41）→ 链 [第 3 章 知识库](./docs/learning/03-knowledge-base.md)
  2. **冻结 7B 演示模型**：`exp-20261116-resume500`（`Qwen2.5-7B-Instruct-4bit`，Apache 2.0，LoRA `77 MB`；1.5B 流程验证模型 `exp-20261114-120250`）→ 链 [POC 训练总结](./docs/experiments/poc-training-summary.md)
  3. **SFT 有效性验证（`SC-016`）**：**PASS**（60 题条级 `1/60 → 17/60`，款级 `9/60 = 15.0%`，基座未知文件子集 `0/30 → 21/30`）→ 链 [POC 训练总结](./docs/experiments/poc-training-summary.md)
  4. **重复评测稳定性（`SC-015`）**：**PASS**（`eval/cases/v1/` 全 7 类 98 题两轮独立冷启动最大波动 **`0.0 pp`**）→ 链 [T064 重复评测](./docs/experiments/T064-eval-repeatability.md)
  5. **端到端验收（`quickstart.md`）**：**V1–V7 + US4 全 8 场景 PASS**（含 7B + Gradio UI 10 分钟黄金主线与脱敏/零外连核查）→ 链 [T071 验证记录](./docs/experiments/T071-quickstart-verification.md)
  6. **确定性自动化测试**：`uv run --offline --no-sync pytest` **462 passed, 6 xfailed**，`ruff check src tests` 全绿 → 链 [T071 验证记录](./docs/experiments/T071-quickstart-verification.md)
- **3 条客观边界说明**（呼应第 8 章 `[L8.2]`–`[L8.4]`）：
  1. **不以精选演示题冒充全库召回，不外推至 1,000 篇**：98 题全量实测 `SC-002 = 0.121`、`SC-003 = 0.188`，引用准确率校验前 `0.405` → 校验后 `0.669`（已定位引用 `0.589 → 0.973`）；1,000 篇规模曲线（`SC-012`）与 RAG 对照留待正式阶段。
  2. **功能边界（路线 A 与主动追问）**：按 [T075 实验结论](./docs/experiments/T075-article-training.md)，冻结演示模型未合入文章续训权重，普法文章限于给定案情与核准条款的预审单篇演示；主动追问能力（`intent` 首轮反问）尚未学会。
  3. **已知缺陷 `T078`**：《上海市工伤保险实施办法》（63/63 条）括号条旨误切为第 1 款导致款号顺延 `+1`，POC 阶段保持 KB 与基线不动，已建档移至正式阶段修复（详见 [第 8 章 复盘](./docs/learning/08-lessons-and-next.md)）。

#### 5.3 `## 环境与前置条件`
- 硬件要求：macOS（Apple Silicon），**训练建议 ≥32GB 统一内存**（MLX 4bit QLoRA 实测峰值 11.5–13.5 GB，需开启 `grad_checkpoint: true`）；**仅运行演示建议 ≥16GB（推荐 32GB）**。
- 软件依赖：Python `3.12` + [uv](https://docs.astral.sh/uv/)（`uv sync` 按 `uv.lock` 还原，锁死 `mlx-lm 0.32.2`、`gradio 6.31.0` 等）。
- 外部大模型 API Key（**仅离线数据合成环节需要**）：在仓库根目录创建 `.env`（已被 `.gitignore` 忽略）写入 `TU_EXTERNAL_LLM_API_KEY=sk-...`，默认对接 DeepSeek（见 [configs/synth.yaml](./configs/synth.yaml)）；**运行时推理、对话、UI、评测均不调用任何外部服务**。
- Hugging Face 国内加速环境变量（首次拉取基座模型必设）：`export HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1`；基座进入本机缓存后可加 `HF_HUB_OFFLINE=1` 与 `uv run --offline --no-sync` 完全断网运行。

#### 5.4 `## 快速开始（按场景选择）`
- **`### 场景 A：已有演示产物 / 换机直接运行（约 5 分钟）`**
  - 说明 `artifacts/` 不在 Git 中；若已有最小演示产物包（**4 个文件、共约 79 MB**：`manifest.json`、`adapters/adapters.safetensors`、`adapters/adapter_config.json`、`kb-20261119-045641.sqlite`），按 [换机迁移指南](./docs/demo-scenarios.md#9-换机器演示与最小产物迁移指南) 解压到仓库根目录后，执行 `uv sync`，再开**两个终端**：
    - 终端 1（模型服务，仅监听 `127.0.0.1:8080`）：
      ```bash
      # 首次运行需下载 7B 4bit 基座（约 4.4 GB）；已缓存后可改用 HF_HUB_OFFLINE=1 断网启动
      HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1 \
        uv run tu serve model --exp exp-20261116-resume500
      ```
      等待出现 `Starting httpd at 127.0.0.1 on port 8080...`。
    - 终端 2（本地 Gradio 演示界面，仅监听 `127.0.0.1:7860`）：
      ```bash
      # 推荐：--temperature 0.0 与 SC-015 零波动评测基线一致；如需轻微措辞变化可省略（默认 0.7）
      uv run tu ui --temperature 0.0 --inbrowser
      ```
      说明浏览器打开 `http://127.0.0.1:7860` 的核心操作（多轮对话、「新会话」释放内存上下文、「保存当前回复为 Markdown」、严禁公网共享、未开终端 1 时有中文引导、演示完双终端 `Ctrl+C` 停止），推荐按 [docs/demo-scenarios.md](./docs/demo-scenarios.md) 的 10 分钟黄金主线演练；并附命令行备选 `uv run tu chat`（`/new`、`/save <路径.md>`、`/quit`）。
- **`### 场景 B：从零复现全流程`**（保持精炼的 6 步 0–5，避免和命令速查表大段重复）
  - **步骤 0：还原环境与跑通测试**：`uv sync`、`uv run --offline --no-sync pytest`、`uv run --offline --no-sync ruff check src tests`、`uv run --offline --no-sync tu version`。
  - **步骤 1：语料入库与知识库维护**：
    - 给出 `uv run tu kb import inputs/project/001`（预期 24 篇 / 3,809 条 / 问题 24 个）与抽查/对比命令（`tu kb list`、`tu kb show "中华人民共和国劳动法" 24`、`tu kb diff <old_ver> <new_ver> --summary-only`、`tu kb derive <source_kb>`）。
    - **显式防呆提示块**：`configs/app.yaml` 默认 `kb.version: null`（自动使用最新 SQLite），且新导入库的已确认关联为 `0` 条；在已有活跃库机器上仅验证入库请加 `--artifacts /tmp/kb-test` 隔离，或先锁定 `configs/app.yaml` 的 `kb.version`。
  - **步骤 2：条款关联抽取 → 人工审阅 → 差异导入**：
    - 给出 `tu kb relations extract --kb-version <ver>`、`tu kb relations review <pending.jsonl> --kb-version <ver>`、`tu kb relations confirm <review.jsonl> --kb-version <ver>`（标注 `--kb-version` 必填），并说明审定清单归档在 `data/relation-reviews/`、完整操作见 [docs/relations-confirm-guide.md](./docs/relations-confirm-guide.md)。
  - **步骤 3：外部大模型合成 SFT 训练数据（需 API Key）**：
    - 给出 `set -a && source .env && set +a && uv run tu synth sft`（说明产出 `artifacts/datasets/ds-<kb>-<N>/`，调试可加 `--skip-llm`，增量重建可配合 `--reuse-dataset` / `--reuse-only` / `--refresh-relations` / `--articles-file`）。
  - **步骤 4：本机 QLoRA 训练（1.5B 调试 / 7B 演示）**：
    - 给出 `export HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1`、`uv run tu train --config configs/train/debug-1.5b.yaml`（实测约 2–4 小时 / 2 epoch，历史 1.5B 基线约 4 小时）与 `uv run tu train --config configs/train/demo-7b.yaml`（M1 Pro 32GB 已默认 `grad_checkpoint: true`，约 12–14 小时/轮；当前冻结演示模型 `exp-20261116-resume500`）。
    - **显式互斥提醒**：训练前务必停止 `tu serve model` 与 `tu ui`，避免 32GB 统一内存叠加溢出。
  - **步骤 5：评测、报告与版本对比**（先启动终端 1 `tu serve model`）：
    - 冒烟评测：`uv run tu eval run --exp exp-20261116-resume500 --cases eval/cases/smoke`
    - 完整 98 题评测：`uv run tu eval run --exp exp-20261116-resume500 --cases eval/cases/v1`
    - 只读渲染报告（叠加人工评审 CSV）：`uv run tu eval report <run_id> --reviews eval/reviews/t064-reviews.csv`
    - 版本对比 / `SC-015` 重复稳定性 / `SC-016` 验收判定：
      - `uv run tu eval compare <run1> <run2> --sc015 --reviews eval/reviews/t064-reviews.csv --save`
      - `uv run tu eval compare --sc016 <base_run> <trained_run>`（标注恰好 2 个 run ID，不可与 `--sc015`/`--out`/`--save`/`--reviews` 混用）
    - 指向 [quickstart.md](./specs/001-legal-clause-assistant/quickstart.md) 查看全部 V1–V7 + US4 验证场景。

#### 5.5 `## 常用命令速查（tu CLI）`
- 按 5 个逻辑分组（或 1 张清晰分组表），**100% 覆盖 `src/tu_assistant/cli.py` 全部 21 个注册叶子命令**：
  1. **基础与知识库（7 条）**：`tu version`、`tu kb import`、`tu kb derive`、`tu kb list`、`tu kb show`、`tu kb lookup`、`tu kb diff`
  2. **条款关联（3 条）**：`tu kb relations extract`、`tu kb relations review`、`tu kb relations confirm`
  3. **数据合成与训练（3 条）**：`tu synth evalcases`、`tu synth sft`、`tu train`
  4. **本地服务与交互（3 条）**：`tu serve model`、`tu chat`、`tu ui`
  5. **评测与用例审核（5 条）**：`tu eval cases review`、`tu eval cases promote`、`tu eval run`、`tu eval report`、`tu eval compare`
- 每条写清真实命令名、必选/高频参数与一句话说明，并加注“以 `uv run tu <子命令> --help` 及 `src/tu_assistant/cli.py` 为准”。

#### 5.6 `## 仓库结构`
- 清晰列出所有核心受版本控制目录/文件（表格式）：
  - `src/tu_assistant/`（`kb/`、`citation/`、`chat/`、`runtime/`、`synth/`、`train/`、`eval/`、`ui/`、`cli.py`、`config.py`、`manifest.py`）
  - `configs/`（[app.yaml](./configs/app.yaml)、[synth.yaml](./configs/synth.yaml)、`train/` 下 1.5B/7B 配置）
  - `inputs/project/001/`（24 篇公开法律语料，已入库 Git；`inputs/excluded/` 为 4 篇评估排除文件）
  - `data/relation-reviews/`（人工审定并归档的三份条款关联审阅清单）
  - `eval/`（`cases/smoke/` 2 题、`cases/v1/` 98 题全 7 类、`review-template.csv`、`reviews/t064-reviews.csv`、`diagnostics/`）
  - `tests/`（确定性单元测试与集成测试，基线 `462 passed, 6 xfailed`）
  - `scripts/`（数据整理、训练守护与实验诊断脚本）
  - `docs/`（演示剧本、条款关联指南、实验记录、学习文档 00–08、执行单）
  - `specs/001-legal-clause-assistant/` 与 `.specify/memory/constitution.md`（SDD 规格、宪章、计划、契约、任务清单）
  - `AGENTS.md`（项目开发与安全约定）
- 单独加粗说明**不入 Git 的本地文件**：`artifacts/`（知识库 SQLite、数据集、LoRA 适配器、评测输出与日志，全部按上述步骤重建或通过 79 MB 最小包迁移）与 `.env`（外部大模型 API Key）。

#### 5.7 `## 常见问题与注意事项`
覆盖 6 条高频实战问题（精炼，每条 1–2 行）：
1. **`kb.version: null` 防劫持与知识更新需重训**：测试重导请加 `--artifacts /tmp/<dir>` 隔离或在 `configs/app.yaml` 显式锁定 `kb.version`；仅切库只更新校验层原文，新增/实质修订条款须重抽关联并重训模型（见 [quickstart.md](./specs/001-legal-clause-assistant/quickstart.md)）。
2. **训练与演示不可同开**：M1 Pro 32GB 同时运行 `tu train` 与 `tu serve model` / `tu ui` 会叠加内存至 `22.5–28.5+ GB` 导致卡顿或 OOM，须严格串行（原理见 [L7.6](./docs/learning/07-serving-demo.md#l76-为什么训练与演示不能在-m1-pro32gb上同时进行)）。
3. **HF 下载极慢或断网离线运行**：下载基座必设 `HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1`；基座进入本机缓存后可设 `HF_HUB_OFFLINE=1` 并配合 `uv run --offline --no-sync` 完全离线运行。
4. **长样本训练显存与防休眠**：7B 训练配置已默认开启 `grad_checkpoint: true`（峰值约 23 GB → 11.5 GB）；长时间合成或训练可用 `caffeinate -is -w <PID>` 防休眠。
5. **代理导致 `git push` 返回 503**（按决策 3A）：若系统 HTTP/HTTPS 代理干扰 Git 推送，可临时取消代理变量：`env -u http_proxy -u https_proxy git push`。
6. **`tu ui` 提示无法连接模型服务或端口占用**：确认终端 1 的 `tu serve model` 已就绪（`127.0.0.1:8080`），若 `7860` 被占用可传 `--port 7861`；演示时切场景务必先点「新会话」。

#### 5.8 `## 文档索引`
全部使用可点击相对 Markdown 链接（`./...`），按 4 个清晰分组表格呈现：

1. **演示、操作与验收指南**：
   - [docs/demo-scenarios.md](./docs/demo-scenarios.md) — 10 分钟现场黄金主线、5 大场景库、汇报边界与 4 文件 79 MB 换机迁移指南
   - [docs/experiments/T071-quickstart-verification.md](./docs/experiments/T071-quickstart-verification.md) — `quickstart.md` V1–V7 + US4 全 8 场景端到端验收记录
   - [docs/relations-confirm-guide.md](./docs/relations-confirm-guide.md) — 条款关联四态审阅与事务化差异导入指南
   - [specs/001-legal-clause-assistant/quickstart.md](./specs/001-legal-clause-assistant/quickstart.md) — POC 全部验证场景步骤与知识更新操作说明
2. **实验诊断与评测报告**：
   - [docs/experiments/README.md](./docs/experiments/README.md) — 实验记录总目录与编号规范
   - [docs/experiments/poc-training-summary.md](./docs/experiments/poc-training-summary.md) — POC 训练目标达成结论、SC-016 判定与正式阶段路线判断
   - [docs/experiments/T064-eval-repeatability.md](./docs/experiments/T064-eval-repeatability.md) — 冻结 7B 98 题两轮冷启动重复评测与 SC-015（`0.0 pp`）报告
   - [docs/experiments/T075-article-training.md](./docs/experiments/T075-article-training.md) — 文章样本续训实验、回归门槛判定与路线 A 决策
   - [docs/experiments/E001-1.5b-citation-failure.md](./docs/experiments/E001-1.5b-citation-failure.md) / [E002](./docs/experiments/E002-eval-served-base-model.md) / [E003](./docs/experiments/E003-memorization-vs-exposure.md) — 7B NaN 修复、误测基座事故排查、曝光与泛化实验
3. **配套学习文档（00–08 全套已完结，按 `[L章.节]` 编号）**：
   - [docs/learning/README.md](./docs/learning/README.md) — 阅读顺序与提问方式
   - [00 术语表](./docs/learning/00-glossary.md) · [01 全局视角](./docs/learning/01-big-picture.md) · [02 硬件与环境](./docs/learning/02-hardware.md) · [03 知识库与出处校验](./docs/learning/03-knowledge-base.md) · [附录A 工具](./docs/learning/appendix-tools.md)
   - [04 训练数据](./docs/learning/04-training-data.md) · [05 模型训练](./docs/learning/05-training.md) · [06 质量评测](./docs/learning/06-evaluation.md) · [07 推理与演示](./docs/learning/07-serving-demo.md) · [08 复盘与演进](./docs/learning/08-lessons-and-next.md)
4. **规格、契约与项目约定（SDD）**：
   - [项目宪章（constitution.md）](./.specify/memory/constitution.md) · [开发与安全约定（AGENTS.md）](./AGENTS.md)
   - [需求规格（spec.md）](./specs/001-legal-clause-assistant/spec.md) · [实施计划（plan.md）](./specs/001-legal-clause-assistant/plan.md) · [技术决策（research.md）](./specs/001-legal-clause-assistant/research.md) · [数据模型（data-model.md）](./specs/001-legal-clause-assistant/data-model.md) · [任务清单（tasks.md）](./specs/001-legal-clause-assistant/tasks.md)
   - 接口契约：[CLI（contracts/cli.md）](./specs/001-legal-clause-assistant/contracts/cli.md) · [引用格式（citation-format.md）](./specs/001-legal-clause-assistant/contracts/citation-format.md) · [数据集格式（datasets.md）](./specs/001-legal-clause-assistant/contracts/datasets.md) · [系统接口（system-interface.md）](./specs/001-legal-clause-assistant/contracts/system-interface.md)

---

### 6. 原子化施工步骤（自底向上，每步可自检）

- **Step 1：基线核验（动手前确认工作区干净）**
  - 检查 `git status --short` 为空，确认当前基线与本执行单一致。
  - 本步最小自检：
    ```bash
    git status --short && uv run --offline --no-sync tu version
    ```
- **Step 2：重写更新根目录 `README.md`**
  - 严格按 §5.1–§5.8 写入新版 `README.md`，确保：
    - 7 个二级标题完整、清晰、无冗余；
    - 21 个 `tu` 叶子命令全部准确覆盖，必填参数与互斥规则无误；
    - 全部站内文档链接使用 `./...` 可点击相对路径，零 `file://`，零指向 `artifacts/` 或 `.env` 的相对 Markdown 链接；
    - 不含 `127.0.0.1:8002`（按决策 3A），不含任何 `inputs/` 条文正文片段。
  - 本步最小自检：
    ```bash
    grep -n "^## " README.md && ! grep -nE "file://|\]\([^)]*(artifacts/|\.env)|127\.0\.0\.1:8002" README.md
    ```
- **Step 3：编写并运行本地只读确定性核查脚本 `artifacts/logs/t072/verify_t072.py`**
  - 在 `.gitignore` 忽略目录 `artifacts/logs/t072/` 下编写 `verify_t072.py`，完整落实 §7.1 全部 6 项硬断言（任何失败必须以非零退出码终止，严禁假阳性 `[OK]`）。
  - 本步最小自检：
    ```bash
    uv run --offline --no-sync python artifacts/logs/t072/verify_t072.py
    ```
- **Step 4：运行全量回归与只读保护门禁**
  - 按 §7.2 跑完 `pytest`、`ruff`、T075 `output.sha256`、4 份历史 KB SHA-256、`artifacts/serve/current.json` 及 `git status --short` / `git diff --stat`，随后按 `.agents/skills/task-review-loop/SKILL.md` 进入独立只读复审闭环。

---

### 7. 确定性核查矩阵与验收门禁

#### 7.1 确定性核查矩阵（写入 `artifacts/logs/t072/verify_t072.py`，严禁假阳性 `[OK]`）

| 核查项 | 核查对象与方法 | 硬断言底线（禁止弱断言） |
|---|---|---|
| **1. 全量 Markdown 相对链接与 GFM 锚点检验** | 动态提取 `README.md` 全部 `[text](target)`（跳过 `http://`/`https://` 外链与代码块内伪链接），解析文件路径与可选 `#anchor`，对存在锚点的目标文件动态计算 GFM slug 集合校验命中 | **0 断链、0 失效锚点**；`file://` 出现数为 **0**；指向 `artifacts/` 或 `.env` 的相对 Markdown 链接数为 **0** |
| **2. `tu` CLI 全部 21 个叶子命令覆盖与关键参数校验** | 动态调用 `typer.main.get_command(tu_assistant.cli.app)` 递归枚举全部真实叶子命令（断言恰好 21 个），逐一校验命令全称（如 `tu kb derive`、`tu eval cases promote`）全部出现在 `README.md` 中；另校验必填/推荐参数出现 | 21/21 真实叶子命令覆盖率 **100%**；必含 `tu kb relations confirm` + `--kb-version`、`tu eval run` + `--cases`、`tu ui --temperature 0.0`、`--artifacts /tmp/`（或 `--artifacts` 隔离说明）、`--sc015`、`--sc016` |
| **3. 全仓文档索引完整性核查** | 校验 `README.md` 相对链接目标集合是否包含全部核心已定稿文档（共 33 个核心 Markdown 文档路径） | 必含 `docs/demo-scenarios.md`、`docs/relations-confirm-guide.md`、`docs/experiments/{README,poc-training-summary,T064-eval-repeatability,T071-quickstart-verification,T075-article-training,E001-1.5b-citation-failure,E002-eval-served-base-model,E003-memorization-vs-exposure}.md`、`docs/learning/{README,00-glossary,01-big-picture,02-hardware,03-knowledge-base,04-training-data,05-training,06-evaluation,07-serving-demo,08-lessons-and-next,appendix-tools}.md`、`.specify/memory/constitution.md`、`specs/001-legal-clause-assistant/{spec,plan,research,data-model,tasks,quickstart}.md`、`specs/001-legal-clause-assistant/contracts/{cli,citation-format,datasets,system-interface}.md`、`AGENTS.md` |
| **4. POC 基线数字与三大高危预警核查** | 正则/子串核查 `README.md` 必含的实测基线数字、预警关键词与按决策 3A 清除的旧私人端口 | 必含：`24`、`3,809`、`67`、`98`、`exp-20261116-resume500`、`kb-20261119-045641`、`17/60`、`9/60`、`21/30`、`0.0 pp`、`462`、`0.121`、`0.188`、`0.405`、`0.669`、`79 MB`、`T078`、`kb.version`、`127.0.0.1`、`HF_HUB_OFFLINE=1`、训练与演示互斥提醒；`127.0.0.1:8002` 出现数为 **0**；无 `TODO` / `TBD` 占位符 |
| **5. 章节结构核查** | 提取 `README.md` 全部 `## ` 二级标题 | 精确包含 §5 规定的 7 个核心章节（`POC 状态与核心基线`、`环境与前置条件`、`快速开始`、`常用命令速查`、`仓库结构`、`常见问题与注意事项`、`文档索引`），总行数建议在 180–320 行之间（避免退化为过度冗长手册或残缺目录） |
| **6. 变更文件与只读红线检查** | 执行 `git status --porcelain --untracked-files=all` | 变更与未跟踪文件集合严格是 `{"README.md", "docs/handoffs/T072-readme-handoff.md"}` 的子集；严禁触碰 `src/`、`tests/`、`configs/`、`specs/`、`tasks.md`、`docs/learning/`、`docs/experiments/`、`docs/demo-scenarios.md` 及 `inputs/` |

#### 7.2 验收门禁命令清单

```bash
# 1. README 确定性核查（6 项全 [OK]，退出码 0）
uv run --offline --no-sync python artifacts/logs/t072/verify_t072.py

# 2. 全量自动化测试与代码风格零回归（须与基线 462 passed, 6 xfailed 完全一致）
uv run --offline --no-sync pytest
uv run --offline --no-sync ruff check src tests

# 3. 历史产物、4 份 KB 与活跃服务元数据只读保护核验
shasum -a 256 -c artifacts/logs/t075/01/output.sha256
shasum -a 256 artifacts/kb/*.sqlite
cat artifacts/serve/current.json

# 4. 变更边界核验（仅允许 README.md 与验收收尾后的本执行单；严禁勾选 tasks.md）
git status --short
git diff --stat
```

---

### 8. 学习文档更新点

- `docs/learning/00`–`08` 全部学习文档与术语表已于 `T073` / `T074` 全部收口（均标 `✅`）；
- **`T072` 不修改 `docs/learning/` 下的任何文件**，仅在根目录 `README.md` 的 `## 文档索引` 中完整呈现 `00`–`08` 与 `appendix-tools.md` 的可点击阅读入口。

---

### 9. 实施方偏差止损规则

- **可自决微调**：段落衔接措辞、Markdown 表格列宽对齐、命令示例中的注释措辞，以及本地 `artifacts/logs/t072/verify_t072.py` 的日志打印格式（不得改变 §5 事实口径与 §7 核查底线）。
- **必须立即停工上报（严禁擅自绕过）**：
  1. 动态内省 `src/tu_assistant/cli.py` 发现真实命令或必填参数与 §3.1 冲突；
  2. 核查脚本发现 §5.8 列出的任何目标文档路径或 `#anchor` 不存在；
  3. 发现需要修改 `README.md` 以外的任何仓库受控文件（如 `contracts/cli.md`、`docs/experiments/README.md`、`src/`、`configs/`、`tasks.md`）；
  4. 任何情况下需要读取 `inputs/` 目录下文件内容。

---

## 10. 实施结果与独立复审记录（2026-11-24）

### 10.1 实施摘要（按用户拍板 `1A 2A 3A`）

- **`README.md`（结构化重写，219 行）**：
  - 按 7 个顶级二级章节组织：POC 状态与核心基线（6 行实测基线表 + 3 条客观边界声明）、环境与前置条件、快速开始（场景 A 已有产物 5 分钟直接演示 vs 场景 B 从零 0–5 步全流程复现，内置 `kb.version: null` 防劫持预警与训练/演示互斥提醒）、常用命令速查（100% 覆盖 `cli.py` 全部 21 个注册叶子命令）、仓库结构、常见问题与注意事项（已按决策 3A 泛化代理 503 排障提示并清除私人端口）、分层可点击文档索引（33 份核心文档全覆盖，含完结版 `docs/learning/00`–`08`）。
- **本地只读核查脚本**：`artifacts/logs/t072/verify_t072.py`（`.gitignore` 忽略，不入 Git）。

### 10.2 独立只读复审闭环（`reviewer-t072`，Gemini 4 Neon High，共 2 轮）

- **Round 1（需修改：4 项阻断项 B1–B4 + 3 项非阻断建议）**：
  1. **[B1]** 场景 B 步骤 2 关联审阅路径 `artifacts/kb/relations_pending.jsonl` 漏 `<ver>-` 前缀 → **已修复**为 `artifacts/kb/<ver>-relations_pending.jsonl` 并在 `verify_t072.py` 新增防回归断言；
  2. **[B2]** `tu kb derive` 说明原写“仅变更编号/关系”与 `kb/derive.py` 强制关联不变不变量矛盾 → **已修复**为“补齐多款条文第 1 款显式款号（原文与原有关联不变，不动旧库）”；
  3. **[B3]** `tu eval cases review` 说明原写成静态校验 → **已修复**为“终端交互式人工核对候选用例：查看问题与 `gold` 条款并标记 `confirmed`（原地回写 JSONL）”；
  4. **[B4]** 1.5B 训练耗时原沿用旧估算“约 1 小时” → **已修复**为“实测约 2–4 小时 / 2 epoch（历史基线约 4 小时），流程验证”，并同步更正本单 §5.4 L182；
  5. **非阻断建议 1–3**：步骤 1 增补 `tu kb derive <source_kb>`；`tu ui` 速查行改为 `[--temperature <float>]` 并注明默认 `0.7`、演示推荐 `0.0`；`verify_t072.py` 加强 `tu kb relations confirm` + `--kb-version`、`tu eval run` + `--cases` 同行共现断言 → **均已采纳**。
- **Round 2（通过：阻断项 = 0，非阻断建议 = 0）**：
  - `uv run --offline --no-sync python artifacts/logs/t072/verify_t072.py`：6/6 `[OK]`，退出码 `0`（55 相对链接 0 断链、21/21 CLI 命令与共现检查通过、33/33 核心文档、21/21 数字与预警、7 个 H2 / 219 行）；
  - `uv run --offline --no-sync pytest`：**462 passed, 6 xfailed**；
  - `uv run --offline --no-sync ruff check src tests`：**All checks passed!**；
  - `shasum -a 256 -c artifacts/logs/t075/01/output.sha256`：**25/25 OK**；4 份历史 KB SQLite 与 `artifacts/serve/current.json` 完好；
  - 两轮复审均比对送审前后 `git diff | shasum -a 256` 确认审查员字节级零修改，且 `specs/001-legal-clause-assistant/tasks.md` 中 `T072` 仍为未勾选 `[ ]`。
