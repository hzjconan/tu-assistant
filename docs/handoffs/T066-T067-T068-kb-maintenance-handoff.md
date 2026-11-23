# T066 + T067 + T068 执行单 · 知识库版本差异、配置化切换与更新闭环验证（Phase 6 / US4）

**状态：已验收完成（2026-11-23）。** 基于主线提交 `f8eb339`（T065 已验收提交，Phase 1–5 除移出 POC 的 T078 外已全部收口）。本执行单面向 Phase 6 / US4（维护和更新法规知识库），将紧密联动的 **T066（`tu kb diff` 版本差异比对）**、**T067（`configs/app.yaml` `kb.version` 配置化加载与接线）** 与 **T068（基于 `tests/fixtures/` 的端到端知识库更新集成测试及 `quickstart.md` 重训风险说明）** 合并为一轮确定性工程交付，一次性收口 US4，并为紧随其后的 Phase 7（`T069` Gradio 演示界面与 `T071` quickstart 全量验证）提供统一的知识库与会话配置加载底座。

> **合规与红线声明**：
> 1. 起草与实施全过程**严禁读取 `inputs/` 目录下任何文件**（包括直接读取、grep 或运行任何输出其内容的脚本）；
> 2. **历史产物只读保护**：严禁修改任何历史知识库（`artifacts/kb/` 下 4 份既有 `.sqlite` 及其 `manifest.json`）、历史数据集、已训权重、历史评测目录及 `artifacts/logs/t075/01/output.sha256` 锁定的 25 项文件；`tu kb diff`、`tu chat`、`tu eval run` 等均以 SQLite 只读模式（`mode=ro`）打开知识库，绝不创建空库或写入任何字节；
> 3. **条款正文不泄漏**：`tu kb diff` 严格遵守“只输出编号与变化类型”，严禁在输出中打印条款原文（`Clause.text`）；
> 4. **运行时隔离**：`chat/`、`runtime/`、`ui/`、`eval/` 持续满足零外部大模型客户端导入约束（`tests/unit/test_runtime_isolation.py`）；
> 5. **收口门禁**：在用户明确确认前，不得勾选 `specs/001-legal-clause-assistant/tasks.md` 中的 T066/T067/T068，不得 `git commit`。

---

## 1. 推荐任务编号与选择理由

**推荐任务：合并推进 `T066 + T067 + T068`（Phase 6 / US4 法规知识库维护与更新整体收口）。**

- **T066 `[P] [US4]`**：实现 `tu kb diff <v1> <v2>` 于 `src/tu_assistant/kb/diff.py`：列出新增、删除、原文变化的条款（只输出编号与变化类型）；
- **T067 `[US4]`**：在 `configs/app.yaml` 中完善 `kb.version` 生效链路，编排层与出处校验层按配置加载指定知识库版本，切换版本无需修改代码（FR-004）；
- **T068 `[US4]`**：用 `tests/fixtures/` 样例验证“修改条款 → 重新入库 → 校验层使用新原文”流程，写入 `tests/integration/test_kb_update.py`；在 `quickstart.md` 中补充“知识更新需重训”的说明（research R1 风险）。

### 1.1 为什么优先推进 Phase 6（US4），而不是直接跳到 Phase 7？

1. **顺接项目主线，彻底关门全部业务用户故事（US1–US4）**：
   - `T065` 已于 `f8eb339` 验收完成，Phase 1–5 除明确移出 POC 的 `T078` 外已全部清零；
   - Phase 6（US4）是最后一个尚未实现的功能故事，完成后即进入纯演示与收尾阶段（Phase 7）。
2. **为 `T069`（Gradio UI）先铺好统一配置加载底座，避免返工**：
   - 核对源码发现，`src/tu_assistant/ui/` 目前为空目录；即将实现的 `tu ui` 需要从 `configs/app.yaml` 读取 `runtime.*`、`session.*` 与 `kb.version` 初始化 `TrainedAssistant`。先落地 `T067` 的统一配置解析与 `TrainedAssistant.from_config(...)`，`tu chat`、`tu eval run` 与 `tu ui` 可一次性共享同一套无重复接线，不必写完 UI 再回头补 `kb.version`。
3. **为 `T071`（运行 quickstart V1–V7）与 `T074`（复盘文档）补齐前置内容**：
   - `T068` 要求在 `quickstart.md` 补充知识更新验证与 R1 重训风险说明，应在 `T071` 执行全量验证之前就位。

### 1.2 为什么推荐合并 `T066 + T067 + T068` 为一个逻辑组，而非拆成三次交付？

- **三项任务天然构成一条不可割裂的端到端闭环**：
  - `T066` 解决“更新后改了哪些条款”（变更可观测）；
  - `T067` 解决“如何不改代码切换知识库版本”（配置驱动生效）；
  - `T068` 则是用 `tests/fixtures/` 把 `import` → `diff`（T066）→ 改 `app.yaml` 切换 `kb.version`（T067）→ `citation/verify` & `chat/orchestrator` 交付新原文串起来的端到端集成测试与说明。
- **工作量适中且 100% 确定性，契合既往合并惯例**：
  - 摸底发现 `configs/app.yaml` 已预留 `kb.version: null`，`T067` 实为补齐统一加载器与修复 `cli.py` 忽略配置的缺口（约 80–120 行代码）；`T066`（`kb/diff.py` + CLI）约 180–220 行；`T068` 为集成测试与 `quickstart.md` 补充。三项合计体量与先前成功合并验收的 `T061 + T063`、`T054 + T055` 相当，且完全不依赖外部 API、GPU 推理或人工审题，可在单轮独立复审闭环内高质量收口。
  - 若用户更倾向严格单任务推进，第 6 节决策 1 提供“先单做 `T066`”的备选方案。

### 1.3 与其他未完成候选任务的横向对比

| 候选任务 | 当前状态与前置条件 | 优先级判断 |
|---|---|---|
| **`T066 + T067 + T068`（推荐）** | Phase 6 全部 3 项，前置依赖（Phase 2 知识库与校验层）已完备；`kb/diff.py` 与 `test_kb_update.py` 尚未创建，`configs/app.yaml` 已预留 `kb.version: null` 但代码未接入 | **最优下一步**：纯确定性工程，一次收口 US4，并为 `T069`/`T071` 扫清配置与文档前置 |
| **`T066` 单做** | `[P]` 任务，可完全独立 | 可行，但会导致 `T067` 过小且 `T068` 需等第三次执行单与复审闭环；合并推进更高效（见决策 1） |
| **`T069`（Gradio 演示界面 `tu ui`）** | `src/tu_assistant/ui/` 当前仅空 `__init__.py` | 应复用 `T067` 的 `TrainedAssistant.from_config(...)` 统一读取 `kb.version` 与 `session.*`，先做 Phase 6 更顺滑 |
| **`T070`（演示场景脚本 `docs/demo-scenarios.md`）** | 依赖可用模型与 UI 演示流程 | 待 `T069` UI 界面形态确定后编写，可与 UI 操作步骤精确对齐 |
| **`T071`（跑 quickstart V1–V7）** | 依赖 `T068` 补充 quickstart 及 `T069`（V6）就绪 | 当前缺少 V6 界面与 US4 说明，尚不具备运行条件 |
| **`T072` / `T073` / `T074`（README 与第 7、8 章学习文档）** | 收尾类文档 | 需在 `T066–T071` 全部完成后统一汇总真实命令、界面与验证记录 |
| **`T078`** | 已标记 `[Post-POC / 正式阶段]` | 2026-11-19 经用户确认移出 POC 范围，不纳入候选 |

