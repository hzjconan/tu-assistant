# T077 执行单 · 修正责任关系的条、款定位并追溯影响（合并修订版）

**状态**　已完成（2026-11-19，独立复审通过，已按第 6 节收尾并勾选 [tasks.md](../../specs/001-legal-clause-assistant/tasks.md) 中的 T077；T019 待第二批 `references`/`exception_of` 审阅导入后再勾选）。本单合并 [astra 版](T077-kb-clause-relations-handoff-astra.md) 与 [neon 版](T077-relation-granularity-handoff-neon.md)，并吸收独立评审意见。以 neon 版的现状核查与步骤为底稿，替换其中四处高风险做法：严格款级口径、只靠 SC-016 复现验收、重新导入 KB、整条展开不去重。第 4 步另有一次 T019 人工审阅。

**已审定口径**（详见第 1 节）

| # | 事项 | 决定 |
|---|---|---|
| 1 | 只写“第N条”的解析 | C 兼容款级：新样本一律写款号；校验层保留“引文唯一匹配某款”的回退并单独计数；单款含项直接定位 `aN:p1` |
| 2 | 新 KB 第一款编号 | 写成 `第N条第1款`，阿拉伯数字；若第 2 步统计出受影响样本占训练集超过 20%，先报告再决定是否只在新数据中写款号 |
| 3 | 新 KB 生成方式 | 从 `kb-20261113-093057` 派生，不重新导入 `inputs/` |
| 4 | 范围 | 抽取规则三类关系一次修好；人工审阅分两批，第一批为全部 `liability_for` 候选及已知偏差项；整条引用按款展开由用户逐款取舍，SC-005 按去重后的责任条款计分；T019 待两批都导入后勾选 |

**起点**　`2049c04`；基准 KB `kb-20261113-093057`（24 篇 / 3,809 行 / 1,663 条）；演示模型 `exp-20261116-resume500`。全程不读取 `inputs/`，新 KB 从旧 SQLite 派生。

## 为什么优先做 T077

