# T064 执行单 · 7B 演示模型重复评测（SC-015 稳定性验证）、文章 DeepSeek 初审与人工终审及 T059 核销准备

**状态：已验收完成（2026-11-23）。** 基于主线提交 `bea2d97`（T049 已验收提交）。用户已拍板全部决策（决策 1/2/4 选 A，决策 3 选“外部 DeepSeek 初审 + 人工终审”，确认项 3a/3b 均选 A）。两轮独立冷启动 98 题评测、人工终审落盘、SC-015 对比归档、实验与学习文档更新均已完成，经 2 轮独立复审一致通过并由用户确认同步勾选 `T064` 与 `T059` 提交推送。

> **合规与红线声明**：
> 1. 起草与实施全过程**严禁读取 `inputs/` 目录下任何文件**；
> 2. **严禁改动 `src/` 业务代码、`tests/` 测试、`configs/` 配置、`eval/cases/v1/`、`specs/` 及任何历史产物**（历史 KB、历史数据集、已训权重、历史 20 个 `artifacts/eval/run-*` 目录及 `artifacts/logs/t075/01/output.sha256` 锁定的 25 项文件）；
> 3. **运行时与离线评测打分严格隔离（宪章原则 III/IV）**：两轮 7B 评测全程纯本机离线推理（`127.0.0.1:8080` + `HF_HUB_OFFLINE=1`）；外部 DeepSeek 初审仅作为独立离线脚本位于 `scripts/experiments/t064/`，**绝不侵入 `src/tu_assistant/{chat,runtime,ui,eval}/`**，且只发送 `eval/cases/v1/articles.jsonl` 的虚构题目、`rubric`、KB 公开法条与本地模型生成结果（零用户真实对话、零 `inputs/`）；
> 4. 未经用户明确确认最终验收前，不得勾选 `tasks.md`（`T064` / `T059`）或执行 `git commit`。

---

## 1. 推荐任务编号与选择理由

**推荐任务：`T064` [US3]（对 7B 演示模型重复评测 2 次，用 `tu eval compare` 验证指标波动 ≤2 个百分点［SC-015］，结果存于 `artifacts/eval/`），并同步满足 `T059` 的核销条件。**

### 1.1 为什么优先做 `T064`？

1. **严格承接已批准的 Phase 5 推进顺序**：在 `T061+T063`、`T062` 与 `T049` 执行单中已确立并获批准的路线为：
   `T061+T063`（已完成）→ `T062`（已完成）→ `T049`（已完成，98 题全 7 类就位）→ **`T064`（本单）** → `T065`（整理完整 `docs/learning/06-evaluation.md`）。
2. **全部前置条件已 100% 齐备，可一次性产出全 7 类指标基线**：
   - 冻结演示模型 `exp-20261116-resume500`（T075 路线 A 选定）与活跃知识库 `kb-20261119-045641`（67 条已确认关联）已锁定；
   - `eval/cases/v1/` 已随 T049 扩充至 **98 题 / 116 轮**，覆盖全部 7 个类别（`clause_id`、`article`、`multi_violation`、`intent`、`refusal`、`false_refusal`、`exception`），在 `kb-20261119-045641` 上 `gold_clause_issues=0`；
   - 编排层护栏（T054 脱敏、T056 篇数控制）与评测工具链（T061/T063 `tu eval report`、T062 `tu eval compare --sc015 --reviews --save`、T076 `--sc016`）已全部合入并全量测试通过。
3. **同步收口 `T059`（Phase 4 闭环）并解除 `T065`（Phase 5 闭环）阻塞**：
   - **关于 `T059` 尚未勾选的原因与关联**：`T059` 的训练、再训与 SC-016 验收（`exp-20261116-resume500`、E003 B1、条级 `1→17/60`、款级 `9/60`、未知文件 `0→21/30`）早在 2026-11-18 已实质达成，唯一对应 quickstart V5 的未完项是“7B 全指标评测与同模型重复评测波动 ≤2 个百分点（SC-015）”。在 `T056` 执行单第 7 节（决策 4）中，**用户已明确拍板选选项 2：“待 Phase 5 的 T064 跑完后再勾 T059”**。因此完成 `T064` 即可同时为 `T064` 与 `T059` 提供完整验收依据，收口 Phase 1–4（除已移出 POC 的 `T078`）；
   - **`T065` 强依赖 `T064` 的真实数据**：`T065` 要求“用本项目评测结果分析薄弱类别并反推数据改进方向”，必须先拿到 `T064` 在完整 98 题（含文章人工评审终判与新增的 `multi_violation`、`intent`、`boundaries`）上的实测报告与逐类失败数据，才能避免空谈。
4. **实机耗时可控，无需通宵窗口**：
   - 本任务仅执行本地推理、离线对比与小批量 DeepSeek 初审，不涉及训练；按本机 M1 Pro / 32GB 历史实测（见 §2.3），单轮 98 题 / 116 轮预计 **9–12 分钟**，2 轮独立冷启动含 A/B 冒烟总计约 **20–28 分钟**，4-bit 7B 推理内存占用约 5–7 GB，远低于 32 GB 上限，且远满足 SC-015“1 个工作日内完成一次完整评测”的可用性要求。

### 1.2 与其他未完成候选任务的横向对比