---

## 2. 现状与只读摸底核实

以下所有代码行号、表结构、配置文件与 4 份历史知识库统计均经仓库只读核实（未触碰 `inputs/`，未打印任何项目法规原文）：

### 2.1 代码与测试基线

- **Git 基线**：`HEAD = f8eb339`（`docs(T065): complete 06-evaluation learning chapter and glossary`），工作区干净；
- **测试与检查基线**：全量 `uv run pytest` **421 passed / 6 xfailed**，`uv run ruff check src tests` 全绿，`shasum -a 256 -c artifacts/logs/t075/01/output.sha256` **25/25 OK**；
- **测试样例夹具（`tests/fixtures/`）**：仅含两份自行编写的公开示例文本（不取自 `inputs/`）：
  - `tests/fixtures/law_sample.txt`（《示例工会法》，`2020年1月1日通过`，含第 1、2、3（含 2 项）、4、6、8、9（含 2 项）条，自带条号缺口第 5、7 条）；
  - `tests/fixtures/notice_sample.txt`（《关于做好工会工作的通知》，一、二（含 2 项）、三分段）。

### 2.2 仓库内 4 份真实历史知识库元数据与版本演变（只读核查）

经只读连接（`mode=ro`）核查 `artifacts/kb/kb-*.sqlite` 表结构（`legal_documents`、`clauses`、`clause_relations`、`kb_meta`）及聚合统计：

| 知识库版本 | 文档数（全为 `current`） | 条款行数 | 已确认关联数 | 相对前一版本的真实差异（只统计哈希与计数） |
|---|---:|---:|---:|---|
| `kb-20261113-071600` | 26 | 5,953 | 0 | 初始全量导入 |
| `kb-20261113-091537` | 25 | 3,817 | 35 | 删除 1 篇（《民法典》，`-2,136` 条）；新增 `0` / 原文变化 `0` |
| `kb-20261113-093057` | 24 | 3,809 | 35 | 删除 1 篇（社保衔接通知，`-8` 条）；新增 `0` / 原文变化 `0` |
| `kb-20261119-045641`（当前活跃） | 24 | 3,809 | 67 | 从 `093057` 派生：新增 `0` / 删除 `0` / 原文变化 `0`；**仅 `number_text` 变化 `1,026` 行**（T077 多款第 1 款显式标注）；已确认关联 `35 → 67`（`+42 / -10`，保留 `25`） |

> **关键洞察**：相邻真实版本既有“删整篇法规”（`071600 → 091537 → 093057`），也有“原文零变化但 `number_text` 与 `clause_relations` 大幅变化”（`093057 → 045641`）。这直接决定了 `kb/diff.py` 不能把 `number_text` 误判为“原文变化”，同时应在摘要中呈现编号写法与已确认关联的变动，便于维护者看清派生库的实际变化。

### 2.3 摸底发现的 5 处关键源码现状与隐蔽缺陷

1. **`configs/app.yaml` 已预留 `kb.version: null`，但运行时与评测 CLI 完全未读取**：
   - `configs/app.yaml:16-17` 已写明：`kb: { version: null }`；
   - `src/tu_assistant/cli.py:1044-1049`（`tu eval run`）与 `cli.py:1322-1327`（`tu chat`）均已调用 `cfg = load_app_config(config)`，却硬编码为 `Path(artifacts, "kb", f"{kb_version}.sqlite") if kb_version else _latest_kb(artifacts)`，导致修改 `configs/app.yaml` 中的 `kb.version` **完全不生效**；
   - 同时 `configs/app.yaml:19-20` 的 `paths.artifacts: "artifacts"` 在 CLI 中也未作为默认值回退。
2. **`store.py:297` `open_kb(path)` 存在静默建空库陷阱**：
   - 当前实现为 `return sqlite3.connect(Path(path))`；若用户把 `kb.version` 或 `--kb-version` 写错一个字符，`sqlite3.connect` 会**静默在 `artifacts/kb/` 下创建一个 0 字节空 `.sqlite` 文件**，后续查询才报 `sqlite3.OperationalError: no such table`，既污染目录又难以排错。
3. **`ingest.py:136` 秒级版本号在连续入库时会撞名崩溃**：
   - `new_kb_version()` 精度为秒（`kb-%Y%m%d-%H%M%S`），且 `import_directory` 不接受自定义 `kb_version` 参数也未检查目标文件是否存在；若在 1 秒内连续两次入库（如 `T068` 集成测试先导 v1 再导 v2），第二次 `create_kb(kb_path)` 会直接撞到已有文件并抛出 `table legal_documents already exists`！
4. **`doc_id` 含 `version_label` 哈希，纯按 `clause_id` 做 diff 会误报整法删增**：
   - `store.py:76` 定义 `doc_id = sha256(f"{title}|{version_label}")[:16]`，`clause_id = f"{doc_id}:a{article_no}[:p{paragraph_no}][:i{item_no}]"`；
   - 当一部 50 条的法规因修正而更新 `version_label`（如 `2020年通过` → `2024年修正`），即使只改了 1 条，全部 50 个 `clause_id` 都会变。若 `kb/diff.py` 仅按 `clause_id` 集合差比对，会报“删除 50 条 + 新增 50 条、原文变化 0 条”，违背法务维护直觉；
   - 相反，SQLite 已有唯一约束 `one_current_per_title`（`legal_documents(title) WHERE status = 'current'`）与 `uniq_clause_no`（`doc_id, article_no, ifnull(paragraph_no, -1), ifnull(item_no, -1)`），对全部 `status='current'` 文档，**`(title, article_no, paragraph_no, item_no)` 是数学上严格唯一的逻辑键**。
5. **编排层与出处校验层缺少配置化入口**：
   - `TrainedAssistant`（`chat/assistant.py:50`）与 `verify_output`（`citation/verify.py:143`）目前只接收外部已打开的 `sqlite3.Connection`，缺少按 `configs/app.yaml` 加载指定 KB 的工厂/辅助入口，不便于 `tu chat`、未来 `tu ui`（T069）与集成测试（T068）统一复用。

---

## 3. 实施边界与核心设计

