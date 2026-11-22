# T061 + T063 执行单 · 完善评测报告与普法文章人工评审模板

**状态：已验收完成（2026-11-22）。** 基于主线提交 `61a8043`（T056 已验收提交）。本执行单承接 Phase 5 / US3（统一评测集衡量系统质量），将紧密耦合的 **T061（`src/tu_assistant/eval/report.py` 完善评测报告）** 与 **T063（`eval/review-template.csv` 人工评审表格模板及报告内待评审文章清单）** 合并为一轮确定性工程交付，沉淀可供后续 **T062（通用 `tu eval compare`）** 复用的统一指标聚合接口，并在全流程中严格保护历史产物与既有测试基线。

> **合规与红线声明**：起草与实施全过程**严禁读取 `inputs/` 目录下任何文件**；**严禁改动历史产物**（历史 KB、历史数据集、已训权重及历史 `artifacts/eval/<run_id>/`）；运行时与评测包（`eval/`）严格满足零外部 LLM 客户端导入约束（`tests/unit/test_runtime_isolation.py`）。

---

## 1. 推荐任务编号与选择理由

**推荐任务：合并推进 `T061 + T063`（完善评测报告与人工评审模板）。**

### 1.1 为什么将 T061 与 T063 合并，而不把 T062 一并塞入？

- **T061 与 T063 双向紧耦合，不可拆分**：
  - `T063` 要求提供 `eval/review-template.csv`（FR-037），**并明确要求“在 `report.md` 中按 `case_id` 列出待评审的普法文章”**；
  - `T061` 要求在 `src/tu_assistant/eval/report.py` 完善报告，**并明确要求“SC-009（文章正确性）、SC-010（文章多样性）从人工评审表格（T063）汇总”**。
  - 两者共享同一套 CSV 契约与同一份 `report.md` 渲染入口，合并实施可一次性闭环，避免出现半成品接口或二次返工。
- **T062 留作紧随其后的下一步，控制单轮复审半径**：
  - `T061 + T063` 负责沉淀单次评测的统一聚合函数 `summarize_run`（覆盖 SC-001 ~ SC-011、失败清单与人工评审汇总）；
  - `T062`（通用多 run 对比 `tu eval compare <run_id>...` 与 `compare.md`）可直接复用 `summarize_run` 与 T076 已有可比性校验框架，专注于多 run 对齐、指标差值、SC-015 波动判定与逐题增减对照，避免把两套独立 CLI 面与十余项决策挤在同一轮 5 轮复审闭环中。

### 1.2 与其他主要候选任务的横向对比

| 候选任务 | 当前状态与前置条件 | 为何优先做 `T061 + T063` |
|---|---|---|
| **`T061 + T063`（推荐）** | 均为 `[P]` 任务，依赖已全部就绪；当前 `src/tu_assistant/eval/report.py` 尚未创建，仅在 `runner.py` 中有简易 `_render_report` | 纯确定性代码、模板与单测，零外部 API/推理/人工审题阻塞；立即修复现有报告缺漏 SC-006、缺少 POC 目标值对照、缺少校验前/后两列表、缺少失败清单与人工评审汇总等缺口；为后续 T062、T049、T064 打通共享指标聚合底座 |
| **`T062`（通用 `tu eval compare`）** | 当前 `eval/compare.py` 仅实现 T076 的 `--sc016` 模式 | 通用对比需要读取每个 run 的全量 SC-001 ~ SC-011 汇总值；若先做 T062 会被迫重复写一份聚合逻辑，极易与 T061 产生指标口径漂移 |
| **`T049`（补写 v1 多违法行为与意图确认约 20 题）** | Phase 3 US1 唯一未勾项；当前 `eval/cases/v1/` 仅含 `clause_id` 60 题 + `article` 10 题（`multi_violation`/`intent` 均为 0 题） | T049 涉及 ~20 题内容编写与用户逐题人工审阅，周期长；`T061 + T063` 对 7 类用例全部通用，先落地零返工；待 T061–T063 工具就绪后再做 T049，接着在完整 v1（约 90 题）上一次跑完 T064，无需重复跑 7B 评测 |
| **`T064`（7B 重复评测 2 次验证 SC-015）与 `T059` 核销** | 用户在 T056 拍板决策 #4 已明确：**T059 留待 T064 完成后核销** | T064 强依赖 `T061 + T063`（产出完整 V5 报告）和 `T062`（用 `tu eval compare` 验证波动 ≤2 个百分点），当前尚不具备运行条件 |
| **Phase 6（`T066–T068`，US4 知识库维护）** | P4 优先级，模块独立，可穿插 | 不阻塞 Phase 5 与 T059 收口；当前 `tu chat` / `tu eval run` 已默认读最新 KB 且支持 `--kb-version`，可在 Phase 5 后、Phase 7 `tu ui` 前或并行完成 |
| **Phase 7（`T069–T074`，Gradio UI 与收尾）** | 最终演示与 V1–V7 验收（其中 V5 明确要求 SC-001 ~ SC-011 完整报告与 SC-015 ≤2 个百分点） | 应先补齐 Phase 5 评测能力并核销 T059，再进入演示界面与最终验收 |
| **`T078`** | 已标记 `[Post-POC / 正式阶段]` | 2026-11-19 已由用户确认移出 POC 范围，不纳入候选 |

