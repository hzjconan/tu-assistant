# T073 执行单 · 完整撰写与收口推理与演示学习文档 `docs/learning/07-serving-demo.md` 及术语表更新

- **状态**：已完成并验收（2026-11-24，内部 2 轮独立只读复审通过，用户确认提交）— 按方案 **`1A 2A 3A`** 实施
- **对应任务**：`specs/001-legal-clause-assistant/tasks.md` Phase 7 — **`T073`**（单项推进，不合并 `T072` / `T074`）
- **Git 基线**：`167fe5c`（`main`，工作区干净；`T071` 已验收提交）
- **活跃产物基线**：
  - 冻结 7B 演示模型：`exp-20261116-resume500`（基座 `mlx-community/Qwen2.5-7B-Instruct-4bit` 4bit 约 `4.4 GB`；`adapters/adapters.safetensors` 实测 `77.04 MB`；训练耗时 `49,593 s`）
  - 1.5B 流程验证模型：`exp-20261114-120250`（基座 `mlx-community/Qwen2.5-1.5B-Instruct-4bit`；`adapters/adapters.safetensors` 实测 `20.15 MB`；训练耗时 `14,342 s`）
  - 活跃知识库：`artifacts/kb/kb-20261119-045641.sqlite`（24 篇法规 / 3,809 条记录 / 67 条已确认关联：`liability_for` 26 + `references` 41）
  - 当前服务元数据：`artifacts/serve/current.json` 指向 `exp-20261116-resume500`（`model="default_model"`，`endpoint="http://127.0.0.1:8080/v1"`）
  - 自动化与只读基线：`uv run --offline --no-sync pytest` **462 passed, 6 xfailed**，`uv run --offline --no-sync ruff check src tests` 全绿，`shasum -a 256 -c artifacts/logs/t075/01/output.sha256` **25/25 OK**
- **不可逾越的红线**：
  1. **严禁读取 `inputs/` 目录下任何文件**（包括直接读取、grep 或运行任何输出其内容的脚本）；
  2. **纯文档边界**：本任务仅修改 `docs/learning/07-serving-demo.md`、`docs/learning/00-glossary.md`、`docs/learning/README.md`（验收收尾时在本执行单末尾追加实施与复审记录；允许在 `.gitignore` 忽略的 `artifacts/logs/t073/` 下存放本地只读校验脚本，不入 Git）；**严禁改动 `src/`、`tests/`、`configs/`、`eval/`、`specs/`、`README.md`、`docs/demo-scenarios.md` 及任何历史产物**；
  3. **运行时零侵入**：不触碰推理服务、不改 `artifacts/serve/current.json`、不改动 4 份历史 KB 与 T075 `output.sha256` 覆盖的 25 项文件；
  4. **验收门禁前不落账**：完成独立只读复审闭环并获用户明确确认前，不得勾选 `tasks.md` 中的 `T073`，不得执行 `git commit` 或 `git push`。

---

## 上篇：面向用户决策

### 1. 推荐任务编号与选择理由

**推荐本轮单项推进 `T073`（撰写 `docs/learning/07-serving-demo.md`：模型服务、对话编排、演示界面、训练与演示不能同时进行的原因；更新术语表）。**

POC 阶段目前仅剩最后 3 项收尾文档任务（`T072`、`T073`、`T074`；`T078` 已明确移出 POC），建议按 **`T073`（本单）→ `T074`（全项目复盘终章）→ `T072`（`README.md` 最终全仓索引）** 的顺序依次收尾：

| 候选任务 | 核心范围与现状 | 为何本次优先单项推进 `T073`（且不合并相邻任务） |
|---|---|---|
| **`T073`（本次推荐）** | 收口 `docs/learning/07-serving-demo.md` + `00-glossary.md` + `docs/learning/README.md`。当前已有 `[L7.1]`–`[L7.3]` 零散小节（166 行），缺少章首导航、模型服务与运行时隔离全貌、对话编排完整 10 步流水线及“训练与演示为何不能同时进行” | ① **承接顺序完全就绪**：`T069`（Gradio UI）、`T070`（演示剧本）、`T071`（V1–V7 实机验证）刚全部落地，第 7 章所需的源码锚点、实机延迟与硬件实测数据 100% 齐备，趁热整理零失真；② **为 `T074` 冻结 `[L7.x]` 锚点**：终章 `08-lessons-and-next.md` 复盘服务/UI 踩坑与正式阶段演进时可直接引用定稿的 `[L7.4]`–`[L7.6]` 链接；③ **顺手修复已发现瑕疵**：现有 `07-serving-demo.md:150` 含本机绝对 `file://` 路径及偏移行号、`docs/learning/README.md:18` 仍停留在 `已含 L7.1` 的过时描述。 |
| `T074` | 撰写 `docs/learning/08-lessons-and-next.md`（全项目踩坑汇总、POC 说明/没说明什么、校验前准确率深度解读、正式阶段 R12、T078 已知缺陷登记） | 属于**全项目战略复盘终章**，涵盖 Phase 1–7 全部技术决策与对外口径，审查权重高；应放在第 7 章锚点定稿之后独立成单，避免与 `T073` 合并导致单次变更过大、技术细节与战略复盘混杂。 |
| `T072` | 更新 `README.md`（项目简介、环境准备、常用命令、文档索引） | `README.md` 已在 `3b944c9` 更新过一版（含 7B 训练与 `tu ui`）；作为**全仓总入口与文档导航**，目前 `08-lessons-and-next.md` 尚未创建、第 7 章仍标 `进行中`。若先做 `T072`，势必漏掉第 8 章或留下断链，完成后还须二次修改；放最后收尾可一次性索引 `demo-scenarios.md`、`T071-quickstart-verification.md` 与 `01`–`08` 完整学习文档，零返工。 |

---

### 2. 待用户拍板的决策清单

请审阅以下 3 项取舍并直接回复选择（例如 `1A 2A 3A`）：