### 3.1 文件变更边界

| 文件路径 | 操作 | 职责 |
|---|---|---|
| `src/tu_assistant/kb/diff.py` | **新增** | **T066**：只读加载两份知识库、按现行逻辑键比对条款新增/删除/原文变化、统计文档与编号写法/关联元信息变化、渲染“只含编号与变化类型”的确定性文本报告 |
| `src/tu_assistant/kb/store.py` | **修改** | **T067**：新增 `KBError`、安全校验的 `latest_kb_path` / `resolve_kb_path` / `open_kb_from_config`，为 `open_kb` 增补存在性检查与可选 `read_only=True` 只读模式（保留 `create_kb` 建库语义不变） |
| `src/tu_assistant/kb/ingest.py` | **修改** | 为 `import_directory` 增加可选 `kb_version: str | None = None` 及自动生成版本号的防同秒撞名保护（已有同名文件时追加 `-01` / `-02` 或显式传重名抛 `FileExistsError`），防止误覆盖旧库 |
| `src/tu_assistant/citation/verify.py` | **修改** | **T067**：保留 `verify_output(text, conn)` 原签名零变更；新增 `verify_output_from_config(text, config_path=..., *, kb_version=None, artifacts_dir=None, overrides=None)`，按配置加载指定 KB 并自动关闭连接 |
| `src/tu_assistant/chat/assistant.py` | **修改** | **T067**：保留 `TrainedAssistant(client, kb_conn, ...)` 原签名零变更；新增 `TrainedAssistant.from_config(...)` 工厂方法、`session_config_from(cfg)`、`kb_version`/`kb_path` 只读属性、`close_kb()` 与上下文管理器（仅关闭自身管理的连接） |
| `src/tu_assistant/config.py` | **修改** | **T067**：新增共享 `resolve_model_name(cfg, artifacts_dir)`（当 `runtime.model_name` 为 `default` 时读取 `artifacts/serve/current.json`），供 `TrainedAssistant.from_config` 与 CLI 共用 |
| `src/tu_assistant/eval/runner.py`、`eval/compare.py` | **修改** | **T067**：`run_eval` 与 `load_doc_index` 统一改为 `open_kb(..., read_only=True)` 只读打开；`compare.py` 内原 `resolve_kb_path(manifest, artifacts_dir)` 重命名为 `_kb_path_from_manifest` 消除同名歧义 |
| `src/tu_assistant/cli.py` | **修改** | **T066 + T067**：① 新增 `tu kb diff <v1> <v2>` 子命令（走 `diff_kbs`/`resolve_diff_kb`）；② `tu chat` 生产路径直接调用 `TrainedAssistant.from_config(...)` 与 `session_config_from(cfg)`，并在 `finally` 中调用 `close_cb()`（同时保留 `if hasattr(TrainedAssistant, "from_config")` 的 `else` 回退分支以零改动兼容 monkeypatch 无 `from_config` 替身的旧单测），`tu eval run` 接入 `_resolve_cli_kb` 与 `session_config_from`；③ `cli._model_name` 改为对 `config.resolve_model_name` 的薄委托；④ `tu kb list/show/lookup/relations extract/relations review`、`tu synth evalcases/sft`、`tu eval cases review` 全部走 `_resolve_cli_kb` + 只读打开，消除静默建空库风险 |
| `configs/app.yaml` | **微调注释（按决策 3）** | 保持 `kb.version: null`（默认取最新），补充清晰注释说明配置具体版本号即可无代码切换、命令行 `--kb-version` 可覆盖 |
| `specs/001-legal-clause-assistant/quickstart.md` | **修改** | **T068**：保持 V1–V7 编号不变，新增「知识库更新与版本切换（US4）」小节及 **research R1“知识更新需重训”风险说明** |
| `specs/001-legal-clause-assistant/contracts/cli.md` | **按决策 4 微调** | 在「知识库」命令表中补录 `tu kb diff <v1> <v2>` 一行 |
| `tests/unit/test_kb_diff.py` | **新增** | **T066** 单元测试：新增/删除/原文变化、跨版本号修订、`number_text` 变化不误判、已确认关联变化、反泄漏断言（不含原文）、错误路径与只读零改动校验、CLI 退出码 |
| `tests/unit/test_kb_config.py` | **新增** | **T067** 单元测试：`kb.version` 优先级（CLI > YAML > latest）、`paths.artifacts` 回退、非法版本名与路径穿越拦截、不存在版本不生成空 `.sqlite`、`verify_output_from_config`、`TrainedAssistant.from_config` 与 `tu chat`/`tu eval run` CLI 透传 |
| `tests/integration/test_kb_update.py` | **新增** | **T068** 集成测试：以 `tests/fixtures/` 端到端验证“改条/增条/删条/升版本号 → 重导 → `kb diff` → 改 `app.yaml` 切换版本 → 校验层与编排层生效” |
| `docs/learning/03-knowledge-base.md`、`00-glossary.md` | **修改** | 增补 `[L3.3.1]` 学习小节与 2 条术语（附锚点链接） |

**明确不做（防越界）**：
- 不触碰 `inputs/`，不修改 `artifacts/kb/` 下的 4 份历史 `.sqlite` 或任何历史 `manifest.json` / `eval` / `train` / `datasets` 产物；
- 不实现增量入库（`research.md` R8/R12 明确 POC 采用整批重导，增量更新留到正式阶段）；
- 不修改 `citation/verify.py` 的四态判定规则、不修改 `chat/orchestrator.py` 的提示词/脱敏/篇数逻辑、不修改 `eval/` 任何指标或对比口径；
- 不提前实现 `T069`（`src/tu_assistant/ui/` 保持不动）。

---

### 3.2 T066 核心设计：`src/tu_assistant/kb/diff.py` 与 `tu kb diff <v1> <v2>`