| 候选任务 | 当前状态与前置条件 | 为何优先做 `T064` |
|---|---|---|
| **`T064`（推荐）** | 依赖 `T059`（模型已冻结）、`T049`（98 题就位）、`T061–T063`（报告、评审表与 `--sc015` 对比就位），全部前置已满足 | 直接完成 quickstart V5、SC-015 门禁与普法文章人工终审闭环，同步满足 `T059` 核销条件，并为 `T065` 提供全 7 类 + SC-009/010 真实数据 |
| **`T065`（完整整理 `docs/learning/06-evaluation.md`）** | 已随前序任务累积至 `[L6.1]–[L6.6]` | 缺少完整 98 题（特别是多违法行为、多轮意图、拒答边界及文章评审）的 7B 实测结果；紧接 `T064` 之后收口 Phase 5 最顺畅 |
| **Phase 6（`T066–T068`，US4 知识库维护）** | P4 优先级，含 `tu kb diff`、`configs/app.yaml` 的 `kb.version` 接线与更新集成测试 | 与当前 Phase 5 评测主线独立；且 `T067` 会改动配置加载路径，先在冻结的编排与评测基线上跑完 `T064`，再进入 Phase 6 更干净、无基线漂移 |
| **Phase 7（`T069–T074`，Gradio UI 与收尾）** | 依赖 US1/US2 与 Phase 5（`T071` 全量验证包含 V5 的 SC-015，`T070`/`T074` 需依据全量能力画像挑选演示场景与声明边界） | 先拿到 `T064` 完整 98 题画像并收口 Phase 4–5，再推进 UI 与收尾可避免返工 |
| **`T078`** | 已标记 `[Post-POC / 正式阶段]` | 2026-11-19 已由用户确认移出 POC 范围，不纳入候选 |

---

## 2. 现状与只读摸底核实

以下版本、统计数字、指纹与源码契约均经仓库只读核实（未触碰 `inputs/`）：

### 2.1 代码、测试与历史产物锁基线

- **代码基线**：`bea2d97`（`feat(eval): add multi_violation, intent, and boundary cases to v1 (T049)`），工作区干净。
- **测试与静态检查基线**：`uv run pytest` **421 passed / 6 xfailed**，`uv run ruff check src tests` 全绿。
- **历史产物哈希锁**：`shasum -a 256 -c artifacts/logs/t075/01/output.sha256` **25/25 OK**（锁定 T075 的 4 个 run、审阅材料及权重；全程须保持 25/25 OK）。
- **现有 `artifacts/eval/` 状态**：共 20 个历史 `run-*` 目录（含 `run-20261122-090018` 空目录，属历史中断遗留，保持只读不删不改）；尚无任何 `compare-*` 归档目录。

### 2.2 冻结演示模型、活跃知识库与 `eval/cases/v1/` 真实统计

| 锁定输入项 | 路径 / 标识 | 实测指纹与规模 |
|---|---|---|
| **冻结 7B 演示模型** | `exp-20261116-resume500`（底座 `mlx-community/Qwen2.5-7B-Instruct-4bit`） | 最终权重 `artifacts/train/exp-20261116-resume500/adapters/adapters.safetensors`，SHA-256 `b62a7d0e86f490d946fb69d795d80707f2b3386c1cbb0a0529e6adef2ae18930`；`artifacts/serve/current.json` 当前即指向该实验，`127.0.0.1:8080` 空闲 |
| **活跃知识库** | `artifacts/kb/kb-20261119-045641.sqlite` | SHA-256 `40d4ea70333404ccd9724fccddc09c51311de0123ea9416a37549fd7742f13bb`；24 篇现行法规、3,809 条记录、67 条已确认关联（`liability_for` 26 + `references` 41）；对 `eval/cases/v1` 全 98 题 `validate_gold_clauses` **0 问题** |
| **运行时配置** | `configs/app.yaml` | `runtime.model_endpoint: http://127.0.0.1:8080/v1`、`allowed_hosts: [127.0.0.1, localhost]`、`model_name: default`；`session`: `max_questions_per_turn=5`、`default_article_count=3`、`max_article_count=10` |
| **离线外部模型配置** | `configs/synth.yaml` | `external_llm.base_url: https://api.deepseek.com`、`model: deepseek-chat`、`seed: 42`、`timeout_s: 120`；API Key 仅从环境变量 `TU_EXTERNAL_LLM_API_KEY` 读取（仅用于离线初审草稿） |

**`eval/cases/v1/` 逐文件真实统计（共 98 题、116 轮、全 7 类）**：

| 文件 | 题数 | 类别分布 | 对话总轮数 | Git blob（须保持只读零改动） |
|---|---:|---|---:|---|
| `eval/cases/v1/reviewed.jsonl` | 60 | `clause_id: 60` | 60 | `63a1f9533e78fb71fd9bf99bb1fb663127eb22eb` |
| `eval/cases/v1/articles.jsonl` | 10 | `article: 10`（含 9 题 `expect_articles`、2 题 `protected_names`、1 题 `article-007` 应拒答） | 14 | `fc72e84a5c591f73556330bbe1e62989201fe912` |
| `eval/cases/v1/multi_violation.jsonl` | 10 | `multi_violation: 10` | 10 | `fff6051aaa06e09076a869709bcc626470499db9` |
| `eval/cases/v1/intent.jsonl` | 10 | `intent: 10` | 23 | `0453b64269b24603d8dc142c3a25eae18d011670` |
| `eval/cases/v1/boundaries.jsonl` | 8 | `refusal: 3`、`false_refusal: 2`、`exception: 3` | 9 | `d1e75e4ece6b256489e85a723ed3381f19712b95` |
| **合计** | **98** | **7 类全覆盖** | **116** | — |

### 2.3 本机耗时估算与关键运行风险摸底

