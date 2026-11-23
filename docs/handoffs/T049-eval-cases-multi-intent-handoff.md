# T049 执行单 · 评测集 v1 扩充：多违法行为、多轮意图确认与咨询边界用例

**状态：已验收完成（2026-11-23）。** 基于主线提交 `594ec36`（T062 已验收提交）。本执行单承接 Phase 3 / US1 的唯一剩余未勾项 **T049**，并顺接用户在 T061/T063 与 T062 中批准的推进路径，为 `eval/cases/v1/` 补齐**多违法行为（`multi_violation`，SC-004）**与**多轮意图确认固定对话脚本（`intent`，SC-001）**用例（并同步补齐 8 题咨询类 `refusal` / `false_refusal` / `exception` 边界用例，全部 4 项决策均按推荐选项 A 实施），使后续 **T064（7B 重复评测 2 次验证 SC-015 并核销 T059）** 能一次性产出覆盖 SC-001 ~ SC-011 全指标的完整 V5 报告，避免重复跑 7B 评测。

> **合规与红线声明**：起草、核对与实施全过程**严禁读取 `inputs/` 目录下任何文件**；**严禁改动历史正式评测基线**（`eval/cases/v1/reviewed.jsonl`、`eval/cases/v1/articles.jsonl`）与**历史产物**（历史 KB、历史数据集、已训权重及历史 `artifacts/eval/<run_id>/`）；**用户未逐题审定前，任何候选用例不得写入 `eval/cases/v1/`**；运行时与评测模块严格保持零外部 LLM 客户端导入约束。

---

## 1. 推荐任务编号与选择理由

**推荐任务：`T049` [US1]（编写评测集 v1 的多违法行为与意图确认固定对话脚本用例约 20 题，加入 `eval/cases/v1/`，由用户审阅确认）。**

### 1.1 为什么优先做 `T049`？

1. **直接承接已批准的推进节奏**：在 `T061 + T063` 与 `T062` 执行单中已确立并获批准的推进顺序为：
   `T061 + T063`（已完成） → `T062`（已完成） → **`T049`（本单）** → `T064`（7B 重复评测 2 次验证 SC-015 并同步核销 `T059`） → `T065`（整理 `docs/learning/06-evaluation.md`）。
2. **解除 `T064` / `T059` 核销与 quickstart V5 的直接阻塞，避免重复跑 7B**：
   - 经只读摸底，当前 `eval/cases/v1/` 仅有 **70 题**（`reviewed.jsonl` 60 题 `clause_id` + `articles.jsonl` 10 题 `article`），**`multi_violation`（SC-004）与 `intent`（SC-001）均为 0 题**（此外咨询类 `refusal`、`false_refusal`、`exception` 也均为 0 题）；
   - `specs/001-legal-clause-assistant/quickstart.md` V5 明确要求评测报告覆盖 SC-001 ~ SC-011，并在同模型重复运行中验证 SC-015（波动 ≤ 2 个百分点）；
   - 若跳过 `T049` 先跑 `T064`，SC-001 与 SC-004 均为 `-`（无样本），等 `T049` 完成后又得在完整 v1 上重跑 2 轮 7B 评测，造成重复算力与时间浪费。
3. **收口 Phase 3（US1 / MVP）的唯一剩余未勾项**：完成后 Phase 1–3（除已明确移出 POC 的 `T078`）全部闭环。
4. **下游工具与历史兼容防线已全部就绪**：`T048`（SC-001/SC-004/SC-005/SC-008 指标）、`T061 + T063`（完整报告与待审清单）、`T062`（通用多 run 对比与目录型评测集扩题兼容 `run.rows ⊆ chk.case_ids`）均已验收合入，T049 往 `eval/cases/v1/` 增量新增 `.jsonl` 文件不会破坏任何既有历史对比。

### 1.2 与其他未完成候选任务的横向对比

| 候选任务 | 当前状态与前置条件 | 为何优先做 `T049` |
|---|---|---|
| **`T049`（推荐）** | Phase 3 US1 唯一未勾项；`multi_violation` 与 `intent` 指标代码（T048）、报告（T061）及扩题兼容对比（T062）已全部就绪 | 补齐评测集 SC-001 / SC-004（及可选 SC-008 咨询边界）样本缺口，直接为 `T064` + `T059` 核销提供完整 v1 评测集 |
| **`T064`（7B 重复评测 2 次验证 SC-015）与 `T059` 核销** | 依赖完整 v1 评测集与 `T062`；用户在 T056 已拍板 `T059` 留待 `T064` 后核销 | 应紧随 `T049` 之后执行，在完整 v1 上一次性完成 2 次 7B 重复评测与 SC-015 校验，避免返工重跑 |
| **`T065`（撰写 `docs/learning/06-evaluation.md` 完整章节）** | 已按实现进度累积至 `[L6.1]–[L6.5]` | 需要 `T064` 在完整 v1（含多违法行为、意图确认、拒答）上的真实 7B 实测结果来分析薄弱类别并反推数据改进方向 |
| **Phase 6（`T066–T068`，US4 知识库维护）** | P4 优先级，模块独立（`kb/diff.py`、配置切换 `kb.version`、更新集成测试） | 不阻塞 Phase 5 评测闭环与 `T059` 核销；适合在 Phase 5 完成后（或与 `T049` 人工审题等待期穿插）推进 |
| **Phase 7（`T069–T074`，Gradio UI 与收尾）** | 最终演示界面、演示脚本、V1–V7 全量验证与复盘 | 强依赖 Phase 5 与 V5（SC-001 ~ SC-011 完整报告 + SC-015）收口 |
| **`T078`** | 已标记 `[Post-POC / 正式阶段]` | 2026-11-19 已由用户确认移出 POC 范围，不纳入候选 |