1. **输入定位与只读打开**：
   - `resolve_diff_kb(ref: str | Path, artifacts_dir: str | Path = "artifacts") -> Path`：
     - 若 `ref` 是指向现有文件的路径（如直接传 `path/to/foo.sqlite`），直接使用；
     - 否则将其视为 `kb_version` 名称，做安全校验（禁止空串、首尾空白、`.`、`..`、`/`、`\`），解析为 `Path(artifacts_dir) / "kb" / f"{ref}.sqlite"`；
     - 文件不存在则抛出 `KBError`（CLI 返回退出码 `2`），**绝不调用普通 `sqlite3.connect` 导致建空文件**。
   - 打开方式：`sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)`，并检查 `legal_documents`、`clauses`、`clause_relations` 三张必需表均存在（否则报 `KBError`，退出码 `2`）。
2. **比对口径（对应决策 2 推荐项 A）**：
   - **默认比对范围**：两库中全部 `status='current'` 的法律文件（与 `spec.md` FR-008“默认依据现行有效版本”一致）；若任一库还存在非 `current`（`amended` / `repealed`）文档，在结果结构与报告头部记录 `non_current_docs` 计数提示（不与现行条款混排造成噪音）。
   - **唯一逻辑匹配键**：`ClauseKey = tuple[str, int, int | None, int | None]`，即 `(doc.title, clause.article_no, clause.paragraph_no, clause.item_no)`。
     - 由 SQLite 索引 `one_current_per_title` + `uniq_clause_no` 保证同库内严格唯一；
     - 即使某部法规经修订导致 `version_label` 与 `doc_id` 变更，仍能逐条精准对齐，只把真正改了原文的条款标为 `modified`，并在 `doc_changes` 中记录 `version_changed: title (v1_label → v2_label)`。
   - **严格三类条款变化**（数据结构 `ClauseDiffItem`）：
     - `added`（`+` 新增）：仅在 `v2` 存在的逻辑键；
     - `removed`（`-` 删除）：仅在 `v1` 存在的逻辑键；
     - `modified`（`~` 原文变化）：两库均存在且 `c1.text != c2.text`（精确逐字比对，不做模糊语义判断）。
     - 每条 `ClauseDiffItem` 仅存标识字段：`change_type`、`title`、`article_no`、`paragraph_no`、`item_no`、`number_text_v1`、`number_text_v2`、`clause_id_v1`、`clause_id_v2`、`version_label_v1`、`version_label_v2`——**数据结构本身就不保存条款正文 `text`**，从源头杜绝原文泄漏！
   - **辅助元信息统计（不混入 `modified`）**：
     - `doc_changes`：新增文件列表、删除文件列表、版本标签变更列表；
     - `number_text_changed_count`：原文未变但 `number_text` 变化的条款数（如 T077 派生库 `093057 → 045641` 的 `1,026` 条）；
     - `relations_diff`：已确认条款关联（`confirmed=1`）的变化统计（按现行逻辑端点或 `(from_key, to_key, relation_type)` 对齐：`v1_count`、`v2_count`、`added`、`removed`，对 `093057 → 045641` 精确产出 `35 → 67 (+42 / -10)`）。
3. **确定性排序与渲染格式（严禁输出正文）**：
   - 排序键：`(title, article_no, paragraph_no or 0, item_no or 0)`；
   - CLI 命令：`tu kb diff <v1> <v2> [--artifacts artifacts] [--summary-only]`
     - 默认输出头部汇总（版本、文档数、条款新增/删除/原文变化计数、文档变更、编号写法变化与已确认关联变化）+ 逐条清单（例如 `[~ 原文变化] 《示例工会法》第四条 (clause_id=...)`、`[+ 新增] ...`、`[- 删除] ...`）；
     - `--summary-only` 仅输出汇总与文件级变化（便于对比删整部《民法典》这类上千条差异时快速浏览）；
     - 退出码：正常完成（无论有无差异）均返回 `0`；输入错误/文件缺失/损坏库返回 `2`（与 `tu eval report` / `tu eval compare` 保持一致）。

---

### 3.3 T067 核心设计：统一 `kb.version` 解析与配置化加载

1. **统一解析函数（`src/tu_assistant/kb/store.py`）**：
   - 新增异常类 `class KBError(ValueError): pass`（便于与 `ReportError` / `CompareError` 风格统一，CLI 统一捕获并以退出码 `2` 报错）。
   - `_validate_kb_version(version: Any) -> str`：
     - 必须是非空字符串（拦截 YAML 误配 `int`/`bool`/`list`），去首尾空白后不得为空，不得包含 `/`、`\`、`..` 或等于 `.`；
   - `latest_kb_path(artifacts_dir: str | Path = "artifacts") -> Path`：
     - 查找 `Path(artifacts_dir) / "kb"` 下 `kb-*.sqlite`，按文件名排序取最新；不存在时抛 `KBError("未找到任何知识库版本，请先运行 tu kb import")`。
   - `resolve_kb_path(kb_version: str | None = None, *, config: dict | None = None, config_path: str | Path | None = None, artifacts_dir: str | Path | None = None) -> Path`：
     - 确定 `cfg`：若传入 `config` 用之；否则若传入 `config_path` 则调用 `load_app_config(config_path)`；否则为空字典 `{}`；
     - 确定 `eff_artifacts`：显式 `artifacts_dir`（非 `None`）优先 > `get(cfg, "paths.artifacts", "artifacts")`；
     - 确定 `eff_version`：显式 `kb_version`（非 `None`）优先 > `get(cfg, "kb.version")`；
     - 若 `eff_version is None`：调用 `latest_kb_path(eff_artifacts)`；
     - 否则：先 `_validate_kb_version(eff_version)`，构造 `p = Path(eff_artifacts) / "kb" / f"{eff_version}.sqlite"`，若 `not p.is_file()` 抛 `KBError(f"知识库版本不存在：{eff_version}（未找到 {p}）")`；
     - 返回 `p`。
   - `open_kb(path: str | Path, *, read_only: bool = False) -> sqlite3.Connection`：
     - 当 `str(path) != ":memory:"` 时，先检查 `Path(path).is_file()`，缺失时抛 `KBError(f"知识库文件不存在：{path}")`（彻底消灭静默创建 0 字节空库隐患；注：所有建库流程均走 `create_kb`，全仓库经 grep 核实无任何调用方依赖 `open_kb` 创建新库）；
     - `read_only=True` 时以 `sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)` 打开。
   - `open_kb_from_config(config_path: str | Path = DEFAULT_APP_CONFIG, *, kb_version: str | None = None, artifacts_dir: str | Path | None = None, overrides: dict | None = None, read_only: bool = True) -> tuple[sqlite3.Connection, Path]`：
     - 一站式加载 `app.yaml` + `overrides` → `resolve_kb_path` → `open_kb(path, read_only=read_only)`，返回 `(conn, kb_path)`。
2. **出处校验层接入（`src/tu_assistant/citation/verify.py`）**：
   - 保持 `verify_output(text: str, conn: sqlite3.Connection) -> VerifyResult` 零改动；
   - 新增 `verify_output_from_config(text: str, config_path: str | Path = DEFAULT_APP_CONFIG, *, kb_version: str | None = None, artifacts_dir: str | Path | None = None, overrides: dict | None = None) -> VerifyResult`，内部调用 `open_kb_from_config(..., read_only=True)` 并在 `finally` 中安全关闭连接。
3. **编排/助手层接入（`src/tu_assistant/chat/assistant.py`）**：
   - 保持 `TrainedAssistant(client, kb_conn, ...)` 零改动；
   - 新增类方法 `TrainedAssistant.from_config(config_path: str | Path = DEFAULT_APP_CONFIG, *, client: ModelClient | None = None, kb_version: str | None = None, artifacts_dir: str | Path | None = None, overrides: dict | None = None, eval_mode: bool = False, temperature: float = 0.7) -> TrainedAssistant`：
     - 读取 `app.yaml`（支持 `overrides`）→ 解析并只读打开指定 KB（标记 `_owns_kb = True`，记录 `self.kb_path` 与 `self.kb_version`）；
     - 若未传入 `client`，按 `runtime.model_endpoint` / `runtime.allowed_hosts` / `runtime.model_name`（复用 `current.json` 解析）创建 `ModelClient`（仍严格经过白名单检查！）；
     - 提供 `close_kb()` 与 `__enter__`/`__exit__`：仅当 `_owns_kb` 为真时关闭内部连接，避免误关测试或外部注入的连接。
4. **CLI 接线（`src/tu_assistant/cli.py`）**：
   - `tu chat` 与 `tu eval run`：将 `artifacts` 默认改为 `None`（未显式传 `--artifacts` 时回退到 `app.yaml` 的 `paths.artifacts`，再兜底 `"artifacts"`），通过 `resolve_kb_path(kb_version, config=cfg, artifacts_dir=artifacts)` 解析知识库；捕获 `KBError` 打印红色错误到 `stderr` 并以退出码 `2` 退出；`tu chat` 进入对话时顺带显示当前加载的 `kb_version`（如 `知识库：kb-20261119-045641`），便于用户直观确认版本切换生效；
   - `tu kb list/show/lookup` 等离线维护命令：按决策 3 推荐项，保持 `--kb-version` / 最新（不隐式读工作区根目录 `configs/app.yaml`，避免干扰测试与多目录操作），但同样改用 `resolve_kb_path` + `open_kb(..., read_only=True)`，消除静默建空库风险。
5. **`ingest.py` 防同秒撞名修复**：
   - `import_directory(input_dir, artifacts_dir="artifacts", *, kb_version: str | None = None)`：
     - 若显式传入 `kb_version`：校验合法性，若目标 `.sqlite` 已存在则抛 `FileExistsError`；
     - 若未传入：生成 `base = new_kb_version()`；若 `kb_dir / f"{base}.sqlite"` 已存在，依次尝试 `f"{base}-01"`、`f"{base}-02"`… 直到找到空闲版本号，确保连续入库永不覆盖旧库、永不撞表崩溃。

---

### 3.4 T068 核心设计：端到端更新集成测试与 `quickstart.md` 补充

1. **集成测试 `tests/integration/test_kb_update.py`（全确定性、零模型推理、零读取 `inputs/`）**：
   - 测试素材仅从 `tests/fixtures/law_sample.txt` 与 `tests/fixtures/notice_sample.txt` 复制到 `tmp_path` 后按场景编辑：
     - **场景 1（同版本标签改条 + 增条 + 删条 + `kb diff` 反原文泄漏）**：
       - `v1` 导入原始 `law_sample.txt` + `notice_sample.txt`；
       - `v2` 修改《示例工会法》第四条原文（增加“以任何形式”）、新增第十条、删除第六条，重新调用 `import_directory` 生成 `v2`；
       - 验证 `diff_kbs(v1, v2)` 准确识别：第四条 `modified`、第十条 `added`、第六条 `removed`，其余条款不变；
       - 验证 `render_diff(result)` 及 `tu kb diff` CLI 输出仅含编号与变化类型，**断言旧原文与新原文子串均未出现在输出中**。
     - **场景 2（改 `app.yaml` 切换 `kb.version`，零代码改动，校验层与编排层立即使用新原文）**：
       - 写临时 `app.yaml` 指定 `kb.version: <v1>`，用确定性 stub `ModelClient`（固定输出引用《示例工会法》第四条 **v1 旧原文**，模拟未重训模型）：
         - `verify_output_from_config` 与 `TrainedAssistant.from_config` 下，第四条判定为 `ok`，交付 v1 原文；
       - 仅修改 `app.yaml` 的 `kb.version: <v2>`（零代码改动），再次运行同一 stub 客户端与完全相同的查询：
         - `verify_output_from_config` 与 `TrainedAssistant.from_config` 下，第四条判定为 `corrected`，**交付文本自动替换为 v2 新原文**，旧原文不再出现！
       - 再将 `app.yaml` 设为 `kb.version: null`，确认自动加载最新 `v2` 并交付新原文。
     - **场景 3（删除条款后校验层拦截）**：
       - 同一 stub 模型仍引用已在 `v2` 删除的第六条 → 切到 `v2` 后 `verdict == "not_found"`，引用块被替换为 `〔此处引用未通过校验，已删除〕`。
     - **场景 4（法规修订升级 `version_label`：`2020年1月1日通过` → `2024年6月1日修正`）**：
       - 修改文件头日期为 `2024年6月1日修正` 并仅微调第四条原文，重导为 `v3`；
       - 验证 `diff_kbs(v1, v3)` 仅报第四条 `modified`（不会误报全法删除 + 新增），且 `doc_changes` 准确记录《示例工会法》版本变更；
       - 模型仍按旧 `2020-01-01` 版本标签与旧原文引用第四条 → 切到 `v3` 后，校验层自动兜底现行 `2024-06-01` 版本、修正标记版本并替换为 `v3` 新原文（`verdict == "corrected"`）。
     - **场景 5（错误防线与历史库只读保护）**：
       - `app.yaml` 配置不存在的 `kb.version` → 报 `KBError` 且磁盘上未创建空 `.sqlite`；
       - 整个测试流程结束后，`v1.sqlite` 的 SHA-256 哈希与入库时完全一致。
2. **`specs/001-legal-clause-assistant/quickstart.md` 补充**：
   - 保持现有 `V1`–`V7` 章节标题与编号零改动；
   - 新增「知识库更新与版本切换（US4）」小节，给出标准操作命令：
     ```bash
     uv run tu kb import <新文档目录>
     uv run tu kb diff <旧kb_version> <新kb_version>
     # 在 configs/app.yaml 中设置 kb.version（或保留 null 自动使用最新）
     uv run pytest tests/integration/test_kb_update.py
     ```
   - 明确写入 **“知识更新需重训（research R1 风险）”** 警示块：
     - **立即生效的部分（校验层）**：切换 `kb.version` 后，已修改条款的原文会被自动纠正为新原文，已删除条款会被立即拦截删除；
     - **不会自动生效的部分（模型参数记忆）**：因 POC 采用“SFT 参数记忆 + 推理时不检索”路线（R1），仅更新知识库不会改变模型权重——新增条款模型无法主动识别引出，修改后的适用条件或废止逻辑模型仍可能按旧记忆错选条号；
     - **完整生效链路**：实质性增删改法规后，须重新抽取并确认关联（按需）→ `tu synth sft --kb-version <新版本>` → `tu train` → `tu eval run` 回归评测（对应 spec SC-014）。

---

## 4. 具体实施步骤与确定性验收方法

### 4.1 实施步骤（待用户拍板后执行）

1. **步骤 1（`store.py` & `ingest.py`）**：在 `src/tu_assistant/kb/store.py` 落地 `KBError`、`latest_kb_path`、`resolve_kb_path`、`open_kb(..., read_only=...)`、`open_kb_from_config`；在 `src/tu_assistant/kb/ingest.py` 为 `import_directory` 补齐可选 `kb_version` 与防同秒撞名保护。
2. **步骤 2（`kb/diff.py`）**：实现只读加载、现行逻辑键对齐、条款三分法差异、文档/编号写法/关联元信息摘要与纯编号渲染器（无正文泄漏）。
3. **步骤 3（`citation/verify.py` & `chat/assistant.py`）**：新增 `verify_output_from_config` 与 `TrainedAssistant.from_config`（含只读属性与连接生命周期管理），原签名与行为保持 100% 兼容。
4. **步骤 4（`cli.py` & `configs/app.yaml`）**：注册 `tu kb diff <v1> <v2>`；将 `tu chat`、`tu eval run` 接入 `resolve_kb_path`（读取 `configs/app.yaml` `kb.version` 与 `paths.artifacts`，命令行覆盖优先）；完善 `configs/app.yaml` 注释；按决策 4 同步 `contracts/cli.md`。
5. **步骤 5（测试编写）**：新增 `tests/unit/test_kb_diff.py`、`tests/unit/test_kb_config.py` 与 `tests/integration/test_kb_update.py`，全部使用内存库或 `tmp_path` + `tests/fixtures/`，零依赖外部服务与真实 `inputs/`。
6. **步骤 6（文档更新）**：更新 `specs/001-legal-clause-assistant/quickstart.md`、`docs/learning/03-knowledge-base.md`（新增 `[L3.3.1]`）与 `docs/learning/00-glossary.md`（新增 2 条术语并核查锚点）。
7. **步骤 7（回归、只读真实抽验与独立复审闭环）**：运行全量确定性验收命令，进入 `.agents/skills/task-review-loop/SKILL.md` 独立只读复审闭环（最多 5 轮），完成后向用户汇报。

### 4.2 确定性验收标准与命令

| 验收维度 | 验收命令 / 检查项 | 确定性通过标准 |
|---|---|---|
| **新增单元与集成测试** | `uv run pytest tests/unit/test_kb_diff.py tests/unit/test_kb_config.py tests/integration/test_kb_update.py` | 全部 PASS；覆盖新增/删除/原文变化、跨版本标签修订、反原文泄漏、`kb.version` 优先级与切换、空库防创建、只读零改动 |
| **全量自动化回归** | `uv run pytest` | 在既有 `421 passed / 6 xfailed` 基础上全绿无新增失败；含 `tests/unit/test_runtime_isolation.py`（V7 运行时隔离）与 `tests/integration/test_citation_verify.py`（V3） |
| **代码规范检查** | `uv run ruff check src tests` | 0 warnings / 0 errors |
| **真实历史 KB 只读抽验（不输出正文）** | `uv run tu kb diff kb-20261113-071600 kb-20261113-091537 --summary-only`<br>`uv run tu kb diff kb-20261113-091537 kb-20261113-093057`<br>`uv run tu kb diff kb-20261113-093057 kb-20261119-045641` | 分别精确吻合：`删除 2136 / 新增 0 / 原文变化 0`、`删除 8 / 新增 0 / 原文变化 0`、`新增 0 / 删除 0 / 原文变化 0` 且提示 `编号写法变化 1026 条` 与 `已确认关联 35 → 67（+42 / -10）`；输出中不包含任何条文正文 |
| **历史产物只读完好性** | 实施前后对比 4 份 `artifacts/kb/kb-*.sqlite` 的 `shasum -a 256`；执行 `shasum -a 256 -c artifacts/logs/t075/01/output.sha256` | 4 份历史 KB 哈希 100% 不变；`output.sha256` **25/25 OK** |
| **合规边界复核** | `git status --short` 与 `git diff --stat` | 仅包含 §3.1 表格允许文件；未读/未改 `inputs/`，未引入外部客户端到运行时模块 |

---

## 5. 学习文档更新点

1. **`docs/learning/03-knowledge-base.md`**：
   - 在 `## L3.3 知识库版本与 SQLite` 后新增 **`### [L3.3.1] 知识库更新、版本差异比对与“校验生效 vs 参数重训”的边界`**（并同步更新章首 `## 本章知识点` 导航）：
     - 为什么 `kb diff` 用“现行文件标题 + 条款项号”逻辑键对齐而不是直接按 `clause_id` 对比（结合 `doc_id` 哈希机制与法规修订场景）；
     - 为什么 `kb diff` 严格只输出编号与变化类型、且把 `number_text` / 关联变化单列在摘要中（结合真实 `kb-20261113-093057 → kb-20261119-045641` 实测数字）；
     - 配置化切换 `kb.version` 如何实现“零改代码切库”以及 `open_kb` 防静默建空库工程细节；
     - **核心认知**：SFT 参数化路线下，更新知识库只能让出处校验层立刻生效（改旧文、拦删条），但模型参数记忆不会自动更新，新条款识别与适用逻辑变更必须重训（衔接 R1 与正式阶段 RAG 对照动机）。