**建议的 Phase 5 + T049 推进节奏**：
`T061 + T063`（本单） → `T062`（通用 `tu eval compare`） → `T049`（补齐约 20 题 `multi_violation` + `intent` 并经用户审定） → `T064`（在完整 v1 上对冻结父模型重复评测 2 次、验证 SC-015 ≤2 个百分点并同步核销 `T059`） → `T065`（整理 `docs/learning/06-evaluation.md`）。

---

## 2. 背景与只读摸底核实

以下数据、接口与文件状态均经仓库只读核实（未触碰 `inputs/`）：

### 2.1 当前代码、测试与活跃产物基线

- **代码基线**：`61a8043`（`feat(chat): implement deterministic article count guardrails (T056)`），全量 `uv run pytest` 基线 **388 passed / 6 xfailed**，`ruff` 全绿。
- **活跃知识库**：`artifacts/kb/kb-20261119-045641.sqlite`（24 篇文档、3,809 条记录、67 条已确认关联：`liability_for` 26 + `references` 41）；60 题历史基线旧 KB 为 `kb-20261113-093057.sqlite`（24 篇、3,809 条、35 条已确认关联）。
- **冻结演示模型**：`exp-20261116-resume500`（最终 adapter SHA-256 前缀 `b62a7d0e86f4`）。
- **当前正式评测集 `eval/cases/v1/`（共 70 题）**：
  - `eval/cases/v1/reviewed.jsonl`：60 题，全部为 `category="clause_id"`、`source="synthetic_reviewed"`；
  - `eval/cases/v1/articles.jsonl`：10 题，全部为 `category="article"`、`source="synthetic_reviewed"`（其中 `article-001..004/009` 含多篇期望 `>=2`；`article-005/006/008/010` 为单篇或单篇改稿；`article-007` 为 `should_refuse=true`；`article-009/010` 含 `protected_names`）。
- **代表性历史评测 run 实测核对**：

| run_id | 用例集 / 题数 | KB | SC-006（`complete/total`） | 引用四态 `ok / corrected / not_found / incomplete` | 关键模式差异 |
|---|---|---|---|---|---|
| `run-20261117-081504` | `v1/reviewed.jsonl`（60） | `kb-20261113-093057` | `59/59`（1.000） | `34 / 0 / 1 / 25`（总 60，已定位 35） | **旧 schema**：`scores` 不含 `refusal_evidence` 与 `refusal_correct` |
| `run-20261120-183952` | `v1`（70） | `kb-20261119-045641` | `84/91`（0.923） | `63 / 8 / 0 / 20`（总 91，已定位 71） | **受 T075 哈希锁保护**：`report.md` SHA-256 记录于 `artifacts/logs/t075/01/output.sha256` |
| `run-20261122-090101` | `v1/articles.jsonl`（10） | `kb-20261119-045641` | `5/6`（0.833） | `4 / 1 / 0 / 1`（总 6，已定位 5） | 含 T054 接线后 `turns[].anonymize` 字段 |

### 2.2 现有实现中核查出的具体缺口与口径风险

1. **`src/tu_assistant/eval/report.py` 缺失**：目前报告渲染写死在 `src/tu_assistant/eval/runner.py` 的 `_render_report`（L80–L211），仅有简易总表与按类别计数。
2. **SC-006（出处标注完整率）完全缺失**：`runner.py` 已将每题的 `citation_complete` 与 `citation_total` 写入 `results.jsonl`，但 `_render_report` 从未展示 SC-006。
3. **SC-007（引用准确率）存在跨模块口径分歧，且缺少校验前/后两列对照表**：
   - `metrics.citation_accuracy`（`src/tu_assistant/eval/metrics.py` L36–L57）注释写明“`not_found / incomplete` 为失败”，但实现中把 `incomplete` 排除出分母（`n = ok + corrected + not_found`），且 `tests/unit/test_metrics.py::TestCitationAccuracy::test_incomplete_excluded` 锁定了该行为；
   - `runner.py` `_render_report`（L94–L96）则采用全分母 `acc_total = ok + corrected + not_found + incomplete`，已体现在 `docs/experiments/T075-article-training.md` L126（`69.2% / 78.0%`）；
   - 更关键的是：`verify.py`（L162–L164）会把“多款条文未写款号且无法凭引文唯一定位”的带标记引用也判为 `verdict="incomplete"`，但 `citation_completeness`（`metrics.py` L32）只要有 `title` 与 `article_no` 就计入 `complete`——导致 `run-20261117-081504` 中 SC-006 显示 `59/59 (100%)`，实际却有 **25 处** `incomplete` 引用未经原文校验！若 SC-007 也排除 `incomplete`，这 25 处未校验引用就会同时从 SC-006 与 SC-007 漏出（详见第 6 节决策 3）。