---

## 2. 现状与只读摸底核实

以下数据、接口签名与代码行为均经仓库只读核实（未触碰 `inputs/`）：

### 2.1 当前代码、知识库与评测集基线

- **代码与测试基线**：`594ec36`（`feat(eval): implement multi-run compare and SC-015 stability check (T062)`），`uv run pytest` **414 passed / 6 xfailed**，`ruff` 全绿。
- **历史产物哈希锁**：`shasum -a 256 -c artifacts/logs/t075/01/output.sha256` **25/25 OK**（须全程保持零改动）。
- **活跃知识库**：`artifacts/kb/kb-20261119-045641.sqlite`
  - 共 **24 篇**现行法规（`status='current'`）、**3,809 条**条款记录；
  - 共 **67 条**已确认条款关联（`confirmed=1`）：其中 **`liability_for` 26 条**（覆盖 6 部法规：《中华人民共和国工会法》《女职工劳动保护特别规定》《中华人民共和国妇女权益保障法》《中华人民共和国公司法》《上海市集体合同条例》《上海市就业促进条例》）、**`references` 41 条**（覆盖 8 部法规）；
  - **T078 已知缺陷避让**：《上海市工伤保险实施办法》（`doc_id=9fc301cd90566af9`）存在括号条旨被误切导致款号整体顺延 +1 的已知缺陷（已移出 POC），**T049 所有新增用例一律避开该文件**。
- **现有正式评测集 `eval/cases/v1/` 盘点（共 70 题，在 `kb-20261113-093057` 与 `kb-20261119-045641` 上 `validate_gold_clauses` 均为 0 问题）**：

| 文件 | 题数 | 类别分布 | Git blob（须保持只读不变） | 备注 |
|---|---:|---|---|---|
| `eval/cases/v1/reviewed.jsonl` | 60 | `clause_id: 60` | `63a1f9533e78fb71fd9bf99bb1fb663127eb22eb` | T076 `--sc016` 历史 run 直接绑定该单文件 |
| `eval/cases/v1/articles.jsonl` | 10 | `article: 10`（含 1 题 `should_refuse=true`） | `fc72e84a5c591f73556330bbe1e62989201fe912` | T058/T054 历史文章基线 |
| **当前缺失类别** | **0** | `multi_violation=0`、`intent=0`、`refusal=0`、`false_refusal=0`、`exception=0` | — | SC-001、SC-004 无样本；SC-008 范围外仅 `article-007` 1 题、专设误拒题 `0/0` |

### 2.2 源码接口与打分契约摸底（关键风险提前排雷）

逐行核查 `src/tu_assistant/eval/{cases,metrics,runner,report,compare}.py`、`src/tu_assistant/chat/{orchestrator,anonymize}.py`、`src/tu_assistant/synth/evalcases.py` 与 `src/tu_assistant/cli.py`，确认以下 6 项直接影响 T049 用例设计的硬约束：

1. **目录加载与历史对比兼容性（`eval/cases.py` L38–59、`eval/compare.py` L137–223）**：
   - `load_cases("eval/cases/v1")` 按 `sorted(p.glob("*.jsonl"))` 加载目录下全部 `.jsonl`；
   - 因此 T049 必须将新用例写入**独立的 `.jsonl` 文件**（如 `multi_violation.jsonl`、`intent.jsonl`、`boundaries.jsonl`），严禁修改 `reviewed.jsonl` 或 `articles.jsonl`；
   - `T076 --sc016` 历史 run 指向单文件 `eval/cases/v1/reviewed.jsonl`，完全不受影响；`T062` 通用对比已支持目录扩题子集兼容（`set(run.rows) ⊆ chk.case_ids`），历史目录型 run（如 `run-20261120-183952`）继续可比。
2. **`multi_violation`（SC-004）与 SC-002/SC-003/SC-005 的联动契约（`eval/cases.py` L71–86、`eval/metrics.py` L60–90、`eval/runner.py` L108–125）**：
   - `validate_gold_clauses` 会校验 `gold.clauses` 及每个 `gold.violations[i]` 下的 `clauses` 与 `liability` 全部存在于知识库；
   - `multi_violation_score(cited_ids, gold_violations)` 逐条检查 `bool(cited_ids & set(v.get("clauses", [])))` 并求平均（主体名称匹配在 POC 写入 `rubric` 供人工复核，见 `metrics.py` L64–65）；
   - `runner.py` 同时对 `final_raw` 计算 SC-002（recall）、SC-003（precision）和 SC-005（`relation_completion_score`，基于已确认 `liability_for` 关联）；
   - **字段对齐要求**：每条 `v` 须含非空 `actor`、`clauses`（与适用的 `liability`），且 **`gold.clauses` 必须设为所有 `v["clauses"]` 与 `v["liability"]` 的去重并集**——这样模型补全法律责任条款时既提升 SC-005，也不会在 SC-003（precision）被误判为“多引无关条款”。