1. **决策 1：`07-serving-demo.md` 的编号组织方式（保留原 `[L7.1]`–`[L7.3]` 锚点 vs 整体重新编号）**
   - **1A（推荐）**：**保留既有 `[L7.1]`、`[L7.2]`、`[L7.3]` 原始编号与标题锚点不动**（延续 `05-training.md` 与 `T065` `06-evaluation.md` 已验证做法），在章首新增「本章知识点」逻辑阅读导航表，文末增补 **`[L7.4]`（模型服务与运行时隔离）、`[L7.5]`（对话编排 10 步全链路与交付对照）、`[L7.6]`（训练与演示为何不能同时进行）、`[L7.7]`（可以继续问的问题）**；仅对 `[L7.3]` 做 3 处局部纠偏（本机绝对路径改相对路径及精确行号、`~4.3 GB` 统一对齐 `[L2.2]` `~4.4 GB` 并补录实测 adapter 体积、`05-training.md` 相对链接统一格式）。
     - *理由*：对 `00-glossary.md`（现存 3 条锚点）、`tasks.md` 与 `T056`/`T069` 执行单中的历史编号实现 100% 零破坏，同时靠章首阅读路线兼顾逻辑阅读体验。
   - **1B**：按逻辑顺序把全章重新编号为 `[L7.1]`（模型服务）→ `[L7.7]`（延展提问），同步修改 `00-glossary.md` 中现有 3 条锚点。
     - *理由*：从头到尾阅读顺序像教科书，但会造成与 `tasks.md` 及历史执行单中 `[L7.1]`/`[L7.2]` 编号不再对应。

2. **决策 2：`docs/learning/00-glossary.md` 的术语分区整理方式**
   - **2A（推荐）**：在 `00-glossary.md` 末尾新增独立分区 **`## 推理与演示`**（与现有 `## 评测` 并列），将此前暂放于 `## 硬件与工具` 末尾的 3 条服务/界面术语（`确定性护栏`、`会话状态隔离`、`SQLite 线程亲和`）整洁迁入，并增补 5 条新术语（`OpenAI 兼容接口`、`动态挂载 Adapter / 权重合并（Fuse）`、`端点白名单`、`对话编排流水线`、`内存带宽受限（Memory-Bandwidth Bound）`），形成完整 8 条分区。
     - *理由*：与 `## 模型基础` / `## 训练技术` / `## 评测` 的领域划分完全一致，避免 `## 硬件与工具` 混杂过多运行时与 Web 概念。
   - **2B**：不新增分区，保留原有 3 条在 `## 硬件与工具` 不动，将新增 5 条继续追加在 `## 硬件与工具` 末尾。
     - *理由*：Diff 更小，但分区语义略杂。

3. **决策 3：`T070` 演示剧本与 `T071` V4/V6 实机数据的纳入深度**
   - **3A（推荐）**：在 `[L7.5]` 结合 `docs/demo-scenarios.md` 与 `docs/experiments/T071-quickstart-verification.md`，用简明对照表展示 `tu chat` vs `tu ui` 两种入口的实机响应延迟（2.2–34.1 s / 91 ms 硬拒）、导出形态（V4 `6,621 B` / V6 `163 B` 逐字节一致）并一句话点出 V6 Step 4 第 2 轮路线 A 简短改稿压缩边界（链接至 T071 详情），把全项目结论与战略复盘留给 `T074`（`08-lessons-and-next.md`）。
     - *理由*：落实 `docs/learning/README.md` “所有命令、日志和数字都来自本项目真实运行结果”的原则，又与 `T074` 职责清晰切分不重复。
   - **3B**：仅写纯架构原理与源码流水线，不引入 `T070`/`T071` 的实机耗时与边界数据。
     - *理由*：篇幅更短，但缺少本项目实测体感锚点。

---

## 下篇：面向实施方（便宜模型）的零歧义施工图

> 若用户拍板选择非推荐项，待定稿折叠清除落选分支后再开工；以下按推荐项 `1A 2A 3A` 展开精确施工口径。

### 3. 现状锚点与文档/环境陷阱预警

#### 3.1 关键源码与文档锚点（均已只读核实）