2. **`docs/learning/00-glossary.md`**：
   - 在 `## 训练数据` 末尾（与 `[L3.4.1]` 既有 3 条知识库术语保持同组）新增 2 条术语，并验证锚点有效：
     - `知识库版本差异（KB Diff）` → 链接至 `[L3.3.1](./03-knowledge-base.md#l331-...)`；
     - `知识更新与参数滞后` → 链接至 `[L3.3.1](./03-knowledge-base.md#l331-...)`。

---

## 6. 待用户拍板的决策清单

请逐项确认以下 4 个设计决策（均可直接回复编号如 `1A 2A 3A 4A`，或提出修改意见）：

### 决策 1：本次实施的任务粒度
- **选项 A（推荐）：合并推进 `T066 + T067 + T068`（Phase 6 / US4 整体收口）**
  - **理由**：三项任务天然构成“差异可观测 → 配置切换 → 集成验证与文档”闭环，总改动约 300–400 行纯确定性代码与测试，与先前 `T061+T063`、`T054+T055` 粒度一致，一次闭环即可清空 Phase 6、直接衔接 `T069`（Gradio UI）。
- **选项 B：本次仅实施 `T066`（`kb/diff.py` + `tu kb diff`），`T067 + T068` 留作下一份执行单**
  - **理由**：每轮改动面更小，但会增加一次独立执行单审阅与 5 轮复审往返。