3. **`intent`（SC-001）与 `classify_turn_intent` 的“防伪确认”陷阱（`chat/anonymize.py` L241–281, L580–644、`eval/metrics.py` L225–237）**：
   - `intent_score(turns, gold, max_turns=3)` 判定 `turns[:3]` 中是否出现 `t.get("intent") == gold["intent"]`；
   - `classify_turn_intent` **仅可能返回 `"consult"`、`"article"` 或 `None`**（与 FR-010 一致），其判定顺序为：
     1. 用户消息命中 `_RE_EXPLICIT_WRITE` / `_RE_EXPLICIT_REVISE` / `_RE_ELLIPTICAL_REVISE` → 直接返回 `"article"`（T054 为确保 FR-030 隐私脱敏宁严勿漏而设）；
     2. 用户消息命中 `_RE_NEGATE_ARTICLE` 或 `_RE_EXPLICIT_CONSULT`（含 `只问|只想问|单纯咨询|条款适用吗|适用吗|合法吗|违法吗|构成违法吗|怎么处理|怎么维权|怎么办|有什么法律责任|承担什么责任|是不是必须`）→ 直接返回 `"consult"`；
     3. 否则检查助手回复是否符合文章结构（≥2 个小节或 H1 + ≥1 个小节）→ `"article"`，或是否含咨询结构（`违法行为认定|适用条款|法律责任`）或条款引用（`has_citation`）→ `"consult"`；
     4. 均不命中 → 保持 `current_intent`（第 1 轮即 `None`）。
   - **由此得出 3 条必须遵守的出题硬规则**：
     - **规则 A（第 1 轮零触发词）**：`intent` 题第 1 轮模糊开场必须通过 `classify_user_intent_signals(turn1, article_task_active=False)` 全 `False` 校验——绝不写“合法吗/怎么办/写文章”等显式词，杜绝第 1 轮被正则“伪确认”；
     - **规则 B（咨询收敛轮让模型真考）**：`gold.intent="consult"` 的第 2/3 轮确认句使用自然表达（如“我想了解相关的法律规定，具体情况是……”），不触发 `_RE_EXPLICIT_CONSULT`，使 `session.intent` 必须依靠模型实际给出咨询结构或条款引用才转为 `"consult"`；
     - **规则 C（不支持需求归 `refusal`，不放 `intent`）**：因 `classify_turn_intent` 永不返回 `"refusal"`，测试 FR-014（“帮我起草仲裁申请书”）的多轮/单轮用例不能放进 `category="intent"`（否则 SC-001 必然判 0），应放入 `category="refusal"`（设 `gold.should_refuse=true`）由 SC-008 正确度量。
   - **诚实记录测量边界**：对于 FR-013 中途切换至普法文章（`gold.intent="article"`）的脚本，用户明确要求写文章会按 FR-030 安全护栏触发 `_RE_EXPLICIT_WRITE` 使 `intent="article"`；本任务不破坏 T054 隐私护栏，该测量边界通过逐题 `rubric` 人工核对交付内容与在 `[L6.6]` 中明确说明来兜底。
4. **去重单测约束（`tests/unit/test_synth_articles.py` L637–696、`src/tu_assistant/train/dataset.py` L57–82）**：
   - `test_revision_user_prompts_do_not_overlap_v1_eval` 与 `test_t057_n4_vague_modes_and_prompt_bank_no_eval_overlap` 会自动加载整个 `eval/cases/v1` 目录，要求与文章提示词模板池 3-gram Jaccard ≥ 0.8 的重叠数为 **0**；
   - 同样需用 `dedup_against_eval` 只读核对既有训练集 `ds-kb-20261113-093057-8410` 与 `ds-kb-20261119-045641-8247`（`train.jsonl` + `valid.jsonl`），确保新增问句与训练问句零高重合（宪章原则 V）。
5. **现有候选生成/审阅 CLI 的能力核实**：
   - `src/tu_assistant/synth/evalcases.py` 当前仅支持单轮 `clause_id` 生成，不支持 `multi_violation` 与多轮 `script`；
   - `src/tu_assistant/cli.py`（L889–923）中 `tu eval cases review` 当前未展示 `gold.violations`、`gold.intent` 与 `source`；`tu eval cases promote`（L971–1000）无条件覆写 `row["source"] = "synthetic_reviewed"`（若用例为手工原创 `source="manual"` 会被误覆写，见第 6 节决策 4）。

---

## 3. 实施边界、用例蓝图与约束

### 3.1 文件变更边界

