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

- [ ] T001 创建 plan.md 中的目录结构：`configs/`、`configs/train/`、`src/tu_assistant/{kb,citation,chat,runtime,synth,train,eval,ui}/`、`tests/{unit,integration,fixtures}/`、`eval/cases/`，各包含 `__init__.py`
- [ ] T002 在 `pyproject.toml` 中用 uv 初始化项目（Python 3.12），添加依赖 mlx-lm、typer、pyyaml、python-docx、pdfplumber、beautifulsoup4、openai、gradio，开发依赖 pytest、ruff；锁定版本（`uv.lock`），优先选择发布超过 7 天的版本
- [ ] T003 [P] 在 `pyproject.toml` 中配置 ruff（lint + format）与 pytest，入口脚本 `tu = "tu_assistant.cli:app"`
- [ ] T004 [P] 创建配置文件骨架：`configs/app.yaml`（`runtime.model_endpoint`、`runtime.allowed_hosts: [127.0.0.1, localhost]`、`session.max_questions_per_turn: 5`、`session.default_article_count: 3`、`session.max_article_count: 10`）、`configs/synth.yaml`（`external_llm.base_url`、`external_llm.model`、改写倍数 3–5、提示词版本）；API Key 只从环境变量 `TU_EXTERNAL_LLM_API_KEY` 读取
- [ ] T005 [P] 实现配置加载 `src/tu_assistant/config.py`（读取 YAML，支持命令行覆盖）
- [ ] T006 [P] 实现产物清单工具 `src/tu_assistant/manifest.py`：为 `artifacts/` 下每个产物写 `manifest.json`（ID、创建时间、输入版本、配置哈希、随机种子），满足宪章原则 VI

---

## Phase 2: Foundational（所有用户故事的前置）

**Purpose**: 知识库、出处校验、模型端点、训练封装、评测核心

**⚠️ CRITICAL**: 本阶段完成前不能开始任何用户故事

### 知识库：入库与条款切分

- [ ] T007 [P] 实现中文数字与编号转换 `src/tu_assistant/kb/numbers.py`（"第五十一条" → 51，"（三）" → 3，保留原始写法）
- [ ] T008 [P] 单元测试 `tests/unit/test_numbers.py`：覆盖十、十一、二十、一百零一、一百一十等边界
- [ ] T009 [P] 实现文档读取 `src/tu_assistant/kb/readers.py`：`.txt`（项目方当前文档均为纯文本）、`.docx`、文本型 `.pdf`、`.html` 统一转为纯文本
- [ ] T010 实现条款切分 `src/tu_assistant/kb/parse.py`：识别 `第X编/章/节` 标题路径、`第X条`（条）、条内自然段（款）、`（一）（二）`（项）；兼容不以"第X条"组织、而以"一、二、三"分段的通知类文件；输出 Clause 列表（依赖 T007）
- [ ] T011 [P] 准备测试用公开法条片段 `tests/fixtures/`（自行编写的示例文本，不取自 `inputs/`），含条 / 款 / 项、编号缺口、重复编号、"一、二、三"分段等情形
- [ ] T012 单元测试 `tests/unit/test_parse.py`：用 T011 的样例验证切分结果与 `parse_warnings`（依赖 T010、T011）
- [ ] T013 实现知识库存储 `src/tu_assistant/kb/store.py`：SQLite，每次入库生成新 `kb_version` 文件 `artifacts/kb/<kb_version>.sqlite`；表 LegalDocument、Clause、ClauseRelation 字段按 data-model.md；约束："同一文件内 (`article_no`, `paragraph_no`, `item_no`) 唯一"、"同一 `title` 至多一个 `status=current`"
- [ ] T014 实现入库校验 `src/tu_assistant/kb/validate.py`：编号连续性缺口、重复、空条款写入 `parse_warnings`，生成 `parse_report.md`（只含文件序号、条款数、问题编号，不含条文内容）（FR-005）
- [ ] T015 实现 `tu kb import <dir>` 与 `tu kb show <title> <article_no>`，入口 `src/tu_assistant/cli.py`（contracts/cli.md）；文件版本信息（`version_label`、`promulgated_on`、`status`）从文件名或文件头解析，缺失时写入问题清单（FR-002）
- [ ] T016 对 `inputs/project/` 执行入库，**只查看统计输出**（文件数、每文件条款数、问题条目数）；按问题清单调整切分规则。注意最大文件约 329KB，若为汇编类文件需拆分处理。如需查看原文片段，先征得用户同意