| 主题 | 文件与精确行号 | 实测职责 / 事实 |
|---|---|---|
| 模型服务启动 | `src/tu_assistant/cli.py:395-440` | `serve_model`：仅允许 `host in {"127.0.0.1", "localhost"}`（L407–409）；读 `manifest.json["config"]["base_model"]`（L412–413）；校验 `adapters/` 存在（L414–417）；写 `artifacts/serve/current.json`（含 `model: "default_model"`，`L421-430`）；子进程启动 `python -m mlx_lm.server --model <base> --adapter-path <adapter> --host <host> --port <port>`（L432–440） |
| 服务发现与模型名解析 | `src/tu_assistant/config.py:62-73` | `resolve_model_name(cfg, artifacts_dir)`：当 `configs/app.yaml` 中 `runtime.model_name == "default"` 时读取 `artifacts/serve/current.json["model"]`（即 `"default_model"`） |
| `mlx_lm.server` 路由机制 | `.venv/.../mlx_lm/server.py:390-395, 473-486`（`mlx-lm 0.32.2`） | `_model_map["default_model"] = cli_args.model`、`_adapter_map["default_model"] = cli_args.adapter_path`；`load()` 按请求体 `model` 查表，传具体基座名会绕开 `_adapter_map` 退回裸底座；服务端内置 `LRUPromptCache`（L528） |
| 运行时客户端与白名单 | `src/tu_assistant/runtime/client.py:13-79` | `EndpointNotAllowedError`（L13）、`check_endpoint_allowed`（L17–23）、`ModelClient`（L33–79，构造即校验白名单，`timeout_s=300.0`，`POST {endpoint}/chat/completions`，`httpx 0.28.1`） |
| 运行时隔离测试 | `tests/unit/test_runtime_isolation.py:19-59` | 端点白名单单测 + AST 静态扫描 `chat/`、`runtime/`、`ui/`、`eval/` 严禁导入 `openai` 与 `tu_assistant.synth*` |
| 系统接口与配置切库 | `src/tu_assistant/chat/assistant.py:23-61, 64-202` | `SessionConfig`（`__post_init__` 调 `validate_count_limits`）、`session_config_from`、`Reply`、`Assistant` Protocol、`TrainedAssistant`（`from_config` 支持 `kb.version` 零改代码切库、`open_kb(..., read_only=True, check_same_thread=...)`） |
| 内存会话与导出 | `src/tu_assistant/chat/session.py:14-59`、`src/tu_assistant/chat/export.py:12-17`、`src/tu_assistant/chat/prompts.py:14-37` | `Turn` / `Session`（仅存内存，`close` 即 `pop` 释放）、`to_openai_messages`、`export_markdown`（默认导出最后一轮 assistant Markdown）、`v2-short` `SYSTEM_TEMPLATE`（注入 `max_questions`） |
| 对话编排 10 步流水线 | `src/tu_assistant/chat/orchestrator.py:31-32, 46-181` | `DISCLAIMER`（L31）、`RE_QUESTION_LINE`（L32）、`process_turn`（L46–181，含篇数判定、实体优先登记、事务快照、超限早退、临时请求副本附注、模型调用、`verify_output`、已确认关联补全、`classify_turn_intent`、免责声明、`anonymize_article_text` / `sanitize_citations`、追问计数、`except Exception` 全链路回滚） |
| 命令行与网页入口 | `src/tu_assistant/cli.py:1295-1374`（`tu chat`）、`src/tu_assistant/cli.py:1376-1459`（`tu ui`）、`src/tu_assistant/ui/app.py:26-452` | `tu chat` 支持 `/save` `/new` `/quit`；`tu ui` 仅允许 `127.0.0.1`、`check_same_thread=False`、`Gradio 6.31.0` 零遥测/零 Google Fonts/`delete_cache=(600, 7200)`/单并发队列/`STATE_TTL_WHEN_CLOSED=3600` |
| 硬件与训练实测基线 | `docs/learning/02-hardware.md:29, 77-87, 109-144`、`configs/train/demo-7b.yaml:10-29`、`docs/experiments/T071-quickstart-verification.md:14-23, 67-105` | 7B 4bit 底座 `~4.4 GB`；7B 训练短样本 `~9 GB`、长样本不开检查点 `23 GB`、开 `--grad-checkpoint` `11.5 GB`（`~83 tok/s`，`~3.7 s/iter`，1 epoch 约 `12–14 h`）；7B 推理基线 `4.5 GB`（`~35 tok/s`）；`save_every: 500` |

#### 3.2 摸底发现的 5 处陷阱与必须采用的写法

1. **现有 `[L7.3]` 含本机绝对路径与过期行号（必须修）**：`docs/learning/07-serving-demo.md:150` 当前写着 `[cli.py](file:///Users/hzjconan/workspace/tu-assistant/src/tu_assistant/cli.py#L400-L441)`，换机必断链且行号偏了 5 行 → 必须改为仓库相对路径 `[cli.py](../../src/tu_assistant/cli.py#L395-L440)`。
2. **现有 `[L7.3]` 底座体积口径与 `[L2.2]` 有 0.1 GB 差异（必须对齐）**：`07-serving-demo.md:93, 108` 写 `~4.3 GB` / `约 4.3 GB`，而 `02-hardware.md:29` 实测为 `~4.4GB` → 统一改为 `~4.4 GB`（并注明本项目实测 `adapters.safetensors` 体积：7B `77.04 MB`、1.5B `20.15 MB`，让“几十 MB”有真实数字锚点）。
3. **两处过时过渡文案易遗漏（必须清零）**：`07-serving-demo.md:3` 仍写“当前已写入 `[L7.1]`、`[L7.2]`”（漏了 `[L7.3]` 且仍标待整理），`docs/learning/README.md:18` 仍写“进行中（已含 L7.1 编排层文章数量控制；完整章节由 T073 整理）” → 必须同步清除过渡语并标为 `✅`。
4. **沙箱环境禁止在校验脚本里 `import mlx_lm`**：本机沙箱无 Metal GPU 设备，只读实测 `import mlx_lm` 会直接抛 `ImportError: [metal::load_device] No Metal device available` → 确定性核查脚本只能做纯文件文本/AST/正则/GFM 锚点解析，严禁导入 `mlx_lm` 或 `mlx`。
5. **GFM 锚点与 Mermaid 语法防雷**：
   - GFM 标题生成锚点会移除中英文标点（`[` `]` `：` `（` `）` `、` `/` `“` `”` `` ` `` 等），空格转 `-`，英文字母转小写；所有目录表与术语表锚点**必须由核查脚本按 GFM 规则自动核验 0 失配**；
   - Mermaid 仅使用 `flowchart TD`，所有含括号、冒号、斜杠或中文标点的节点标签必须用双引号包裹（如 `N1["① 篇数判定 (decide_article_count)"]`），严禁在节点标签中写 `<br>` 等 HTML 标签。

---

### 4. 改动范围表与明确不做清单（Non-Goals）

#### 4.1 文件改动表

| 文件路径 | 操作 | 精确职责 |
|---|---|---|
| `docs/learning/07-serving-demo.md` | **修改** | ① 替换章首过渡提示为正式导言 + `## 本章知识点` 逻辑导览表；② 保留 `[L7.1]`、`[L7.2]` 标题与正文不动；③ 保留 `[L7.3]` 标题与主体，修正 L93/L108 体积口径、L150 相对路径与行号、L157 相对链接格式；④ 新增 `[L7.4]`、`[L7.5]`（含 Mermaid 流水线图与 V4/V6 实测对照表）、`[L7.6]`，并将原 `### 可以继续问的问题` 升级整合为 `## [L7.7] 可以继续问的问题` |
| `docs/learning/00-glossary.md` | **修改** | 按决策 2A 新增 `## 推理与演示` 分区，迁入原 `## 硬件与工具` 末尾 3 条服务/界面术语并增补 5 条新术语（合计 8 条），全部指向 `07-serving-demo.md` 经核验的精确 GFM 锚点；核对全表零断链 |
| `docs/learning/README.md` | **修改** | 第 7 章行（L18）状态更新为 `✅`，内容简介同步覆盖模型服务、对话编排、演示界面与硬件互斥原因（`L7.1–L7.7`） |
| `artifacts/logs/t073/verify_t073.py` | **新增（本地忽略产物，不入 Git）** | 纯只读确定性核查脚本，验证跨文档链接与 GFM 锚点、源码 `file:line` 存在性、关键数字一致性、Mermaid 节点语法及禁用项零残留 |
| `docs/handoffs/T073-serving-demo-learning-handoff.md` | **验收收尾时追加** | 独立复审通过后，仅在末尾追加实施结果与复审记录 |