### 决策 2：`tu kb diff` 的匹配口径与辅助摘要展示
- **选项 A（推荐）：默认对 `status='current'` 文档按逻辑键 `(title, article_no, paragraph_no, item_no)` 对齐；主清单严格三分法（`added` / `removed` / `modified` 仅看 `text`）；顶部摘要补充文件版本变化、`number_text` 变化计数与已确认关联变化计数，且全程永不输出原文**
  - **理由**：符合 `one_current_per_title` + `uniq_clause_no` 唯一性约束；法规修订升 `version_label` 时能精准定位改动条款而不误报全法删增；同时对真实派生库 `kb-20261113-093057 → kb-20261119-045641` 能直观反映 `1,026` 行编号标注与 `35 → 67` 关联变动，又不污染“原文变化”口径。
- **选项 B：严格按 `clause_id` 精确匹配，且只统计 `added` / `removed` / `modified` 三项（不展示文档版本、`number_text` 与关联摘要）**
  - **理由**：实现最简，但法规改 `version_label` 会误报整法删除+新增，且 `093057 → 045641` 会显示完全无变化，实用性较弱。

### 决策 3：`configs/app.yaml` 中 `kb.version` 默认值与 CLI 适用范围
- **选项 A（推荐）：`configs/app.yaml` 保持 `kb.version: null`（表示自动取最新，填入具体版本号如 `"kb-20261119-045641"` 即锁定切换）；所有读取 `--config` 的运行/评测入口（`tu chat`、`tu eval run`、未来 `tu ui`、`TrainedAssistant.from_config`、`verify_output_from_config`）均按 `CLI --kb-version > app.yaml kb.version > latest` 生效；`tu kb list/show/lookup` 等离线查库命令保持 `--kb-version` / 最新（不隐式读工作区根目录 `app.yaml`），但统一走防建空库校验**
  - **理由**：`artifacts/` 不提交 git，保持 `null` 默认值能确保新环境与 `tu kb import` 后立即生效（契合 FR-004），又支持随时改配置文件锁定或回退任意历史版本；不让离线 `tu kb *` 命令隐式耦合工作区 `app.yaml`，可避免临时 `--artifacts` 测试被意外污染。