4. **缺少 POC 目标值对照与免责定位**：未对照 `spec.md` SC-001 ~ SC-011 目标值，未在报告头部显式注明“POC 阶段目标值仅供参考、不作为验收条件”。
5. **缺少逐条失败用例清单**：无法在 `report.md` 直接定位失败用例 ID、类别与确定性失败原因。
6. **缺少人工评审模板（`eval/review-template.csv`）、待评审普法文章列表与 SC-009/SC-010 汇总**：
   - `tasks.md` T063 与 `data-model.md` §3 定义的 `ReviewComment` 含 6 列：`run_id, case_id, reviewer, verdict, comment, created_at`；
   - **设计缺口（须决策）**：仅用单个 `verdict` 列无法同时区分 **SC-009（文章正确性）** 与 **SC-010（文章多样性 / 实质重复率）**（详见第 6 节决策 2）。
7. **历史 `results.jsonl` 兼容与哈希锁保护**：
   - `run-20261117-081504` 等早期 run 不含 `scores.refusal_evidence`，`report.py` 必须兼容历史格式（缺字段时按 `detect_refusal(final_text)` 兜底复算或安全降级，不能 `KeyError`）；
   - `artifacts/logs/t075/01/output.sha256` 锁定了 4 份历史 run 的 `report.md` 哈希，**严禁任何命令默认原地覆盖已有 `artifacts/eval/<run_id>/report.md`**（详见第 6 节决策 4）。
8. **既有单元测试对 `report.md` 的精确文本契约**：
   经全库检索 `tests/`，以下精确子串已被 `tests/unit/test_article_eval.py` 与 `tests/unit/test_anonymize.py` 断言，重构至 `report.py` 后必须 **100% 逐字保留**：
   - `"SC-008（自动初筛，依据见 results.jsonl 的 refusal_evidence）"`
   - `"范围外正确拒答 ..."`、`"范围内误拒 ..."`、`"常规题 ..."`、`"专设误拒题 ..."`、`"无样本（0/0）"`
   - `"SC-011"`、`"标注 X 题，其中 Y 题有可评文章"`、`"另有 Z 轮未识别出文章结构但含保护名称"`（且 `Z == 0` 时不得出现该短语）
   - `"引用冲突暂缓交稿"` 及 `"{case_id} 第{turn}轮"`

---

## 3. 实施边界与核心设计

### 3.1 文件变更边界

| 文件 | 操作 | 职责 |
|---|---|---|
| `src/tu_assistant/eval/report.py` | **新增** | 单次评测指标汇总（`summarize_run`）、失败用例抽取（`extract_failures`）、待评审普法文章抽取（`extract_pending_articles`）、人工评审 CSV 读取/校验/汇总（`load_reviews`、`aggregate_reviews`）、Markdown 报告渲染（`render_report`）及只读读取已有 run 生成报告（`render_run_report`） |
| `eval/review-template.csv` | **新增** | 提交至仓库的人工评审表格模板（FR-037），仅含标准表头（UTF-8，无假数据行） |
| `src/tu_assistant/eval/runner.py` | **修改** | 将 `_render_report` 委托给 `report.render_report`（保留 `_render_report` 兼容签名或直接透传 `manifest` 信息），不改变逐题推理与打分逻辑 |
| `src/tu_assistant/cli.py` | **修改** | 按决策 4 新增只读子命令 `tu eval report <run_id> [--reviews <csv>] [--out <path>] [--artifacts artifacts]` |
| `tests/unit/test_report.py` | **新增** | 覆盖全部 SC-001 ~ SC-011 汇总、SC-007 两列表、失败清单、CSV 校验/去重/汇总、历史 schema 兼容、CLI 只读不覆盖保护与边界情形 |
| `docs/learning/06-evaluation.md`、`README.md`、`00-glossary.md` | **修改** | 增补 `[L6.4]` 学习小节并同步索引与术语 |

**明确不做（防越界）**：
- 不修改 `src/tu_assistant/eval/metrics.py` 的既有函数签名与 `citation_accuracy` 返回语义（保护 `test_metrics.py` 与历史单题打分一致性）；
- 不修改 `src/tu_assistant/eval/compare.py`（留待 T062，T076 `--sc016` 零触碰）；
- 不修改 `eval/cases/v1/`、`specs/`、`configs/`、任何历史 `artifacts/` 目录（含 `artifacts/eval/<old_run>/report.md`）；
- 不实现 `tu eval review import` 等系统内交互录入功能（`contracts/cli.md` 明确列为正式阶段特性）。

### 3.2 核心数据结构与共享聚合接口（为 T062 铺路）

在 `src/tu_assistant/eval/report.py` 提供结构化、纯函数、确定性的 `summarize_run(results: list[dict], *, reviews: list[ReviewEntry] | None = None, run_id: str | None = None) -> dict`：