| 文件 | 操作 | 职责 |
|---|---|---|
| `eval/cases/candidates/multi_violation.jsonl` | **新增** | 多违法行为候选用例（`mv-001` ~ `mv-010`，`confirmed=false`），供用户审题 |
| `eval/cases/candidates/intent.jsonl` | **新增** | 多轮意图确认固定对话脚本候选（`intent-001` ~ `intent-010`，`confirmed=false`），供用户审题 |
| `eval/cases/candidates/boundaries.jsonl` | **新增（决策 1 选项 A）** | 咨询边界候选（`refusal-001..003`、`false-refusal-001..002`、`exc-001..003`，共 8 题），供用户审题 |
| `eval/cases/v1/multi_violation.jsonl`、`intent.jsonl`（及可选 `boundaries.jsonl`） | **新增（仅在用户逐题审定确认后）** | 正式评测集增量文件；与既有 `reviewed.jsonl` / `articles.jsonl` 完全隔离 |
| `src/tu_assistant/cli.py` | **小幅修改（决策 4 选项 A）** | `eval cases review` 补齐显示 `violations` / `intent` / `source`；`eval cases promote` 保留 `manual`/`public_case` 来源（仅把 `synthetic` 转为 `synthetic_reviewed`） |
| `tests/unit/test_v1_multi_intent_eval.py` | **新增** | 确定性结构/KB/零触发词/防回归校验 + 固定回复端到端 `run_eval`/`render_report`/`compare_runs` 测试（及 CLI `review`/`promote` 单测） |
| `docs/learning/06-evaluation.md`、`README.md`、`00-glossary.md` | **修改** | 增补 `[L6.6]` 学习小节并同步索引与术语表 |

**明确不做（防越界）**：
- **不改动** `eval/cases/v1/reviewed.jsonl` 与 `eval/cases/v1/articles.jsonl` 的任何字节；
- **不改动** `src/tu_assistant/chat/{orchestrator,anonymize,prompts,article_count}.py`、`src/tu_assistant/eval/{metrics,runner,report,compare}.py` 的既有业务逻辑与判定口径；
- **不启动真实 7B 模型推理**（7B 重复评测留给紧随其后的 `T064`）；
- **不改动** 任何历史 `artifacts/`（KB、数据集、训练权重、历史 eval run），不读取 `inputs/`。

### 3.2 候选用例覆盖蓝图（总计 28 题，选项 B 则为前两组共 20 题）

所有案情人物与单位均使用**虚构泛称或明显虚构名称**，不取自真实对话与 `inputs/`；所有条款 ID 均对照 `kb-20261119-045641.sqlite` 精确到条/款/项并避开《上海市工伤保险实施办法》。

#### 组 1：`multi_violation`（10 题：`mv-001` ~ `mv-010`，直接评测 SC-004 并联动 SC-002/003/005）

覆盖 FR-016（一段描述多个违法行为）与 FR-017（**不预设违法主体类型**，覆盖用人单位、直接负责主管人员/董事高管、工会组织/工作人员、劳务派遣单位与用工单位、发包/分包/施工总承包单位、从业人员等）：

| 建议题号 | 违法主体组合（体现 FR-017 多元主体） | 涉及法规与违法行为组合（2–3 项） | 是否联动已确认 `liability_for`（SC-005） |
|---|---|---|---|
| `mv-001` | 用人单位 + 单位直接负责的主管人员 | 阻挠职工依法组建工会 + 擅自调动任期内工会主席工作岗位（《工会法》） | 是（工会法已确认责任边） |
| `mv-002` | 用人单位（同一主体两项违法） | 长期拖欠劳动报酬 + 未依法缴纳社会保险费（《劳动法》/《劳动合同法》/《社会保险法》） | 视具体条款核对 |
| `mv-003` | 用人单位 + 女职工保护双行为 | 安排怀孕七个月以上女职工夜班/加班 + 扣减孕期工资或变相辞退（《女职工劳动保护特别规定》/《妇女权益保障法》） | 是（女职工特别规定/妇女权益保障法已确认责任边） |
| `mv-004` | 施工总承包单位 + 分包单位（双单位） | 工程款/工资专用账户未按规落实或违规转包分包致欠薪（《保障农民工工资支付条例》） | 视具体条款核对 |
| `mv-005` | 劳务派遣单位 + 实际用工单位（双单位） | 未取得许可擅自派遣或克扣被派遣劳动者报酬 + 用工单位违规超比例/在非“三性”岗位用工（《劳动合同法》/《劳务派遣行政许可实施办法》） | 视具体条款核对 |
| `mv-006` | 生产经营单位 + 从业人员个人（单位 + 个人） | 单位未提供合格劳动防护用品且强令冒险作业 + 另有个别员工违规拒绝佩戴已配发防护用品（《安全生产法》） | 视具体条款核对 |
| `mv-007` | 工会工作人员 / 基层工会组织（非企业主体） | 工会工作人员挪用工会经费或损害职工/工会权益 + 基层工会未履行法定民主/维权程序（《工会法》/《上海市工会条例》） | 是（工会法已确认责任边） |
| `mv-008` | 公司董事 / 高级管理人员（个人） + 公司（单位） | 董事高管违反忠实义务谋取商业机会/挪用资金 + 公司裁减/改制未听取工会或职工意见（《公司法》） | 是（公司法已确认责任边） |
| `mv-009` | 用人单位（上海地方特色双行为） | 拒绝或拖延开展集体协商 + 拒不提供集体协商所需材料或打击报复协商代表（《上海市集体合同条例》） | 是（上海集体合同条例已确认责任边） |
| `mv-010` | 用人单位（就业歧视 + 职业健康双行为） | 招聘设置性别/生育限制门槛 + 未安排接触职业病危害岗位职工岗前/在岗职业健康检查（《妇女权益保障法》/《上海市就业促进条例》/《职业病防治法》） | 是（就业促进条例/妇女权益保障法已确认责任边） |