1. **同机型（M1 Pro / 32GB）历史实测耗时对照（仅 `exp-20261116-resume500`）**：
   - `run-20261117-081504`（60 题 `clause_id` / 60 轮）：**228 秒**（3 分 48 秒，约 3.8 秒/轮）；
   - `run-20261120-024531`（10 题 `article` / 14 轮）：**146 秒**（2 分 26 秒，约 10.4 秒/轮）；
   - `run-20261122-090101`（T054 后 10 题 `article` / 14 轮）：**151 秒**（2 分 31 秒）；
   - 据此估算：98 题 / 116 轮单轮约 **9–12 分钟**，2 轮独立冷启动含重启与 A/B 冒烟总计约 **20–28 分钟**；`ModelClient` 单次请求超时 `300s`（`max_tokens=4096`）。
2. **`mlx_lm.server` 内存级 `LRUPromptCache`（已拍板重启消除）**：
   - `.venv/lib/python3.12/site-packages/mlx_lm/server.py`（L48、L843、L964）维护进程内 `LRUPromptCache`；已按决策 1（选项 A）确定两轮之间优雅重启 `tu serve model`，确保两次独立冷启动并各自重做 `ab.py 0` 路由冒烟。
3. **本机 Metal GPU / 网络与沙箱边界**：
   - 仅 `tu serve model`、`ab.py`、`tu eval run`（需要 Metal GPU 与 `127.0.0.1:8080`）以及离线 `deepseek_review_articles.py`（需要访问 `https://api.deepseek.com` 与 `TU_EXTERNAL_LLM_API_KEY`）各自单步在非沙箱本机环境执行；其余所有只读对比、报告、单测、静态检查与哈希核验全部在标准沙箱内完成。
4. **时间命名口径差异（仅作知情备忘）**：
   - `eval/runner.py` 生成的 `run-<YYYYMMDD-HHMMSS>` 使用 **UTC** 时间戳，`eval/compare.py` 生成的 `compare-<YYYYMMDD-HHMMSS>` 使用 **本机** 时间戳，各自在 `manifest.json` 写明 ISO 时间。

### 2.4 源码逐行核查：人工评审 CSV、SC-015 与外部初审隔离契约（决策 3 关键防坑）

逐行核查 `src/tu_assistant/eval/report.py`（L133–341）、`src/tu_assistant/eval/compare.py`（L862–1118）、`src/tu_assistant/synth/llm.py`（L13–109）与 `tests/unit/test_runtime_isolation.py`（L19–59），核实以下 **5 条硬约束**（决策 3 流程设计必须严格遵守）：

1. **10 道文章题的精确允许维度（由 `report._required_dimensions` 强制校验，违者抛 `ReportError` 退 2）**：
   - **`correctness`（SC-009，9 题）**：`article-001`、`002`、`003`、`004`、`005`、`006`、`008`、`009`、`010`；
   - **`diversity`（SC-010，仅 5 道多篇题允许标注）**：`article-001`（`[3]`）、`002`（`[2]`）、`003`（`[3]`）、`004`（`[4]`）、`009`（`[None, 3]`）；对单篇题（`005/006/008/010`）标 `diversity` 会被 `load_reviews` 硬拒；
   - **`other`（1 题应拒答）**：`article-007`（`should_refuse=true`）**只能**标注 `dimension=other`（或留空，自动归 `other`）；标 `correctness`/`diversity` 会被 `load_reviews` 硬拒；其 `verdict=fail` 会进入失败清单但不影响 SC-009/SC-010 数值。
2. **`--sc015 --reviews` 的“双 Run 必须同时有评审行”硬约束（防单侧 `None` 误杀）**：
   - `compare_runs`（`compare.py` L875–889）会分别按 `run_id=run_1` 和 `run_id=run_2` 过滤 CSV；
   - **若评审 CSV 只填了 `run_1`、未填 `run_2`**，则 `run_1` 的 SC-009/SC-010 有数值、`run_2` 为 `None` → `compare_runs` 置 `partial_none=True` → `evaluate_sc015`（L1069–1081）**必定判 `FAIL`（“部分 run 无有效分母”，退出码 1）**！
   - 因此最终确认 CSV **必须同时包含 `<run_1>` 与 `<run_2>` 两个 `run_id` 的评审记录**。
3. **防止 AI 草稿与人工终判双重计数（`reviewer` 隔离规则）**：
   - `load_reviews` 的去重键是 `(run_id, case_id, dimension, reviewer)`（`report.py` L271），`aggregate_reviews` 会把同一 `dimension` 下**不同 `reviewer`** 的记录全部累加进分母。
   - 因此**严禁**把 DeepSeek 初审行与用户人工确认行混写在同一个最终 CSV 中！必须双文件分离：
     - **AI 初审草稿（不传给最终 `--reviews`）**：`artifacts/logs/t064/reviews-deepseek-draft.csv`（`reviewer="deepseek-chat-draft"`）+ 可读审阅单 `artifacts/logs/t064/article-review-sheet.md`；
     - **人工终审定稿（传给正式 `tu eval report/compare --reviews`）**：`eval/reviews/t064-reviews.csv`（仅保留用户逐题确认/改判后的最终行，统一 `reviewer="user"`，并在 `comment` 中按需注明“经 DeepSeek 初审辅助”与“Run 2 与 Run 1 逐字一致经人工确认复用”）。