- **选项 B：将 `configs/app.yaml` 默认值写死为 `"kb-20261119-045641"`，并让全部 `tu kb *` 子命令默认读取仓库 `configs/app.yaml`**
  - **理由**：本机显式锁死当前版本，但在新拉取仓库（尚无 `artifacts/kb/`）或 `tu kb import` 产生新版本后易因未手动改配置而报错或停在旧库。

### 决策 4：是否同步在 `specs/001-legal-clause-assistant/contracts/cli.md` 补录 `tu kb diff <v1> <v2>`
- **选项 A（推荐）：同步在 `contracts/cli.md` 的「知识库」命令表补录 `tu kb diff <v1> <v2>`（1 行）**
  - **理由**：`contracts/cli.md` 是 CLI 契约文档，补录 1 行可保持契约与真实命令集一致，无任何破坏性。
- **选项 B：仅按 `tasks.md` T068 字面修改 `quickstart.md`，不改动 `contracts/cli.md`**
  - **理由**：把 `specs/` 目录改动控制在绝对最小范围。

---

## 7. 用户拍板与实施/独立复审记录（2026-11-23）

### 7.1 用户拍板决策
用户确认全部按推荐建议（**`1A + 2A + 3A + 4A`**）实施，并将执行单文件命名为 `docs/handoffs/T066-T067-T068-kb-maintenance-handoff.md`。

### 7.2 实施与 2 轮独立只读复审闭环
按 `.agents/skills/task-review-loop/SKILL.md` 启动单节点高思考独立只读审查员（`reviewer`，`gemini-4-neon-high`）完成 2 轮复审并一致通过：

- **Round 1（结论：需修改 · 2 项阻断项 + 4 项非阻断建议）**：
  1. **阻断项 1（已修复）**：`TrainedAssistant.from_config` 未对 `paths.artifacts: null` 或空白串做规范化回退，当 `client=None` 读取 `serve/current.json` 时会触发 `TypeError`。
     - **处置**：在 `src/tu_assistant/kb/store.py` 抽取共享函数 `normalize_artifacts_dir(artifacts_dir, *, config)`（对 `None`、非 `str`/`Path` 或空白串统一回退至 `Path("artifacts")`），并在 `resolve_kb_path`、`TrainedAssistant.from_config`、`tu eval run` 与 `tu chat` 中统一复用；新增单测 `test_from_config_default_client_null_artifacts_and_connection_cleanup`。
  2. **阻断项 2（已修复）**：`tests/unit/test_kb_config.py` 缺少 `tu eval run` CLI 配置透传测试，以及 `latest_kb_path` 按 `stem` 排序防 `-01` 倒序和 `import_directory` 同秒防撞名的确定性单元测试。
     - **处置**：在 `tests/unit/test_kb_config.py` 新增 `test_cli_eval_run_respects_kb_version_and_artifacts_from_config` 与 `test_latest_kb_path_stem_order_and_import_directory_collision_suffix`（monkeypatch 固定时间戳验证 `-01`/`-02` 生成、`latest_kb_path` 选出 `-02`、显式重名抛 `FileExistsError`）。
  3. **4 项非阻断建议（全部采纳）**：
     - 清理 `src/tu_assistant/cli.py` 中已无调用方的死代码 `_latest_kb`，并在 `tu chat` 中以 `try ... finally: conn.close()` 确保 `ModelClient` 初始化异常时安全释放连接；
     - `src/tu_assistant/kb/store.py` 的 `open_kb(..., read_only=True)` 改用 `f"{p.resolve().as_uri()}?mode=ro"` 构造安全 URI；
     - `src/tu_assistant/kb/diff.py` 中 `_load_snapshot` 外层捕获 `sqlite3.Error` 统一转为 `KBError`；
     - `tests/unit/test_kb_diff.py` 补齐显式 `.sqlite` 路径、非 SQLite 垃圾文件与缺列损坏库单测；`tests/integration/test_kb_update.py` 补齐 `kb.version: null` 实际交付 `new_art4_text` 的断言。
- **Round 2（结论：一致通过 · 阻断项 = 0，非阻断建议 = 0）**：
  - 独立审查员逐项复核确认 Round 1 全部问题已彻底解决且无新回归，随后已回收审查节点。

### 7.3 第三方独立评审意见修订与说明（2026-11-23）
收到用户转交的第三方独立评审意见（共 9 条：一、应修改 1–3；二、建议修改 4–6；三、执行单文档更新 7–9），已逐条核实并全部采纳落地：