> 每题 `gold` 结构：`{"clauses": [...去重并集...], "violations": [{"actor": "...", "conduct": "...", "clauses": [...], "liability": [...]}, ...], "rubric": [...]}`。

#### 组 2：`intent`（10 题：`intent-001` ~ `intent-010`，固定多轮脚本，直接评测 SC-001）

所有题第 1 轮均为**不含 `_RE_EXPLICIT_CONSULT` / `_RE_EXPLICIT_WRITE` 触发词的大白话模糊开场**；全 script 长度为 2–3 轮（对齐 `intent_score` 的 `max_turns=3`）：

| 子类型 | 题数 | 题号 | 固定脚本形态与覆盖需求 | `gold.intent` | `gold.clauses`（按决策 3 选项 A） |
|---|---:|---|---|---|---|
| **模糊开场 → 确认咨询（2 轮）** | 3 | `intent-001..003` | T1 大白话模糊开场（如工会组建受阻、加班费争议、女职工产假待遇）→ T2 明确“我想了解相关的法律规定”并补齐关键事实（FR-010、FR-011、US1-1/2） | `"consult"` | 标注明确适用条款 |
| **模糊开场 → 连续补充事实（3 轮）** | 2 | `intent-004..005` | T1 模糊开场 → T2 明确想了解法律规定并给部分事实 → T3 继续补充关键事实（如工伤/职业病、集体协商/职代会），检验多轮上下文衔接（FR-009、US1-6） | `"consult"` | 标注第 3 轮综合事实对应条款 |
| **模糊开场 → 跳过追问直接作答（2 轮）** | 2 | `intent-006..007` | T1 模糊开场 → T2“我手头信息不全，先别问了，直接按现有情况说说相关规定吧”（FR-012、US1-7，核查分情形作答并注明存疑） | `"consult"` | 不标（避免信息不全导致 SC-002 失真；用 `rubric` 评审） |
| **模糊开场 → 中途切换普法文章（2–3 轮）** | 3 | `intent-008..010` | 2 题 T1 模糊开场 → T2 直接改口要普法宣传文章；1 题 T1 模糊开场 → T2 先问规定 → T3 改口要写成一篇给职工看的普法文章（FR-013） | `"article"` | 不标（用 `rubric` 评审切换与交付结构） |

#### 组 3：`boundaries`（8 题，决策 1 选项 A 纳入；选项 B 暂不纳入）

补齐 T038 遗留的 3 个空类别，使 `eval/cases/v1/` 覆盖全部 7 类 `EvalCase`：

| 类别 | 题数 | 题号 | 覆盖场景 | `gold` 关键字段 |
|---|---:|---|---|---|
| `refusal` | 3 | `refusal-001..003` | ① 库外领域咨询（如个人所得税专项附加扣除/刑法交通肇事）；② POC 已排除法规（《民法典》民间借贷利息/离婚房产分割，spec 2026-11-13 澄清）；③ **本期不支持需求（FR-014，2 轮脚本）**：T1 模糊开场“被公司辞退了想找工会帮忙” → T2“帮我直接起草一份劳动仲裁申请书” | `should_refuse: true` + `rubric` |
| `false_refusal` | 2 | `false-refusal-001..002` | 看似跨界/冷门但**确在 24 篇库内**的合法咨询（如企业开展职工读书阅读活动的促进保障《全民阅读促进条例》、公司职工民主管理/职工董事《公司法》），激活 `report.py` 专设误拒题统计 | `clauses: [...]` + `rubric`（`should_refuse` 为假） |
| `exception` | 3 | `exc-001..003` | 表面触及原则性条文、但存在法定例外情形（FR-018 / US1-4）：如竞业限制人员范围例外（普通一线工人非高管/高技/涉密人员）、用人单位解除劳动合同限制的法定例外、或加班时长/特殊工时及法律援助经济困难审查豁免情形 | `clauses: [...]` + `rubric` |

---

## 4. 具体实施步骤与确定性验收方法

### 4.1 两阶段实施步骤（先审题，后发布，严禁跳过用户确认）