### 条款关联

- [ ] T017 实现规则抽取条款关联 `src/tu_assistant/kb/relations.py`：识别"违反本法第X条""依照第X条"等显式引用，生成 `relations_pending.jsonl`（`origin=rule`，`confirmed=false`）
- [ ] T018 实现 `tu kb relations extract` / `tu kb relations confirm <file>`；"只有确认过的关联用于训练数据和关联补全指标"（data-model.md）
- [ ] T019 用户人工确认关联关系：在 `artifacts/kb/relations_pending.jsonl` 中逐条标注 `confirmed`，用 `tu kb relations confirm` 导入（说明写在 `docs/relations-confirm-guide.md`）

### 出处校验层（宪章原则 I）

- [ ] T020 [P] 实现引用解析 `src/tu_assistant/citation/parse.py`：按 contracts/citation-format.md 的正则解析引用块与其后的 `> ` 原文；检测正文裸引用（"第X条"未带完整标记）
- [ ] T021 实现出处校验 `src/tu_assistant/citation/verify.py`：按编号查知识库，结论 `ok` / `corrected`（替换为知识库原文）/ `not_found`（删除引用块，替换为 `〔此处引用未通过校验，已删除〕`）/ `incomplete`（裸引用，记录）；同时返回校验前原文供评测（research R5）（依赖 T013、T020）
- [ ] T022 单元测试 `tests/unit/test_citation.py`：四种结论各至少 2 例；中文 / 阿拉伯数字编号；省略原文时自动补入
- [ ] T023 集成测试 `tests/integration/test_citation_verify.py`：一段含正确引用、原文有误、不存在编号、裸引用的样例输出，校验后条款原文 100% 与知识库一致（quickstart V3）

### 模型端点与对话框架

- [ ] T024 [P] 实现运行时模型客户端 `src/tu_assistant/runtime/client.py`：OpenAI 兼容 Chat Completions；启动时校验 `runtime.model_endpoint` 主机在 `runtime.allowed_hosts` 内，否则拒绝启动（宪章原则 III、IV）
- [ ] T025 [P] 实现 `tu serve model --exp <exp_id>`：封装 `mlx_lm.server`，加载基座 + 适配器，只监听 127.0.0.1
- [ ] T026 实现会话与接口 `src/tu_assistant/chat/session.py`、`src/tu_assistant/chat/assistant.py`：`Assistant` 协议、`SessionConfig`、`Reply`（contracts/system-interface.md）；会话只存内存，`close` 后释放（FR-009）
- [ ] T027 实现对话编排 `src/tu_assistant/chat/orchestrator.py`：拼装 system prompt（含 `max_questions_per_turn`）、调用模型、出处校验、统计追问问题数（contracts/citation-format.md §5）、评测模式下返回 `raw_content`（依赖 T021、T024、T026）
- [ ] T028 [P] 单元测试 `tests/unit/test_runtime_isolation.py`：端点白名单校验；静态检查 `chat/`、`runtime/`、`ui/`、`eval/` 不导入外部大模型客户端（quickstart V7）

### 数据合成与训练框架

- [ ] T029 [P] 实现外部大模型客户端 `src/tu_assistant/synth/llm.py`（仅 synth 使用）：调用前断言输入只来自知识库；记录提供方、模型名、提示词版本、种子
- [ ] T030 [P] 实现合成样本自动检查 `src/tu_assistant/synth/check.py`：引用可解析、条款存在、原文一致；不通过的丢弃并统计（research R4）
- [ ] T031 [P] 实现数据集构建 `src/tu_assistant/train/dataset.py`：按 contracts/datasets.md 输出 `messages` JSONL，按 9:1 划分 `train.jsonl` / `valid.jsonl`；按条款数量均衡抽样（避免最大文件主导）；与评测集按条款与问句相似度去重并记录 `dedup_against`
- [ ] T032 实现训练封装 `src/tu_assistant/train/mlx_train.py` 与 `tu train --config`：调用 `mlx_lm lora`，记录 ExperimentRun 清单（基座及许可证、数据集、超参、种子、耗时、峰值内存、日志路径）；创建 `configs/train/debug-1.5b.yaml`（Qwen2.5-1.5B-Instruct-4bit）与 `configs/train/demo-7b.yaml`（Qwen2.5-7B-Instruct-4bit，`--grad-checkpoint`，全部线性层）