- **输入**：`results.jsonl` 的行列表（内存字典），以及可选的已解析评审列表；不读外部网络、不依赖 SQLite（仅消费已保存的 `results` 与 `manifest`）。
- **返回结构**（确定性可序列化 dict，供 `render_report` 与后续 T062 `compare.py` 直接消费）：
  - `case_count`：总用例数；
  - `by_category`：`{category: {"total": int, "failed": int}}`；
  - `sc001`：`{"value": float | None, "hits": int, "total": int}`（`category == "intent"` 且 `scores.intent is not None`）；
  - `sc002`：`{"value": float | None, "n": int}`（`scores.recall is not None` 均值）；
  - `sc003`：`{"value": float | None, "n": int}`（`scores.precision is not None` 均值）；
  - `sc004`：`{"value": float | None, "n": int}`（`category == "multi_violation"` 且 `scores.multi_violation is not None` 均值）；
  - `sc005`：`{"value": float | None, "n": int}`（`scores.relation_completion is not None` 均值）；
  - `sc006`：`{"value": float | None, "complete": int, "total": int}`（累计 `citation_complete / citation_total`）；
  - `sc007`：`{"pre": float | None, "post": float | None, "total": int, "resolved_pre": float | None, "resolved_post": float | None, "resolved_total": int, "counts": {"ok": int, "corrected": int, "not_found": int, "incomplete": int}}`；
  - `sc008`：`{"outside_rate": float | None, "outside_hits": int, "outside_total": int, "false_refusal_rate": float | None, "false_refusal_hits": int, "false_refusal_total": int, "regular_hits": int, "regular_total": int, "special_hits": int, "special_total": int, "recomputed_count": int}`（历史 run 缺 `refusal_evidence` 时自动用 `detect_refusal(final_text)` 兜底复算并记录 `recomputed_count`）；
  - `sc009` / `sc010`：`{"status": "missing_file" | "no_rows" | "scored", "value": float | None, "counts": {"pass": int, "minor_issue": int, "fail": int}, "total": int, "covered_cases": int, "eligible_cases": int}`；
  - `sc011`：`{"ratio": float | None, "passed": int, "total": int, "annotated_cases": int, "evaluable_cases": int, "unparsed_leak_rounds": int}`；
  - `auxiliary`：`{"blocked_turns": list[tuple[str, int]], "article_count_ok": int, "article_count_total": int}`。

### 3.3 人工评审表格模板与 CSV 校验/去重口径（T063）

- **模板路径**：`eval/review-template.csv`（UTF-8 无 BOM，LF 换行）。
- **推荐表头（决策 2 选项 A）**：
  `run_id,case_id,reviewer,verdict,comment,created_at,dimension`
  - 前 6 列与 `tasks.md` T063 及 `data-model.md` §3 `ReviewComment` 逐字一致；
  - 第 7 列 `dimension` 为可选列：
    - `correctness` → 汇总到 **SC-009（文章正确性）**；
    - `diversity` → 汇总到 **SC-010（文章多样性 / 实质重复率）**；
    - `other` 或空串（当 `dimension` 列存在但留空，或针对 `should_refuse=true` 的文章题如 `article-007`）→ 记录为已评审/归档意见，不计入 SC-009/SC-010 分母；
    - **纯 6 列兼容**：若用户传入仅含前 6 列（不含 `dimension` 列）的 CSV，不报错；对非 `should_refuse` 的普法文章行默认按 `correctness` 归入 SC-009，SC-010 标注“待评审（缺少 diversity 维度标注）”。
- **确定性校验规则（Fail-Fast，抛 `ReportError`，CLI 返回退出码 2）**：
  1. 缺失 6 个必需列中的任意一列 → 报错并指明缺失列名；
  2. 只筛选 `row["run_id"] == target_run_id` 的行（允许同一份 CSV 跨多个 run 累积记录，不报错）；若 `run_id` 匹配：
     - `case_id` 不在当前 run 的 `results.jsonl` 中 → 报错（带行号），防止填错题号或混入非评测对话（满足 `data-model.md` §3“只对评测输出做评审，不评审真实用户会话”）；
     - `verdict` 不在 `{"pass", "minor_issue", "fail"}`（允许前后空白，大小写不敏感规范化）→ 报错（带行号）；
     - `reviewer` 为空 → 报错（带行号）；
     - `dimension` 列存在且非空，但值不在 `{"correctness", "diversity", "other"}` → 报错（带行号）；
     - 若对 `should_refuse=true` 的用例标注 `correctness` / `diversity`，或对单篇题（`expect_articles` 无 `>=2` 轮次）标注 `diversity` → 报错或给出确定性拒绝（建议直接报错带行号，避免污染 SC-009/SC-010 分母）。
  3. 重复行处理：同一 `(run_id, case_id, dimension, reviewer)` 出现多条记录时，按 `created_at`（ISO 8601 字符串可比，若相同或为空按行号靠后者胜出）取最新一条，支持追加式修订评审；不同评审人（如“项目方”与“法律专业人员”）对同一题的评审各自计入 1 条，并在报告中同时列出**评审条数与覆盖题数**（如 `覆盖 8/9 题，共 10 条评审`）。
- **SC-009 / SC-010 汇总口径**：
  - **SC-009（文章正确性，POC 目标 `≥90%`）**：`dimension="correctness"` 有效记录中 `pass / total`（同步展示 `pass=x, minor_issue=y, fail=z`，便于观察轻微瑕疵占比）；
  - **SC-010（文章多样性，POC 目标：实质重复率 `≤10%`）**：`dimension="diversity"` 有效记录中 `fail / total`（`fail` 表示评审认定“实质重复”；同步展示 `pass=x, minor_issue=y, fail=z`）。

