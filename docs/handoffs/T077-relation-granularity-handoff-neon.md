# T077 执行单 · 修正责任关系的条、款定位并追溯影响

> **归档声明**：本草稿已被合并修订版 [T077-relation-clause-handoff.md](T077-relation-clause-handoff.md) 取代，仅作历史归档，请勿照本稿执行。

**状态**　待用户审阅（执行单阶段，未修改代码、未写入新 KB）。起点为 `2049c04`，基准历史 KB 为 `kb-20261113-093057`（24 篇 / 3,809 条款行 / 1,663 条），演示模型为 `exp-20261116-resume500`。

**任务编号**　**T077**（衔接 [T019](../../specs/001-legal-clause-assistant/tasks.md) 用户人工审阅确认关系）。

## 为什么优先做 T077

1. **阻塞 US2 扩量与续训**：[T052 独立复审](T052-article-synthesis-handoff.md#84-不阻断-t052t057-扩量前须处理)核实，当前 KB 的 12 对已确认 `liability_for` 关系中有 **6 对错款**、另有 **2 处整条引用覆盖不全**，导致普法文章可用素材缩减至 6 对、同文件多违法组合实质仅剩 1 组。[T057 执行单](T057-article-dataset-handoff.md)已将核对 T077 修正后的关系列为扩量前置，进而阻塞 [T075](../../specs/001-legal-clause-assistant/tasks.md) 的 7B 续训。
2. **避免后续任务返工**：T077 需明确多款条文中“整条”与“第一款”的编号、对应原文及校验层解析口径。先稳住口径，后续 [T053](../../specs/001-legal-clause-assistant/tasks.md)（文章修改样本）、T057（合入数据集）和 Phase 5 评测报告都能建立在统一地基上。
3. **影响范围覆盖基础层与指标**：已确认关系同时作用于知识类关系样本、编排层关联补全兜底（FR-019）与 **SC-005** 指标；且需包含人工审阅节点（T019），越早完成越利于下游并行推进。

---

## 0. 执行前现状核查摘要（只读统计，未触碰 `inputs/`）

在起草本执行单前，对 `kb-20261113-093057.sqlite`、历史数据集与历史评测 run 做了结构化只读核查，关键事实如下：

1. **KB 条文结构（24 篇 / 1,663 条 / 3,809 行）**
   - 单款无项：762 条；单款含多项：114 条；**多款条文（≥2 款）：787 条**。
   - 全部 787 条多款条文的第 1 款，`number_text` 均只写为 `第N条`（无“第1款”），第 2 款起写 `第N条第2款`（根因在 [parse.py](../../src/tu_assistant/kb/parse.py) 第 120 行）。
   - 校验层 [verify.py](../../src/tu_assistant/citation/verify.py) 收到无款号的 `〔《…》第N条〕` 时，仅在 `len(rows) == 1`（单款无项）直接定位；对多款条文（787 条）和单款含多项（114 条），省略原文或引文差一字均判 `incomplete`，只有引文逐字等于某款规范原文时才落回该款。
2. **已确认关系的问题面（35 条：12 `liability_for` + 23 `references`）**
   - **6 对 `liability_for` 错款**：`40124ed5e360acee:a10:p1 -> a38:p1`（明指第二款）、`40124ed5e360acee:a15:p1 -> a39:p2`（第二款）、`a98741e9ca9f6fa1:a22:p1 -> a79:p1`（第二款）、`c2699265cef115bb:a40:p1 -> a77:p1`（第四款）、`c2699265cef115bb:a41:p1 -> a78:p1`（第二款）、`cd730370ca29c4df:a6:p1 -> a13:p1`（第六条第二款，且同行并列提及第七条、第九条第一款）。
   - **2 处整条引用覆盖不全**：`40124ed5e360acee:a21:p1 -> a40:p1`（a21 有 3 款，其中 p2、p3 各含 4 项）；`4b6c1f293f717293:a3:p1 -> a51:p1`（a3 有 2 款，且同行并列提及第十二条）。
   - **并列 / 区间漏抽与 `references` 同类问题**：[relations.py](../../src/tu_assistant/kb/relations.py) 只匹配触发词后第一个“第X条”且不捕获款/项，导致漏抽“第四十三条和第四十八条”“第一百八十一条至第一百八十四条”等，23 条 `references` 中同样存在明指某款/某项却落回 `p1` 的记录（如 `f603773a50aeb8a5:a116` 第三款、`a214` 第二款、`be21194cc551533d:a44` 第一/四/五项）。
3. **对历史训练样本与评测的影响**
   - 抽稀前全量数据集 `ds-kb-20261113-093057-16741` 收录了全部 12 条 `liability_for` 关系样本（train 10 / valid 2）；实际训练 `exp-20261116-resume500` 的 `ds-kb-20261113-093057-8410` 保留了其中 **7 条**（全在 `train.jsonl`），其中 **5 条是错款样本**（第 6 对错款 `a41` 与 2 处整条引用未进入 `ds-8410` 训练集）。
   - 另发现 [knowledge.py](../../src/tu_assistant/synth/knowledge.py) 的 `relation_samples` 使用 `a.text`/`b.text` 而非 `_canonical_text`，对带子项的条款（如 `a98741e9ca9f6fa1:a43:p1`、`f603773a50aeb8a5:a181:p1`）只输出引言；同时 [check.py](../../src/tu_assistant/synth/check.py) 未拦截 `incomplete` 引用。
   - `eval/cases/v1/reviewed.jsonl`（60 题）中有 **18 题 gold 为多款条文第 1 款**、1 题为单款含项；SC-016 基线 `run-20261117-081504` 的 9 道精确命中中 **0 道来自多款第 1 款**（全部为单款无项 3 题或显式第 2 款 6 题），而 `cand-051`、`cand-055` 模型命中了正确条号却因写“第N条”缺款号被判 `incomplete`。
   - 历史 run（`run-20261117-022645` / `run-20261117-081504` / `run-20261118-020130`）上 `SC-005` 有效分母均为 0，且旧 12 对关系与 v1 全部 gold 条款交集为 0。

---

## 1. 需要用户拍板的三项口径（审阅确认后再实施）

以下三项直接影响新 KB、校验层与关系审阅，请审阅并确认取舍：

### 取舍 1：多款条文的“整条”与“第一款”编号及校验层解析口径

1. **ID 兼容性（固定原则）**：`clause_id` 保持 `doc_id:aN:pM[:iK]` 不变，确保 `eval/cases/v1/` 全部 gold 与历史 run / SC-016 零破坏。
2. **新 KB 的 `number_text`（推荐）**：
   - 单款条文（单款无项 + 单款含项）保持 `第X条`；
   - 多款条文（≥2 款）第 1 款显式带款号：`第X条第1款`（与现有 `第X条第2款` 一致；如你偏好统一中文数字 `第一款/第二款`，可在此一并切换，解析正则两者皆兼容）。
3. **校验层 [verify.py](../../src/tu_assistant/citation/verify.py) 对无款号 `〔《…》第N条〕` 的解析**：
   - 单款无项 → 定位 `aN:p1`，规范原文 = 该款原文（不变）；
   - **单款含多项** → 该条唯一一款，无歧义直接定位 `aN:p1`，规范原文 = 引言 + 各项（修复当前 `len(rows)==1` 误判为 `incomplete` 的问题）；
   - **多款条文只写 `〔《…》第N条〕`**（请选择其一）：
     - **方案 B1（推荐，严格款级）**：对齐 [citation-format.md](../../specs/001-legal-clause-assistant/contracts/citation-format.md) §1“精确到条，有款、项时精确到款、项”。多款条文只写 `第N条` 一律判 **`incomplete`**（即使附带了第一款原文，也不再悄悄落回 `aN:p1`，杜绝“挂整条名义交付第一款原文”）。引用多款时须逐款写明 `第N条第1款`、`第N条第2款`……
     - **方案 B2（允许整条引用）**：多款条文只写 `第N条` 解析为整条，规范原文 = 该条全部各款（含各自子项）按款序换行拼接；若只附第一款原文则按 `corrected` 自动补齐整条。*代价*：需引入无款号的虚拟整条标识（`doc_id:aN`），并同步调整 `eval/metrics`、`SC-016`、`confirmed_relations_from` 的匹配规则。
   - **附带口径确认**：当模型显式写了**不存在的款号**（如单款条文写成 `第2款`，历史 `cand-034` 即属此类），目前 `verify.py` 因条存在而判 `incomplete`；建议明确改为 **`not_found`**（编号在库中不存在，按宪章原则 I 删除引用块），并在单测中锁定。

### 取舍 2：整条引用与并列/区间引用在 `ClauseRelation` 中的展开与修复范围

- **整条引用多款条文（如 `a21`、`a3`）**：推荐在规则抽取时按款展开为多条候选（`a21:p1 -> a40:p1`、`a21:p2 -> a40:p1`、`a21:p3 -> a40:p1`），交由 **T019 人工审阅**逐款确认哪些款属于实质受责条款（剔除纯定义/总则款），与款级校验口径及 `confirmed_relations_from` / `SC-005` 天然一致。
- **规则抽取修复范围**：推荐一次性修好 [relations.py](../../src/tu_assistant/kb/relations.py) 对**款/项捕获 + 并列/区间拆解 + 整条多款展开**的支持，覆盖 `liability_for`、`exception_of`、`references` 全部三类关系，生成全量候选交 T019 审阅。（如希望缩小本次人工审阅量，也可分批：先审全量 `liability_for` 候选，其余 `references` 留作第二批核对。）

### 取舍 3：历史已训练 adapter 的实测方式

- 推荐在本地起 `tu serve model --exp exp-20261116-resume500`，用只读诊断脚本（`temperature=0`，产物写入 `artifacts/logs/t077/`，不放入 `eval/cases/`）对 6 对错款与 2 处整条引用构造两类探针（直接问该条/该款的法律责任 + 换用具体款号反问），实测模型实际记住了错款还是正确款，记录结论供 T057/T075 决定是否补充纠偏样本。

---

## 2. 实施步骤（按推荐方案编写，确认取舍后据此执行）

### 第 1 步　复现与历史影响基线固化

1. 编写可复现的只读审计脚本（放在 `scripts/` 下或 T077 专用诊断脚本），针对历史 KB `kb-20261113-093057.sqlite` 输出完整核查清单至 `artifacts/logs/t077/baseline_audit.md`（引文摘要严格 ≤15 字，绝不读取 `inputs/`）：
   - 复现 6 对错款与 2 处整条引用的精确证据（`to_clause` 原文引用片段 vs 库中 `from_clause_id` 及该条全部款/项结构）；
   - 同步列出其余 4 对 `liability_for` 与 23 条 `references` 中的款/项偏差与并列漏抽；
   - 统计历史数据集（`ds-kb-20261113-093057-16741` 与 `ds-kb-20261113-093057-8410`）中关系样本及多款第一款样本的占比与进入训练集明细；
   - 统计 `eval/cases/v1/*.jsonl` 的条/款分布，以及历史评测 `run-20261117-081504` 中多款第一款被判 `incomplete` 的明细与历史 `SC-005` 数值。
2. 记录历史 `kb-20261113-093057.sqlite`、`ds-kb-20261113-093057-8410` 与关键历史 `eval` run 的路径与校验值，确保全程只读保留、零修改。

### 第 2 步　落地多款编号、校验层与知识样本口径

1. **[kb/parse.py](../../src/tu_assistant/kb/parse.py)**：在一整条切分结束（flush 整条）时，根据该条实际款数决定第 1 款的 `number_text`——单款条文保持 `第X条`，多款条文（≥2 款）第 1 款改写为 `第X条第1款`（子项随之变为 `第X条第1款第Y项`）。`clause_id` 保持不变。
2. **[citation/verify.py](../../src/tu_assistant/citation/verify.py)**：
   - 无款号/项号引用 `〔《…》第N条〕` 时：按“该条 distinct `paragraph_no` 数量”判断——仅 1 款时直接定位该款主行（`item_no is None`，兼容单款无项与单款含项，规范原文自动拼接子项）；≥2 款时按确认后的方案 B1（或 B2）处理；
   - 显式指定了 `paragraph_no` 或 `item_no` 但在该条中不存在时，按确认口径判 `not_found`（删除引用块）而非 `incomplete`。
3. **[synth/knowledge.py](../../src/tu_assistant/synth/knowledge.py) 与 [synth/check.py](../../src/tu_assistant/synth/check.py)**：
   - `relation_samples` 统一改用 `_canonical_text(a, clauses)` / `_canonical_text(b, clauses)`，修复带子项条款原文残缺问题；
   - 检查 `citation_issue` 对 `incomplete` 引用的处理，避免含无法定位引用的样本混入训练集；
   - 核对 [synth/articles.py](../../src/tu_assistant/synth/articles.py) `_materials` 在新 KB 口径下的兼容性。

### 第 3 步　修复关系抽取、交互审阅与版本化确认逻辑

1. **[kb/relations.py](../../src/tu_assistant/kb/relations.py)**：
   - 扩展解析逻辑：在触发词（`违反` / `所列` / `除外` / `依照/按照/依据/比照`）之后，解析连续引用列表，覆盖：
     - 显式款、项定位（`第X条第Y款`、`第X条第Y款第Z项`、`第X条第Z项`）；
     - 并列与区间表达（`、第Y条`、`和第Y条`、`或者第Y条`、`第X条至第Y条`、同条并列多款/多项如 `第一项、第二项`）；
     - 整条引用落到多款条文时，按该条全部款主行展开为逐款候选（保留去重，过滤指向自身）。
   - 为每条候选补充可追溯的元数据（如 `evidence` 引用片段或 `scope` 标明“明指款 / 明指项 / 整条展开”，写入 pending JSONL 辅助人工审阅，同时保持 SQLite 表结构不变或向后兼容）。
2. **[cli.py](../../src/tu_assistant/cli.py) 中的 `tu kb relations review` 与 `confirm`**：
   - `review` 展示时：
     - 用 `_canonical_text` 输出 `from`/`to` 完整原文（含子项，避免审阅时漏看各项）；
     - 标明 `from` 条款所在“条”共有几款、当前候选指向第几款，以及 `to` 原文里触发该候选的引用片段，防止再次发生错款误判；
   - `confirm` 写入时：
     - 不原地覆写旧版已归档 KB；明确要求作用于新生成的 KB 版本（或提供明确校验避免覆盖被历史实验引用的旧 KB），导入时以审阅文件为完整事实源清理该新 KB 中被改为 `false` 的关系，并更新该 KB 的 `manifest.json` 记录确认统计与 pending 文件哈希。
3. 同步更新 [relations-confirm-guide.md](../relations-confirm-guide.md)（审阅确认后提交）。

### 第 4 步　生成新 KB 版本并停下等待 T019 人工审阅

1. 保持 `artifacts/kb/kb-20261113-093057.sqlite` 原样不动；运行 `uv run tu kb import inputs/project/001` 生成新版本 `artifacts/kb/kb-<新时间戳>.sqlite`（只查看命令统计输出与 `parse_report.md`，绝不读取 `inputs/` 任何文件）。
2. 运行 `uv run tu kb relations extract --kb-version <新版本>` 生成新的 `relations_pending.jsonl`，输出候选条数、与旧 35 条的增删改对比清单（每条标明 `from`/`to` ID、款数、触发引用片段）。
3. **人工关卡（T019）**：暂停自动化写入，交由用户用 `uv run tu kb relations review <pending>` 逐条审阅（至少覆盖全部 `liability_for` 候选及已核查出的偏差项），确认无误后执行 `uv run tu kb relations confirm <pending> --kb-version <新版本>` 写入新 KB。

### 第 5 步　前后对比核验（关系样本、SC-005 与评测集兼容性）

1. **知识类关系样本对比**：分别对旧 KB（`kb-20261113-093057`）和新 KB 运行确定性 `knowledge.relation_samples` + `check_sample`，输出前后条数、丢弃数、逐条变更对比表至 `artifacts/logs/t077/relation_samples_diff.md`。
2. **SC-005 前后对比**：不修改历史 `artifacts/eval/run-*` 原文件，离线脚本用新旧两版 KB 分别对 `run-20261117-022645`、`run-20261117-081504`、`run-20261118-020130` 重算 `relation_completion_score` 及新旧关系与 `eval/cases/v1/*.jsonl` gold 的交集，结果写入 `artifacts/logs/t077/sc005_diff.md`。
3. **文章素材与评测回归检查**：
   - 验证 `synth/articles._materials` 在新 KB 上的统计：`paragraph_mismatch == 0`，记录新的可用 `liability_for` 对数与可组合的同文件多违法对数（直接反馈给 [T057 执行单](T057-article-dataset-handoff.md)）；
   - 验证 `eval/cases/v1/reviewed.jsonl`（60 题）与 `eval/cases/v1/articles.jsonl`（10 题）全部 gold ID 在新 KB 中 100% 存在；
   - 重跑 `uv run tu eval compare --sc016 run-20261117-022645 run-20261117-081504` 确认历史基线验收完全不受影响。

### 第 6 步　已训练 adapter 掌握情况实测

1. 启动本地模型服务 `uv run tu serve model --exp exp-20261116-resume500`（不调用任何外部服务）。
2. 运行只读探针脚本（`temperature=0`，复用 `ModelClient` 端点白名单与 `verify_output`），对 6 对错款（含进入 `ds-8410` 的 5 对及未进入的 `a41`）与 2 处整条引用分别测试：
   - 复现训练分布问法（`违反《X》第N条要承担什么法律责任？`）；
   - 精确款号问法（`违反《X》第N条第M款要承担什么法律责任？`）；
   - 反查/对照款问法（`违反《X》第N条第1款要承担什么法律责任？`）。
3. 将逐题模型原始回复、校验结论与统计总结归档至 `artifacts/logs/t077/adapter_probe.md`（引文摘要 ≤15 字），给出明确的实测判断（模型是否学会了错误映射、T057/T075 续训是否需要显式补强新关系样本）。

### 第 7 步　自动化测试、学习文档与交付复审

1. **自动化测试**：
   - 新增 `tests/unit/test_relations.py`：覆盖显式款/项捕获、并列（`、` / `和`）与区间（`至`）拆解、整条多款展开、不误抽自身引用、以及 `review`/`confirm` 不污染历史 KB；
   - 更新 `tests/unit/test_parse.py`：新增多款条文第 1 款显式带款号、多款子项编号与单款无款号对照测试；
   - 更新 `tests/unit/test_citation.py` 与 `tests/integration/test_citation_verify.py`：覆盖单款含项无款号直接定位、多款无款号按选定口径（B1/B2）判定、不存在款号判定为 `not_found`；
   - 回归 `tests/unit/test_synth_articles.py`、`tests/unit/test_metrics.py`、`tests/unit/test_compare.py` 及全套测试。
2. **学习文档与规格同步**：
   - 在 [03-knowledge-base.md](../learning/03-knowledge-base.md) 的 L3.4 / L3.5 附近新增带编号小节（如 **[L3.4.1]** 条与款的定位粒度：为什么不能把“第N条”等同于“第一款”），用本次真实案例说明规则抽取、人工审阅和校验层三层联动的教训，并更新 [00-glossary.md](../learning/00-glossary.md)；
   - 若因选定口径（如单款含项 / 不存在款号判定）需微调 [citation-format.md](../../specs/001-legal-clause-assistant/contracts/citation-format.md) 措辞，列出精确差异交用户审阅后再提交。
3. 实施完成后在本执行单末尾追加实施记录与实测数据，标记“待审阅”，经用户确认与独立复核后再在 [tasks.md](../../specs/001-legal-clause-assistant/tasks.md) 中勾选 **T077**（及 **T019**）。

---

## 3. 验收标准

- [ ] **复现与留证**：`artifacts/logs/t077/baseline_audit.md` 完整复现 6 对错款、2 处整条引用、历史数据集分布与历史 SC-005 基线；历史 `kb-20261113-093057.sqlite`、`ds-kb-20261113-093057-8410` 与历史 `eval` run 均保持原状未改动。
- [ ] **口径统一与测试通过**：多款“整条 vs 第一款”编号、规范原文与校验层解析口径一致落地；`uv run pytest` 全量通过（含新增 `test_relations.py` 及更新后的解析/校验测试），`uv run ruff check src tests` 通过。
- [ ] **新 KB 与 T019 确认**：新 KB 版本 `kb-<新时间戳>.sqlite` 已入库并由用户完成 T019 关系审阅确认；`eval/cases/v1/*.jsonl` 全部 gold ID 在新 KB 中 100% 可解析；`synth/articles._materials` 在新 KB 上 `paragraph_mismatch == 0`。
- [ ] **前后对比与回归基线**：`relation_samples_diff.md` 与 `sc005_diff.md` 清楚给出新旧 KB 差异；`uv run tu eval compare --sc016 run-20261117-022645 run-20261117-081504` 复现条级 1/60→17/60、款级 9/60、文件子集 0/30→21/30，退出码 0。
- [ ] **adapter 实测完成**：`artifacts/logs/t077/adapter_probe.md` 给出 `exp-20261116-resume500` 在 6 对错款与 2 处整条引用上的实测结果与结论（全过程仅调用本地端点）。
- [ ] **合规与学习文档**：全程未读取 `inputs/` 目录内任何文件内容；学习文档 `[L3.x]` 已更新；文档改动与最终勾选均等待用户审阅同意。