### 评测核心（先于训练，宪章原则 V）

- [ ] T033 [P] 实现评测用例格式与加载 `src/tu_assistant/eval/cases.py`：EvalCase 字段按 data-model.md；校验"`gold.clauses` 中的条款必须存在于对应知识库版本"与"任何用例不得来自真实用户对话"
- [ ] T034 实现评测运行器 `src/tu_assistant/eval/runner.py` 与 `tu eval run`：单轮用例与固定对话脚本（`input.script`）两种；`temperature=0`；输出 `results.jsonl`、`report.md`、EvalRun 清单（依赖 T027、T033）
- [ ] T035 [P] 实现条款识别指标 `src/tu_assistant/eval/metrics.py`：SC-002 召回率、SC-003 精确率、SC-006 出处标注完整率、SC-007 引用准确率（校验前 / 校验后分列）
- [ ] T036 [P] 单元测试 `tests/unit/test_metrics.py`：构造已知答案验证各指标计算
- [ ] T037 实现 `tu synth evalcases --kb <ver>`：用与训练数据不同的提示词生成评测候选用例到 `eval/cases/candidates/`（依赖 T029）
- [ ] T038 编写评测集 v1 的条款识别、拒答、例外类用例（约 35 题）`eval/cases/v1/*.jsonl`：候选用例经人工校验（`source=synthetic_reviewed`）或人工编写，由用户审阅确认后定稿

### 学习文档

- [ ] T039 撰写 `docs/learning/03-knowledge-base.md`：法律文本结构、条款切分规则与本项目文档的统计结果、知识库版本、出处校验原理与四种结论、校验层的局限；更新 `00-glossary.md`

**Checkpoint**: 知识库、出处校验、模型端点、训练封装、评测核心就绪（quickstart V1–V3 通过）

---

## Phase 3: User Story 1 — 确认意图后获得法律条款及解答 (Priority: P1) 🎯 MVP

**Goal**: 从一句大白话开始，多轮追问确认意图，给出带出处的条款、适用分析和法律责任

**Independent Test**: 用评测集中的条款识别、多违法行为、例外、拒答、意图确认用例逐条对话，检查条款正确完整、出处与原文一致、追问轮次合理（spec US1）

### 训练数据（知识类 + 咨询行为类）

- [ ] T040 [P] [US1] 实现知识类样本合成 `src/tu_assistant/synth/knowledge.py`：条款复述、编号与内容互查、改写问答 ×3–5、条款关系（仅用 `confirmed=true` 的关联）（research R3）
- [ ] T041 [P] [US1] 实现意图确认样本合成 `src/tu_assistant/synth/dialogs.py`：模糊开场 → 追问（每个样本的 `max_questions` 取 2–6 随机并写入 system prompt）→ 确认意图 → 回答；含用户要求跳过追问、中途改变意图的样本（FR-010 ~ FR-014）
- [ ] T042 [P] [US1] 实现咨询类样本合成 `src/tu_assistant/synth/consult.py`：单行为、多违法行为多主体（违法主体不预设类型，FR-017）、例外情形、信息不足时分情形回答；输出遵守 contracts/citation-format.md §3
- [ ] T043 [P] [US1] 实现拒答样本合成 `src/tu_assistant/synth/refusal.py`：知识库外问题（其他法律领域、与工会无关、本期不支持的需求如起草维权文书）→ 明确拒答或引导（FR-014、FR-022）
- [ ] T044 [US1] 实现 `tu synth sft --kb <ver>` 汇总 T040–T043 与约 5% 通用对话，经 T030 检查、T031 构建数据集（依赖 T040–T043）

### 编排与交互

- [ ] T045 [US1] 在 `src/tu_assistant/chat/orchestrator.py` 中实现咨询回答末尾固定追加"*以上内容仅供参考，不构成法律意见。*"（FR-023），拒答时不追加结构
- [ ] T046 [P] [US1] 实现 Markdown 导出 `src/tu_assistant/chat/export.py`：`export_markdown` 返回某轮回复的 Markdown（FR-032）
- [ ] T047 [US1] 实现 `tu chat`：命令行多轮对话，`/save <path>` 保存最后一轮为 `.md`，`/new` 新会话