### 3.4 `report.md` 报告结构设计（T061 + T063）

1. **标题与元信息**：
   - `# 评测报告 <run_id>`
   - 实验 ID、知识库版本、评测集路径、用例数、人工评审文件（如有）
   - 显式提示：`> 注：POC 阶段目标值仅供参考、用于观察差距，不作为验收条件（spec.md Success Criteria；POC 验收以 SC-016 为准）。`
2. **## 总体指标（SC-001 ~ SC-011）**：
   - 列：`| 编号 | 指标 | 实测值 | POC 目标值（仅供参考） | 口径 |`
   - 覆盖 SC-001 至 SC-011 全部 11 项（补齐 SC-006；SC-007 展示主口径并在下一节展开校验前/后两列表），并保留两行辅助行：`引用冲突暂缓交稿（T054）`、`文章篇数符合（FR-028）`；
   - SC-008、SC-011、引用冲突暂缓交稿的精确文本片段与第 2.2 节既有单测断言完全一致。
3. **## SC-007 引用准确率（校验前 / 校验后对照）**：
   - 独立两列表：`| 统计口径 | 校验前 | 校验后 | POC 目标值 | 分子 / 分母说明 |`
   - 主行按决策 3（推荐全分母 `ok + corrected + not_found + incomplete`），副行提供已定位引用口径（`ok + corrected + not_found`）供对照；
   - 紧随 `## 引用判定分布`：`ok=...  corrected=...  not_found=...  incomplete=...`。
4. **## 按类别统计**：
   - `| 类别 | 用例数 | 失败用例数 |`
5. **## 逐条失败用例清单**（100% 确定性触发条件）：
   - 只要一条用例满足以下任一确定性条件即列入清单（按 `case_id` 升序，列出所有命中原因，不截断）：
     - 条款未全部命中：`scores.recall is not None and scores.recall < 1.0`；
     - 存在非标准引用：`scores.precision is not None and scores.precision < 1.0`（附注精确率数值，与未命中区分展示）；
     - 引用校验异常：`citation_acc.counts.not_found > 0` 或 `citation_acc.counts.incomplete > 0` 或 `citation_complete < citation_total`；
     - 拒答初筛不符：`refusal_correct is False`（标明“范围外未拒答”或“范围内误拒”）；
     - 关联条款未全补：`relation_completion is not None and relation_completion < 1.0`；
     - 多违法行为未全识别：`category == "multi_violation"` 且 `multi_violation is not None and multi_violation < 1.0`；
     - 意图未在 3 轮内确认：`category == "intent"` 且 `intent is not None and intent < 1.0`；
     - 文章篇数不符：`article_count.ok is False`；
     - 身份信息检查异常：`identity_check` 存在 `passed < total`、`unparsed_leaks` 非空，或任一轮 `anonymize.blocked == True`；
     - 人工评审未通过：加载的评审 CSV 中该 `case_id` 存在 `verdict == "fail"`（标明维度与评审人）。
   - 若全部通过，显示 `无失败用例。`
6. **## 待评审普法文章清单（FR-037 / T063）**：
   - 按 `case_id` 升序逐条列出全部 `category == "article"` 用例：
     `| run_id | case_id | 轮数 / 实得篇数 | 期望篇数 | 需评维度 | 评审状态 | 评分要点（rubric） |`
   - 清晰区分：多篇题（`correctness + diversity`）、单篇/改稿题（`correctness`）、拒答题（`拒答复核（other）`）；
   - 未加载评审表或某维度缺评时，状态列明“待评审”并给出 `eval/review-template.csv` 使用提示与 `tu eval report` 命令示例；无普法文章用例时写“本评测集无普法文章用例。”。

---

## 4. 实施步骤与确定性验收方法

### 4.1 实施步骤

1. **新增评审模板**：创建 `eval/review-template.csv`（按决策 2 确定的表头）。
2. **实现 `src/tu_assistant/eval/report.py`**：
   - 实现 `ReportError`、`ReviewEntry`、`load_reviews`、`aggregate_reviews`；
   - 实现 `summarize_run`、`extract_failures`、`extract_pending_articles`、`render_report`；
   - 实现 `render_run_report(artifacts_dir, run_id, *, reviews_path=None)`（复核 `manifest.json` 与 `results.jsonl` 完整性，缺文件/非法 JSON 抛 `ReportError`，不写磁盘）。
3. **接入 `src/tu_assistant/eval/runner.py`**：
   - `run_eval` 结束时把 `manifest` 元信息（`kb`、`cases`、`exp`）连同 `results` 传给 `report.render_report` 写入新 run 目录的 `report.md`；
   - 保留 `_render_report(run_id, exp_id, results)` 薄封装转发至 `report.render_report`，避免破坏任何直接导入它的测试或脚本。