1. **阶段 A · 工程微调（如决策 4 选 A）与候选起草**：
   - 若用户批准决策 4 选项 A，先更新 `src/tu_assistant/cli.py` 的 `eval cases review`（展示 `violations`、`intent`、`source`）与 `eval cases promote`（保留 `manual`/`public_case` 来源）；
   - 对照 `artifacts/kb/kb-20261119-045641.sqlite`（只读查询条款编号与内容核对适用性，绝不读 `inputs/`，绝不使用 `9fc301cd90566af9`），逐题编写候选用例写入 `eval/cases/candidates/{multi_violation,intent[,boundaries]}.jsonl`（均带 `confirmed: false`、`source: "manual"`、`eval_set_version: "v1"`）；
   - 运行确定性预检脚本校验：① JSONL 合法性与 `case_id` 全局唯一；② `validate_gold_clauses` 零问题；③ 所有 `intent` 题第 1 轮 `classify_user_intent_signals` 全 `False`；④ 与 `eval/cases/v1/` 既有 70 题、文章提示词模板池、`ds-8410`/`ds-8247` 训练集 3-gram 重叠均为 0；
   - **停步送审**：在对话中向用户展示**完整候选用例审题表**（逐题列明题号、类别、问句/完整脚本、涉及主体与条款名称+编号、预期意图/拒答及 `rubric`），请用户逐题确认接受、修改或剔除（用户也可用 `tu eval cases review` 辅助核对）。
2. **阶段 B · 正式发布、确定性测试与学习文档收尾（用户确认审题后执行）**：
   - 按用户审定结论修改并发布至 `eval/cases/v1/multi_violation.jsonl`、`eval/cases/v1/intent.jsonl`（及 `boundaries.jsonl`），保持 `reviewed.jsonl` 与 `articles.jsonl` 字节零改动；
   - 编写单元测试 `tests/unit/test_v1_multi_intent_eval.py`，覆盖第 4.2 节全部确定性验收项；
   - 更新学习文档 `docs/learning/06-evaluation.md`（`[L6.6]`）、`docs/learning/README.md` 与 `docs/learning/00-glossary.md`；
   - 运行完整回归（`uv run pytest`、`uv run ruff check src tests`、T075 哈希锁复核、T076/T062 历史对比只读抽验）；
   - **独立只读复审闭环**：按 `.agents/skills/task-review-loop/SKILL.md` 执行最多 5 轮独立只读复审，通过后向用户汇报最终验收（用户明确确认前不勾选 `tasks.md`、不 `git commit`）。

### 4.2 确定性验收矩阵（只测确定性契约，不把非确定语义判断写进单测）

| 验收项 | 确定性验证方式与通过条件 |
|---|---|
| **1. 既有基线与历史产物零破坏** | ① `git hash-object eval/cases/v1/reviewed.jsonl` == `63a1f9533e78fb71fd9bf99bb1fb663127eb22eb`；② `git hash-object eval/cases/v1/articles.jsonl` == `fc72e84a5c591f73556330bbe1e62989201fe912`；③ `shasum -a 256 -c artifacts/logs/t075/01/output.sha256` 25/25 OK |
| **2. 正式用例 schema 与 KB 完整性** | ① `load_cases("eval/cases/v1")` 加载总数准确（98 题或 90 题），`case_id` 全局唯一，无 `train_probe` 来源，已审定候选与正式文件逐条一致（扣除流程字段）；② `validate_gold_clauses(cases, open_kb("artifacts/kb/kb-20261119-045641.sqlite"))` 返回 `[]`；③ 无任何新增用例引用 T078 缺陷文件 `9fc301cd90566af9` |
| **3. `multi_violation` 与 `intent` 专项结构校验** | ① 每道 `multi_violation` 题 `len(gold.violations) >= 2`，每条均含非空 `actor`/`clauses`，`set(gold.clauses)` 包含全部 violation 的 `clauses` 与 `liability`，且覆盖 ≥ 4 类不同主体角色（含非用人单位主体）及 ≥ 5 题命中已确认 `liability_for` 关联；② 每道 `intent` 题 `input.script` 长度为 2–3 轮、`gold.intent in {"consult", "article"}`、有非空 `rubric`，且**所有第 1 轮开场经 `classify_user_intent_signals(t1, article_task_active=False)` 检验 5 项信号全 `False`**；咨询收敛题第 2/3 轮确认句不触发 `_RE_EXPLICIT_CONSULT` |
| **4. 去重防泄漏校验（宪章原则 V）** | ① `tests/unit/test_synth_articles.py` 既有提示词零重合测试直接通过；② 对 `artifacts/datasets/ds-kb-20261113-093057-8410` 与 `ds-kb-20261119-045641-8247` 的 `train.jsonl` + `valid.jsonl` 运行只读 `dedup_against_eval(..., overlap=0.8)` 确认新增问句高重合数为 **0** |
| **5. 固定回复端到端运行器/报告/对比验证** | 在 `tests/unit/test_v1_multi_intent_eval.py` 中用内存/临时目录 + mock `ModelClient` 跑正式新增用例，断言：① `multi_violation` 全中/半中/零中时 SC-004、SC-002、SC-003、SC-005 精确等于手算值；② `intent` 第 1 轮追问 (`intent=None`) + 第 2/3 轮确认时 SC-001=1.0，3 轮均未确认时 SC-001=0.0；③ 若含 `boundaries.jsonl`，`refusal`/`false_refusal`/`exception` 分别计入 SC-008 范围外 / 专设误拒题 / 常规题分母且 `report.md` 渲染完整无 `-` 缺项（SC-009/010 待人工评审除外）；④ CLI 只读抽验 `tu eval compare --sc016 run-20261117-022645 run-20261117-081504`（退出 0）与 `tu eval compare run-20261117-081504 run-20261118-020130`（退出 0）零回归 |
| **6. 全量测试与代码风格** | `uv run pytest` 全绿（414 passed / 6 xfailed 基线 + 新增测试全通过，含 `test_runtime_isolation.py`）；`uv run ruff check src tests` 全绿；`git status` 确认未误改 `artifacts/` 与 `specs/` |