### 评测与训练

- [ ] T048 [P] [US1] 实现多违法行为与关联补全指标（SC-004、SC-005）、拒答与误拒指标（SC-008）、意图确认指标（SC-001：3 轮内正确确认的比例）于 `src/tu_assistant/eval/metrics.py`，并补充 `tests/unit/test_metrics.py`
- [ ] T049 [US1] 编写评测集 v1 的多违法行为与意图确认（固定对话脚本）用例约 20 题，加入 `eval/cases/v1/`，由用户审阅确认
- [ ] T050 [US1] 用 `configs/train/debug-1.5b.yaml` 训练，评测，跑通全流程（quickstart V4）；记录 loss 曲线与评测结果
- [ ] T051 [US1] 撰写 `docs/learning/04-training-data.md`：训练数据样例（真实生成结果）、为什么改写成问答、追问上限随机化、合成样本检查与丢弃率、评测与训练去重；更新术语表

**Checkpoint**: 1.5B 模型可多轮咨询，全流程跑通（MVP 流程验证）

---

## Phase 4: User Story 2 — 生成普法宣传文章 (Priority: P2)

**Goal**: 按语义主题生成多篇以案说法的普法文章，使用虚构名称，场景差异化，可在会话中修改

**Independent Test**: 用评测集中的普法文章用例生成文章，由项目方按评分要点检查构成要件、出处、法律责任、多样性、语言风格（spec US2）

- [ ] T052 [P] [US2] 实现普法文章样本合成 `src/tu_assistant/synth/articles.py`：主题 → 多篇文章（结构按 contracts/citation-format.md §4），场景在违法主体类型、当事人身份、手段、情节轻重上有差异；人物与单位一律虚构；含多违法行为综合场景（FR-024 ~ FR-029）
- [ ] T053 [P] [US2] 实现修改请求样本合成（"语言再通俗一些""换一个违法主体"），加入 `src/tu_assistant/synth/articles.py`
- [ ] T054 [P] [US2] 实现身份信息检查 `src/tu_assistant/chat/anonymize.py`：从本会话用户消息中按规则抽取候选身份信息（单位后缀"公司/厂/集团/医院/学校"、常见姓氏 + 名字），文章命中则替换为虚构名称并记录（FR-030）
- [ ] T055 [P] [US2] 单元测试 `tests/unit/test_anonymize.py`：真实名称被替换、虚构名称不受影响
- [ ] T056 [US2] 在 `src/tu_assistant/chat/orchestrator.py` 中接入文章数量（默认 3，上限 10，读取 `SessionConfig`）与身份信息检查（依赖 T054）
- [ ] T057 [US2] 将 T052、T053 样本加入 `tu synth sft`，重新生成数据集
- [ ] T058 [US2] 编写评测集 v1 的普法文章用例约 10 题（含评分要点 `rubric`），加入 `eval/cases/v1/`，由用户审阅确认；实现 SC-011（身份信息）自动检查于 `src/tu_assistant/eval/metrics.py`
- [ ] T059 [US2] 用 `configs/train/demo-7b.yaml` 训练演示模型（一到两晚），评测（quickstart V5）；按评测结果调整数据后再训一次
- [ ] T060 [US2] 撰写 `docs/learning/05-training.md`：一次训练的完整过程、超参数含义、用本项目真实日志讲解 loss 曲线、过拟合与欠拟合、1.5B 与 7B 的对比；更新术语表

**Checkpoint**: 7B 演示模型可咨询、可生成普法文章

---

## Phase 5: User Story 3 — 用统一评测集衡量系统质量 (Priority: P3)

**Goal**: 产出覆盖 SC-001 ~ SC-011 的分项报告，支持版本对比与人工评审记录

**Independent Test**: 对同一模型重复评测，指标波动 ≤2 个百分点；两个版本可直接对比（spec US3、SC-015）