4. **接入 `src/tu_assistant/cli.py`**（按决策 4）：
   - 在 `eval_app` 下新增 `tu eval report <run_id> [--reviews <csv>] [--out <path>] [--artifacts artifacts]`；
   - 捕获 `ReportError` 打印中文错误至 stderr 并以退出码 `2` 退出；
   - 若 `--out` 解析路径等于已存在的 `artifacts/eval/<run_id>/report.md`，拒绝覆盖并返回退出码 `2`。
5. **编写单元测试 `tests/unit/test_report.py`**：覆盖第 4.2 节全部确定性验收矩阵。
6. **只读核验历史产物**：用 `tu eval report`（仅打印 stdout 或写入 `/tmp` 临时路径，零改动 `artifacts/`）对 3 份代表性历史 run 做实测抽验，并核验 `shasum -a 256 -c artifacts/logs/t075/01/output.sha256` 保持 100% 通过。
7. **更新学习文档**：按第 5 节补写 `docs/learning/06-evaluation.md`（`[L6.4]`）并同步 `README.md` 与 `00-glossary.md`。
8. **独立只读复审闭环**：按 `.agents/skills/task-review-loop/SKILL.md` 执行最多 5 轮独立复审，全部通过后向用户汇报验收（确认前不勾 `tasks.md`、不 `git commit`）。

### 4.2 确定性验收矩阵（不把不可确定的语义判断写进单测）

| 验收项 | 确定性验证方式与通过条件 |
|---|---|
| **1. 全量 SC-001 ~ SC-011 聚合** | 在 `tests/unit/test_report.py` 构造覆盖全部 7 类用例（`clause_id`/`multi_violation`/`exception`/`refusal`/`false_refusal`/`intent`/`article`）的合成 `results`，逐项手算断言 `summarize_run` 的分子、分母、均值、边界（全空/部分 None/零引用）精确匹配；断言 `report.md` 包含 SC-001 ~ SC-011 全部编号、POC 目标值列及“目标值仅供参考，不作为验收条件”提示 |
| **2. SC-006 与 SC-007 两列表** | 构造含 `ok`、`corrected`、`not_found`、`incomplete`（含裸引用与多款缺款号两类）的样例，断言 SC-006 与 SC-007 校验前/校验后两列数值、分布行与决策 3 选定口径完全一致，且 `tests/unit/test_metrics.py` 零改动通过 |
| **3. 逐条失败用例清单** | 分别构造 10 类失败触发条件（漏召回、低精确、not_found、incomplete、误拒/漏拒、关联漏补、多违规漏检、意图超时、篇数不符、身份泄露/冲突暂缓、人工评审 `fail`）以及全通过正例，断言清单准确列出失败 `case_id` 与对应原因，全通过时输出“无失败用例。” |
| **4. 人工评审模板与 CSV 校验/汇总（T063）** | ① 校验仓库内 `eval/review-template.csv` 表头与可空加载；② 测试正常加载（单人、多人、同评审人追加修订覆盖、混入其他 `run_id` 自动忽略、纯 6 列向下兼容）；③ 测试非法输入均抛 `ReportError` 且带行号/列名（缺必选列、未知 `case_id`、非法 `verdict`、空 `reviewer`、非法 `dimension`、拒答题标 `correctness`、单篇题标 `diversity`）；④ 断言 SC-009（正确率）与 SC-010（实质重复率）计算精确，待评审文章清单按 `case_id` 升序且正确区分“待评审 / 已评”状态 |
| **5. 历史 run 只读兼容与防覆盖保护** | ① 在 `tmp_path` 模拟旧 schema（无 `refusal_evidence`，同 `run-20261117-081504`），断言不报错且正确复算 SC-008；② CLI `tu eval report` 测试：不传 `--out` 输出至 stdout 且原目录零改动；传 `--out` 指向已有 `artifacts/eval/<run_id>/report.md` 时返回退出码 `2` 且原文件字节不变；③ 实测本机 `run-20261117-081504`、`run-20261120-183952`、`run-20261122-090101` 只读渲染无报错，且 `shasum -a 256 -c artifacts/logs/t075/01/output.sha256` 全绿 |
| **6. 全量回归与合规检查** | `uv run pytest` 全绿（既有 **388 passed / 6 xfailed** + 新增 `test_report.py` 全通过，特别验证 `test_article_eval.py`、`test_anonymize.py`、`test_compare.py`、`test_runtime_isolation.py` 零回归）；`uv run ruff check src tests` 全绿；`git status` 确认未改动 `specs/`、`eval/cases/v1/`、`artifacts/` |

---

## 5. 学习文档更新点

- **`docs/learning/06-evaluation.md` 新增 `[L6.4]` 评测报告怎么读：校验前/后准确率、`incomplete` 陷阱与人工评审闭环**：
  - 用本项目真实历史数据（`run-20261117-081504` 中 SC-006 `59/59` 却有 `25` 处 `incomplete`、`run-20261120-183952` 中 `ok=63 / corrected=8 / incomplete=20`）拆解 SC-006 与 SC-007 的边界、校验前与校验后两列的诊断意义（前者反映模型自身背诵准确度，后者反映加上确定性校验层后的交付底线）；
  - 解释为什么 SC-009（法律构成要件正确性）与 SC-010（多篇实质多样性）不能靠简单正则自动化打分，而需要通过带维度标记的 CSV 表格接入人工/法律专业人员评审（FR-037），并与自动指标一起落入同一份报告；
  - 解释为什么 POC 阶段报告列出目标值但明确不作验收条件，以及历史评测产物为什么必须只读保护（哈希锁与可复现原则 VI）。