4. **实得 `< 2` 篇时的 `diversity`（SC-010）口径防失真**：
   - 历史 T075 中父模型 `exp-20261116-resume500` 在 `article-001..004` 与 `article-009` 上实得篇数均为 `0`；`aggregate_reviews` 的 `SC-010 = fail / total` 衡量的是**“同一次生成的多篇文章实质重复率”**。
   - 若某道多篇题实际交付文章 `< 2` 篇（例如模型误拒或未产出标准多篇），根本不存在“多篇之间是否实质重复”的比较对象：强行填 `fail` 会误报“100% 实质重复”，强行填 `pass` 会误报“0% 实质重复”。推荐口径是：**`correctness`（9 题）全部填行（未出稿/误拒按 rubric 判 `fail`）；`diversity` 仅对实得 `≥ 2` 篇的题填行（实得 `< 2` 篇不填 `diversity` 行）**；若两轮全部 5 道多篇题均 `< 2` 篇，则 SC-010 两轮同为 `None`、在 `--sc015` 中如实 `skipped`（若仅单轮产出 `≥ 2` 篇，则篇数本身已剧烈波动，单侧 `None` 触发 `--sc015` FAIL 恰为正确拦截！）。详见 §6 确认项 3b。
5. **宪章原则 III/IV 与运行时静态隔离合规核实**：
   - 宪章原则 III/IV 明确允许“外部大模型服务 MAY 用于离线开发环节（数据合成、评测打分、对照基线），但 MUST NOT 出现在线上运行链路中”；
   - `tests/unit/test_runtime_isolation.py` 静态扫描 `src/tu_assistant/{chat,runtime,ui,eval}/`，禁止导入 `openai` / `tu_assistant.synth`；
   - `src/tu_assistant/synth/llm.py` L13 的 `ALLOWED_INPUT_SOURCES` 已显式允许 `"eval_case"`，且 `from_config(load_synth_config("configs/synth.yaml"))` 原生支持读取 `deepseek-chat`、`seed=42` 与 `TU_EXTERNAL_LLM_API_KEY`；
   - 因此，将离线初审脚本放在 **`scripts/experiments/t064/deepseek_review_articles.py`**（受 Git 版本管理，符合 `docs/experiments/README.md` 规范，零修改 `src/`），调用 `ExternalLLM.chat(..., input_source="eval_case", temperature=0.0)`，即可 100% 满足宪章原则 III/IV、`test_runtime_isolation.py` 与零触碰 `inputs/` 的全部红线。

---

## 3. 实施边界与约束

### 3.1 允许新增 / 修改的文件边界

| 路径 | 阶段 | 操作 | 说明 |
|---|---|---|---|
| `artifacts/eval/<run_1>/`、`artifacts/eval/<run_2>/` | 阶段 A | **新增（Git 忽略）** | 两轮独立冷启动 98 题完整评测产物（各自含 `results.jsonl`、`report.md`、`manifest.json`） |
| `scripts/experiments/t064/deepseek_review_articles.py` | 阶段 A | **新增（Git 跟踪）** | 离线文章初审草稿脚本（调用 `synth.llm.from_config`，`input_source="eval_case"`，`temperature=0.0`，不触碰 `src/` 与 `inputs/`） |
| `artifacts/logs/t064/` | 阶段 A/B | **新增（Git 忽略）** | `preflight.json`、服务/AB/评测日志、`compare-auto.md`、`reviews-deepseek-draft.csv`、`article-review-sheet.md`、`report-run{1,2}-with-reviews.md` |
| `eval/reviews/t064-reviews.csv` | 阶段 B | **新增（Git 跟踪）** | 经用户逐题人工终审确认后的正式评审 CSV（仅含最终 `reviewer="user"` 行，覆盖 `<run_1>` 与 `<run_2>`，严格遵守 `eval/review-template.csv` 格式） |
| `artifacts/eval/compare-<ts>/` | 阶段 B | **新增（Git 忽略）** | 最终正式落盘产物：`tu eval compare --sc015 <run_1> <run_2> --reviews eval/reviews/t064-reviews.csv --save`（含 `compare.md`、`manifest.json`） |
| `docs/experiments/T064-eval-repeatability.md`、`docs/experiments/README.md` | 阶段 B | **新增 / 更新（决策 2 已定）** | 可版本化的 T064 实测报告（输入指纹、两轮耗时、全 98 题 SC-001 ~ SC-011 含人工评审汇总、SC-015 逐项波动判定、历史基线对账与复核命令） |
| `docs/learning/06-evaluation.md`、`docs/learning/README.md`、`docs/learning/00-glossary.md` | 阶段 B | **修改** | 增补 `[L6.7]` 学习小节并同步索引与术语表（全章重构留给 T065） |

### 3.2 明确不做（严格防越界）

- **严禁修改 `src/` 与 `tests/` 任何文件**（亦不改动 `configs/app.yaml`、`configs/synth.yaml`、`eval/cases/v1/`、`eval/review-template.csv`、`specs/`）。若执行中意外发现代码 bug 或 SC-015 超限（退出码 `1`），**立即停步并完整保留现场证据与失败 run 上报用户**，绝不静默改代码或删日志重跑掩盖波动；
- **严禁把 DeepSeek 初审草稿直接充当人工终判落盘**：草稿 CSV 仅存 `artifacts/logs/t064/`，必须经用户人工逐题审阅确认后，才写入正式 `eval/reviews/t064-reviews.csv` 并执行阶段 B 最终对比；
- **严禁触碰历史产物与 `inputs/`**：所有历史 `artifacts/eval/run-*`（含空目录 `run-20261122-090018`）、新建 run 目录的原始 `report.md`、历史 KB、数据集、权重及 `artifacts/logs/t075/` 一律只读不改写；严禁读取 `inputs/` 下任何文件；
- **严禁提前勾选 `tasks.md` 或提交**：必须完成独立只读复审闭环并经用户明确确认验收后，再同步勾选 `T064` 与 `T059`（决策 4 已定）并提交。