- [ ] T061 [P] [US3] 在 `src/tu_assistant/eval/report.py` 中完善报告：全部指标与 POC 目标值对照（不作为验收条件）、引用准确率校验前 / 后两列、逐条失败用例清单；SC-009（文章正确性）、SC-010（文章多样性）从人工评审表格（T063）汇总
- [ ] T062 [P] [US3] 实现 `tu eval compare <run_id>...` 于 `src/tu_assistant/eval/compare.py`：同一评测集与口径的版本对比，输出 `compare.md`（FR-035）
- [ ] T063 [P] [US3] 提供人工评审表格模板 `eval/review-template.csv`（列：`run_id`、`case_id`、`reviewer`、`verdict`（pass / minor_issue / fail）、`comment`、`created_at`），并在 `report.md` 中按 `case_id` 列出待评审的普法文章（FR-037，POC 用表格记录）
- [ ] T064 [US3] 对 7B 演示模型重复评测 2 次，用 `tu eval compare` 验证指标波动 ≤2 个百分点（SC-015），结果存于 `artifacts/eval/`
- [ ] T065 [US3] 撰写 `docs/learning/06-evaluation.md`：各指标计算方法、校验前 / 后两种准确率的含义、用本项目评测结果分析薄弱类别并反推数据改进方向；更新术语表

**Checkpoint**: 评测报告完整、可对比、可复现

---

## Phase 6: User Story 4 — 维护和更新法规知识库 (Priority: P4)

**Goal**: 文档新增、修改、删除后整批重导，生成新知识库版本，系统使用新内容

**Independent Test**: 修改一条条款后重新入库，出处校验层引用新原文；新文档中的内容经重训后可被识别（spec US4）

- [ ] T066 [P] [US4] 实现 `tu kb diff <v1> <v2>` 于 `src/tu_assistant/kb/diff.py`：列出新增、删除、原文变化的条款（只输出编号与变化类型）
- [ ] T067 [US4] 在 `configs/app.yaml` 中增加 `kb.version`，编排层与出处校验层按配置加载指定知识库版本；切换版本无需修改代码（FR-004）
- [ ] T068 [US4] 用 `tests/fixtures/` 的样例验证"修改条款 → 重新入库 → 校验层使用新原文"的流程，写入集成测试 `tests/integration/test_kb_update.py`；在 quickstart 中补充"知识更新需重训"的说明（research R1 风险）

**Checkpoint**: 知识库可更新、可追溯版本

---

## Phase 7: 演示界面与收尾

**Purpose**: 可对外演示的网页界面、演示准备、文档收尾

- [ ] T069 实现 Gradio 演示界面 `src/tu_assistant/ui/app.py` 与 `tu ui`：多轮对话、新会话、保存当前回复为 Markdown；只监听 127.0.0.1（quickstart V6）
- [ ] T070 准备演示场景脚本 `docs/demo-scenarios.md`：模糊开场 → 追问 → 咨询；多违法行为；拒答；生成 3 篇普法文章 → 修改 → 保存（场景内容使用虚构案情）
- [ ] T071 [P] 运行 quickstart.md 全部验证场景（V1–V7），记录结果
- [ ] T072 [P] 更新 `README.md`：项目简介、环境准备、常用命令、文档索引
- [ ] T073 撰写 `docs/learning/07-serving-demo.md`：模型服务、对话编排、演示界面、训练与演示不能同时进行的原因；更新术语表
- [ ] T074 撰写 `docs/learning/08-lessons-and-next.md`：踩坑汇总、POC 说明了什么与没说明什么（含校验前引用准确率的解读）、正式阶段事项（research R12）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：无依赖
- **Foundational (Phase 2)**：依赖 Setup；阻塞所有用户故事。T016 需要 `inputs/project/` 已就位（已就位，28 篇）；T019、T038 需要用户参与
- **US1 (Phase 3)**：依赖 Foundational
- **US2 (Phase 4)**：依赖 US1 的数据合成框架（T044）与编排（T045）；7B 训练（T059）使用 US1 + US2 的全部数据
- **US3 (Phase 5)**：依赖 Foundational 的评测核心；T064 依赖 T059
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
| T044 前 | 提供外部大模型 API Key，确认提供方服务条款允许用输出训练模型 |
| T059 后 | 人工评审普法文章（表格） |

---

## Notes

- [P] 任务 = 不同文件、无依赖
- 每个任务或逻辑组完成后提交；文档类提交须经用户审阅
- 不得读取 `inputs/` 内容；不得在运行时调用外部服务