- **索引与术语同步**：
  - 更新 `docs/learning/README.md` 第 6 章状态为 `进行中（已含 L6.1–L6.4；完整章节由 T065 整理）`；
  - 在 `docs/learning/00-glossary.md` 按需补充“校验前/校验后引用准确率”、“人工评审表（ReviewComment）”等术语并链接至 `[L6.4]`。

---

## 6. 待用户拍板的决策清单

请逐项确认以下 4 项（如均同意推荐项，可直接回复“按推荐方案实施”）：

1. **任务合并边界与 Phase 5 推进顺序**
   - **选项 A（推荐）**：本次合并实施 **`T061 + T063`**（`eval/report.py` 评测报告 + `eval/review-template.csv` 人工评审模板），沉淀共享指标聚合函数 `summarize_run`；后续按 **`T062`（通用对比） → `T049`（补齐 ~20 题多违法行为与意图用例） → `T064`（7B 重复评测 2 次验证 SC-015 并核销 `T059`） → `T065`（整理第 6 章）** 推进。
   - **选项 B**：先做 **`T049`**（起草并人工审阅约 20 题多违法行为与意图确认用例），再回头推进 Phase 5 的 `T061–T065`。
   - **选项 C**：将 **`T061 + T062 + T063`** 一次性合并在单份执行单内实施（改动面与复审复杂度显著增大）。

2. **`eval/review-template.csv` 区分 SC-009 与 SC-010 的列设计及 `minor_issue` 计分口径**
   - **选项 A（推荐）**：保留 `data-model.md` / T063 的全部 6 个标准列，并在第 7 列追加可选列 **`dimension`**（表头：`run_id,case_id,reviewer,verdict,comment,created_at,dimension`，允许值 `correctness` / `diversity` / `other`，同时向下兼容仅含前 6 列的纯标准 CSV）；汇总时 SC-009 严格按 `pass / total`（正确率，目标 ≥90%）、SC-010 按 `fail / total`（实质重复率，目标 ≤10%），并在报告中完整列明 `pass / minor_issue / fail` 三态计数，不隐藏边界情况。
   - **选项 B**：严格保持 6 列不增列，改由两份独立 CSV（分别传正确性与多样性）或在 `comment` 文本中约定前缀（如 `[SC-009]` / `[SC-010]`）区分。

3. **SC-007（引用准确率）报告层全局汇总分母口径（对 `incomplete` 的处理）**
   - **选项 A（推荐）**：报告层 SC-007 主行**保持严格全分母** `all = ok + corrected + not_found + incomplete`（校验前 `ok / all`，校验后 `(ok + corrected) / all`），与现有 `runner.py` 及 `T075-article-training.md` 已披露数字一致，防止多款缺款号导致的 `incomplete` 同时逃逸 SC-006 与 SC-007；同时在 SC-007 校验前/后两列表格中附列“已定位引用口径（`ok + corrected + not_found`）”及四态分布以便对账；`metrics.citation_accuracy` 与 `test_metrics.py` 保持不变。
   - **选项 B**：报告层 SC-007 主行改为排除 `incomplete` 的已定位分母（与单题 `metrics.citation_accuracy` 对齐，但会与 `T075` 历史报告数字产生差异，且未定位的多款引用不再扣减 SC-007）。

4. **人工评审事后汇总的只读 CLI 入口（`tu eval report`）与历史文件保护**
   - **选项 A（推荐）**：新增轻量只读子命令 `tu eval report <run_id> [--reviews <csv>] [--out <path>] [--artifacts artifacts]`，便于人工填完 CSV 后免重跑模型直接生成含 SC-009/SC-010 的报告；**默认不原地覆盖** `artifacts/eval/<run_id>/report.md`（未传 `--out` 时打印到 stdout，若 `--out` 指向已有 `artifacts/eval/<run_id>/report.md` 则拒绝覆盖并返回退出码 2，保护 T075 `output.sha256` 哈希锁）。
   - **选项 B**：不新增 `tu eval report` 子命令，仅在 `tu eval run` 时自动调用 `report.py` 并提供 Python 函数接口（事后汇总 CSV 需手动写脚本调用）。

---

## 7. 实施与独立只读复审记录（2026-11-22）

- **用户决策**：全部按推荐选项 A 实施（合并 T061+T063；7 列含可选 `dimension` 且向下兼容纯 6 列；SC-007 严格全分母主行 + 已定位引用对照行；新增只读 `tu eval report` 且禁止覆盖历史产物）。
- **独立复审闭环**：共进行 **2 轮**独立只读复审（单节点高思考审查员 `gemini-4-neon-high`，只读核查零改动、未触碰 `inputs/`），**一致通过**。

### 7.1 Round 1 复审发现与处置（结论：需修改 → 4 阻断项 + 2 非阻断建议）