---

## 5. 学习文档更新点

- **`docs/learning/06-evaluation.md` 新增 `[L6.6]` 评测集怎么设计才测出真能力：多违法行为、多轮意图脚本与“防正则自证”**：
  - 讲解为什么评测用例不能复述训练模板（3-gram 去重与宪章原则 V）；
  - 结合本项目真实源码（`anonymize.py:classify_turn_intent` 与 `metrics.py:intent_score`）拆解**“测量工具与安全护栏的张力”**：
    - 为什么模糊开场绝对不能带“违法吗/怎么办”等词（避免第 1 轮被用户侧正则伪确认）；
    - 为什么隐私护栏在用户明说“写一篇普法文章”时必须立即切换 `intent="article"`（宁严勿漏），以及由此带来的 SC-001 测量边界（必须结合逐轮 `rubric` 与实际交付结构复核）；
  - 说明 `multi_violation`（SC-004）里为什么 `gold.clauses` 要纳入 `violations[].liability`（避免模型补全责任条款反而被 SC-003 精确率扣分）；
  - 解释新增 `.jsonl` 文件如何实现目录型评测集平滑扩题（70 → 98 题）而不破坏历史 60 题 `SC-016` 基线。
- **索引与术语同步**：
  - 更新 `docs/learning/README.md` 第 6 章状态为 `进行中（已含 L6.1–L6.6；完整章节由 T065 整理）`；
  - 在 `docs/learning/00-glossary.md` 的 `## 评测` 分组补充“固定对话脚本（Fixed Dialog Script）”与“多违法行为识别率（SC-004）”条目并链接至 `[L6.6]`。

---

## 6. 待用户拍板的决策清单

请逐项确认以下 4 项（如均同意推荐项，可直接回复“按推荐方案实施”）：

1. **T049 用例范围与题量配比**
   - **选项 A（推荐）**：核心 20 题（`multi_violation` 10 题 + `intent` 10 题）+ 顺手补齐 8 题咨询边界类（`refusal` 3 题［含 FR-014 仲裁申请书不支持需求］+ `false_refusal` 2 题 + `exception` 3 题），共 **28 题**分 3 个独立文件加入 `eval/cases/v1/`（总数 70 → 98 题）。**理由**：一次覆盖全部 7 类 `EvalCase`，紧随其后的 `T064` 只需跑一轮 2×7B 评测即可产出 SC-001 ~ SC-011 全指标有实测分母的完整 V5 报告，避免后续补题重跑。
   - **选项 B**：严格按 `tasks.md` T049 字面只写 **20 题**（`multi_violation` 10 题 + `intent` 10 题，总数 70 → 90 题），暂不补写咨询 `refusal` / `false_refusal` / `exception`（审题负担少 8 题，但 SC-008 范围外仅剩 `article-007` 1 题、专设误拒题仍为 `0/0`）。

2. **候选用例起草方式与 `source` 标注口径**
   - **选项 A（推荐）**：手工原生起草（`source="manual"`），对照活跃知识库 `kb-20261119-045641.sqlite` 精确核验条款 ID 与已确认关联，先落盘 `eval/cases/candidates/` 并以结构化审题清单交您逐题审定后再发布到 `eval/cases/v1/`。**理由**：零外部 API Key/费用阻塞、无需扩改 `synth/evalcases.py`、问法天然独立于训练合成模板（宪章原则 V）。
   - **选项 B**：先扩展 `src/tu_assistant/synth/evalcases.py` 调用外部大模型生成多违法行为与多轮脚本候选，再人工校验改 `source="synthetic_reviewed"`。

3. **`intent` 用例的 `gold.clauses` 标注策略与 `SC-001` 边界处理**
   - **选项 A（推荐）**：保持 `classify_turn_intent` 与 `metrics.py` / `runner.py` 现有逻辑不变（零回归风险）；`intent` 题第 1 轮严格零触发词、咨询收敛轮不靠正则自证；**仅对事实完整、指向唯一明确条款的 5 道咨询收敛题标注 `gold.clauses`**，跳过追问（2 题）与中途转写文章（3 题）不标 `gold.clauses`（用 `rubric` 复核并在 `[L6.6]` 诚实记录文章切换轮的测量边界）。
   - **选项 B**：全部 10 道 `intent` 题均不标注 `gold.clauses`，使 SC-001 独立测意图确认、SC-002/SC-003 仅由非 `intent` 题计算。

