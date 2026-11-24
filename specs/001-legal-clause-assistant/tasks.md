---

description: "Task list for 001-legal-clause-assistant (POC)"
---

# Tasks: 工会法律条款智能助手（条款咨询与普法文章生成）— POC

**Input**: Design documents from `/specs/001-legal-clause-assistant/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: 宪章要求"确定性的逻辑（文档解析与条款拆分、出处比对校验、评测打分）MUST 有自动化测试"，
因此这些模块包含单元测试任务；其余部分以 quickstart 场景验证。

**Organization**: 按 spec 中的用户故事分阶段。由于宪章原则 V 要求"评测集先于训练建立"，
评测的核心能力（用例格式、运行器、条款识别指标）放在 Foundational 阶段；US3 阶段补全其余指标与对比报告。

**全局约束**（每个任务都适用）：
- 不得读取 `inputs/` 下文件的内容；调试切分规则时只运行输出统计信息的脚本，需要看原文时先征得用户同意（AGENTS.md）。
- 运行时代码不得调用外部服务；外部大模型客户端只允许在 `src/tu_assistant/synth/` 中使用（宪章原则 III、IV）。
- 每个阶段结束时更新 `docs/learning/` 对应章节（AGENTS.md）。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无未完成的依赖）
- **[Story]**: 所属用户故事（US1 咨询 / US2 普法文章 / US3 评测 / US4 知识库维护）

---

## Phase 1: Setup（项目初始化）

**Purpose**: 建立项目骨架与开发环境

- [x] T001 创建 plan.md 中的目录结构：`configs/`、`configs/train/`、`src/tu_assistant/{kb,citation,chat,runtime,synth,train,eval,ui}/`、`tests/{unit,integration,fixtures}/`、`eval/cases/`，各包含 `__init__.py`
- [x] T002 在 `pyproject.toml` 中用 uv 初始化项目（Python 3.12），添加依赖 mlx-lm、typer、pyyaml、python-docx、pdfplumber、beautifulsoup4、openai、gradio，开发依赖 pytest、ruff；锁定版本（`uv.lock`），优先选择发布超过 7 天的版本
- [x] T003 [P] 在 `pyproject.toml` 中配置 ruff（lint + format）与 pytest，入口脚本 `tu = "tu_assistant.cli:app"`
- [x] T004 [P] 创建配置文件骨架：`configs/app.yaml`（`runtime.model_endpoint`、`runtime.allowed_hosts: [127.0.0.1, localhost]`、`session.max_questions_per_turn: 5`、`session.default_article_count: 3`、`session.max_article_count: 10`）、`configs/synth.yaml`（`external_llm.base_url`、`external_llm.model`、改写倍数 3–5、提示词版本）；API Key 只从环境变量 `TU_EXTERNAL_LLM_API_KEY` 读取
- [x] T005 [P] 实现配置加载 `src/tu_assistant/config.py`（读取 YAML，支持命令行覆盖）
- [x] T006 [P] 实现产物清单工具 `src/tu_assistant/manifest.py`：为 `artifacts/` 下每个产物写 `manifest.json`（ID、创建时间、输入版本、配置哈希、随机种子），满足宪章原则 VI

---

## Phase 2: Foundational（所有用户故事的前置）

**Purpose**: 知识库、出处校验、模型端点、训练封装、评测核心

**⚠️ CRITICAL**: 本阶段完成前不能开始任何用户故事

### 知识库：入库与条款切分

- [x] T007 [P] 实现中文数字与编号转换 `src/tu_assistant/kb/numbers.py`（"第五十一条" → 51，"（三）" → 3，保留原始写法）
- [x] T008 [P] 单元测试 `tests/unit/test_numbers.py`：覆盖十、十一、二十、一百零一、一百一十等边界
- [x] T009 [P] 实现文档读取 `src/tu_assistant/kb/readers.py`：`.txt`（项目方当前文档均为纯文本）、`.docx`、文本型 `.pdf`、`.html` 统一转为纯文本
- [x] T010 实现条款切分 `src/tu_assistant/kb/parse.py`：识别 `第X编/章/节` 标题路径、`第X条`（条）、条内自然段（款）、`（一）（二）`（项）；兼容不以"第X条"组织、而以"一、二、三"分段的通知类文件；输出 Clause 列表（依赖 T007）
- [x] T011 [P] 准备测试用公开法条片段 `tests/fixtures/`（自行编写的示例文本，不取自 `inputs/`），含条 / 款 / 项、编号缺口、重复编号、"一、二、三"分段等情形
- [x] T012 单元测试 `tests/unit/test_parse.py`：用 T011 的样例验证切分结果与 `parse_warnings`（依赖 T010、T011）
- [x] T013 实现知识库存储 `src/tu_assistant/kb/store.py`：SQLite，每次入库生成新 `kb_version` 文件 `artifacts/kb/<kb_version>.sqlite`；表 LegalDocument、Clause、ClauseRelation 字段按 data-model.md；约束："同一文件内 (`article_no`, `paragraph_no`, `item_no`) 唯一"、"同一 `title` 至多一个 `status=current`"
- [x] T014 实现入库校验 `src/tu_assistant/kb/validate.py`：编号连续性缺口、重复、空条款写入 `parse_warnings`，生成 `parse_report.md`（只含文件序号、条款数、问题编号，不含条文内容）（FR-005）
- [x] T015 实现 `tu kb import <dir>` 与 `tu kb show <title> <article_no>`，入口 `src/tu_assistant/cli.py`（contracts/cli.md）；文件版本信息（`version_label`、`promulgated_on`、`status`）从文件名或文件头解析，缺失时写入问题清单（FR-002）
- [x] T016 对 `inputs/project/` 执行入库，**只查看统计输出**（文件数、每文件条款数、问题条目数）；按问题清单调整切分规则。注意最大文件约 329KB，若为汇编类文件需拆分处理。如需查看原文片段，先征得用户同意

### 条款关联

- [x] T017 实现规则抽取条款关联 `src/tu_assistant/kb/relations.py`：识别"违反本法第X条""依照第X条"等显式引用，生成 `relations_pending.jsonl`（`origin=rule`，`confirmed=false`）
- [x] T018 实现 `tu kb relations extract` / `tu kb relations confirm <file>`；"只有确认过的关联用于训练数据和关联补全指标"（data-model.md）
- [x] T019 用户人工确认关联关系：在 `artifacts/kb/relations_pending.jsonl` 中逐条标注 `confirmed`，用 `tu kb relations confirm` 导入（说明写在 `docs/relations-confirm-guide.md`）
  - 2026-11-19 两批全部完成并导入 `kb-20261119-045641`（合计 67 条已确认：`liability_for` 26 + `references` 41；撤销旧错边共 10 条）。三份审阅源文件已归档至 `data/relation-reviews/`（旧基线 35 条 + 第一批 29 行 + 第二批 47 行），`relation_samples` 67/67 通过校验。[第二批执行单与对账记录](../../docs/handoffs/T019-relations-batch2-handoff.md)
- [x] T077 修正责任关系的条、款定位并追溯影响。复现 T052 独立复审核实的 6 对错款，另核对 2 处整条引用的覆盖范围。对多款条文明确整条与第一款的编号、各自应配的原文和校验层解析口径，并核查历史样本；排查提取与确认逻辑，修正候选经 T019 用户审阅后写入新 KB 版本。核对知识类关系样本和 SC-005 的前后差异，保留历史数据集、run 与 KB 供比对。已训练 adapter 对这些关系的掌握情况需另行实测。[问题清单](../../docs/handoffs/T052-article-synthesis-handoff.md#84-不阻断-t052t057-扩量前须处理)
  - 2026-11-19 独立复审通过并完成收尾：从 `kb-20261113-093057` 派生 `kb-20261119-045641`（787 条多款条文第 1 款显式标 `第1款`，历史产物零改动），导入第一批 `liability_for` 审定差异（撤销 6 旧错边、新增 20，共 26 对可用且 `paragraph_mismatch=0`；审阅文件归档 `data/relation-reviews/`），落地口径 C 校验与 SC-005/编排去重，完成历史对账与 `exp-20261116-resume500` 24 探针实测。[执行单与复审记录](../../docs/handoffs/T077-relation-clause-handoff.md#6-独立复审2026-11-19)
- [ ] T078 `[Post-POC / 正式阶段]` 修复《上海市工伤保险实施办法》（63/63 条）括号条旨（如“（鉴定程序）”）被 `kb/parse.py` 误切为第 1 款导致款号整体顺延 +1 的问题；同步评估受影响的 5 道 `eval/cases/v1/reviewed.jsonl` 用例（含 SC-016 基线 `cand-039`）、历史基线兼容性与该文件条款关联（T019 第二批行 18–25 暂 `reject`）重抽。2026-11-19 经用户确认移出 POC 范围，KB 与旧数据集保持不动以维持 v1/SC-016 基线，T057 清单与 T074 收尾文档登记已知缺陷、演示脚本避开该文件款号（诊断见 `artifacts/logs/t019/p1_heading_diagnosis.md`）

### 出处校验层（宪章原则 I）

- [x] T020 [P] 实现引用解析 `src/tu_assistant/citation/parse.py`：按 contracts/citation-format.md 的正则解析引用块与其后的 `> ` 原文；检测正文裸引用（"第X条"未带完整标记）
- [x] T021 实现出处校验 `src/tu_assistant/citation/verify.py`：按编号查知识库，结论 `ok` / `corrected`（替换为知识库原文）/ `not_found`（删除引用块，替换为 `〔此处引用未通过校验，已删除〕`）/ `incomplete`（裸引用，记录）；同时返回校验前原文供评测（research R5）（依赖 T013、T020）
- [x] T022 单元测试 `tests/unit/test_citation.py`：四种结论各至少 2 例；中文 / 阿拉伯数字编号；省略原文时自动补入
- [x] T023 集成测试 `tests/integration/test_citation_verify.py`：一段含正确引用、原文有误、不存在编号、裸引用的样例输出，校验后条款原文 100% 与知识库一致（quickstart V3）

### 模型端点与对话框架

- [x] T024 [P] 实现运行时模型客户端 `src/tu_assistant/runtime/client.py`：OpenAI 兼容 Chat Completions；启动时校验 `runtime.model_endpoint` 主机在 `runtime.allowed_hosts` 内，否则拒绝启动（宪章原则 III、IV）
- [x] T025 [P] 实现 `tu serve model --exp <exp_id>`：封装 `mlx_lm.server`，加载基座 + 适配器，只监听 127.0.0.1
- [x] T026 实现会话与接口 `src/tu_assistant/chat/session.py`、`src/tu_assistant/chat/assistant.py`：`Assistant` 协议、`SessionConfig`、`Reply`（contracts/system-interface.md）；会话只存内存，`close` 后释放（FR-009）
- [x] T027 实现对话编排 `src/tu_assistant/chat/orchestrator.py`：拼装 system prompt（含 `max_questions_per_turn`）、调用模型、出处校验、统计追问问题数（contracts/citation-format.md §5）、按已确认 ClauseRelation 对未引用的关联条款做确定性补全提示（FR-019，research R6）、评测模式下返回 `raw_content`（依赖 T021、T024、T026）
- [x] T028 [P] 单元测试 `tests/unit/test_runtime_isolation.py`：端点白名单校验；静态检查 `chat/`、`runtime/`、`ui/`、`eval/` 不导入外部大模型客户端（quickstart V7）

### 数据合成与训练框架

- [x] T029 [P] 实现外部大模型客户端 `src/tu_assistant/synth/llm.py`（仅 synth 使用）：调用前断言输入只来自知识库；记录提供方、模型名、提示词版本、种子
- [x] T030 [P] 实现合成样本自动检查 `src/tu_assistant/synth/check.py`：引用可解析、条款存在、原文一致；不通过的丢弃并统计（research R4）
- [x] T031 [P] 实现数据集构建 `src/tu_assistant/train/dataset.py`：按 contracts/datasets.md 输出 `messages` JSONL，按 9:1 划分 `train.jsonl` / `valid.jsonl`；按条款数量均衡抽样（避免最大文件主导）；与评测集按条款与问句相似度去重并记录 `dedup_against`
- [x] T032 实现训练封装 `src/tu_assistant/train/mlx_train.py` 与 `tu train --config`：调用 `mlx_lm lora`，记录 ExperimentRun 清单（基座及许可证、数据集、超参、种子、耗时、峰值内存、日志路径）；创建 `configs/train/debug-1.5b.yaml`（Qwen2.5-1.5B-Instruct-4bit）与 `configs/train/demo-7b.yaml`（Qwen2.5-7B-Instruct-4bit，`--grad-checkpoint`，全部线性层）

### 评测核心（先于训练，宪章原则 V）

- [x] T033 [P] 实现评测用例格式与加载 `src/tu_assistant/eval/cases.py`：EvalCase 字段按 data-model.md；校验"`gold.clauses` 中的条款必须存在于对应知识库版本"与"任何用例不得来自真实用户对话"
- [x] T034 实现评测运行器 `src/tu_assistant/eval/runner.py` 与 `tu eval run`：单轮用例与固定对话脚本（`input.script`）两种；`temperature=0`；输出 `results.jsonl`、`report.md`、EvalRun 清单（依赖 T027、T033）
- [x] T035 [P] 实现条款识别指标 `src/tu_assistant/eval/metrics.py`：SC-002 召回率、SC-003 精确率、SC-006 出处标注完整率、SC-007 引用准确率（校验前 / 校验后分列）
- [x] T036 [P] 单元测试 `tests/unit/test_metrics.py`：构造已知答案验证各指标计算
- [x] T037 实现 `tu synth evalcases --kb <ver>`：用与训练数据不同的提示词生成评测候选用例到 `eval/cases/candidates/`（依赖 T029）
- [x] T038 编写评测集 v1 的条款识别、拒答、例外类用例（约 35 题）`eval/cases/v1/*.jsonl`：候选用例经人工校验（`source=synthetic_reviewed`）或人工编写，由用户审阅确认后定稿（已确认 60 题 → `eval/cases/v1/reviewed.jsonl`）

### 学习文档

- [x] T039 撰写 `docs/learning/03-knowledge-base.md`：法律文本结构、条款切分规则与本项目文档的统计结果、知识库版本、出处校验原理与四种结论、校验层的局限；更新 `00-glossary.md`

**Checkpoint**: 知识库、出处校验、模型端点、训练封装、评测核心就绪（quickstart V1–V3 通过）

---

## Phase 3: User Story 1 — 确认意图后获得法律条款及解答 (Priority: P1) 🎯 MVP

**Goal**: 从一句大白话开始，多轮追问确认意图，给出带出处的条款、适用分析和法律责任

**Independent Test**: 用评测集中的条款识别、多违法行为、例外、拒答、意图确认用例逐条对话，检查条款正确完整、出处与原文一致、追问轮次合理（spec US1）

### 训练数据（知识类 + 咨询行为类）

- [x] T040 [P] [US1] 实现知识类样本合成 `src/tu_assistant/synth/knowledge.py`：条款复述、编号与内容互查、改写问答 ×3–5、条款关系（仅用 `confirmed=true` 的关联）（research R3）
- [x] T041 [P] [US1] 实现意图确认样本合成 `src/tu_assistant/synth/dialogs.py`：模糊开场 → 追问（每个样本的 `max_questions` 取 2–6 随机并写入 system prompt）→ 确认意图 → 回答；含用户要求跳过追问、中途改变意图的样本（FR-010 ~ FR-014）
- [x] T042 [P] [US1] 实现咨询类样本合成 `src/tu_assistant/synth/consult.py`：单行为、多违法行为多主体（违法主体不预设类型，FR-017）、例外情形、信息不足时分情形回答；输出遵守 contracts/citation-format.md §3
- [x] T043 [P] [US1] 实现拒答样本合成 `src/tu_assistant/synth/refusal.py`：知识库外问题（其他法律领域、与工会无关、本期不支持的需求如起草维权文书）→ 明确拒答或引导（FR-014、FR-022）
- [x] T044 [US1] 实现 `tu synth sft --kb <ver>` 汇总 T040–T043 与约 5% 通用对话，经 T030 检查、T031 构建数据集（依赖 T040–T043）

### 编排与交互

- [x] T045 [US1] 在 `src/tu_assistant/chat/orchestrator.py` 中实现咨询回答末尾固定追加"*以上内容仅供参考，不构成法律意见。*"（FR-023），拒答时不追加结构
- [x] T046 [P] [US1] 实现 Markdown 导出 `src/tu_assistant/chat/export.py`：`export_markdown` 返回某轮回复的 Markdown（FR-032）
- [x] T047 [US1] 实现 `tu chat`：命令行多轮对话，`/save <path>` 保存最后一轮为 `.md`，`/new` 新会话

### 评测与训练

- [x] T048 [P] [US1] 实现多违法行为与关联补全指标（SC-004、SC-005）、拒答与误拒指标（SC-008）、意图确认指标（SC-001：3 轮内正确确认的比例）于 `src/tu_assistant/eval/metrics.py`，并补充 `tests/unit/test_metrics.py`
- [x] T049 [US1] 编写评测集 v1 的多违法行为与意图确认（固定对话脚本）用例约 20 题，加入 `eval/cases/v1/`，由用户审阅确认
  - 2026-11-23 经外部 DeepSeek 初审、用户逐题确认及内部 2 轮独立只读复审通过后验收完成。新增 28 道手工原创用例（`multi_violation.jsonl` 10 + `intent.jsonl` 10 + `boundaries.jsonl` 8：`refusal` 3 / `false_refusal` 2 / `exception` 3，含 Round 1 复审补全 `mv-002`《社会保险法》第八十四条），`eval/cases/v1/` 平滑扩至 98 题覆盖全部 7 类且历史基线 `reviewed.jsonl`/`articles.jsonl` 字节零改动；同步增强 `tu eval cases review / promote`、补齐 `tests/unit/test_v1_multi_intent_eval.py`（全量 `uv run pytest` 421 passed / 6 xfailed，`ruff` 全绿，T075 `output.sha256` 25/25 OK）与学习文档 `[L6.6]` / 术语表。[执行单与复审记录](../../docs/handoffs/T049-eval-cases-multi-intent-handoff.md)
- [x] T050 [US1] 用 `configs/train/debug-1.5b.yaml` 训练，评测，跑通全流程（quickstart V4）；记录 loss 曲线与评测结果
  - 进度：已训 `exp-20261114-120250` 并完成两轮评测（引用失败），详见 `docs/experiments/E001-1.5b-citation-failure.md`
  - **订正（E002，2026-11-17）**：此前评测实测基座（未挂 adapter），结论作废。修复后重评：〔〕50/60（带 system）/ 60/60（无 system），条款召回 0.017/0.033 —— 格式已学会（run-20261117-085921 / -090638）；~~容量瓶颈属实~~（E002 §6.3 订正：1.5B 用旧数据集训练，与 7B 不是对照，只能说"表现更差"，不能归因到容量）
- [x] T051 [US1] 撰写 `docs/learning/04-training-data.md`：训练数据样例（真实生成结果）、为什么改写成问答、追问上限随机化、合成样本检查与丢弃率、评测与训练去重；更新术语表

**Checkpoint**: 1.5B 模型可多轮咨询，全流程跑通（MVP 流程验证）

---

## Phase 4: User Story 2 — 生成普法宣传文章 (Priority: P2)

**Goal**: 按语义主题生成多篇以案说法的普法文章，使用虚构名称，场景差异化，可在会话中修改

**Independent Test**: 用评测集中的普法文章用例生成文章，由项目方按评分要点检查构成要件、出处、法律责任、多样性、语言风格（spec US2）

- [x] T052 [P] [US2] 实现普法文章样本合成 `src/tu_assistant/synth/articles.py`：主题 → 多篇文章（结构按 contracts/citation-format.md §4），场景在违法主体类型、当事人身份、手段、情节轻重上有差异；人物与单位一律虚构；含多违法行为综合场景（FR-024 ~ FR-029）
  - 2026-11-19 经用户确认完成。第二轮校订后的三条候选已通过结构、引用及训练长度复核。[最终校订记录](../../docs/handoffs/T052-article-synthesis-handoff.md#11-第二轮校订记录2026-11-19)
- [x] T053 [P] [US2] 实现修改请求样本合成（"语言再通俗一些""换一个违法主体"），加入 `src/tu_assistant/synth/articles.py`
  - 2026-11-19 经内部 3 轮只读复审与第三方模型复审通过，用户确认完成。落地 `generate_revisions`（`plainer` / `swap_subject`）、`normalize_draft_markers`、运行时历史轮回填、三道 ≤2048 关卡、逐轮评测去重与 `actor_residual` 检查；整理 7 条新 KB 确认初稿（723–960 tok）与 12 条人工确认修改样本（1,314–1,804 tok，`parent` 12/12 可追溯），新增学习文档 `[L4.5.2]`。[执行单与复审记录](../../docs/handoffs/T053-article-revision-handoff.md)
- [x] T054 [P] [US2] 实现身份信息检查 `src/tu_assistant/chat/anonymize.py`：从本会话用户消息中按规则抽取候选身份信息（单位后缀"公司/厂/集团/医院/学校"、常见姓氏 + 名字），文章命中则替换为虚构名称并记录（FR-030）
  - 2026-11-22 经内部 3 轮独立只读复审通过并经用户确认验收。实现常见单姓人名与五类单位字面全称抽取、意图与续改状态判定、稳定虚构代称分配与一次扫描替换、`verify_output` 核准区间追踪与引文冲突暂缓交稿、以及 `Reply.citations` 安全元数据清洗；本机父模型实测 `run-20261122-090101` SC-011 达 2/2、引用冲突 0 轮，新增学习文档 `[L6.3]`。[执行单与复审记录](../../docs/handoffs/T054-article-identity-handoff.md)
- [x] T055 [P] [US2] 单元测试 `tests/unit/test_anonymize.py`：真实名称被替换、虚构名称不受影响
  - 2026-11-22 经内部 3 轮独立只读复审通过并经用户确认验收，全量 `uv run pytest` 282 passed / 6 xfailed（含 68 题 69 条负对照、T075 三条彩排提示、粘连/核准冲突/未核准引语、入口与导出隔离及 R1/R2 回归用例），`ruff` 全绿。
- [x] T056 [US2] 在 `src/tu_assistant/chat/orchestrator.py` 中接入文章数量（默认 3，上限 10，读取 `SessionConfig`）与身份信息检查（依赖 T054）
  - 2026-11-22 经内部 3 轮独立只读复审通过并经用户确认验收（身份信息检查接线此前已随 T054/T055 完成）。落地 `src/tu_assistant/chat/article_count.py` 配置 fail-fast 校验、前置意图共享、防序数/过去时/案情干扰的数量与区间解析、超限/非正数硬拒（与 SC-008 隔离）及 `use_default` 临时请求副本轻量附注（`v2-short` 正文与咨询/明示篇数/路线 A 零改动），补齐 `tu eval run` 透传 `session.*` 配置；新增 `tests/unit/test_article_count.py`（106 passed，全量 `uv run pytest` 388 passed / 6 xfailed，`ruff` 全绿）及学习文档 `docs/learning/07-serving-demo.md`（`[L7.1]`）。[执行单与复审记录](../../docs/handoffs/T056-article-count-handoff.md)
- [x] T057 [US2] 将 T052、T053 样本加入 `tu synth sft`，重新生成数据集
  - 2026-11-20 经内部 2 轮独立只读复审与外部模型复审通过，用户确认完成。产出固化文章池 `artifacts/synth/articles/t057-curated/`（22 初稿 + 24 修改稿 = 46 条，22 家族，6 部法规均衡覆盖，token 520–1,804）与新数据集 `artifacts/datasets/ds-kb-20261119-045641-8247/`（`train 8,962` / `valid 820`，`article` 252 = 2.81%，`refusal` 176 = 1.96%，新 KB 67/67 关系全部保留，`valid ∩ ds-8410 train = 0`，家族零泄漏，74 条 v1 评测去重零重合，全库 max 2,015 ≤ 2,048 token），同步更新 `docs/learning/04-training-data.md`（`[L4.5.3]` / `L4.7`）与 `00-glossary.md`。[执行单与验收记录](../../docs/handoffs/T057-article-dataset-handoff.md)
- [x] T058 [US2] 编写评测集 v1 的普法文章用例约 10 题（含评分要点 `rubric`），加入 `eval/cases/v1/`，由用户审阅确认；实现 SC-011（身份信息）自动检查于 `src/tu_assistant/eval/metrics.py`
- [x] T059 [US2] 用 `configs/train/demo-7b.yaml` 训练演示模型（一到两晚），评测（quickstart V5）；按评测结果调整数据后再训一次
  - 进度：E001 尝试 4（方案 A）`exp-20261115-124801` 因 fp16 注意力反向溢出在 iter ~550 NaN；fp32 注意力 + NaN 守卫修复后从 iter-500 续训（`exp-20261116-resume500`，8,421 iter 零 NaN 完成，最终 val 0.472）；~~评测 `run-20261117-022645`：〔〕引用块 0/60、条款召回 0（与 iter-500 检查点逐字对比 42/60 相同）→ 路线验证未通过~~
  - **订正（E002，2026-11-17）**：此前评测实测基座，结论作废（"42/60 逐字相同"是同基座必然）。修复后重评真实 adapter：训满版〔〕60/60、日期标签 60/60、条款召回 0.150、精确率 0.265；学习曲线 0.000（500 步）→0.083（约 4,500 步）→0.150；上海地方文件题召回 0.045 → ~~落"记忆容量不足"档，"调整数据后再训"转为待用户决策是否转 RAG（E001 尝试 5，E002 §4）~~
  - **再订正（E002 §6 复审 + E003，2026-11-18）**："记忆容量不足"证据不足。与基座同口径对比：文件 16→45/60、条 1→17/60（p≈4e-5）、款 0→9/60，上海文件 0→14/22，SFT 有效。"调整数据后再训"以 E003 B1 执行：同一数据追加 1 epoch（`exp-e003-7b-epoch2`），训练原题显著提升、v1 几乎不变（条级 17→18/60）。**POC 训练目标判定达成**，演示用 `exp-20261116-resume500`；B2 与检索方案转正式阶段候选，见 `docs/experiments/poc-training-summary.md`
  - **SC-016 判定（2026-11-18）**：①条级 1→17/60（p≈4e-5）②款级 9/60=15% ③基座从未识别出的文件 0→21/30（p≈4e-9），三项均满足（research R13）。文章样本合入后的再训见 T075
  - **V5/SC-015 核销（2026-11-23）**：按 T056 决策 4 约定随 T064 验收同步结项；冻结 7B 演示模型 `exp-20261116-resume500` 在完整 98 题 `eval/cases/v1` 上完成两轮独立冷启动评测并通过 SC-015（`0.0 pp` 波动 PASS）。[实验记录](../../docs/experiments/T064-eval-repeatability.md)
- [x] T075 [US2] T057 的数据集就绪后，从 `exp-20261116-resume500` 的 adapter 继续训练 7B（一晚以上，实测 12–14 h）；训练后先做 A/B 冒烟，再在 v1 上复评：SC-016 三项仍满足（回归门槛，依赖 T076），条级、款级命中不低于本次基线（17/60、9/60）
  - 用户确认按实验完成结项。8,962 步续训及 P/C/H/V 评测已完成。候选通过 SC-016，但条级 14/60、款级 6/60，低于 17/60、9/60 的换模门槛。路线 A 保留 `exp-20261116-resume500` 最终权重，US2 限于给定案情和已核准条款的预审单篇演示。[实验结果与三条演示提示词](../../docs/experiments/T075-article-training.md)
- [x] T060 [US2] 撰写 `docs/learning/05-training.md`：一次训练的完整过程、超参数含义、用本项目真实日志讲解 loss 曲线、过拟合与欠拟合、1.5B 与 7B 的对比；更新术语表

**Checkpoint**: 7B 演示模型可咨询、可生成普法文章

---

## Phase 5: User Story 3 — 用统一评测集衡量系统质量 (Priority: P3)

**Goal**: 产出覆盖 SC-001 ~ SC-011 的分项报告，支持版本对比与人工评审记录

**Independent Test**: 对同一模型重复评测，指标波动 ≤2 个百分点；两个版本可直接对比（spec US3、SC-015）

- [x] T061 [P] [US3] 在 `src/tu_assistant/eval/report.py` 中完善报告：全部指标与 POC 目标值对照（不作为验收条件）、引用准确率校验前 / 后两列、逐条失败用例清单；SC-009（文章正确性）、SC-010（文章多样性）从人工评审表格（T063）汇总
  - 2026-11-22 经内部 2 轮独立只读复审与第三方审核意见收口后，用户确认验收。落地 `src/tu_assistant/eval/report.py`（`summarize_run`、`extract_failures`、`extract_pending_articles`、`load_reviews`、`aggregate_reviews`、`render_report`、`render_run_report`）、`runner.py` 委托渲染、只读命令 `tu eval report <run_id> [--reviews] [--out]`（禁止写入已有历史 run 目录）及 `tests/unit/test_report.py`（全量 `uv run pytest` 408 passed / 6 xfailed，`ruff` 全绿，T075 `output.sha256` 25/25 OK），同步新增学习文档 `[L6.4]` 与术语表 `## 评测`。[执行单与复审记录](../../docs/handoffs/T061-T063-eval-report-review-handoff.md)
- [x] T062 [P] [US3] 实现 `tu eval compare <run_id>...` 于 `src/tu_assistant/eval/compare.py`：同一评测集与口径的版本对比，输出 `compare.md`（FR-035）
  - 2026-11-23 经内部 2 轮独立只读复审通过并经用户确认验收。落地 `check_general_comparable`（含目录型评测集扩题兼容与非法 `run_id` 校验）、`align_general_cases`、`same_system_issues`、`compare_runs`（复用 `report.summarize_run` / `extract_failures` / `load_reviews`）、`evaluate_sc015`（13 项百分比指标、`≤ 2.0 pp + 1e-9`、单侧 `None` 判 FAIL、临界精度防歧义）、`render_compare_markdown`、`save_compare_artifact`（原子创建 `compare-<ts>/` 含 `compare.md` + `manifest.json`）及 `tu eval compare` CLI（默认 stdout、`--out` 防历史目录覆盖、`--save`、`--sc015`、`--reviews`，保持 `--sc016` 零回归）；全量 `uv run pytest` 414 passed / 6 xfailed，`ruff` 全绿，T075 `output.sha256` 25/25 OK，新增学习文档 `[L6.5]` 与术语表条目。[执行单与复审记录](../../docs/handoffs/T062-eval-compare-handoff.md)
- [x] T063 [P] [US3] 提供人工评审表格模板 `eval/review-template.csv`（列：`run_id`、`case_id`、`reviewer`、`verdict`（pass / minor_issue / fail）、`comment`、`created_at`），并在 `report.md` 中按 `case_id` 列出待评审的普法文章（FR-037，POC 用表格记录）
  - 2026-11-22 随 T061 一并验收完成。提供 `eval/review-template.csv`（6 个必需列 + 第 7 可选列 `dimension=correctness|diversity|other`，向下兼容纯 6 列且留空默认归 `correctness`；POC 按 `题 × 评审人` 记录统计 SC-009/SC-010），并在 `report.md` 按 `case_id` 升序列出待评审普法文章与实得 0 篇状态。[执行单与复审记录](../../docs/handoffs/T061-T063-eval-report-review-handoff.md)
- [x] T064 [US3] 对 7B 演示模型重复评测 2 次，用 `tu eval compare` 验证指标波动 ≤2 个百分点（SC-015），结果存于 `artifacts/eval/`
  - 2026-11-23 经内部 2 轮独立只读复审通过并经用户确认验收。冻结演示模型 `exp-20261116-resume500` 在活跃 KB `kb-20261119-045641` 与 98 题全 7 类 `eval/cases/v1` 上完成两次独立冷启动评测（`run-20261123-051432`［21 分 06 秒］、`run-20261123-053832`［20 分 56 秒］，98/98 题逐字一致），经离线 DeepSeek 初审脚本（`scripts/experiments/t064/deepseek_review_articles.py`）+ 用户人工终审落盘 `eval/reviews/t064-reviews.csv`，最终 `tu eval compare --sc015 --reviews --save` 归档于 `artifacts/eval/compare-20261123-145054/`（12 项有效指标含 `SC-009=0.000 (0/9)` 均 `0.0 pp` PASS，`SC-010` 因多篇实得 `<2` 篇跳过）；同步沉淀实验记录 `docs/experiments/T064-eval-repeatability.md` 与学习文档 `[L6.7]` / 术语表。[执行单与复审记录](../../docs/handoffs/T064-eval-repeatability-handoff.md)
- [x] T076 [P] [US3] 实现 SC-016 判定（`src/tu_assistant/eval/compare.py`，可由 `tu eval compare` 调用）：输入基座与自训模型在同一评测集上的两个 run，输出三项条件的命中数与 Fisher 精确检验 p 值；口径沿用 `scripts/experiments/e002/review_stats.py` 与 `scripts/experiments/e003/sc016.py`（宽松解析定位到条/文件、严格解析定位到款）；补单元测试
  - 2026-11-18 独立复审通过。`uv run tu eval compare --sc016 run-20261117-022645 run-20261117-081504` 复现条级 1/60 → 17/60、款级 9/60、文件子集 0/30 → 21/30，退出 0。详见[执行单第 11 节](../../docs/handoffs/T076-sc016-handoff.md#11-最终复审通过2026-11-18)。
- [x] T065 [US3] 撰写 `docs/learning/06-evaluation.md`：各指标计算方法、校验前 / 后两种准确率的含义、用本项目评测结果分析薄弱类别并反推数据改进方向；更新术语表
  - 2026-11-23 经内部独立只读复审、外部两轮复审修订及 `reviewer-v3` 终审通过并获用户确认验收，Phase 5（US3）全部任务收口。完成 `docs/learning/06-evaluation.md`（章首导航、`[L6.1]`–`[L6.7]` 口径刷新与锚点保留、新增 `[L6.8]` 全指标口径与 4 处源码边界、`[L6.9]` T064 全 7 类 98 题实测诊断与数据改进反推、`[L6.10]` 延展提问），同步更新 `docs/learning/00-glossary.md`（保留原 8 条并增补 5 条）与 `docs/learning/README.md`（第 6 章标为 `✅`）；本地辅助校验 `verify_t065.py`（108 链接 0 断链、44 项正文数字回查）全通过，`uv run pytest` 421 passed / 6 xfailed，`ruff` 全绿，T075 `output.sha256` 25/25 OK。[执行单与复审记录](../../docs/handoffs/T065-eval-learning-handoff.md)

**Checkpoint**: 评测报告完整、可对比、可复现

---

## Phase 6: User Story 4 — 维护和更新法规知识库 (Priority: P4)

**Goal**: 文档新增、修改、删除后整批重导，生成新知识库版本，系统使用新内容

**Independent Test**: 修改一条条款后重新入库，出处校验层引用新原文；新文档中的内容经重训后可被识别（spec US4）

- [x] T066 [P] [US4] 实现 `tu kb diff <v1> <v2>` 于 `src/tu_assistant/kb/diff.py`：列出新增、删除、原文变化的条款（只输出编号与变化类型）
  - 2026-11-23 随 T066–T068 一并经内部独立只读复审、第三方独立评审修订及终审通过并获用户确认验收。落地 `src/tu_assistant/kb/diff.py`（只读快照、按 `status='current'` 逻辑键 `(title, article_no, paragraph_no, item_no)` 对齐、严格三分法仅按 `text` 判 `modified`、顶部汇总文件版本/`number_text` 变化/已确认关联变化、数据结构与渲染全程 0 字节条文正文泄漏）、`tu kb diff <v1> <v2> [--summary-only]` CLI 与 `tests/unit/test_kb_diff.py`；同步补录 `contracts/cli.md` 并更新学习文档 `[L3.3.1]` / 术语表。[执行单与复审记录](../../docs/handoffs/T066-T067-T068-kb-maintenance-handoff.md)
- [x] T067 [US4] 在 `configs/app.yaml` 中增加 `kb.version`，编排层与出处校验层按配置加载指定知识库版本；切换版本无需修改代码（FR-004）
  - 2026-11-23 随 T066–T068 一并验收完成。落地 `kb/store.py`（`KBError`、`latest_kb_path` 按 `stem` 排序、`normalize_artifacts_dir`、`resolve_kb_path`、`open_kb` 防静默建 0 字节空库与 `as_uri()` 只读模式、`open_kb_from_config`）、`config.resolve_model_name`、`verify_output_from_config`、`TrainedAssistant.from_config` 与 `session_config_from`；`tu chat`、`tu eval run`、`eval/runner.py`、`eval/compare.py` 及离线 `tu kb *`/`tu synth *`/`tu eval cases review` 全部接入只读防呆校验，新增 `tests/unit/test_kb_config.py`。[执行单与复审记录](../../docs/handoffs/T066-T067-T068-kb-maintenance-handoff.md)
- [x] T068 [US4] 用 `tests/fixtures/` 的样例验证"修改条款 → 重新入库 → 校验层使用新原文"的流程，写入集成测试 `tests/integration/test_kb_update.py`；在 quickstart 中补充"知识更新需重训"的说明（research R1 风险）
  - 2026-11-23 随 T066–T068 一并验收完成，Phase 6（US4）全部收口。落地 `kb/ingest.py` 同秒连续入库 `-01`/`-02` 防撞名与可选 `kb_version`、端到端集成测试 `tests/integration/test_kb_update.py`（覆盖改条/删条/增条、同秒防撞名、`kb diff` 反正文泄漏、零改代码切换 `app.yaml` `kb.version`、跨版本标签修订、缺失版本报错防空库及旧库 SHA-256 零修改），并在 `specs/001-legal-clause-assistant/quickstart.md` 补充 US4 验证步骤、`kb.version: null` 自动切库过渡期锁定建议与 research R1“知识更新需重训（含关联重抽确认）”完整链路；全量 `uv run pytest` 434 passed / 6 xfailed，`ruff` 全绿，4 份历史 KB 与 T075 `output.sha256` 25/25 OK。[执行单与复审记录](../../docs/handoffs/T066-T067-T068-kb-maintenance-handoff.md)

**Checkpoint**: 知识库可更新、可追溯版本

---

## Phase 7: 演示界面与收尾

**Purpose**: 可对外演示的网页界面、演示准备、文档收尾

- [x] T069 实现 Gradio 演示界面 `src/tu_assistant/ui/app.py` 与 `tu ui`：多轮对话、新会话、保存当前回复为 Markdown；只监听 127.0.0.1（quickstart V6）
  - 2026-11-23 经初版 2 轮独立复审、第三方二轮评审 7 项修订、`reviewer-v2` 2 轮终审及最终代码实机 V6 联调重跑通过并获用户确认验收。落地 `src/tu_assistant/ui/app.py`（`validate_ui_host` 严格仅允许 `127.0.0.1`、`ChatUIController` 仅依赖 `Assistant` 协议、`cleanup_session` 非阻塞事件循环守护线程清理、`create_ui_app` Gradio 6.31.0 零遥测/零 Google Fonts 外链/`delete_cache=(600, 7200)`/单并发队列、`launch_ui` 写死 `share=False`）、`tu ui` CLI（fail-fast 校验与 `finally` 资源清理）、`kb/store.py` & `chat/assistant.py` 只读连接可选 `check_same_thread`、`chat/orchestrator.py` 全链路 `try/except` 异常回滚悬挂 `user` 轮及状态，以及 `tests/unit/test_ui.py`；全量 `uv run pytest` 462 passed / 6 xfailed，`ruff` 全绿，T075 `output.sha256` 25/25 OK；同步更新学习文档 `[L7.2]` 与术语表。[执行单与复审记录](../../docs/handoffs/T069-gradio-ui-handoff.md)
- [x] T070 准备演示场景脚本 `docs/demo-scenarios.md`：模糊开场 → 追问 → 咨询；多违法行为；拒答；生成 3 篇普法文章 → 修改 → 保存（场景内容使用虚构案情）
  - 2026-11-24 经内部 2 轮独立只读复审通过并获用户确认验收。将根目录 `poc_demo.md` 升级迁入 `docs/demo-scenarios.md` 并删除旧草稿，补齐 10 分钟黄金主线（兼作 quickstart V6 验收清单）、UI/CLI 控件与 Markdown 导出核对、5 大场景库（25 处 `〔...〕` 引文经 `kb-20261119-045641.sqlite` 校验 0 `not_found`/0 `incomplete`/0 T078）、`mv-002` 实测 `ok=4, corrected=2` 精确口径、规格对照与 POC 边界说明表及 4 文件 79 MB 换机迁移指南；全量 `uv run --offline --no-sync pytest` 462 passed / 6 xfailed，`ruff` 全绿，T075 `output.sha256` 25/25 OK。[执行单与复审记录](../../docs/handoffs/T070-demo-scenarios-handoff.md)
- [x] T071 [P] 运行 quickstart.md 全部验证场景（V1–V7），记录结果
  - 2026-11-24 经内部 2 轮独立只读复审通过并获用户确认验收。落盘 `docs/experiments/T071-quickstart-verification.md` 并在 `docs/experiments/README.md` 补录索引，完整覆盖 V1–V7 + US4 全部 8 个场景（V1 `457 passed / 6 xfailed`、V2 `/tmp` 隔离入库 3,809 条 0 差异且零正文泄漏、V3 `4 passed`、V4 1.5B 清单与实机 `tu chat /save` 6,621 B、V5 7B 现行代码只读复跑 `tu eval report` / `--sc015` `0.0 pp` PASS / `--sc016` PASS、V6 7B + `tu ui --temperature 0.0` `gradio_client` 黄金主线 Step 1–6 全通并按用户拍板如实记录 Step 4 第 2 轮路线 A 压缩边界、V7 `106 passed` + `SC-011=2/2`、US4 `1 passed` + `tu kb diff`）；全量 `pytest` 462 passed / 6 xfailed，`ruff` 全绿，4 份历史 KB 与 T075 `output.sha256` 25/25 OK，`current.json` 指向 `exp-20261116-resume500`，端口零残留。[执行单与复审记录](../../docs/handoffs/T071-quickstart-verification-handoff.md)
- [ ] T072 [P] 更新 `README.md`：项目简介、环境准备、常用命令、文档索引
- [x] T073 撰写 `docs/learning/07-serving-demo.md`：模型服务、对话编排、演示界面、训练与演示不能同时进行的原因；更新术语表
  - 2026-11-24 经内部 2 轮独立只读复审通过并获用户确认验收。按 `1A 2A 3A` 收口 `docs/learning/07-serving-demo.md`（章首逻辑阅读导航、保留 `[L7.1]`–`[L7.2]`、修补 `[L7.3]` 3 处瑕疵并补录实测 adapter 体积 `77.04 MB` / `20.15 MB`、新增 `[L7.4]` 模型服务与三层运行时隔离、`[L7.5]` 对话编排 10 步 Mermaid 流水线与 T071 实机延迟对照、`[L7.6]` M1 Pro 32GB 训练与演示互斥四维拆解、`[L7.7]` 7 道延展提问），在 `docs/learning/00-glossary.md` 新增 `## 推理与演示` 8 条术语分区并将 `docs/learning/README.md` 第 7 章标为 `✅`；`verify_t073.py`（132 链接 0 断链、17/17 源码链接与符号通过）、全量 `pytest`（462 passed / 6 xfailed）、`ruff` 与 T075 `output.sha256`（25/25 OK）全绿。[执行单与复审记录](../../docs/handoffs/T073-serving-demo-learning-handoff.md)
- [ ] T074 撰写 `docs/learning/08-lessons-and-next.md`：踩坑汇总、POC 说明了什么与没说明什么（含校验前引用准确率的解读）、正式阶段事项（research R12）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：无依赖
- **Foundational (Phase 2)**：依赖 Setup；阻塞所有用户故事。T016 需要 `inputs/project/` 已就位（已就位，24 篇）；T019、T038 需要用户参与
- **US1 (Phase 3)**：依赖 Foundational
- **US2 (Phase 4)**：依赖 US1 的数据合成框架（T044）与编排（T045）；7B 首训（T059）只用了 US1 数据；合入 US2 文章数据后的再训由 T075 承担（依赖 T057）
- **US3 (Phase 5)**：依赖 Foundational 的评测核心；T064 依赖 T059；T075 的回归判定依赖 T076（T076 可提前实现）
- **US4 (Phase 6)**：依赖 Foundational 的知识库模块，可与 US1–US3 并行
- **Phase 7**：依赖 US1、US2（演示内容）

### Within Each Phase

- 单元测试与被测模块同时完成，测试通过后才算完成
- 数据合成 → 数据集构建 → 训练 → 评测
- 训练任务（T050、T059）期间本机满负荷，可并行做不依赖训练的编码与文档任务

### Parallel Opportunities

- Setup：T003–T006
- Foundational：T007/T009/T011、T020/T024/T025、T029–T031、T033/T035/T036
- US1：T040–T043、T046、T048
- US2：T052–T055
- US3：T061–T063
- US4 整体可与 US2、US3 并行

---

## Parallel Example: User Story 1

```bash
# 四类样本合成器互不依赖，可同时实现：
Task: "实现知识类样本合成 src/tu_assistant/synth/knowledge.py"
Task: "实现意图确认样本合成 src/tu_assistant/synth/dialogs.py"
Task: "实现咨询类样本合成 src/tu_assistant/synth/consult.py"
Task: "实现拒答样本合成 src/tu_assistant/synth/refusal.py"
```

---

## Implementation Strategy

### MVP First（User Story 1）

1. 完成 Phase 1 Setup 与 Phase 2 Foundational（含评测集 v1 的第一部分）
2. 完成 Phase 3 US1：1.5B 模型跑通"入库 → 合成 → 训练 → 对话 → 评测"
3. **停下来验证**：全流程可重复执行，评测报告可产出

### Incremental Delivery

1. Foundational → 知识库与出处校验可用
2. US1 → 1.5B 咨询（流程验证）
3. US2 → 7B 演示模型，咨询 + 普法文章
4. US3 → 完整评测报告与对比
5. Phase 7 → 演示界面，对外演示
6. US4 可在任意时间穿插完成

### 需要用户参与的节点

| 任务 | 用户需要做什么 |
|---|---|
| T016 | 如需查看原文片段调试切分规则，确认是否同意 |
| T019 | 确认条款关联关系 |
| T038、T049、T058 | 审阅评测集用例 |
| T037 前 | 提供外部大模型 API Key，确认提供方服务条款允许用输出训练模型（T037、T040–T043、T052–T053 均依赖） |
| T059 后 | 人工评审普法文章（表格） |

---

## Notes

- [P] 任务 = 不同文件、无依赖
- 每个任务或逻辑组完成后提交；文档类提交须经用户审阅
- 不得读取 `inputs/` 内容；不得在运行时调用外部服务