1. **[B1 阻断 · 已修复]** 历史 run 缺少 `refusal_evidence` 但含旧 `refusal_correct` 时（实测 `run-20261113-092116` 的 `smoke-002`），SC-008 总体指标与失败清单自相矛盾。
   - **处置**：`_resolve_refusal_correct` 改为直接复用 `_resolve_refusal_flag` 与 `_expected_refusal` 同源判定；实测 `run-20261113-092116` 输出 SC-008 `0/1`、按类别 `refusal | 1 | 1`、失败清单 `smoke-002 | 范围外未拒答`，已补冲突回归单测。
2. **[B2 阻断 · 已修复]** `load_reviews` 先 `splitlines()` 导致带引号多行评论丢换行、空行后行号错位、未加引号逗号导致多余列被静默丢弃、非 UTF-8（GBK）与 `csv.Error` 未转为 `ReportError`。
   - **处置**：改用 `csv.DictReader(io.StringIO(raw_text, newline=""))` 与 `reader.line_num`；对目标 `run_id` 拦截 `raw_row.get(None)` 多余列；捕获 `UnicodeDecodeError` 与 `csv.Error` 统一抛 `ReportError`；补齐 4 项回归单测。
3. **[B3 阻断 · 已修复]** 重复行去重时，前条有时间戳 `fail`、后条留空时间戳 `pass` 被错误忽略，且原同时间戳覆盖单测为弱断言。
   - **处置**：仅当双方 `created_at` 均非空且不等时按时间戳比较，否则按 `line_no` 靠后者胜出；消除弱断言（`fail`→`pass` 并校验 `comment`）并补空时间戳追加修订回归单测。
4. **[B4 阻断 · 已修复]** `_validate_run_id` 未拦截 `.` 导致目录逃逸至 `artifacts/eval`。
   - **处置**：拒绝 `.`、`..`、首尾空白及 `Path(run_id).name != run_id`，并补单测。
5. **[S1 / S2 非阻断 · 已采纳]** `cli.py` 防覆盖保护扩展至历史 run 目录内 `report.md` / `manifest.json` / `results.jsonl`，写入捕获 `OSError` 返回退出码 2，补齐 CLI `--reviews`、跨 run/符号链接防覆盖与目录 `--out` 单测；`_esc_cell` 补充 `\r` 且 `by_category` 走 `_esc_cell`；`00-glossary.md` 新建独立 `## 评测` 分组。

### 7.2 Round 2 复审结果（结论：通过）

- **阻断项**：0 项；**未决分歧**：无。
- **非阻断留档备忘**：`load_reviews` 中访问 `reader.fieldnames` 位于 `try ... except csv.Error` 之前（仅在表头含 NUL 字节的极端畸形文件下触发，常规 CSV 无影响，留待后续顺手收口）。
- **验收证据**：
  - `uv run pytest`：**408 passed, 6 xfailed**（基线 388 passed → 新增 20 项单测全绿，含 `test_report.py`、`test_article_eval.py`、`test_anonymize.py`、`test_compare.py`、`test_metrics.py`、`test_runtime_isolation.py`）；
  - `uv run ruff check src tests`：**All checks passed!**；
  - `shasum -a 256 -c artifacts/logs/t075/01/output.sha256`：**25/25 OK**；
  - 只读抽验历史 run：`run-20261117-081504`（60 题）、`run-20261120-183952`（70 题）、`run-20261122-090101`（10 题）、`run-20261113-092116`（2 题）全项指标与原始产物对账一致。

### 7.3 第三方审稿意见处置（2026-11-22，用户拍板全部按推荐修复）

1. **时间格式混用去重**：改为 `datetime.fromisoformat` 解析比较（同为带时区统一转 UTC，同为无时区直接比；任一方解析失败或时区有无不一致时回退按物理行号靠后者胜出），并在 `[L6.4]` 注明推荐 ISO 8601。
2. **7 列模板 `dimension` 留空行为**：与 6 列模板统一，留空时非拒答普法文章默认归 `correctness`，应拒答题与非文章题归 `other`；显式填 `other` 仍归 `other`。
3. **SC-009 / SC-010 统计单位**：在 `report.md` 口径列与 `[L6.4]` 明确说明 POC 按 `题 × 评审人` 记录统计（非逐篇展开）。
4. **规格文档同步**：保持 `specs/001-legal-clause-assistant/data-model.md` 不动，于 `[L6.4]` 及后续 `tasks.md` 结项备注注明“6 必需列 + 第 7 可选列 `dimension`，向下兼容纯 6 列”。
5. **实得 0 篇标注**：待评审清单对实得 0 篇且未评审的普通文章题标注 `待评审（实得 0 篇）`，不改变适用题数分母。
6. **工程收口**：`load_reviews` 将 `fieldnames` 读取纳入 `csv.Error` 捕获、拦截重复列名与非空行缺失 `run_id`；`cli.py` 禁止 `--out` 写入历史 run 目录内任意路径（含新建文件）；`runner.py` 复用 `report._expected_refusal`；`render_report` 消除 `extract_failures` 重复计算。