4. **是否顺手增强 `tu eval cases review / promote` 以支持新字段与 `source="manual"`**
   - **选项 A（推荐）**：在 `src/tu_assistant/cli.py` 做两处轻量向后兼容增强（附单测）：① `eval cases review` 补齐打印 `gold.violations`、`gold.intent`、`source`；② `eval cases promote` 对 `source="manual"` / `"public_case"` 保留原来源，仅将 `"synthetic"` 转为 `"synthetic_reviewed"`（解决 T058 曾记录的来源覆写坑）。
   - **选项 B**：本轮完全不修改 `src/` 代码，仅产出评测集文件、确定性验收单测与学习文档，审定后直接落盘正式 JSONL。

---

## 7. 实施与独立复审记录（2026-11-23）

- **用户决策**：全部 4 项均按推荐（选项 A）实施。
- **阶段 A · 外部 DeepSeek 候选用例初审与用户审定**：
  - 调用外部 `deepseek-chat`（`temperature=0`，仅输入人工虚构候选用例与 `kb-20261119-045641.sqlite` 查出的公开法条原文，未触碰 `inputs/`）对 28 道候选用例逐题初审：PASS 16 / MINOR 12 / ISSUE 0；
  - 逐条核实并采纳 11 项 MINOR 修订（另 `intent-009` 经查 KB 原文第 83 条精确对应第 43 条升为 PASS），重跑 7 项确定性预检全绿后获用户确认通过，发布至 `eval/cases/v1/{multi_violation,intent,boundaries}.jsonl`（v1 总数 70 → 98 题）。
- **阶段 B · 独立只读复审闭环（`research` / Pro 独立只读子代理，共 2 轮，一致通过）**：
  - **Round 1（需修改）**：发现 3 项阻断项 + 4 项非阻断建议：
    1. **阻断项 1（已修复，请用户终审确认）**：`mv-002`（未办理社保登记 + 欠缴社保费）遗漏库内实际存在的《中华人民共和国社会保险法》第八十四条（`352e44bdb871bd37:a84:p1`，专门规定“用人单位不办理社会保险登记”的法律责任）。已核实 KB 原文并在 `eval/cases/candidates/multi_violation.jsonl:2` 与 `eval/cases/v1/multi_violation.jsonl:2` 同步补全至 `gold.clauses`、`gold.violations[1].liability` 与 `rubric`；
    2. **阻断项 2（已修复）**：`tests/unit/test_v1_multi_intent_eval.py` E2E 测试补齐 3 轮 `intent` 脚本（`intent-004` 第 3 轮确认=1.0、`intent-005` 3 轮均未确认=0.0）及 `article-009`（带 `protected_names`，SC-011=3/3），将 `sc002`（`9.5/13, n=13`）、`sc003`（`1.0, n=10`）、`sc008`（`3/3` / `0/2` / `0/12` / `0/14`）全部改为精确手算断言，并逐行校验 `report.md` 全部 11 行 `| SC-` 指标除 SC-009/SC-010 外无 `-` 缺项；
    3. **阻断项 3（已修复）**：CLI `review` / `promote` 单测补齐缺失 `source`（转 `synthetic_reviewed`）、缺失 `confirmed`（过滤）、`synthetic_reviewed` 保留、以及 `review` 展开 `适用条款:` / `法律责任:` 与不存在条款兜底显示；
    4. **非阻断建议 1–3（已采纳修复）**：加强候选全确认/版本号校验与 `test_boundaries_structure_and_signals`；`consult` 第 2/3 轮收紧为 `not any(sig.__dict__.values())`；`src/tu_assistant/cli.py:898,907` 改为 `row.get("source") or "manual"` 与 `row.get("gold") or {}`；第 4 项 `mv-004` 条款颗粒度保持既定审题口径。
  - **Round 2（一致通过）**：阻断项 0、非阻断建议 0、无未决分歧。
- **验收证据**：
  - `uv run pytest`：**421 passed, 6 xfailed**（基线 414 + 新增 7）；
  - `uv run ruff check src tests`：`All checks passed!`；
  - 历史基线零改动：`git hash-object eval/cases/v1/reviewed.jsonl` == `63a1f9533e78fb71fd9bf99bb1fb663127eb22eb`，`eval/cases/v1/articles.jsonl` == `fc72e84a5c591f73556330bbe1e62989201fe912`；
  - 历史产物哈希锁：`shasum -a 256 -c artifacts/logs/t075/01/output.sha256` **25/25 OK**；
  - 历史对比 CLI 抽验：`uv run tu eval compare --sc016 run-20261117-022645 run-20261117-081504`（退出 0，PASS）与 `uv run tu eval compare run-20261117-081504 run-20261118-020130`（退出 0）零回归。