---

## 4. 具体实施步骤与确定性验收方法

### 4.1 阶段 A：两轮 7B 独立评测 + 自动 SC-015 先验 + 离线 DeepSeek 初审草稿

1. **Step A1 · 环境与输入指纹预检（只读）**
   - 核验 `git status --short` 干净、`lsof -iTCP:8080 -sTCP:LISTEN` 空闲、无残留训练/推理进程、`shasum -a 256 -c artifacts/logs/t075/01/output.sha256` 为 `25/25 OK`；
   - 创建 `artifacts/logs/t064/preflight.json`，登记 Git HEAD、冻结 adapter SHA-256、活跃 KB SHA-256、`eval/cases/v1/*.jsonl` 5 文件 SHA-256、`configs/app.yaml` 哈希、`src/` 全部 `.py` 与 `build_system_prompt(5)` 哈希。
2. **Step A2 · 第 1 轮完整评测（Run 1，独立冷启动）**
   - 离线启动冻结演示模型（日志至 `artifacts/logs/t064/serve-run1.log`）：
     ```bash
     HF_HUB_OFFLINE=1 uv run tu serve model --exp exp-20261116-resume500
     ```
   - 等待 `http://127.0.0.1:8080/v1/models` 就绪；核对 `artifacts/serve/current.json`（`model="default_model"`、`exp="exp-20261116-resume500"`、`base_model="mlx-community/Qwen2.5-7B-Instruct-4bit"`）；
   - 执行 E002 路由冒烟（日志至 `artifacts/logs/t064/ab-run1.log`）：
     ```bash
     uv run python scripts/experiments/e002/ab.py 0
     ```
     核验 `两次输出相同: False` 且 `default_model` 含 `〔` 与日期标签；
   - 执行第 1 轮 98 题完整评测并记录起止墙钟耗时（日志至 `artifacts/logs/t064/run1.log`）：
     ```bash
     uv run tu eval run \
       --exp exp-20261116-resume500 \
       --kb-version kb-20261119-045641 \
       --cases eval/cases/v1
     ```
   - 核验 Run 1 产物完整性（`case_count==98`、`gold_clause_issues==[]`、`results.jsonl` 98 行、`report.md` 非空）；
   - 发送 `SIGTERM` 优雅关闭服务进程组，确认进程退出且 `127.0.0.1:8080` 释放。
3. **Step A3 · 第 2 轮重复评测（Run 2，独立冷启动）**
   - 复核 `src/`、`configs/app.yaml`、`eval/cases/v1/` 哈希与 `preflight.json` 逐项一致；
   - 重新离线启动 `HF_HUB_OFFLINE=1 uv run tu serve model --exp exp-20261116-resume500`（日志至 `artifacts/logs/t064/serve-run2.log`），核对 `current.json` 并再次执行 `uv run python scripts/experiments/e002/ab.py 0`（`artifacts/logs/t064/ab-run2.log`）；
   - 以完全相同命令运行第 2 轮评测并记录耗时（`artifacts/logs/t064/run2.log`）：
     ```bash
     uv run tu eval run \
       --exp exp-20261116-resume500 \
       --kb-version kb-20261119-045641 \
       --cases eval/cases/v1
     ```
   - 核验 Run 2 产物完整性，优雅关闭服务进程，确认端口 `8080` 空闲且 `artifacts/serve/current.json` 仍指向 `exp-20261116-resume500`。
4. **Step A4 · 自动指标先验 SC-015 校验与逐题文本差异核对**
   - 先执行不含人工评审的自动指标 SC-015 检查（不污染最终 `artifacts/eval/compare-*`）：
     ```bash
     uv run tu eval compare --sc015 <run_1> <run_2> --out artifacts/logs/t064/compare-auto.md
     ```
   - 核验退出码为 `0`（全部有效自动指标最大波动 `≤ 2.0 pp`）；同时只读统计两轮 98 题（及单独 10 道文章题）的 `final_raw` 与各轮 `turns[].content` 逐字一致率。
   - **超限应急预案**：若本步退出码为 `1`（任一自动指标波动 `> 2.0 pp` 或单侧 `None`），立即停步并保留两份完整 run，逐题定位差异后上报用户，不进入后续掩盖或重跑。
5. **Step A5 · 离线 DeepSeek 普法文章初审草稿生成（提交用户人工复核）**
   - 编写并运行离线脚本 `scripts/experiments/t064/deepseek_review_articles.py`：
     - 通过 `tu_assistant.synth.llm.from_config(load_synth_config("configs/synth.yaml"))`（`deepseek-chat`、`seed=42`、`temperature=0.0`、`input_source="eval_case"`，读取环境变量 `TU_EXTERNAL_LLM_API_KEY`）；
     - 仅向 DeepSeek 发送 `eval/cases/v1/articles.jsonl` 的虚构案情/题目、`rubric`、从 `kb-20261119-045641.sqlite` 查出的对应 `gold.clauses` 原文，以及本地 7B 在 `results.jsonl` 的各轮交付稿与校验统计；
     - 按确认项 3a/3b 的规则输出两份草稿文件：
       1. `artifacts/logs/t064/reviews-deepseek-draft.csv`（7 列格式，`reviewer="deepseek-chat-draft"`，并现场用 `report.load_reviews` 校验 0 格式错误）；
       2. `artifacts/logs/t064/article-review-sheet.md`（逐题并列展示 `rubric`、自动篇数/脱敏/拒答初筛、模型完整交付稿、Run 1/Run 2 一致性比对，以及 DeepSeek 初审结论与逐条依据）；
   - **暂停交由用户人工终审**：向用户汇报自动 SC-015 先验结果与 `article-review-sheet.md` / `reviews-deepseek-draft.csv` 路径，请用户逐题确认或修改 `verdict` / `comment`。