#### 4.2 明确不做清单（Non-Goals）

- **严禁改动业务代码、测试、配置、规格与历史产物**：不碰 `src/`、`tests/`、`configs/`、`eval/`、`specs/`、`scripts/`、4 份历史 KB、冻结权重、`artifacts/serve/current.json` 及 T075 `output.sha256` 25 项文件；
- **严禁抢做 `T072` 与 `T074`**：不改根目录 `README.md`（归 `T072`），不创建 `docs/learning/08-lessons-and-next.md`（归 `T074`），不在第 7 章展开全项目复盘、SC-007 校验前准确率的战略解读或正式阶段 1000 篇立项路线图（仅在 `[L7.6]` 末尾一句话点出“正式阶段训练与推理物理隔离，见 R12”即可）；
- **严禁触碰 `inputs/` 目录**或粘贴任何法律条文原文片段。

---

### 5. 文档结构与事实口径契约（施工核心，不留猜想空间）

#### 5.1 `docs/learning/07-serving-demo.md` 精确章节骨架与锚点契约

标题采用与 `06-evaluation.md` 一致的体例：

| 节号 | 精确二级标题 | 期望 GFM 锚点（供导航表与术语表引用） | 状态 |
|---|---|---|---|
| H1 | `# 第 7 章 推理与演示：模型服务、对话编排与演示界面` | — | 升级原 H1 |
| 导览 | `## 本章知识点` | `#本章知识点` | 新增（含逻辑阅读路线：`[L7.4]` → `[L7.3]` → `[L7.5]` → `[L7.1]` → `[L7.2]` → `[L7.6]` → `[L7.7]`） |
| L7.1 | `## [L7.1] 对话编排层的确定性护栏：文章数量控制如何与微调模型协作` | `#l71-对话编排层的确定性护栏文章数量控制如何与微调模型协作` | **原样保留** |
| L7.2 | `## [L7.2] 本地演示界面的工程边界：Gradio 6 状态隔离、SQLite 跨线程约束与本地隐私护栏` | `#l72-本地演示界面的工程边界gradio-6-状态隔离sqlite-跨线程约束与本地隐私护栏` | **原样保留** |
| L7.3 | `## [L7.3] 基于底座模型加载训练后权重：动态挂载 Adapter vs 合并权重（Fuse）` | `#l73-基于底座模型加载训练后权重动态挂载-adapter-vs-合并权重fuse` | **保留标题与主体，仅修 3 处局部瑕疵** |
| L7.4 | `## [L7.4] 模型服务与运行时隔离：OpenAI 兼容接口、`current.json` 路由与零外连防线` | `#l74-模型服务与运行时隔离openai-兼容接口currentjson-路由与零外连防线` | 新增 |
| L7.5 | `## [L7.5] 对话编排全链路：从一条用户消息到可交付回复的 10 步流水线` | `#l75-对话编排全链路从一条用户消息到可交付回复的-10-步流水线` | 新增 |
| L7.6 | `## [L7.6] 为什么训练与演示不能在 M1 Pro（32GB）上同时进行` | `#l76-为什么训练与演示不能在-m1-pro32gb上同时进行` | 新增 |
| L7.7 | `## [L7.7] 可以继续问的问题` | `#l77-可以继续问的问题` | 合并升级原 `### 可以继续问的问题`（保留原 4 题 + 新增 3 题 = 7 题） |

> 注：以上 GFM 锚点须在 Step 5 用核查脚本对实际生成的标题做逐字验算，确保 100% 匹配。

#### 5.2 各新增/修补小节的硬性事实口径契约

1. **章首导言与 `## 本章知识点`**：
   - 写明对应任务：Phase 2/3/4/7 的 `T024`–`T028`、`T045`–`T047`、`T054`–`T056`、`T069`–`T071`、`T073`；核心源码位于 `src/tu_assistant/{runtime,chat,ui}/` 与 `src/tu_assistant/cli.py`。
   - 显式说明：保留 `[L7.1]`–`[L7.3]` 历史编号以确保术语表与历史记录零断链，并给出推荐逻辑阅读顺序：`[L7.4]` → `[L7.3]` → `[L7.5]` → `[L7.1]` → `[L7.2]` → `[L7.6]` → `[L7.7]`。
2. **`[L7.3]` 局部 3 处修补（不得擅改其余段落）**：
   - L93：“体积通常只有几十 MB（对比 4bit 7B 底座的 ~4.3 GB）” → 改为“体积通常只有几十 MB（本项目实测 `adapters.safetensors`：7B 为 `77.04 MB`，1.5B 为 `20.15 MB`，对比 4bit 7B 底座的 `~4.4 GB`，见 `[L2.2]`）”；
   - L108：“7B 4bit 约 4.3 GB” → 改为“7B 4bit 约 4.4 GB”；
   - L150：`[cli.py](file:///Users/hzjconan/workspace/tu-assistant/src/tu_assistant/cli.py#L400-L441)` → 改为 `[cli.py](../../src/tu_assistant/cli.py#L395-L440)`；
   - L157：`[L5.11](05-training.md#l511-评测前先确认测的是你的模型e002-实录)` → 改为 `[L5.11](./05-training.md#l511-评测前先确认测的是你的模型e002-实录)`。