1. **阻塞扩量与续训。** [T052 复审](T052-article-synthesis-handoff.md#84-不阻断-t052t057-扩量前须处理)核实，12 对已确认 `liability_for` 中有 6 对错款，另有 2 处整条引用覆盖不全。[T057](T057-article-dataset-handoff.md) 扩量前要核对修正后的关系，T075 续训又依赖 T057。
2. **先定口径，避免返工。** 多款条文中“整条”与“第一款”怎么编号、配什么原文、校验层怎么解析，决定了 T053/T057 样本和 Phase 5 评测的写法。
3. **同时影响训练与指标。** 已确认关系同时进入知识类关系样本、FR-019 关联补全兜底和 SC-005。

## 0. 已核实的现状（只读）

| 事实 | 核实方式 |
|---|---|
| 已确认关系 35 条：`liability_for` 12、`references` 23；无未确认行 | 查询旧 KB |
| 多款条文 787 条，其第一款 `number_text` 均为 `第N条`，无款号 | 查询旧 KB；[parse.py](../../src/tu_assistant/kb/parse.py#L121) |
| 抽取只取触发词后第一个条号，端点取款号最小行，不捕获款、项，漏抽并列与区间 | [relations.py](../../src/tu_assistant/kb/relations.py#L37-L60) |
| `confirm` 只 `INSERT OR REPLACE` 标为 true 的行，不撤销旧边 | [cli.py](../../src/tu_assistant/cli.py#L177-L217) |
| 只写条号时，仅“整条只有一行”能定位；单款含项、多款均须引文逐字等于某款规范原文才落回 | [verify.py](../../src/tu_assistant/citation/verify.py#L95-L105) |
| 关系样本用 `a.text`/`b.text`，带项条款只输出引言 | [knowledge.py](../../src/tu_assistant/synth/knowledge.py#L136-L147) |
| SC-005 按边计数，同一责任条款被多条边指向时会重复计分 | [metrics.py](../../src/tu_assistant/eval/metrics.py#L75-L87) |
| `tu eval compare --sc016` 读 run 中已存的 `cited_clause_ids`，不重新校验 | [compare.py](../../src/tu_assistant/eval/compare.py#L355-L362) |
| `ds-8410` 含责任关系样本 7 条（全在 train），`ds-16741` 为 10/2；数据集未保存 `meta.clause_ids`，归因只能靠文本匹配 | grep 数据集 |

**8 个已知问题**（方向：被违反条款 → 责任条款）

| 旧边 | 原文实际指向 | 类别 |
|---|---|---|
| `40124ed5e360acee:a10:p1 → a38:p1` | 第 10 条第 2 款 | 错款 |
| `40124ed5e360acee:a15:p1 → a39:p2` | 第 15 条第 2 款 | 错款 |
| `a98741e9ca9f6fa1:a22:p1 → a79:p1` | 第 22 条第 2 款 | 错款 |
| `c2699265cef115bb:a40:p1 → a77:p1` | 第 40 条第 4 款 | 错款 |
| `c2699265cef115bb:a41:p1 → a78:p1` | 第 41 条第 2 款 | 错款 |
| `cd730370ca29c4df:a6:p1 → a13:p1` | 第 6 条第 2 款，同句并列第 7 条、第 9 条第 1 款 | 错款加漏抽 |
| `40124ed5e360acee:a21:p1 → a40:p1` | 整条（3 款，p2/p3 各含 4 项） | 整条覆盖 |
| `4b6c1f293f717293:a3:p1 → a51:p1` | 整条（2 款），同句并列第 12 条 | 整条覆盖加漏抽 |

历史 run 的 SC-005 有效分母均为 0，且旧 12 对关系与 v1 gold 无交集，所以历史 run 重算只能证明“无变化”，差异须用固定诊断例证明（见第 5 步）。

## 1. 四项口径（已审定，均采用推荐方案）

### 口径 1：只写“第N条”的引用怎么解析（推荐 C，兼容款级）

| 方案 | 多款条文只写 `第N条` | 对历史的影响 |
|---|---|---|
| B1 严格款级 | 一律判 `incomplete` | `resume500` 学到的“第N条 + 第一款原文”写法全部失效，T075 款级基线 9/60 与新口径不可比 |
| B2 整条 | 解析为整条，原文为各款拼接 | 需新增无款号的条级 ID，`metrics`、SC-016、`confirmed_relations_from` 都要改 |
| **C 兼容款级（推荐）** | 新生成的样本一律写款号；校验层保留“引文唯一匹配某款即落回该款”的回退，并在判定结果中单独计数，便于观察模型何时改掉旧写法；无引文仍判 `incomplete` | 历史输出判定不变，新旧可比 |

三个方案都要做：**单款含项**只写条号时直接定位 `aN:p1`，原文为引言加各项。这修复了一个现有误判。

不并入本任务：“显式写了不存在的款号”从 `incomplete` 改判 `not_found`。它会改变宪章原则 I 的删除行为，影响超出关系修正，另立任务处理。

### 口径 2：新 KB 是否把多款条文第一款写成 `第N条第1款`（推荐：是，并先量化影响）

`clause_id` 不变，gold 与历史 run 都不受影响。代价是 787 条第一款的知识样本标记全部改变，T075 从 `resume500` 续训时要重新学写法。第 2 步先统计受影响的样本数与占比，交 T057 决定是否补足样本或调整配比。款号用阿拉伯数字，与现有 `第2款` 及已训练 adapter 的写法一致；[引用契约](../../specs/001-legal-clause-assistant/contracts/citation-format.md)示例中的中文数字写法，校验层仍照常识别。若受影响样本占训练集超过 20%，先报告用户，再决定是否只在新数据中写款号。

### 口径 3：新 KB 的生成方式（推荐：从旧库派生）

复制旧 SQLite，在副本上改 `number_text`，并按审定差异撤销、新增关系。其余 27 条无关的已确认关系原样保留，不必重新导入 `inputs/`，也不必全量重审。派生后核对：两库 `clause_id` 集合与条款原文完全一致，只有 `number_text` 和 `clause_relations` 有差异。

### 口径 4：本次范围与整条引用的表示（推荐：分批，整条按款展开、SC-005 去重）

- **抽取规则一次修好，三类关系都用。** 捕获款、项，拆解并列与区间。整条引用落到多款条文时，按款展开为候选。
- **人工审阅分两批。** 第一批审全部 `liability_for` 候选和已知偏差项。`references`、`exception_of` 作为第二批。T019 在两批都导入后才勾选。
- **整条展开后由用户逐款取舍**，剔除纯定义、总则性质的款。`relation_completion_score` 改为按“去重后的责任条款”计分，同一责任条款只计一次，以免分母膨胀、重复计分。关系样本中重复出现的责任条款也要报告条数，交 T057 决定是否合并。

## 2. 实施步骤

### 第 1 步　固定旧版本，生成基线审计

1. 只读打开旧 KB、`ds-8410`、`ds-16741` 和三个历史 run（`run-20261117-022645`、`run-20261117-081504`、`run-20261118-020130`），记录路径和 sha256。
2. 诊断脚本放在 `scripts/t077/`，产物写入 `artifacts/logs/t077/`。抽取试验用独立产物目录，避免覆盖已有的 `kb-20261113-093057-relations_pending.jsonl`。
3. 输出 `baseline_audit.md`，引文片段不超过 15 字：8 个问题的证据（责任条款片段、旧端点、该条款与项结构）；另 4 对 `liability_for` 和 23 条 `references` 的偏差与漏抽；历史数据集中关系样本按文本匹配归因的明细（标明无法归因的记录）；v1 gold 的条、款分布；历史 SC-005 数值。

### 第 2 步　落地编号、校验与样本口径

1. **派生新 KB（口径 2/3）。** 新增派生命令或脚本：复制旧库后更新多款条文第一款主行及其各项的 `number_text`，写新的 `manifest.json`（派生来源、源库 sha256、变更计数）。[parse.py](../../src/tu_assistant/kb/parse.py) 同步改为同样规则，并由单测保证重新导入的结果与派生结果一致。
2. **校验层（口径 1）。** 按该条不同 `paragraph_no` 的个数判断：只有 1 款时直接定位主行，原文自动拼上各项；2 款及以上按选定方案处理。
3. **样本。** `relation_samples` 改用 `_canonical_text`。统计 `check.py` 放行了多少带 `incomplete` 引用的样本，只报告，是否拦截交 T057 决定。统计口径 2 影响的知识样本数。

### 第 3 步　修正抽取、审阅展示与确认入口

1. **[relations.py](../../src/tu_assistant/kb/relations.py)**：按口径 4 扩展。每条候选写入 `evidence`（触发片段）和 `scope`（明指款、明指项、整条展开），只进入 pending JSONL，不改 SQLite 表结构。
2. **`review`**：用 `_canonical_text` 展示完整原文，显示被引条共几款、当前候选指向第几款，以及触发片段。
3. **`confirm` 改为事务化差异导入**：
   - 显式指定 KB 版本，拒绝写入被 manifest 标记为历史的版本；
   - 审阅文件中 `revoke` 的旧边删除，确认的新边插入，拒绝和待查的边不生效，文件未列出的已确认关系保留；
   - 整批放在一个事务中，遇到坏行或不存在的端点时整批回滚；
   - 同一批次重复导入结果不变；
   - manifest 记录批次、审阅文件哈希和确认统计。
4. 同步更新 [relations-confirm-guide.md](../relations-confirm-guide.md)。

### 第 4 步　生成候选，停下等待 T019 审阅

1. 在派生的新 KB 上运行 `uv run tu kb relations extract --kb-version <新版本>`。输出候选数，以及与旧 35 条的增删改对照（每行含 from/to 完整 ID、款数、触发片段、旧边、新建议、待确认项）。
2. **人工关卡。** 用户审第一批，逐项标注确认、拒绝或待查，并列明撤销的旧边。审阅前只在测试库试导入；正式 KB 以确认清单为准导入。
3. 导入后对账：新库只含审定变更，旧错边已撤销，旧库 sha256 与第 1 步一致。

### 第 5 步　用相同输入核对下游差异

| 对象 | 方法与产物 |
|---|---|
| 知识关系样本 | 两版 KB 各跑 `relation_samples` 和 `check_sample`，按依据 ID、责任 ID、引用文本列增删改；对照历史数据集中实际落盘的样本（split、重复次数）→ `relation_samples_diff.md` |
| 校验层 | 用新校验器对三个历史 run 的 `final_raw` 重新打分，与已存的 `cited_clause_ids` 逐题对账；按口径 C，预期判定不变，第一款回退次数单列 → `reverify_diff.md` |
| SC-005 | ①对历史 run 重算（预期分母为 0，作为“无变化”证据）；②构造固定诊断例（覆盖错款、整条展开、同一责任条款被多款指向），先固定引用 ID 只换关系表，再走完整校验，区分关系变化和解析变化 → `sc005_diff.md` |
| 评测兼容 | v1 两个 jsonl 的全部 gold ID 在新 KB 中可解析；`tu eval compare --sc016` 照旧复现（只作回归，不用来证明校验层没变） |
| 文章素材 | 新 KB 上 `_materials` 的 `paragraph_mismatch == 0`，记录可用责任关系对数和同文件多违法组合数，反馈给 T057；“多违法能否发生于同一纠纷”留给 T057 审阅 |

### 第 6 步　adapter 实测

本地起 `uv run tu serve model --exp exp-20261116-resume500`。用只读探针（`temperature=0`）测 8 处问题，每处三种问法：训练分布的条号问法、正确款号问法、第一款对照问法。记录原始回答与校验结论，写入 `adapter_probe.md`。结论只依据实测：模型记住的是错款还是正确款，T075 是否需要纠偏样本。

### 第 7 步　测试、学习文档与交付

1. **测试**：
   - 新增 `tests/unit/test_relations.py`：明确第 2/4 款、款项并列、区间、整条展开、自引用、无效编号；
   - 确认入口：撤销加新增、重复导入、坏行回滚、拒绝写入历史 KB；
   - 补充 `test_parse.py`、`test_citation.py`、`test_citation_verify.py`、`test_metrics.py`（SC-005 去重）；
   - 跑全量 `uv run pytest` 和 `uv run ruff check src tests`。
2. **学习文档**：在 [03-knowledge-base.md](../learning/03-knowledge-base.md) 按现有编号补节，用一条实际修订说明整条引文、第一款引文和责任关系的区别，以及抽取、审阅、校验三层如何联动；更新 [00-glossary.md](../learning/00-glossary.md)。
3. 若需改[引用契约](../../specs/001-legal-clause-assistant/contracts/citation-format.md)的措辞，列出差异交用户审阅。
4. 在本单末尾追加实施记录（口径、旧/新 KB 版本与校验值、关系差异、对账结果、实测、待验项）。T077 与 T019 分别记录验收状态，勾选和提交待用户确认。

## 3. 验收标准

- [x] 旧 KB、历史数据集与 run 的 sha256 与第 1 步一致；`baseline_audit.md` 复现了 8 个问题。
- [x] 新 KB 由旧库派生：`clause_id` 集合与原文一致，差异只在 `number_text` 和已审定的关系。
- [x] 第一批审阅已导入，旧错边已撤销，拒绝和待查项未生效；重复导入、坏行回滚测试通过。
- [x] `reverify_diff.md` 显示历史 run 判定与口径一致；`sc005_diff.md` 用诊断例证明差异，同一责任条款不重复计分。
- [x] `relation_samples_diff.md` 给出逐条增删改，以及口径 2 影响的样本数。
- [x] `adapter_probe.md` 给出 8 处问题的实测结论（只调用本地端点）。
- [x] `uv run pytest` 与 `ruff` 通过；学习文档已更新；未读取 `inputs/`；提交待用户同意。

## 4. 不在本单范围

- 不存在的款号改判 `not_found`（另立任务）。
- `check.py` 是否拦截 `incomplete` 引用的样本（本单只统计，T057 决定）。
- 第二批 `references`、`exception_of` 的人工审阅（完成后才勾选 T019）。

---

## 5. 实施记录 · 待复审（2026-11-19）

### 5.1 版本与校验值（历史产物零改动）

| 产物 | 版本 / 路径 | SHA-256（前 16 位） | 说明 |
|---|---|---|---|
| 历史旧 KB（只读保留） | `artifacts/kb/kb-20261113-093057.sqlite` | `e6a964968c69b7cc` | 与第 1 步基线一致，18 个历史文件全部 0 偏差 |
| 派生新 KB（最终态） | `artifacts/kb/kb-20261119-045641.sqlite` | `2680cc54b31b4686` | 由旧库派生：更新 787 条多款条文第 1 款及子项共 1,026 行 `number_text`；`clause_id` 与原文零变化 |
| 第一批审阅文件 | `artifacts/kb/kb-20261119-045641-batch1-liability_review.jsonl` | 记入新 KB `manifest.json` | 共 29 行：用户审定 `revoke` 6、`confirm` 20、`reject` 3、`pending` 0 |

### 5.2 代码与文档变更

- **KB 编号与派生**：[parse.py](../../src/tu_assistant/kb/parse.py)（多款条文第 1 款及子项显式标 `第1款`）、[derive.py](../../src/tu_assistant/kb/derive.py)（无损派生新 KB 并校验不变量，写 `writable: true`）、[ingest.py](../../src/tu_assistant/kb/ingest.py)（新导入 KB 标 `writable: true`）、[store.py](../../src/tu_assistant/kb/store.py)（新增 `delete_relation`）。
- **抽取、审阅与事务化确认**：[models.py](../../src/tu_assistant/kb/models.py)（`evidence`/`scope` 仅落 pending JSONL，不改 SQLite 表结构）、[relations.py](../../src/tu_assistant/kb/relations.py)（款/项捕获、并列/区间拆解、整条按款展开、拒写历史/被引用库、原子事务 `apply_relations_diff`）、[cli.py](../../src/tu_assistant/cli.py)（`tu kb derive`、`tu kb relations extract --out`、四态 `review` 含完整子项原文与总款数提示、事务化 `confirm --kb-version`）、[relations-confirm-guide.md](../relations-confirm-guide.md)。
- **校验层与下游去重**：[citation/models.py](../../src/tu_assistant/citation/models.py) & [verify.py](../../src/tu_assistant/citation/verify.py)（单款含项无款号直接定位 `aN:p1`；口径 C 多款引文回退以 `fallback_para_matches` 单独计数）、[knowledge.py](../../src/tu_assistant/synth/knowledge.py)（`relation_samples` 改用 `_canonical_text` 并修复 `references`/`exception_of` 的 `meta.clause_ids` 与助手引文一致）、[metrics.py](../../src/tu_assistant/eval/metrics.py)（SC-005 按去重责任条款计分）、[orchestrator.py](../../src/tu_assistant/chat/orchestrator.py)（系统补充条款保序去重）。
- **学习文档**：[03-knowledge-base.md](../learning/03-knowledge-base.md) 新增 `[L3.4.1]` 并更新 L3.4 / L3.5；[00-glossary.md](../learning/00-glossary.md) 补充术语。
- **诊断脚本**：`scripts/t077/`（`baseline_audit.py`、`prepare_batch1.py`、`prescreen_relations.py`、`reverify_runs.py`、`compare_downstream.py`、`adapter_probe.py`），全部产物写入 `artifacts/logs/t077/`。

### 5.3 第一批人工审阅与导入对账

- 新规则在新 KB 上全量抽取 89 条候选（`liability_for` 29、`references` 60）；结合 DeepSeek 离线预审（`artifacts/logs/t077/batch1_prescreen.md`，35 次调用、`input_source="kb_clause"`，不自动确认）与用户逐条核对：
  - **撤销 6 条旧错款边**：`a10:p1→a38:p1`、`a15:p1→a39:p2`、`a22:p1→a79:p1`、`a40:p1→a77:p1`、`a41:p1→a78:p1`、`a6:p1→a13:p1`；
  - **确认 20 条新增 `liability_for`**：含 6 条修正款、整条展开款与并列/区间新增款；
  - **拒绝 3 条**：行 13（《工会法》第三条第 2 款，属工会职责宣示非第五十一条罚则对象）、行 24–25（《公司法》第一百五十四条第 2/3 款 → 第一百条，属认股书载明事项而非法律责任）。
- 导入后新 KB `kb-20261119-045641` 共含已确认关系 **49 条**（`liability_for` 26 条、`references` 23 条保持原样留待第二批）。

### 5.4 下游对账结果（全部归档至 `artifacts/logs/t077/`）

1. **基线审计与口径 2 影响面**（`baseline_audit.md` / `relation_samples_diff.md`）：
   - `ds-8410/train` 受多款第 1 款编号变更影响 **1,556 / 8,921（17.4%）**，未超 20% 阈值；`ds-16741/train` 为 **2,618 / 19,195（13.6%）**；KB 复述样本（长度 ≥10）受影响 **961 / 3,722（25.8%）**。
   - `check.py` 放行的含 `incomplete` 引用样本（只统计，交 T057 决策）：`ds-8410/train` 743 行（含关系样本 1 行），`ds-16741/train` 1,385 行（含关系样本 2 行）。
   - `relation_samples` + `check_sample`：旧 KB 35/35 通过，新 KB **49/49** 通过（补齐带子项完整原文并修复 `references` 的 `clause_ids` 期望）。新 KB 中共有 5 个责任条款被多条依据共享（3–5 条不等），明细已记录供 T057 决定是否合并问答。
2. **普法文章素材池**（`relation_samples_diff.md` §5，反馈 T057）：
   - `paragraph_mismatch`：`6 → 0`；
   - 可用责任素材对（`eligible`）：`6 → 26`；
   - 同文件不同责任条文的成对多违法候选组合：`2 → 20`（覆盖 4 部法规；具体能否共场景留待 T057 人工审阅）。
3. **校验层历史对账**（`reverify_diff.md`）：
   - 三个历史 run（`run-20261117-022645` / `081504` / `020130`）在旧/新 KB 上多款兼容回退均为 **0** 次；
   - 除 `run-20261117-081504` 的 `cand-037`（单款含项修复带来的 1 题预期变化，不影响 9/60）外，其余 179 题/次 `cited_clause_ids` 完全一致；
   - `eval/cases/v1/reviewed.jsonl`（60 题）与 `articles.jsonl`（18 条 gold）在新 KB 中 0 缺失；`tu eval compare --sc016 run-20261117-022645 run-20261117-081504` 仍为 PASS（1→17/60、9/60、0→21/30，退出码 0）。
4. **SC-005 对比**（`sc005_diff.md`）：
   - 历史 run 重算：`run-20261117-022645`、`081504` 仍为 0；`run-20261118-020130` 从 0 变为 **1**（`cand-015` 引用了 `40124ed5e360acee:a21:p2`，新 KB 整条展开后成功触发 SC-005=0.000）；新 26 条 `liability_for` 与 v1 全部 gold 交集仍为 0。
   - 固定诊断例（D1–D6、T1–T4）逐一验证：撤销旧错边不再误扣分、修正款与区间新增生效、共享责任条款去重（`a21:p1+p2` 与 `a3:p1` 仅补 `a40:p1` 计 `1/2 = 0.500` 而非 `2/3`）。

### 5.5 已训练 Adapter 实测（`adapter_probe.md`）

- 本地起 `tu serve model --exp exp-20261116-resume500`（`model=default_model`，`temperature=0`），对 8 处问题 × 3 种问法共 24 条探针实测：
  - **精确命中目标责任条款**：0 / 24；**引出旧错款 `p1` 或正确款**：0 / 24；
  - **宽松命中目标责任条号**：仅 P2（第三十九条）与 P6（第十三条）在 A/B/C 三种问法下命中条号（2/6 组），且均因未写款号被判 `incomplete`；
  - 同一问题的 B（正确款号）与 C（第 1 款对照）问法输出条款号完全相同，说明旧 adapter 既未顽固记死旧错款，也未掌握款级责任对应；T075 续训时无需额外设计负样本遗忘，由 T057 合入新 KB 的 26 条修正后关系样本与对应普法文章样本覆盖学习即可。

### 5.6 自动化验证与待用户确认项

- **测试与 Lint**：`uv run pytest` **180 passed, 6 xfailed**，`uv run ruff check src tests scripts/t077` 全通过；18 个历史产物文件 SHA-256 核验 0 改动；全程未读取 `inputs/`。
- **建议审阅的契约措辞微调（暂未改契约文件）**：[citation-format.md](../../specs/001-legal-clause-assistant/contracts/citation-format.md) §1/§2 可增补一句说明：“单款条文（含单款多项）可省略款号；多款条文须显式写明款号（含第1款），省略款号仅在引文与某款原文逐字唯一匹配时做兼容回退，否则记为 `incomplete`。”
- **验收状态**：
  - **T077**：全部实施与验收项已产出，标记**待复审**，经用户审阅确认后再在 [tasks.md](../../specs/001-legal-clause-assistant/tasks.md) 勾选并决定提交。
  - **T019**：第一批（`liability_for`）已完成审阅并导入新 KB；第二批（`references` / `exception_of`，见 `candidates_diff.md` §4，含 4 条旧偏差与 41 条新增候选）待后续审阅导入后再勾选 T019。

---

## 6. 独立复审（2026-11-19）

**复审结论：通过（无阻塞项）。** 全部核心目标、代码实现、数据对账与自动化测试均已独立核实通过。以下整理核实结果、非阻塞改进建议及三项收尾处理意见，供实施方按用户最终确认落实后再勾选 [tasks.md](../../specs/001-legal-clause-assistant/tasks.md) 中的 T077（T019 保持不勾）、勾选本单第 3 节验收框并执行 commit（不 push）。

### 6.1 独立核实摘要

| 核实项 | 结果 |
|---|---|
| 测试与 Lint | `uv run pytest`（180 passed, 6 xfailed）与 `uv run ruff check src tests scripts/t077` 全通过 |
| 旧 KB 只读性 | `kb-20261113-093057.sqlite` SHA-256 为 `e6a96496…`，与第 1 步基线一致、零改动 |
| 新 KB 关系对账 | 共 49 条已确认关系：`liability_for` 26（12 − 撤销 6 + 新增 20）+ `references` 23；manifest 记录撤销 6、实际删 6 |
| 8 个已知问题逐条查库 | 6 条错款边已撤销并替换为正确款（如 `a10:p2`、`a40:p4`、`a6:p2`）；漏抽 `a7`/`a9:p1`/`a12` 已补齐；`a21` 展开 p1–p3；用户拒绝项（含《工会法》第三条第 2 款等 3 条）未生效 |
| 抽取与引文解析抽样 | 区间、并列、款区间、项区间、倒序区间解析正确；新格式 `第十条第1款第一项` 校验层可正常解析 |
| 关键代码审查 | `confirm` 事务化导入与坏行回滚、派生不变量校验、SC-005 与关联补全去重、`relation_samples` 带子项完整原文均符合执行单口径 |
| 历史对账 | `cand-037`（单款含项修复）与 `cand-015`（SC-005 首个有效分母）的变化均属预期且说明清晰 |

### 6.2 非阻塞改进建议（收尾或后续处理）

1. **默认 KB 变更提示**：CLI 不带 `--kb-version` 时现默认指向 `kb-20261119-045641`。复现 T075 历史结果须显式传 `--kb-version kb-20261113-093057`，建议在实施记录中补一句提示。
2. **新 KB 可写窗口与引用检查范围**：一旦 T057 生成的数据集或评测 manifest 引用了 `kb-20261119-045641`，`confirm` 会拒绝再写入。因此 T019 第二批（`references` / `exception_of`）需在 T057 之前导入，或之后再派生新 KB。另 `_find_kb_references` 目前仅扫 `datasets/` 和 `eval/`，不含 `synth/` 与 `train/`，当前影响不大，记作后续留意。
3. **撤销不存在的边**：当 `revoked_deleted < revoked` 时目前静默成功，建议至少打印警告，便于人工发现审阅清单中的失效旧边。
4. **事务与 manifest 写入顺序**：SQLite `COMMIT` 后再写 `manifest.json`，若写 manifest 失败会产生短暂不一致；本地 POC 可接受，知悉即可。
5. **交接 T057 的补充提醒**：口径 2 影响全训练集 17.4%（未触发 20% 阈值），但 KB 复述类样本受影响比例达 **25.8%**，建议在交接给 T057 时专门点出。

### 6.3 三项收尾处理意见（经用户确认口径）

1. **第一批人工审阅结果留存（不放开 `artifacts/`）**
   - **不建议**将 `artifacts/` 从 `.gitignore` 排除：该目录含 SQLite、adapter、数据集、评测 run 等大文件/二进制文件，且整目录忽略改为白名单规则容易误提交。
   - **建议做法**：把人工决策作为源数据入库，KB 继续作为可重建产物——新建受版本控制的目录（如 `data/relation-reviews/`），将 `artifacts/kb/kb-20261119-045641-batch1-liability_review.jsonl`（29 行，仅含 clause ID、决策及十余字触发片段，对应语料均已公开入库）复制入库，并与新 KB `manifest.json` 中的 `file_sha256` 核对一致。
   - **补齐重建链**：同时建议找回 T018 旧库原有 35 条已确认关系的确认文件一并放入同一目录，使 `inputs/ → tu kb import → tu kb derive → tu kb relations confirm` 整条链可从 git 完整复现。后续 T019 第二批审阅文件也放该目录，并在 [relations-confirm-guide.md](../relations-confirm-guide.md) 中写明“人工审阅文件入库，KB 不入库”。
2. **保留 astra 版与 neon 版草稿执行单**
   - 用户确认**保留**（本单开头直接链接了两份文件，删除会导致断链）。
   - 建议在 [T077-kb-clause-relations-handoff-astra.md](T077-kb-clause-relations-handoff-astra.md) 与 [T077-relation-granularity-handoff-neon.md](T077-relation-granularity-handoff-neon.md) 开头各补一行归档声明（“已被 `T077-relation-clause-handoff.md` 合并取代，仅作归档”），避免后续误照旧版执行。
3. **[citation-format.md](../../specs/001-legal-clause-assistant/contracts/citation-format.md) 契约微调（只写规则，不写实现）**
   - 修改目的**不是**把实施记录写进契约，而是消除契约与校验层实际行为的不一致：当前 §1 写款号为“可选 `第M款`”、§2 `incomplete` 只列了裸引用，与校验层规则不符。
   - **建议写入的规范规则**：“单款条文（含单款多项）可省略款号；多款条文须显式写明款号（含第1款），省略款号仅在引文与某款原文逐字唯一匹配时才算有效，否则判为 `incomplete`。”（若希望契约保持最简，至少把 §1“可选 `第M款`”改为“单款条文可选”。）
   - **不写入契约**：`fallback_para_match` 计数、“口径 C”命名、T077 任务编号等过程与实现细节，这些保留在本执行单即可。

### 6.4 收尾落实记录（2026-11-19，用户确认）

- **审阅文件入库**：新建 `data/relation-reviews/`，归档旧库基线 35 条审阅文件（`kb-20261113-093057-relations_pending.jsonl`，SHA-256 `3ebd6052ce3cb31a`）与本次第一批 29 行审定文件（`kb-20261119-045641-batch1-liability_review.jsonl`，SHA-256 `014b8379e03f323c`，与新 KB `manifest.json` 的 `file_sha256` 一致）；[relations-confirm-guide.md](../relations-confirm-guide.md) 已注明“人工审阅文件入库，KB 不入库”及完整重建链。
- **草稿归档声明**：[T077-kb-clause-relations-handoff-astra.md](T077-kb-clause-relations-handoff-astra.md) 与 [T077-relation-granularity-handoff-neon.md](T077-relation-granularity-handoff-neon.md) 开头均已补充取代归档声明。
- **契约微调**：[citation-format.md](../../specs/001-legal-clause-assistant/contracts/citation-format.md) §1/§2 已按 §6.3 第 3 条更新规范规则（不含实现细节）。
- **非阻塞改进与交接提示**：
  - `tu kb relations confirm` 在 `revoked_deleted < revoked` 时已输出黄色告警，并在 `tests/unit/test_relations.py` 补测覆盖；
  - **默认 KB 变更提示**：CLI 不带 `--kb-version` 时现默认指向 `kb-20261119-045641`，复现历史实验须显式传 `--kb-version kb-20261113-093057`；
  - **可写窗口提示**：T019 第二批（`references` / `exception_of`）须在 T057 数据集引用 `kb-20261119-045641` 之前导入，否则需再派生新 KB；
  - **交接 T057 提醒**：口径 2 影响全训练集 17.4%，但 KB 复述类样本受影响达 **25.8%**（961/3,722），T057 组数据与配比时需重点考量。
- **勾选状态**：本单第 3 节验收框及 [tasks.md](../../specs/001-legal-clause-assistant/tasks.md) 中 **T077** 已勾选，**T019** 保持未勾选待第二批完成后处理。