### 4.2 阶段 B：人工终审落盘 → 最终 `--sc015 --reviews` 对比 → 文档与独立复审收口

6. **Step B1 · 落盘人工终审定稿 CSV**
   - 按用户终审意见生成 **`eval/reviews/t064-reviews.csv`**（仅含人类最终确认行，统一 `reviewer="user"`，ISO 8601 UTC `created_at`，**覆盖 `<run_1>` 与 `<run_2>` 两个 `run_id`**；逐字一致的题在 `run_2` 的 `comment` 注明“与 `<run_1>` 交付稿逐字一致，经人工确认复用”，有差异的题按各自人工终判独立记录）；
   - 用 `report.load_reviews` 分别校验 `<run_1>` 与 `<run_2>` 均 0 异常，确认无双 `reviewer` 重复计数。
7. **Step B2 · 最终报告复核与 SC-015 正式落盘**
   - 只读生成带人工评审汇总的单轮报告副本（不覆盖 `artifacts/eval/<run_id>/report.md`）：
     ```bash
     uv run tu eval report <run_1> --reviews eval/reviews/t064-reviews.csv --out artifacts/logs/t064/report-run1-with-reviews.md
     uv run tu eval report <run_2> --reviews eval/reviews/t064-reviews.csv --out artifacts/logs/t064/report-run2-with-reviews.md
     ```
   - 执行最终 SC-015 稳定性判定并落盘至 `artifacts/eval/compare-<ts>/`：
     ```bash
     uv run tu eval compare --sc015 <run_1> <run_2> --reviews eval/reviews/t064-reviews.csv --save
     ```
   - 核验退出码 `0`、`SC-015 总判定：PASS`、`manifest.json` 中 `inputs.reviews == "eval/reviews/t064-reviews.csv"`、`case_count == 98`、`sc015_passed == true`。
8. **Step B3 · 历史基线只读对账、文档沉淀与独立复审**
   - 复核历史 SC-016 零回归：`uv run tu eval compare --sc016 run-20261117-022645 run-20261117-081504`（退出 `0`，`1→17/60`、`9/60`、`0→21/30`）；
   - 只读对账本次 Run 1 中原 60 题（`reviewed.jsonl`）相对 `run-20261117-081504`、原 10 题文章（`articles.jsonl`）相对 `run-20261122-090101` 的子集表现；
   - 撰写 `docs/experiments/T064-eval-repeatability.md` 并登记于 `docs/experiments/README.md`（决策 2 已定）；
   - 更新 `docs/learning/06-evaluation.md`（`[L6.7]`）、`docs/learning/README.md`、`docs/learning/00-glossary.md`；
   - 运行全量回归与合规检查：`uv run pytest`（421 passed / 6 xfailed，含 `test_runtime_isolation.py`）、`uv run ruff check src tests`、`uv run ruff check scripts/experiments/t064/deepseek_review_articles.py`、`shasum -a 256 -c artifacts/logs/t075/01/output.sha256`（25/25 OK）、`git status --short`；
   - 按 `.agents/skills/task-review-loop/SKILL.md` 执行独立只读复审闭环（最多 5 轮），完成后汇报最终验收结果，**待用户明确确认后，同步勾选 `tasks.md` 的 `T064` 与 `T059`（决策 4 已定）并提交**。

### 4.3 确定性验收矩阵

| 验收项 | 确定性检验命令 / 条件 | 通过标准 |
|---|---|---|
| **1. 路由与身份真伪防线（E002）** | `ab-run1.log`、`ab-run2.log` + 两份 `manifest.json` | 两次冷启动 A/B 冒烟均 `两次输出相同: False` 且 `default_model` 含 `〔` 与日期标签；两份 `manifest.json` 均满足 `config.model == "default_model"`、`config.exp == "exp-20261116-resume500"`、`config.base_model == "mlx-community/Qwen2.5-7B-Instruct-4bit"`、`config.temperature == 0.0`、`config.use_system_prompt is True` |
| **2. 完整 98 题输入对齐与零坏题** | 两份 `manifest.json` 与 `results.jsonl` | `inputs.cases == "eval/cases/v1"`、`Path(inputs.kb).stem == "kb-20261119-045641"`、`case_count == 98`、`gold_clause_issues == []`；两份 `results.jsonl` 各恰好 98 行且 `case_id` 与磁盘 `eval/cases/v1/` 98 题完全一致 |
| **3. 自动先验与最终 `--reviews` 双重 SC-015 门禁** | ① `tu eval compare --sc015 <r1> <r2> --out artifacts/logs/t064/compare-auto.md`；② `tu eval compare --sc015 <r1> <r2> --reviews eval/reviews/t064-reviews.csv --save` | 两条命令退出码均为 **`0`**、均输出 `SC-015 总判定：PASS`；最终落盘目录 `artifacts/eval/compare-<ts>/` 含 `compare.md` 与 `manifest.json`（`type == "eval_compare"`、`config.mode == "sc015"`、`config.threshold_pp == 2.0`、`inputs.reviews == "eval/reviews/t064-reviews.csv"`、`case_count == 98`、`sc015_passed == true`）；全部有效指标最大波动 `≤ 2.0 pp` 且无单侧 `None` 异常 |
| **4. 人工评审 CSV 口径与双文件隔离** | `eval/reviews/t064-reviews.csv` 经 `report.load_reviews` 校验（分别对 `<r1>` 与 `<r2>`） | 0 `ReportError`；`reviewer` 仅含人工终审标识（绝不混入 `deepseek-chat-draft` 导致双重计数）；`<r1>` 与 `<r2>` 均覆盖 9 题 `correctness` + `article-007` `other` + 全部实得 `≥ 2` 篇多篇题的 `diversity`；`tu eval report <r1> --reviews ...` 退出 `0` 且完整输出 SC-001 ~ SC-011（含 SC-009 实测值与校验前/后两列） |
| **5. 离线初审隔离、历史锁与全量回归** | `uv run pytest`、`uv run ruff check src tests scripts/experiments/t064/deepseek_review_articles.py`、`shasum -a 256 -c artifacts/logs/t075/01/output.sha256`、`tu eval compare --sc016 run-20261117-022645 run-20261117-081504` | `pytest` **421 passed / 6 xfailed**（含 `test_runtime_isolation.py` 全绿）；`ruff` 全绿；T075 哈希锁 **25/25 OK**；SC-016 退出 `0`（`1→17/60`、`9/60`、`0→21/30`）；`src/`、`tests/`、`configs/`、`eval/cases/v1/`、`specs/` 零改动 |
| **6. 环境清理与合规红线** | `lsof -iTCP:8080 -sTCP:LISTEN`、`git status --short` | 端口 `8080` 空闲；未读取 `inputs/`；单次完整评测耗时远低于 1 个工作日；`tasks.md` 在用户最终确认前保持未勾选 |