3. **`[L7.4]` 模型服务与运行时隔离（必备 4 块）**：
   - **OpenAI 兼容接口解耦**：说明 `mlx_lm.server`（本机实测 `mlx-lm 0.32.2`）暴露标准 `POST /v1/chat/completions`，`ModelClient`（`runtime/client.py:33-79`，基于 `httpx 0.28.1`，默认 `timeout_s=300.0`、`max_tokens=4096`）只负责发请求，正式阶段切换到 vLLM 不改编排层代码（`research.md` R7）。
   - **`current.json` 路由闭环**：串联 `cli.py:421-430` 写入 `artifacts/serve/current.json`（`model="default_model"`、`base_model`、`exp`、`endpoint`）→ `config.py:62-73` `resolve_model_name()` 读取 → `mlx_lm/server.py:393-395, 477-486` 按 `_model_map["default_model"]` / `_adapter_map["default_model"]` 加载，清晰复盘为何不能传具体基座名（交叉链接 `[L5.11]` 与 `[L7.3]`）。
   - **运行时三层零外连防线（宪章原则 III、IV，FR-033）**：
     - 第 1 层（服务端监听）：`tu serve model` 限制 `{"127.0.0.1", "localhost"}`（`cli.py:407-409`）；`tu ui` 更严格，仅放行 `127.0.0.1`（`ui/app.py:31, 50-56`）；
     - 第 2 层（客户端端点白名单）：`check_endpoint_allowed` 校验 `configs/app.yaml` 中 `runtime.model_endpoint` 主机属于 `runtime.allowed_hosts`，否则启动即抛 `EndpointNotAllowedError`（`runtime/client.py:13-23, 43`）；
     - 第 3 层（静态 AST 门禁）：`tests/unit/test_runtime_isolation.py` 扫描 `chat/`、`runtime/`、`ui/`、`eval/` 禁止导入 `openai` 与 `tu_assistant.synth*`（外部 API 只允许存在于离线 `synth/`）。
   - **推理服务端缓存与温度取舍**：说明 `mlx_lm.server` 维护 `LRUPromptCache` 前缀缓存（衔接 `[L6.7]` 重复评测须冷启动清缓存），以及现场演示推荐 `tu ui --temperature 0.0`（确定性复现 T064 `SC-015` `0.0 pp` 基线）vs 默认 `0.7` 的取舍（链接 `../demo-scenarios.md`）。
4. **`[L7.5]` 对话编排全链路（必备 3 块）**：
   - **统一 `Assistant` 协议与无代码切库**：说明 `tu chat`、`tu ui`、`tu eval run` 三端共享 `Assistant` Protocol（`new_session` / `send` / `export_markdown` / `close`，`chat/assistant.py:57-61`），POC 实现 `TrainedAssistant`、`from_config` 按 `configs/app.yaml` 的 `kb.version`（`null` 自动最新 vs 填版本号锁定）以只读 SQLite 打开知识库，正式阶段可零改动替换为 `RetrievalAssistant`。
   - **`process_turn` 10 步流水线（含 Mermaid `flowchart TD` + 步骤对照表）**：严格按 `src/tu_assistant/chat/orchestrator.py:46-181` 真实执行顺序写出：
     1. 篇数判定 `decide_article_count`（L56–60）；
     2. 用户真实实体抽取登记 `extract_user_entities`（L61–65，故意先于超限早退，衔接 `[L7.1]`）；
     3. 事务快照 `prev_len` / `prev_intent` / `prev_active`（L66–68）并记录 `user` 轮（L69）；
     4. 超限/非正数硬拒早退 `decision.action == "rejected"`（L72–84，不调模型）；
     5. 组装 `v2-short` system prompt（`build_system_prompt` 注入 `max_questions_per_turn`，L86–93）与 `to_openai_messages`（L94），若 `use_default` 仅向临时请求副本末尾附注篇数指令（L95–100）；
     6. 调用 `client.chat(messages, temperature=temperature)` 获取 `raw`（L101–102）；
     7. 出处校验 `verify_output(raw, kb_conn)`（L104–106，同时产出 `protected_spans` 核准引文区间，衔接 `[L3.5]`）；
     8. 已确认关联条款兜底补全（FR-019，L109–126：`confirmed_relations_from` 查 KB 67 条已确认关联，去重后追加 `**相关条款（系统补充）**` 并扩入 `protected_spans`）；
     9. 会话意图与续改态更新 `classify_turn_intent`（L129–138）+ 仅在 `has_citation` 为真时追加 `DISCLAIMER`（`*以上内容仅供参考，不构成法律意见。*`，FR-023，L140–141，拒答无引用时不追加）；
     10. 普法文章身份脱敏与元数据清洗（`should_anonymize` 分支，L147–158：`anonymize_article_text` 保护 `protected_spans`，引文冲突时暂缓交稿 `anonymize_blocked=True` 并清空 `citations`，否则 `sanitize_citations`）+ 追问行数统计 `RE_QUESTION_LINE`（L160）+ `eval_mode` 保留 `raw_content`（L165）；
     - **全链路异常回滚**（`except Exception`，L177–181）：回滚 `session.messages[prev_len:]`、`session.intent` 与 `article_task_active`，防止断连/超时或 SQLite 报错留下悬挂 `user` 轮。
   - **`tu chat` vs `tu ui` 交付形态与 T071 实机延迟对照（按决策 3A）**：用表格对比两类入口（运行线程模型、会话清理方式、Markdown 导出方式 `/save <path>` vs `gr.DownloadButton`），引用 `T071` 实测数据（V4 1.5B `tu chat /save` `6,621 B`；V6 7B `tu ui --temperature 0.0`：单条咨询 `2.2–3.3 s`、多违法 `mv-002` `34.1 s`、关联补全 + 切换写稿 `2.8 s / 4.0 s / 19.7 s`、15 篇硬拒 `91 ms`、下载 `.md` `163 B` 逐字节一致），并如实一句话点出 V6 Step 4 第 2 轮路线 A 简短改稿压缩边界（链接至 `../experiments/T071-quickstart-verification.md` 与 `../demo-scenarios.md`）。