1. **意见 1（`tu chat` 复用 `TrainedAssistant.from_config`、消除 `_model_name` 重复并补 `session_config_from`）**：
   - 将模型名解析逻辑提取为 `src/tu_assistant/config.py` 的共享函数 `resolve_model_name(cfg, artifacts_dir="artifacts")`，由 `TrainedAssistant.from_config` 与 `cli.py`（`tu eval run`）统一调用；同时在 `cli.py` 中保留 `_model_name(cfg, artifacts)` 作为对 `resolve_model_name` 的薄委托函数，以零改动兼容既有单测 `tests/unit/test_served_model_name.py`；
   - 在 `src/tu_assistant/chat/assistant.py` 新增 `session_config_from(cfg, *, use_system_prompt=True)`，供 `tu chat`、`tu eval run` 及下游 `T069`（`tu ui`）共用；
   - `tu chat` 生产路径改为直接调用 `TrainedAssistant.from_config(config, kb_version=kb_version, artifacts_dir=artifacts)`，回显 `assistant.kb_version`，并在 `try ... finally` 中调用 `assistant.close_kb()`；同时为兼容既有单测 `tests/unit/test_article_count.py::test_cli_chat_forwards_session_config`（该测试 monkeypatch 了一个不带 `from_config` 类方法的 `_DummyAssistant` 替身），保留了 `if hasattr(TrainedAssistant, "from_config"): ... else: ...` 回退分支（在 `else` 分支中也对 `open_kb` 增加了 `try ... except: conn.close(); raise` 异常保护），使既有测试无需任何改动即可通过。
2. **意见 2（`quickstart.md` 补全关联重抽确认/按需 `derive` 必做步骤，并在 `quickstart.md` 与 `configs/app.yaml` 注明 `kb.version: null` 自动切库过渡期风险）**：
   - 已在 `specs/001-legal-clause-assistant/quickstart.md` 的 US4 小节拆分为「重要提示 1：`kb.version: null` 自动切库与未确认关联的过渡期风险」与「重要提示 2：知识更新需重训（research R1 风险）」，明确写出 `tu kb import` 新库初始 `confirmed=0`、必须重新执行 `tu kb relations extract -> review/confirm`（及按需 `tu kb derive`），且在新库关联确认完成或做同口径评测对比前应先在 `configs/app.yaml` 锁定 `kb.version`；
   - 已同步在 `configs/app.yaml` 的 `kb.version` 注释中补齐该锁定提醒。
3. **意见 3（`eval/runner.py` 与 `eval/compare.py` 改为只读打开 KB）**：
   - `src/tu_assistant/eval/runner.py:92` 的 `open_kb(kb_path)` 与 `src/tu_assistant/eval/compare.py:323` 的 `load_doc_index` 均已改为 `open_kb(kb_path, read_only=True)`。
4. **意见 4（消除 `resolve_kb_path` 同名歧义）**：
   - 已将 `src/tu_assistant/eval/compare.py` 中从评测 manifest 解析路径的辅助函数重命名为 `_kb_path_from_manifest(manifest, artifacts_dir)`，同步更新 `cli.py` 调用点。
5. **意见 5 & 6（`tests/integration/test_kb_update.py` 固定同秒时间戳验证 `-01` 后缀，并补齐执行单 §3.4 场景 5 错误防线断言）**：
   - 在 `test_kb_update_diff_and_config_switch_end_to_end` 中通过 `monkeypatch.setattr("tu_assistant.kb.ingest.new_kb_version", lambda: "kb-20261123-000001")` 固定同秒时间戳，确定性断言 `v1_ver == "kb-20261123-000001"` 且 `v2_ver == "kb-20261123-000001-01"`，使代码与 docstring 完全一致；
   - 同时在该集成测试步骤 6 补齐执行单 §3.4 场景 5（配置不存在的 `kb.version: kb-nonexistent-9999` 时，`verify_output_from_config` 与 `TrainedAssistant.from_config` 均抛 `KBError` 且不创建空 `.sqlite`），与 `tests/unit/test_kb_config.py` 形成双重保障。
6. **意见 7、8、9（执行单状态更新、CLI 接入范围与退出码变化记录、三组真实历史 KB 对比反泄漏核查说明）**：
   - 已更新本执行单顶部状态与红线第 5 条、§3.1 变更表；
   - **CLI 命令范围扩展与退出码说明**：
     - `tu kb diff` 通过 `diff_kbs`/`resolve_diff_kb` 解析版本并只读打开；
     - `tu chat` 生产路径通过 `TrainedAssistant.from_config`（内部调用 `resolve_kb_path` + 只读打开）加载知识库；
     - `tu eval run`、`tu kb list/show/lookup`、`tu kb relations extract/review`、`tu synth evalcases/sft` 及 `tu eval cases review` 全部接入 `_resolve_cli_kb` + `open_kb(..., read_only=True)`；
     - 当知识库文件不存在或版本号非法时，上述全部命令统一捕获 `KBError`、输出错误到 `stderr` 并返回退出码 `2`（此前无库时 `_latest_kb` 返回 `1`、传错 `--kb-version` 时静默建 0 字节空库后抛 `OperationalError`），并且全部以只读模式打开 SQLite。

### 7.4 验收实测结果汇总
- **新增测试**：`uv run pytest tests/unit/test_kb_diff.py tests/unit/test_kb_config.py tests/integration/test_kb_update.py` → **13 passed**；
- **全量回归**：`uv run pytest` → **434 passed, 6 xfailed**（含 `test_runtime_isolation.py`、`test_citation_verify.py`、`test_article_count.py`、`test_compare.py`）；
- **代码规范**：`uv run ruff check src tests` → **All checks passed!**；
- **真实历史 KB 只读对比抽验（3 组均逐行核查确认无任何条文正文泄漏）**：
  - `kb-20261113-071600 -> kb-20261113-091537 --summary-only`：现行文件 `26 -> 25`，条款 `5953 -> 3817`（删除 `2136` / 新增 `0` / 原文变化 `0`），删除文件《中华人民共和国民法典》，已确认关联 `0 -> 35 (+35 / -0)`；同时不带 `--summary-only` 抽查确认全部 2,136 行明细仅含 `[- 删除] 《中华人民共和国民法典》（2021-01-01）第X条... (clause_id=...)` 编号与 ID，0 字节条文正文；
  - `kb-20261113-091537 -> kb-20261113-093057`：现行文件 `25 -> 24`，条款 `3817 -> 3809`（删除 `8` / 新增 `0` / 原文变化 `0`），8 条明细仅含编号（`第1段`–`第4段` 及子项 `第2段第1项`–`第4项`）与 `clause_id`，0 字节条文正文；
  - `kb-20261113-093057 -> kb-20261119-045641`：条款新增 `0` / 删除 `0` / 原文变化 `0` / 原文未变 `3809`，`编号写法变化（原文未变）：1026 条`，`已确认条款关联：35 条 -> 67 条（+42 / -10，保留 25）`，0 字节条文正文；
- **只读完好性**：4 份历史 `artifacts/kb/kb-*.sqlite` SHA-256 哈希 100% 不变；`shasum -a 256 -c artifacts/logs/t075/01/output.sha256` **25/25 OK**；`tasks.md` 尚未勾选、尚未 `git commit`，待用户最终确认。