---

## 5. 学习文档更新点（及与 T065 / 07 / 08 的分工）

- **本单更新（轻量实测补节，避免越界抢占 T065）**：
  - **`docs/learning/06-evaluation.md` 新增 `[L6.7]` 重复评测、确定性边界与“AI 初审 + 人工终判”闭环**：
    - 解释贪婪解码（`temperature=0`）理论上逐 token 确定，但在真实本地推理中仍可能因 Metal/GPU 浮点归约顺序、服务端 `LRUPromptCache` 冷热状态产生微小差异，因此工程上必须用两轮独立冷启动实测验证 SC-015（`≤ 2.0 pp`）；
    - 用本次 T064 两轮真实 run 的实测数据（单轮耗时、逐题文本一致率、SC-001 ~ SC-011 全指标与最大波动 pp）说明如何区分“测量工具稳定可靠（SC-015）”与“POC 模型能力基线”；
    - 结合本次外部 DeepSeek 初审 + 人工终审实践，讲清三个工程边界：① 离线评测打分（宪章 III/IV 允许）与线上零外调的物理隔离；② 为何 AI 草稿与人类终判必须分文件隔离（防止 `reviewer` 维度双重计数）；③ 为何实得 `< 2` 篇的题不能硬填 `diversity` 分数（避免失真）。
  - **索引与术语同步**：
    - 更新 `docs/learning/README.md` 第 6 章状态为 `进行中（已含 L6.1–L6.7；完整章节由 T065 整理）`；
    - 在 `docs/learning/00-glossary.md` 的 `## 评测` 补充“贪婪解码（`temperature=0`）”与“前缀缓存（Prompt Cache）”条目并链接至 `[L6.7]`。
- **与后续学习章节的分工**：
  - **`T065`（完整 `docs/learning/06-evaluation.md`）**：基于 T064 落盘的 98 题全量结果（含人工终审 SC-009/SC-010），完成第 6 章总览与结构整理、SC-001 ~ SC-011 指标计算体系串讲、7 大类别薄弱项深度剖析与正式阶段数据改进方向反推，补齐章末“可以继续问的问题”；
  - **`T073`（`docs/learning/07-serving-demo.md`）**：聚焦模型服务部署、对话编排全貌、Gradio 演示界面与训练/演示互斥原理；
  - **`T074`（`docs/learning/08-lessons-and-next.md`）**：聚焦全项目踩坑汇总、POC 证明边界与正式阶段路线。

---

## 6. 决策拍板状态与剩余实操确认项

### 6.1 已拍板定案的决策（2026-11-23）

| 编号 | 决策项 | 用户拍板结论 |
|---|---|---|
| **决策 1** | 两轮评测之间的服务重启策略 | **已定案（选项 A）**：两轮之间重启 `tu serve model`（两次独立冷启动 + 各自执行 `ab.py 0` 路由冒烟）。 |
| **决策 2** | 评测结果的 Git 持久化归档方式 | **已定案（选项 A）**：新增可版本化实验记录 `docs/experiments/T064-eval-repeatability.md` 并登记至 `docs/experiments/README.md`。 |
| **决策 3** | 普法文章评审方式（SC-009 / SC-010） | **已定案（用户新方案）**：先用离线脚本调用外部 DeepSeek（`deepseek-chat`, `temperature=0`）按 `rubric` 初审生成预填草稿，再交用户人工复核终判，最终以 `eval/reviews/t064-reviews.csv` 接入 `tu eval report / compare --sc015 --reviews --save` 收口。 |
| **决策 4** | T064 验收确认后 `T059` 核销安排 | **已定案（选项 A）**：待 T064 通过独立复审并经用户明确确认验收时，在 `tasks.md` 中同步勾选 `T064` 与 `T059`。 |

### 6.2 决策 3 细化后的 2 项实操确认（确认后即可开工执行阶段 A）

请确认以下 2 个落地细节（如均同意推荐项，直接回复“按推荐开工”即可启动阶段 A；同时请确认终端环境已配置 `TU_EXTERNAL_LLM_API_KEY`）：