5. **`[L7.6]` 为什么训练与演示不能在 M1 Pro（32GB）上同时进行（必备 4 维拆解）**：
   - **维度 1 · 统一内存账本**：汇总 `02-hardware.md` 与 `demo-7b.yaml` 实测数字：macOS + 桌面常驻约 `6–10 GB`；7B QLoRA 训练（开 `--grad-checkpoint`）长样本峰值约 `11.5 GB`（不开 `23 GB`）；7B 推理服务（4bit 底座 `~4.4 GB` + `77.04 MB` adapter）静态约 `4.5 GB`，加上多轮对话 KV Cache 与 `LRUPromptCache` 动态增至 `5–7+ GB`；三者叠加（`25–28+ GB`）逼近 32 GB 机器 Metal 安全可用上限，极易触发 swap 抖动或系统 OOM Kill（一旦杀掉跑了一晚的训练进程，最多损失距上次 `save_every: 500` 检查点之间的步数）。
   - **维度 2 · GPU 计算队列与内存带宽争抢**：解释自回归解码（token-by-token）是典型的**内存带宽受限（Memory-Bandwidth Bound）**操作——每生成 1 个 token 都需重读约 `4.4 GB` 权重；而训练（`~83 tok/s`、`~3.7 s/iter`，1 epoch 约 `12–14 h`）持续打满同一颗 Apple Silicon GPU 与统一内存总线。同时运行会导致演示响应延迟成倍恶化（触发前端卡顿或超时）、训练吞吐骤降并加剧笔记本热节流。
   - **维度 3 · 工程版本与状态隔离风险**：避免演示时误连正在写入或切换中的实验权重 / 被覆盖的 `artifacts/serve/current.json`；强调现场演示前必须确认无后台训练进程，并核实 `current.json` 指向冻结模型 `exp-20261116-resume500`。
   - **维度 4 · POC 单机操作规程 vs 正式阶段物理隔离**：POC 阶段“训练前停服务、演示前停训练”（双终端只开 `tu serve model` + `tu ui`）；正式阶段通过独立训练节点（RTX 5090 / 云 GPU）与独立推理服务节点（vLLM）物理隔离，权重经版本化产物单向发布（衔接 `research.md` R7、R11、R12）。
6. **`[L7.7]` 可以继续问的问题**：
   - 保留原 `07-serving-demo.md:163-166` 的 4 个问题，再补充 3 个覆盖模型服务、编排流水线与硬件互斥的延展问题（例如：为何 `mlx_lm.server` 的 `LRUPromptCache` 会影响重复评测、为什么 `extract_user_entities` 必须排在超限拦截之前而免责声明要看 `has_citation`、自回归解码为什么是“内存带宽受限”而非“算力受限”以及 vLLM 的 Continuous Batching 如何缓解并发瓶颈）。

#### 5.3 `docs/learning/00-glossary.md` 与 `docs/learning/README.md` 契约

- **`docs/learning/00-glossary.md`（按决策 2A）**：
  - 从 `## 硬件与工具`（原 L92–L94）迁出 3 条：`确定性护栏（Guardrail）`（→ `[L7.1]`）、`会话状态隔离（gr.State）`（→ `[L7.2]`）、`SQLite 线程亲和（check_same_thread）`（→ `[L7.2]`）；
  - 在文件末尾（`## 评测` 之后）新增 `## 推理与演示` 分区，包含上述 3 条 + 新增 5 条（共 8 条）：
    1. `OpenAI 兼容接口` → `[L7.4](./07-serving-demo.md#l74-模型服务与运行时隔离openai-兼容接口currentjson-路由与零外连防线)`
    2. `端点白名单` → `[L7.4](./07-serving-demo.md#l74-模型服务与运行时隔离openai-兼容接口currentjson-路由与零外连防线)`
    3. `动态挂载 Adapter / 权重合并（Fuse）` → `[L7.3](./07-serving-demo.md#l73-基于底座模型加载训练后权重动态挂载-adapter-vs-合并权重fuse)`
    4. `对话编排流水线` → `[L7.5](./07-serving-demo.md#l75-对话编排全链路从一条用户消息到可交付回复的-10-步流水线)`
    5. `内存带宽受限（Memory-Bandwidth Bound）` → `[L7.6](./07-serving-demo.md#l76-为什么训练与演示不能在-m1-pro32gb上同时进行)`
    6. `确定性护栏（Guardrail）` → `[L7.1](./07-serving-demo.md#l71-对话编排层的确定性护栏文章数量控制如何与微调模型协作)`
    7. `会话状态隔离（gr.State）` → `[L7.2](./07-serving-demo.md#l72-本地演示界面的工程边界gradio-6-状态隔离sqlite-跨线程约束与本地隐私护栏)`
    8. `SQLite 线程亲和（check_same_thread）` → `[L7.2](./07-serving-demo.md#l72-本地演示界面的工程边界gradio-6-状态隔离sqlite-跨线程约束与本地隐私护栏)`
- **`docs/learning/README.md`（L18）**：
  - 将第 7 章行更新为：
    `| [07 推理与演示](./07-serving-demo.md) | 模型服务、动态挂载与合并、对话编排 10 步流水线、演示界面与硬件互斥原因（L7.1–L7.7） | ✅ |`

---