1. **确认项 3a · 当 Run 1 与 Run 2 的文章交付稿逐字一致时，DeepSeek 送审策略**
   - **选项 A（推荐）：按差异按需送审**——固定将 Run 1 的全部 10 道文章题送 DeepSeek 初审；程序逐题比对 Run 2 与 Run 1 的全部交付轮次，仅对存在字符差异的题再把 Run 2 独立送审。若两轮 10 题全部逐字一致，用户只需复核 1 套 10 题稿件，定稿时按“逐字一致经人工确认复用”同步写入 `run_2` 记录（满足 `--sc015 --reviews` 双 run 均有有效分母的要求，且节省一半 API 调用与人工重复阅读）。
   - **选项 B：双轮全量独立送审**——无论 Run 1 与 Run 2 交付稿是否逐字一致，均将两轮共 20 题次分别送 DeepSeek 初审并分别呈现供人工复核。

2. **确认项 3b · 当某道多篇文章题实得 `< 2` 篇（如误拒或仅出 0/1 篇）时，`diversity`（SC-010）的记录口径**
   - **选项 A（推荐）：`correctness` 全量填行、`diversity` 仅对实得 `≥ 2` 篇的题填行**——9 道常规文章题全部填 `correctness`（未出稿/误拒按 `rubric` 判 `fail`）；5 道多篇题仅当实际拆出 `≥ 2` 篇文章时才评判并填写 `diversity` 行（实得 `< 2` 篇不填 `diversity` 行，避免把“未出稿”误报成“0% 重复”或“100% 实质重复”）；`article-007` 填 `dimension=other`。
   - **选项 B：5 道多篇题无论是否出稿均强制填写 `diversity=fail`**（SC-010 会把未出稿统一计入“实质重复率”）。

---

## 7. 实施结果与独立复审记录（2026-11-23）

### 7.1 实施产物与验收实测摘要

- **两轮独立冷启动评测**：
  - Run 1：`artifacts/eval/run-20261123-051432`（`13:14:32 → 13:35:38`，墙钟 21 分 06 秒，`case_count=98`，`gold_clause_issues=[]`，`ab-run1.log` 通过）
  - Run 2：`artifacts/eval/run-20261123-053832`（`13:38:32 → 13:59:28`，墙钟 20 分 56 秒，`case_count=98`，`gold_clause_issues=[]`，`ab-run2.log` 通过）
  - 两轮逐字一致性：**98/98 题 `final_raw` 与 `turns[].content` 100% 逐字一致**。
- **离线 DeepSeek 初审 + 人工终审**：
  - 离线脚本：`scripts/experiments/t064/deepseek_review_articles.py`（`calls=10`，`prompt_tokens=10,396`，`completion_tokens=1,970`），草稿存 `artifacts/logs/t064/{reviews-deepseek-draft.csv,article-review-sheet.md}`；
  - 人工终审定稿：`eval/reviews/t064-reviews.csv`（仅 `reviewer="user"`，覆盖两轮共 20 行，已修正 `article-009` 第 1 轮咨询轮误报泄露的 comment；`report.load_reviews` 两轮均 0 异常）。
- **SC-015 稳定性与回归门禁**：
  - 自动先验：`artifacts/logs/t064/compare-auto.md`（11 项有效指标 `0.0 pp`，退出码 `0` PASS）；
  - 最终正式落盘：`artifacts/eval/compare-20261123-145054/{compare.md,manifest.json}`（12 项有效指标含 `SC-009=0.000 (0/9)` 全部 `0.0 pp`，`SC-010` 跳过，`sc015_passed=true`，退出码 `0` PASS）；
  - 历史 SC-016 零回归：`tu eval compare --sc016 run-20261117-022645 run-20261117-081504` 退出码 `0`（`1/60→17/60`、`9/60`、`0/30→21/30`）；
  - 回归与合规：`uv run pytest` **421 passed, 6 xfailed**，`uv run ruff check src tests scripts/experiments/t064/deepseek_review_articles.py` **All checks passed!**，`shasum -a 256 -c artifacts/logs/t075/01/output.sha256` **25/25 OK**，端口 `8080` 空闲，`src/`、`tests/`、`configs/`、`eval/cases/v1/`、`specs/`、`tasks.md` 零改动。

### 7.2 独立只读复审闭环（`reviewer` · Gemini 4 Neon High，共 2 轮，一致通过）

- **Round 1（结论：需修改）**：
  - 阻断项 1：`docs/experiments/T064-eval-repeatability.md` L5/L26–27 与 `docs/learning/06-evaluation.md` L225 记录的两轮起止时间将 `run_id` 的 `:32` 秒抹零（写作 `13:14:00`/`13:38:00` 及“约 21.5 分钟”），与真实 `run_id` / `manifest.json` / `serve-run*.log` 存在 32 秒偏差（真实为 `13:14:32→13:35:38`［21 分 06 秒］、`13:38:32→13:59:28`［20 分 56 秒］，均值约 21 分钟）。→ **已全量采纳修复**。
  - 非阻断建议 1：清理本次首次沙箱尝试 `tu eval run` 遗留的空目录 `artifacts/eval/run-20261123-051348/`（保留历史 `run-20261122-090018` 不动）。→ **已采纳删除**。
  - 非阻断建议 2：`docs/experiments/T064-eval-repeatability.md` L44 表述微调为“5 题在多篇生成轮次经自动拆篇实得篇数均为 `0`（`< 2` 篇）”。→ **已采纳微调**。
- **Round 2（结论：通过；阻断项：无；非阻断建议：无）**：
  - 复核全部修复闭环、全量 `pytest` / `ruff` / T075 哈希锁 / 文件边界无回归，审查节点已回收。