### 6. 原子化施工步骤（自底向上，每步可自检）

- **Step 1：前置只读基线核验**
  - 确认工作区干净、只读基线完整：
    ```bash
    git status --short && shasum -a 256 -c artifacts/logs/t075/01/output.sha256 | tail -n 5
    ```
- **Step 2：完善 `docs/learning/07-serving-demo.md`**
  - 按 §5.1–§5.2 更新章首导言与 `## 本章知识点`；原样保留 `[L7.1]`、`[L7.2]`；完成 `[L7.3]` 3 处局部修补；撰写 `[L7.4]`、`[L7.5]`（含 Mermaid `flowchart TD` 流水线图与 V4/V6 对照表）、`[L7.6]`、`[L7.7]`。
  - 本步最小自检：确认标题完整、无 `file://` 绝对路径、无“完整章节由 T073 整理”残留：
    ```bash
    grep -n "^## " docs/learning/07-serving-demo.md && ! grep -nE "file://|完整章节由 T073 整理|~4\.3 GB|约 4\.3 GB" docs/learning/07-serving-demo.md
    ```
- **Step 3：更新 `docs/learning/00-glossary.md`**
  - 按 §5.3（决策 2A）新增 `## 推理与演示` 分区，迁入原 3 条服务/界面术语并增补 5 条新术语（共 8 条），保持全表 Markdown 表格格式统一。
  - 本步最小自检：确认 `## 推理与演示` 存在且无重复术语行：
    ```bash
    grep -n -E "^## |07-serving-demo\.md" docs/learning/00-glossary.md
    ```
- **Step 4：更新 `docs/learning/README.md`**
  - 将第 7 章（L18）更新为 `✅` 与完整简介（保留第 8 章待 `T074` 完成状态不动）。
  - 本步最小自检：
    ```bash
    grep -n "07-serving-demo" docs/learning/README.md
    ```
- **Step 5：编写并运行本地只读确定性核查脚本 + 全量回归门禁**
  - 在 `artifacts/logs/t073/verify_t073.py`（不入 Git）编写只读核查脚本，逐项跑通 §7 确定性核查矩阵，再运行全量回归与只读基线检查。

---

### 7. 确定性核查矩阵与验收门禁

#### 7.1 确定性核查矩阵（写入 `artifacts/logs/t073/verify_t073.py`，逐项打印 `[OK]` / `[FAIL]`）

| 核查项 | 核查对象与方法 | 硬断言底线（禁止弱断言） |
|---|---|---|
| **1. 跨文档链接与 GFM 锚点全检** | 解析 `docs/learning/{README.md,00-glossary.md,07-serving-demo.md}` 中全部 Markdown 相对路径链接与 `#anchor`，按 GitHub GFM 标题 slug 算法校验目标文件与目标标题真实存在 | **0 断链、0 失效锚点**；`07-serving-demo.md` 导航表 7 项与 `00-glossary.md` `## 推理与演示` 全部 8 条术语精确命中目标标题；含 `file://` 绝对路径数为 **0** |
| **2. 既有编号与锚点兼容性** | 校验 `07-serving-demo.md` 仍精确包含原 `[L7.1]`、`[L7.2]`、`[L7.3]` 标题（逐字一致），并新增 `[L7.4]`–`[L7.7]` | 原 3 节标题 100% 逐字匹配；新 4 节标题全部存在且顺序为 `L7.1`–`L7.7`；`docs/learning/README.md` 第 7 章含 `✅` 且不含 `进行中` |
| **3. 源码行号与符号锚点回查** | 对 `07-serving-demo.md` 中所有引用的仓库源码链接（如 `../../src/tu_assistant/cli.py#L395-L440`）核对文件存在、行号不越界且行区间内包含对应函数/类名 | 所有源码路径真实存在，起止行号满足 `1 <= start <= end <= total_lines`，且目标符号（如 `def serve_model`、`def process_turn`、`class ModelClient`、`class ChatUIController`）真实位于对应范围 |
| **4. 关键事实数字回查** | 校验正文出现的关键工程数字与仓库真实基线一致 | `77.04 MB`（7B adapter）、`20.15 MB`（1.5B adapter）、`4.4 GB`（4bit 底座）、`11.5 GB` / `23 GB`（7B 长样本训练峰值）、`4.5 GB`（7B 推理基线）、`35 tok/s`、`83 tok/s`、`500`（`save_every`）、`67`（已确认关联）、`3,809`（条款数）、`91 ms` / `34.1 s` / `6,621` / `163`（T071 实测）全部按口径命中；不再出现 `~4.3 GB`、`约 4.3 GB` 或“完整章节由 T073 整理” |
| **5. Mermaid 语法防雷检查** | 提取 `07-serving-demo.md` 中所有 `mermaid` 代码块 | 至少包含 1 个 `flowchart TD` 代码块；不含 `<br>` 等 HTML 标签；所有带 `(` `)` `：` `/` 的节点文本均使用双引号包裹 |
| **6. 严禁越界与红线检查** | 检查 `git status --porcelain` 与 `git diff --name-only` | 变更文件集合严格是 `{"docs/learning/07-serving-demo.md", "docs/learning/00-glossary.md", "docs/learning/README.md"}` 的子集（收尾前不含其他已跟踪或未跟踪文件）；全文件不含任何从 `inputs/` 复制的法规条文长引语 |

#### 7.2 验收门禁命令清单

```bash
# 1. 文档确定性核查（全部 [OK]，退出码 0）
uv run --offline --no-sync python artifacts/logs/t073/verify_t073.py

# 2. 全量自动化测试与代码风格零回归（须与基线 462 passed, 6 xfailed 完全一致）
uv run --offline --no-sync pytest
uv run --offline --no-sync ruff check src tests

# 3. 历史产物与活跃服务元数据只读保护核验
shasum -a 256 -c artifacts/logs/t075/01/output.sha256
cat artifacts/serve/current.json

# 4. 变更边界核验（仅允许 docs/learning/ 下 3 个文件；严禁改动 src/tests/configs/README.md/tasks.md）
git status --short
git diff --stat
```

---

### 8. 学习文档更新点汇总

- **主文档**：`docs/learning/07-serving-demo.md`（收口完整第 7 章：`[L7.1]`–`[L7.7]`，新增模型服务隔离 `[L7.4]`、编排 10 步全链路 `[L7.5]`、硬件互斥原理 `[L7.6]`、延展提问 `[L7.7]`，并修正 `[L7.3]` 3 处局部瑕疵）；
- **术语表**：`docs/learning/00-glossary.md`（新增 `## 推理与演示` 8 条术语并全量验锚点）；
- **目录索引**：`docs/learning/README.md`（第 7 章标 `✅`）。

---

### 9. 实施方偏差止损规则

- **可自决微调**：段落衔接措辞、表格排版对齐、Mermaid 节点内部 ID 命名、以及本地 `artifacts/logs/t073/verify_t073.py` 的输出格式（不得改变 §5 事实口径与 §7 核查底线）。
- **必须立即停工上报（严禁擅自绕过）**：
  1. 发现正文需要引用的源码符号、行号、配置值或 T071/02-hardware 实测数字与本执行单 §3/§5 不一致；
  2. 核查脚本发现跨文档（如 `05-training.md`、`06-evaluation.md`、`00-glossary.md` 原有条目）存在历史断链且需要修改本任务清单外文件；
  3. 发现任何需要改动 `src/`、`tests/`、`configs/`、`README.md` 或历史产物的情况；
  4. 任何情况下需要读取 `inputs/` 目录下文件内容。

---

## 10. 实施结果与独立复审记录（2026-11-24）

### 10.1 实施摘要（按用户拍板 `1A 2A 3A`）

- **`docs/learning/07-serving-demo.md`**：
  - 升级章首导言并新增 `## 本章知识点` 逻辑阅读导航表（`[L7.4]` → `[L7.3]` → `[L7.5]` → `[L7.1]` → `[L7.2]` → `[L7.6]` → `[L7.7]`）；
  - 原样保留 `[L7.1]`、`[L7.2]` 编号与正文；修补 `[L7.3]` 3 处局部瑕疵（统一 `~4.4 GB` 并补录实测 adapter 体积 `77.04 MB` / `20.15 MB`、本机绝对路径改为相对路径 `../../src/tu_assistant/cli.py#L395-L440`、`05-training.md` 相对链接统一为 `./05-training.md#...`）；
  - 新增 `[L7.4]`（模型服务与运行时三层隔离）、`[L7.5]`（`Assistant` 协议、Mermaid `flowchart TD` 10 步流水线、`tu chat` vs `tu ui` 及 T071 实机延迟对照表）、`[L7.6]`（M1 Pro 32GB 训练与演示互斥四维拆解）、`[L7.7]`（7 道延展提问）。
- **`docs/learning/00-glossary.md`**：从 `## 硬件与工具` 迁出原 3 条服务/界面术语，文末新增 `## 推理与演示` 分区并增补 5 条新术语（共 8 条），全部指向经核验的精确 GFM 锚点。
- **`docs/learning/README.md`**：第 7 章更新为 `✅` 与完整简介（`L7.1–L7.7`），第 8 章保持待 `T074` 完成状态不动。
- **本地只读核查脚本**：`artifacts/logs/t073/verify_t073.py`（`.gitignore` 忽略，不入 Git）。

### 10.2 独立只读复审闭环（`reviewer`，Gemini 4 Neon High，共 2 轮）

- **Round 1（需修改：3 项阻断项 + 2 项非阻断建议）**：
  1. 阻断项 1：`07-serving-demo.md:217, 219` 两处源码行号错位（`session.py#L22-L59` → `#L29-L59`；`assistant.py#L84-L132` → `#L101-L137`）→ **已修复**；
  2. 阻断项 2：`artifacts/logs/t073/verify_t073.py` 存在硬编码漏检与假阳性 `[OK]` 打印 → **已重构**：改为动态提取 `07-serving-demo.md` 全部 17 处 `.py#L...` 链接（16 唯一）并校验符号与非空起始行、`check_mermaid()` 同步覆盖 `{...}` 节点，且全部改为 0 失败才输出 `[OK]`；
  3. 阻断项 3：`07-serving-demo.md` `[L7.6]` 内存账本表合计行原沿用本单 §5.2 第 5 点笔误 `25–28+ GB` 且表头混用“实测”口径 → **已修复**：表头改为 `内存占用（实测 / 估算）` 并逐行标注，合计行修正为 **`约 22.5–28.5+ GB`**（特此订正本单 §5.2 第 5 点原笔误）；
  4. 非阻断建议 1 & 2：`orchestrator.py:147-165` 更新为 `orchestrator.py:147-176` 并补充“真实姓名或单位名”；`save_every: 500` 间隔说明由“约每 30 分钟”更新为“约每 30–50 分钟” → **均已采纳**。
- **Round 2（通过：阻断项 = 0，非阻断建议 = 0）**：
  - 全量门禁独立复跑通过：`verify_t073.py` 退出码 `0`（132 链接 0 断链、0 `file://`、17/17 源码链接与符号校验通过、16/16 必查数字、0 禁用串、Mermaid `[]`/`{}` 校验通过）；
  - `uv run --offline --no-sync pytest`：**462 passed, 6 xfailed**；
  - `uv run --offline --no-sync ruff check src tests`：**All checks passed!**；
  - `shasum -a 256 -c artifacts/logs/t075/01/output.sha256`：**25/25 OK**；`artifacts/serve/current.json` 未变；
  - 两轮复审均比对送审前后 `git diff | shasum -a 256` 确认审查员字节级零修改，且 `specs/001-legal-clause-assistant/tasks.md` 中 `T073` 仍为未勾选 `[ ]`。
