# T062 执行单 · 通用多 Run 评测对比（`tu eval compare`）与 SC-015 稳定性校验

**状态：已验收完成（2026-11-23）。** 基于主线提交 `8d46fb4`（T061 + T063 已验收提交）。用户已批准第 6 节全部 4 项决策采用推荐方案（选项 A）。本执行单承接 Phase 5 / US3（统一评测集衡量系统质量），在复用 T076 可比性核对框架与 T061 `summarize_run` / `extract_failures` 共享聚合底座的前提下，于 `src/tu_assistant/eval/compare.py` 与 `src/tu_assistant/cli.py` 实现通用多 run 对比 `tu eval compare <run_id>...`（输出 `compare.md`，满足 FR-035），并补齐面向 T064 的 **SC-015 重复评测稳定性判定（`≤ 2.0 pp`）**，同时保持既有 `--sc016` 行为与全部历史产物 100% 零破坏。

> **合规与红线声明**：起草与实施全过程**严禁读取 `inputs/` 目录下任何文件**；**严禁改动历史产物**（历史 KB、历史数据集、已训权重及历史 `artifacts/eval/<run_id>/`）；评测模块（`src/tu_assistant/eval/`）严格满足零外部 LLM 客户端导入约束（`tests/unit/test_runtime_isolation.py`）。

---

## 1. 推荐任务编号与选择理由

**推荐任务：`T062`（实现通用 `tu eval compare <run_id>...` 于 `src/tu_assistant/eval/compare.py`，输出 `compare.md`，FR-035）。**

### 1.1 为什么优先做 `T062`？

1. **承接用户已批准的 Phase 5 推进顺序**：在 `T061 + T063` 执行单中已明确并获拍板的推进路径为：
   `T061 + T063`（已完成） → **`T062`（通用对比）** → `T049`（补齐 ~20 题多违法行为与意图用例） → `T064`（7B 重复评测 2 次验证 SC-015 并同步核销 `T059`） → `T065`（整理 `docs/learning/06-evaluation.md`）。
2. **直接复用刚落地的 `report.py` 共享聚合底座**：T061 刚在 `src/tu_assistant/eval/report.py` 沉淀了纯函数、确定性的 `summarize_run`、`extract_failures` 与 `load_reviews`，`T062` 立即接入可保证单次报告与多 run 对比 **100% 同源同口径**，彻底避免指标口径漂移。
3. **直接解除 `T064` 与 `T059` 的工具阻塞**：`T064` 明确要求“对 7B 演示模型重复评测 2 次，用 `tu eval compare` 验证指标波动 ≤2 个百分点（SC-015），结果存于 `artifacts/eval/`”，且 `T059` 核销依赖 `T064` 完成。
4. **纯确定性工程交付、零外部阻塞**：不依赖外部 API、不依赖模型服务启动或长时推理、不依赖人工审题，范围清晰且可由单元测试 + 仓库内真实历史 run 只读抽验完全闭环。

### 1.2 与其他主要未完成候选的横向对比

| 候选任务 | 当前状态与前置条件 | 为何优先做 `T062` |
|---|---|---|
| **`T062`（推荐）** | `[P]` 任务，依赖（`T061`/`T063` 与 `T076`）已全部就绪；当前 `cli.py` 在不带 `--sc016` 时返回占位错误 `"目前仅支持 --sc016；通用多 run 对比由 T062 实现"` | 纯确定性代码与单测，立即打通 FR-035 多版本对比与 SC-015 稳定性校验，为 `T064` / `T059` / `T065` 铺平最后一块工具拼图 |
| **`T049`（补写 v1 多违法行为与意图确认约 20 题）** | Phase 3 US1 唯一未勾项；当前 `eval/cases/v1/` 仅含 60 题 `clause_id` + 10 题 `article` | 涉及 ~20 道新用例编写与用户逐题审阅，周期更长；先完成 `T062`（轻量确定性工程），再专心做 `T049` 内容审定，随后在完整 v1（~90 题）上一次跑完 `T064` |
| **`T064`（7B 重复评测 2 次验证 SC-015）与 `T059` 核销** | 强依赖 `T062` 的 `tu eval compare`；用户在 T056 已拍板 `T059` 留待 `T064` 后核销 | 缺少 `T062` 无法用正式 CLI 校验 SC-015 ≤ 2 个百分点并产出 `compare.md` |
| **`T065`（撰写 `docs/learning/06-evaluation.md` 完整章节）** | 已按实现进度累积至 `L6.1–L6.4` | 需等 `T062`（对比方法与 SC-015）及 `T064`（完整 7B 重复评测实测数据）完成后统一收口 |
| **Phase 6（`T066–T068`，US4 知识库维护）** | P4 优先级，模块独立（`kb/diff.py`、`configs/app.yaml` 的 `kb.version`、更新集成测试） | 不阻塞 Phase 5 与 T059 收口；待 Phase 5 收尾后（或 `T069` Gradio UI 前）实施更顺畅 |
| **Phase 7（`T069–T074`，Gradio UI 与收尾）** | 最终演示界面与 V1–V7 全量验证（V5 明确包含 SC-015 ≤ 2 个百分点） | 应先完成 Phase 5 评测闭环与 `T059` 核销，再进入演示与收尾 |
| **`T078`** | 已标记 `[Post-POC / 正式阶段]` | 2026-11-19 已由用户确认移出 POC 范围，不纳入候选 |

---

## 2. 背景与只读摸底核实

以下数据、代码状态与历史产物均经仓库只读核实（未触碰 `inputs/`）：

### 2.1 当前代码与测试基线

- **代码基线**：`8d46fb4`（`feat(eval): implement full eval report and manual review template (T061, T063)`）。
- **测试基线**：`uv run pytest` **408 passed / 6 xfailed**，`ruff` 全绿。
- **既有 `compare.py`（T076）现状**：
  - 已实现 `CompareError`、`EvalRunResults`、`load_run`、`CasesCheck`、`cases_source_check`、`comparability_issues`、`role_issues`、`align_cases`、`load_doc_index`、`resolve_kb_path`、`loose`、`fisher_exact_two_sided`、`score_case`、`Sc016Result`、`sc016`。
  - `src/tu_assistant/cli.py`（L1103–L1176）：`tu eval compare` 当前仅接受 `--sc016`（恰好 2 个 run），未传 `--sc016` 时直接提示 `"目前仅支持 --sc016；通用多 run 对比由 T062 实现"` 并以退出码 `2` 退出。
  - **既有单测占位断言（实施时须同步更新）**：`tests/unit/test_compare.py` L423–424 存在：
    ```python
    r3 = runner.invoke(app, ["eval", "compare", "rb", "rt", "--artifacts", str(tmp_path)])
    assert r3.exit_code == 2 and "T062" in r3.output
    ```
    T062 落地后，该行须更新为验证通用对比正常执行（返回退出码 `0` 并输出对比报告），同时补充单参数 `eval compare rb` 返回 `2` 的测试。
  - **路径校验补齐**：`report.py` 已有 `_validate_run_id` 拦截 `.`、`..`、`/`、`\` 与首尾空白，而 `compare.py:load_run` 尚未校验 `run_id` 合法性；T062 顺手在 `load_run` 入口补齐同等校验（非法 `run_id` 抛 `CompareError` 返回 2），同时惠及 `--sc016` 与通用对比。

### 2.2 仓库现有历史评测 Run 实测核对（只读）

对 `artifacts/eval/` 下全部 20 个目录的 `manifest.json` 与 `results.jsonl` 只读核查，发现以下可直接用于 T062 只读抽验的真实历史组（全部经 `comparability_issues` 与 `summarize_run` 实测确认）：

| 真实历史对比组 | 共同条件（KB / 评测集 / 设置） | 实测指标与逐题变化（只读核对） | 验证价值 |
|---|---|---|---|
| **多版本 3-run 对比**：`run-20261117-081504`（resume500）→ `run-20261118-020130`（epoch2）→ `run-20261120-183627`（T075 article-01） | `kb-20261113-093057` / `eval/cases/v1/reviewed.jsonl`（60 题 `clause_id`）/ `temp=0.0, sys=True` | SC-002：`0.150 → 0.150 → 0.100`；SC-003：`0.265 → 0.188 → 0.128`；SC-006：`1.000 → 1.000 → 0.984`；SC-007 校验前/后：`0.567 → 0.800 → 0.770`；前两轮虽同为 9 通过 / 51 失败，实则 `fail→pass` 3 题、`pass→fail` 3 题（`both_pass=6`）；且混含旧 schema（无 `refusal_evidence`，自动复算 60 题）与新 schema | 验证 `≥3` 个 run 对比、旧/新 schema 兼容、聚合持平但逐题互换的诊断价值 |
| **同模型重复评测（SC-015 PASS 正例）**：`run-20261116-021610` vs `run-20261117-022645`（均为 7B 裸基座） | `kb-20261113-093057` / `eval/cases/v1/reviewed.jsonl`（60 题）/ `temp=0.0, sys=True` | 相同请求模型 `Qwen2.5-7B-Instruct-4bit`；各项有效指标均为 `0.000 vs 0.000`，最大波动 `0.0 pp ≤ 2.0 pp` → `--sc015` PASS（退出 0） | 真实历史同模型重复评测正例 |
| **代码变更后波动超限（SC-015 FAIL 反例）**：`run-20261120-024531` vs `run-20261122-090101`（均为 `exp-20261116-resume500`，T054 脱敏前 vs 后） | `kb-20261119-045641` / `eval/cases/v1/articles.jsonl`（10 题 `article`）/ `temp=0.0, sys=True` | SC-006：`0.833 → 0.833`；SC-007 校验前/后：`0.667/0.833 → 0.667/0.833`；SC-008 范围外 `1.000` / 误拒 `0.444` 不变；**SC-011：`0.000 (0/2) → 1.000 (2/2)`（`+100.0 pp`）** → `--sc015` FAIL（退出 1） | 验证普法文章类指标与 SC-011 波动拦截 |
| **反例校验组** | ① 诊断集：`run-20261117-124545` vs `run-20261118-020647`（`train-probe-v1.jsonl`）；② 跨 KB/评测集：`run-20261117-081504` vs `run-20261120-183952`；③ 缺 manifest 目录：`run-20261122-090018` | 均应报确定性 `CompareError`（退出 2） | 真实历史反例防线 |
| **T076 回归组** | `run-20261117-022645` vs `run-20261117-081504` | `--sc016` 复现条级 `1/60 → 17/60`、款级 `9/60`、文件子集 `0/30 → 21/30`，PASS（退出 0） | 保证 T076 零回归 |

- **历史产物哈希锁**：`artifacts/logs/t075/01/output.sha256` 锁定 25 项文件（含 `run-20261120-024531`、`025521`、`183627`、`183952` 的 `manifest.json`/`report.md`/`results.jsonl`）。任何对比操作严禁写入已有历史 run 目录，验收必复核 `shasum -a 256 -c artifacts/logs/t075/01/output.sha256` 25/25 OK。

---

## 3. 实施边界与核心设计

### 3.1 文件变更边界

| 文件 | 操作 | 职责 |
|---|---|---|
| `src/tu_assistant/eval/compare.py` | **修改** | ① 为 `load_run` 补齐 `run_id` 安全校验；② 新增通用多 run 可比性与对齐校验（`check_general_comparable`、`align_general_cases`、`same_system_issues`）；③ 新增结构化对比聚合与 SC-015 稳定性判定（`compare_runs`、`evaluate_sc015`）；④ 新增 Markdown 渲染与安全落盘（`render_compare_markdown`、`save_compare_artifact`）；⑤ **不改变**既有 T076 `--sc016` 函数签名与判定语义 |
| `src/tu_assistant/cli.py` | **修改** | 扩展 `tu eval compare`：保留 `--sc016` 原样分支；支持通用多 run 对比（`runs` `≥2`、`--sc015`、`--reviews`、`--out`、`--save`、`--artifacts`），补全互斥选项检查与历史 run 目录防覆盖保护 |
| `tests/unit/test_compare.py` | **修改** | 更新 L423–424 的 T062 占位断言，新增覆盖通用多 run 对比、可比性校验、目录扩题兼容、逐题状态变化、SC-015 判定（含浮点边界与单侧 `None`）、`--reviews`、`--out`/`--save` 落盘与防覆盖保护的完整单元测试 |
| `docs/learning/06-evaluation.md`、`README.md`、`00-glossary.md` | **修改** | 增补 `[L6.5]` 学习小节并同步索引与术语表 |

**明确不做（防越界）**：
- 不修改 `src/tu_assistant/eval/metrics.py`、`runner.py`、`cases.py`、`report.py` 的既有打分与报告行为（`compare.py` 只导入 `report.py` 公开接口 `POC_TARGETS`、`ReportError`、`extract_failures`、`load_reviews`、`summarize_run`）；
- 不改变 `tu eval compare --sc016` 的任何判定口径、输出格式与退出码；
- 不修改 `eval/cases/v1/`、`specs/`、`configs/`、任何历史 `artifacts/` 目录，不运行模型推理。

### 3.2 多 Run 可比性校验与对齐规则（通用对比 vs `--sc015` vs `--sc016`）

| 检查维度 | `--sc016`（保持原样） | 通用对比（FR-035） | `--sc015`（重复评测稳定性） |
|---|---|---|---|
| **run 数量与去重** | 恰好 2 个（基座 + 自训） | `≥ 2` 个，且 `run_id` 不得重复（重复报 `CompareError` 退出 2） | `≥ 2` 个，且 `run_id` 不得重复（重复报 `CompareError` 退出 2） |
| **KB / 评测集名 / `temperature` / `use_system_prompt`** | 冲突退 2；缺失退 1 | 冲突退 2；缺失归入 `issues`（无法确认可比性，退 1） | 冲突退 2；缺失归入 `issues`（无法判定，退 1） |
| **诊断集拦截** | 命中路径或 `source=train_probe` 退 2 | **同样拦截**，命中退 2（遵守 `data-model.md` §3） | **同样拦截**，命中退 2 |
| **磁盘评测集与结果 ID 关联**（见决策 3） | 严格 `chk.case_ids == set(run.rows)`（原样不动） | `run.rows ⊆ chk.case_ids` 放行（若为真子集，在 `compare.md` 顶部写明“评测集后续扩题，仅按历史共有 N 题对比”）；存在 `run.rows - chk.case_ids` 退 2；文件缺失/为空归入 `issues` 退 1 | 同通用对比（确保 `run.rows` 全部溯源至非诊断评测集，且路径缺失无法确认时退出 1） |
| **跨 run 逐题对齐** | 仅 `category == "clause_id"` 且 `len(gold.clauses) == 1` | **全 7 类用例全部参与**：要求所有 run 的 `set(run.rows)` 完全一致，且每个 `case_id` 的 `category`、每轮 `turns[].user`、`gold` 完全一致（不一致退 2）；至少 1 题（空结果退 2） | 同通用对比 |
| **模型 / 实验角色约束** | 严格基座 vs 同底座 `default_model` | **不限制角色**（允许不同 adapter、基座 vs 自训、1.5B vs 7B、不同代码版本对比） | **核对同一系统版本**：全部 run 必须相同 `config.model`；若为 `default_model` 则必须相同 `config.exp` 与 `config.base_model`（冲突退 2；缺 `config.model` 或 adapter 缺 `exp`/`base_model` 归入 `issues` 退 1） |

> **兼容提示**：若参与对比的任一历史 run 缺少 `scores.refusal_evidence`（如 `run-20261117-081504`），`report.summarize_run` 会自动按 `detect_refusal(final_text)` 只读复算 SC-008，并在 `compare.md` 元信息中标注各 run 的 `recomputed_count`，不修改历史文件。

### 3.3 指标对比口径与 SC-015 稳定性判定

1. **共享聚合入口**：每个 run 按 `case_id` 升序构造 `results_list = [run.rows[cid] for cid in sorted(run.rows)]`，调用：
   - 可选 `reviews = load_reviews(reviews_path, run_id=run.run_id, results=results_list)`（`ReportError` 统一转为 `CompareError`，退出码 2）；
   - `failures = extract_failures(results_list, reviews=reviews)`；
   - `summary = summarize_run(results_list, reviews=reviews, run_id=run.run_id, _failures=failures)`。
2. **参与总体对比与 SC-015 的 13 项百分比指标**（均取自 `summary`，值域 `[0.0, 1.0]`）：
   - `SC-001`（`sc001.value`，意图确认率）
   - `SC-002`（`sc002.value`，条款召回率）
   - `SC-003`（`sc003.value`，条款精确率）
   - `SC-004`（`sc004.value`，多违规识别率）
   - `SC-005`（`sc005.value`，关联条款完整率）
   - `SC-006`（`sc006.value`，出处标注完整率）
   - `SC-007（校验前）`（`sc007.pre`，严格全分母主口径）
   - `SC-007（校验后）`（`sc007.post`，严格全分母主口径）
   - `SC-008（范围外正确拒答）`（`sc008.outside_rate`）
   - `SC-008（范围内误拒）`（`sc008.false_refusal_rate`）
   - `SC-009`（`sc009.value`，加载 `--reviews` 且有记录时）
   - `SC-010`（`sc010.value`，加载 `--reviews` 且有记录时）
   - `SC-011`（`sc011.ratio`，文章身份无泄露率）
   - 另附**非门禁对照/辅助行**（展示在表中供对账，不参与 SC-015 门禁判定）：`SC-007（已定位·校验前/后）`、`引用判定分布（ok/corr/nf/inc）`、`引用冲突暂缓交稿（T054）`、`文章篇数符合（FR-028）`。
3. **差值与最大波动计算**：
   - 设某指标在各 run 的值序列为 `[v_0, v_1, ..., v_{k-1}]`（`v_0` 为基准 run）：
     - 全为 `None` → 显示 `-`；SC-015 状态为 `skipped`（无样本/待评审）；
     - **部分为 `None`、部分为数值**（例如某轮有有效分母、另一轮分母为 0）→ 差值与波动显示 `无法比较（部分无样本）`；SC-015 状态为 **`FAIL`（部分 run 无有效分母）**，严禁过滤 `None` 后误算为 `0.0 pp`；
     - 全部为数值 → 末轮相对基准差值 `delta = v_{k-1} - v_0`（同时展示 `±0.000 (±0.0 pp)`），多 run 跨度 `spread = max(vals) - min(vals)`（单位 `pp = spread * 100`）；SC-015 通过条件为 `spread <= 0.02 + 1e-9`（带 `1e-9` 容差，避免 IEEE 754 `0.17 - 0.15 = 0.020000000000000018` 误判超限）。
   - SC-015 总判定：若至少 1 项指标有效参与且全部通过（无超限、无单侧 `None`），总判定 `PASS`（退出 `0`）；若任一项失败或所有指标均无样本（0 项可评），总判定 `FAIL` / `无法判定`（退出 `1`）。

### 3.4 `compare.md` 报告结构设计

1. **标题与元信息**：
   - `# 评测对比报告`
   - 对比 run（按输入顺序，标注第 1 列为基准）、共同知识库、共同评测集、用例数、评测设置（`temperature`、`use_system_prompt`）、可选人工评审文件、兼容/扩题提示（如有）；
   - **参与对比的 Run 概览表**：`| 序号 | run_id | 实验（exp） | 基座 / 请求模型 | 用例数 | 失败用例数 |`；
   - POC 目标值定位提示与单位说明（`1 pp = 0.01`）。
2. **## SC-015 重复评测稳定性判定**（仅在 `--sc015` 模式下输出，置于总体指标前方便一眼看结论）：
   - 系统版本一致性核对摘要、阈值 `≤ 2.0 pp`、逐项参与判定的指标波动与 `PASS / FAIL / 跳过` 表、以及加粗 **总判定**。
3. **## 总体指标对比（SC-001 ~ SC-011）**：
   - 2 个 run：`| 编号 | 指标 | <run_1>（基准） | <run_2> | 差值（相对基准） | 最大波动 | POC 目标值 |`；
   - `≥ 3` 个 run：`| 编号 | 指标 | <run_1>（基准） | <run_2> | ... | <run_k> | 末轮相对基准 | 最大波动 | POC 目标值 |`；
   - 覆盖全部 13 项百分比指标 + 对照/辅助行（数值均附带分子/分母或 n，表格单元经 Markdown 转义）。
4. **## 按类别失败数对比**：
   - `| 类别 | 用例数 | <run_1> 失败数 | ... | <run_k> 失败数 | 末轮相对基准 |`（按类别名升序）。
5. **## 逐题状态变化（相对基准 `<run_1>`）**：
   - 汇总计数（基准 vs 末轮）：`新通过（fail→pass）`、`退步（pass→fail）`、`始终通过`、`始终失败`（其中失败原因变化数）；
   - **新通过用例（fail → pass）** 明细表（按 `case_id` 升序，列原失败原因）；
   - **退步用例（pass → fail）** 明细表（按 `case_id` 升序，列新失败原因）；
   - 当 `≥ 3` 个 run 时，额外输出 **多轮状态切换矩阵**（仅列出在各 run 间出现过 `pass/fail` 切换的 `case_id`，列每轮 `PASS`/`FAIL`，按 `case_id` 升序）；
   - 若所有 run 间逐题通过状态完全一致，明确输出“各 run 逐题通过/失败状态无变化。”

### 3.5 CLI 接口与产物保护

```bash
# 1. 通用多 run 对比（默认只读输出到 stdout）
uv run tu eval compare <run_1> <run_2> [<run_3> ...] [--reviews <csv>] [--artifacts artifacts]

# 2. 写入指定文件（禁止写入已有历史 run 目录）
uv run tu eval compare <run_1> <run_2> --out /tmp/compare.md

# 3. 落盘至独立产物目录 artifacts/eval/compare-<YYYYMMDD-HHMMSS>/（含 compare.md + manifest.json）
uv run tu eval compare <run_1> <run_2> --save

# 4. SC-015 同模型重复评测稳定性判定（T064 使用，可组合 --save 或 --out）
uv run tu eval compare --sc015 <run_1> <run_2> [--save]

# 5. SC-016 POC 验收判定（T076，保持 100% 原样兼容）
uv run tu eval compare --sc016 <base_run> <trained_run>
```

- **选项互斥与参数校验（均返回退出码 `2`）**：
  - `len(runs) < 2`；
  - `--sc016` 与 `--sc015` 同时传入；
  - `--sc016` 与 `--out` / `--save` / `--reviews` 同时传入（避免语义混淆）；
  - `--out` 与 `--save` 同时传入；
  - `--out` 解析路径位于 `artifacts/eval/` 下任意已存在子目录内（复用 `eval_report` 同等防护，避免覆盖历史 `run-*` 或历史 `compare-*`）。
- **`--save` 碰撞保护**：若同秒内已存在 `artifacts/eval/compare-<ts>`，自动追加序号 `-2`、`-3`…，确保永不覆盖既有目录；`manifest.json` 通过 `write_manifest` 写入，包含 `artifact_type="eval_compare"`、`inputs={"runs": [...], "kb": ..., "cases": ..., "reviews": ...}`、`config={"mode": "sc015" | "general", "threshold_pp": 2.0}` 与 `extra`（`case_count`、`sc015_passed` 等）。

---

## 4. 实施步骤与确定性验收方法

### 4.1 实施步骤

1. **加固 `load_run` 与新增通用校验（`src/tu_assistant/eval/compare.py`）**：
   - 在 `load_run` 入口增加 `run_id` 合法性校验（拒绝空串、`.`、`..`、`/`、`\`、首尾空白）；
   - 实现 `check_general_comparable`、`align_general_cases`、`same_system_issues`，保持既有 `comparability_issues`、`role_issues`、`align_cases`、`sc016` 原样不动。
2. **实现通用聚合对比、SC-015 判定与 Markdown 渲染（`src/tu_assistant/eval/compare.py`）**：
   - 实现 `compare_runs`（复用 `report.summarize_run`、`extract_failures`、`load_reviews`）；
   - 实现 `evaluate_sc015`（13 项百分比指标、`≤ 0.02 + 1e-9`、单侧 `None` 拦阻、全空无法判定）；
   - 实现 `render_compare_markdown` 与 `save_compare_artifact`（落盘 `compare.md` + `manifest.json`）。
3. **接入 CLI（`src/tu_assistant/cli.py`）**：
   - 扩展 `eval_compare`，补齐 `--sc015`、`--reviews`、`--out`、`--save`、互斥校验、防历史目录覆盖保护及退出码约定（`0` / `1` / `2`）。
4. **补充单元测试（`tests/unit/test_compare.py`）**：
   - 更新 L423–424 占位断言并补充第 4.2 节全部确定性验收用例。
5. **仓库真实历史产物只读抽验**：
   - 用正式 CLI 只读验证第 2.2 节的 5 组真实历史用例（3-run 对比、SC-015 PASS、SC-015 FAIL、SC-016 回归、诊断集/跨 KB 拒绝），并核验 `shasum -a 256 -c artifacts/logs/t075/01/output.sha256` 保持 25/25 OK。
6. **更新学习文档**：按第 5 节补写 `docs/learning/06-evaluation.md`（`[L6.5]`）并同步 `README.md` 与 `00-glossary.md`。
7. **独立只读复审闭环**：按 `.agents/skills/task-review-loop/SKILL.md` 执行最多 5 轮独立复审，全部通过后汇报验收（用户确认前不勾选 `tasks.md`、不 `git commit`）。

### 4.2 确定性验收矩阵（不把不可确定的语义判断写进单测）

| 验收项 | 确定性验证方式与通过条件 |
|---|---|
| **1. 2-run 与 3-run 通用对比聚合** | 在 `tests/unit/test_compare.py` 构造覆盖多类别（`clause_id`/`multi_violation`/`refusal`/`false_refusal`/`intent`/`article`）的合成 2-run 与 3-run 样本，逐项手算断言 13 项指标、相对基准差值（pp）、最大波动、按类别失败数及逐题 `fail→pass` / `pass→fail` 与 3-run 状态矩阵精确匹配 |
| **2. SC-015 稳定性判定与边界** | ① 同模型波动 `0.0 pp` → PASS（退出 0）；② 浮点边界 `0.15` vs `0.17`（精确 `2.0 pp`）→ PASS（退出 0）；③ `0.15` vs `0.171`（`2.1 pp`）→ FAIL（退出 1）；④ 单侧 `None`（一方有分母一方无分母）→ FAIL（退出 1）；⑤ 全部指标无样本 → 无法判定（退出 1）；⑥ 不同 `exp` / 不同 `model` / 不同 `base_model` → 输入错误（退出 2）；⑦ `default_model` 缺 `config.exp` 或 `config.base_model` → 无法判定（退出 1） |
| **3. 可比性与安全防线** | ① 重复 `run_id`、单 run、`run_id` 含 `..`/`/`/`.` → 退出 2；② KB 不一致、评测集名不一致、`temperature`/`use_system_prompt` 不一致、`case_id`/提问/`gold` 不一致、诊断集（路径或 `source=train_probe`）→ 退出 2；③ 缺 `temperature`/`use_system_prompt` 或磁盘 `cases` 不存在 → 无法确认（退出 1）；④ 磁盘目录扩题（`run.rows` 为磁盘 `cases` 真子集）→ 放行并在 `compare.md` 输出提示；结果出现磁盘不存在的 `case_id` → 退出 2；⑤ 旧 schema（无 `refusal_evidence`）自动兼容复算 |
| **4. 人工评审 `--reviews` 与落盘/防覆盖保护** | ① 一份 CSV 同时含 2 个 run 的 `correctness`/`diversity` 行，验证 SC-009 / SC-010 正确并排对比与差值计算；② 默认只读输出 stdout 不创建文件；③ `--out` 指向已有历史 `artifacts/eval/<run_id>/...` 被拒绝（退出 2）且原文件字节不变；④ `--save` 创建 `artifacts/eval/compare-<ts>/` 含合法 `compare.md` 与 `manifest.json`（同秒连续调用不覆盖）；⑤ 互斥参数（`--sc016 --sc015`、`--out --save`、`--sc016 --out` 等）全部返回退出码 2 |
| **5. 真实历史产物只读抽验与 T076 零回归** | ① `uv run tu eval compare run-20261117-081504 run-20261118-020130 run-20261120-183627`（退出 0，数值与第 2.2 节一致）；② `uv run tu eval compare --sc015 run-20261116-021610 run-20261117-022645`（PASS，退出 0）；③ `uv run tu eval compare --sc015 run-20261120-024531 run-20261122-090101`（SC-011 100.0 pp FAIL，退出 1）；④ `uv run tu eval compare --sc016 run-20261117-022645 run-20261117-081504`（PASS，退出 0）；⑤ `run-20261117-124545` vs `run-20261118-020647`（诊断集拒绝，退出 2）；⑥ `shasum -a 256 -c artifacts/logs/t075/01/output.sha256` 25/25 OK |
| **6. 全量回归与合规检查** | `uv run pytest` 全绿（408 passed / 6 xfailed 基线 + 新增 `test_compare.py` 全通过，含 `test_runtime_isolation.py` 与 `test_report.py`）；`uv run ruff check src tests` 全绿；`git status` 确认未改动 `specs/`、`eval/cases/v1/`、`artifacts/` |

---

## 5. 学习文档更新点

- **`docs/learning/06-evaluation.md` 新增 `[L6.5]` 多版本对比与重复评测稳定性（FR-035 / SC-015）：为什么“同口径”和“2 个百分点”是对比的前提**：
  - 用本项目真实历史对比（`run-20261117-081504` vs `run-20261118-020130`：两者 SC-002 均为 `0.150` 且均为 9 通过 / 51 失败，但逐题层面有 3 题新通过、3 题退步，同时 SC-003 下降 7.7 pp、SC-007 上升 23.3 pp）说明为什么不能只看单一总分，而要同时看“多指标差值（pp）”与“逐题状态翻转”；
  - 拆解对比前的可比性红线（同一 KB、同一评测集、相同温度与 system prompt、拒绝诊断集 `train_probe`）以及目录型评测集扩题后的历史兼容口径；
  - 解释 `tu eval compare` 三种模式的定位差异：常规模式（跨版本/跨方案看变化）、`--sc015`（同模型重复评测波动 ≤ 2 个百分点，含浮点边界与单侧无分母陷阱）、`--sc016`（POC 验收：基座 vs 自训是否学到知识）。
- **索引与术语同步**：
  - 更新 `docs/learning/README.md` 第 6 章状态为 `进行中（已含 L6.1–L6.5；完整章节由 T065 整理）`；
  - 在 `docs/learning/00-glossary.md` 的 `## 评测` 分组补充“百分点（pp）”、“重复评测波动（SC-015）”术语并链接至 `[L6.5]`。

---

## 6. 待用户拍板的决策清单

请逐项确认以下 4 项（如均同意推荐项，可直接回复“按推荐方案实施”）：

1. **`tu eval compare` 的输出与落盘模式**
   - **选项 A（推荐）**：默认只读输出 `compare.md` 到 stdout（与 `tu eval report` 风格一致，避免随手对比污染 `artifacts/eval/`）；传 `--out <path>` 写到指定文件（禁止写入已有历史 `artifacts/eval/<existing_dir>/`）；传 `--save` 自动落盘到独立产物目录 `artifacts/eval/compare-<YYYYMMDD-HHMMSS>/` 并同时写入 `compare.md` 与 `manifest.json`（`type="eval_compare"`，直接满足 `contracts/cli.md` 与 T064 归档要求，`--out` 与 `--save` 互斥）。
   - **选项 B**：每次执行通用对比默认直接创建 `artifacts/eval/compare-<timestamp>/` 落盘，额外提供 `--stdout` 切换只读打印。

2. **SC-015 重复评测稳定性校验（`--sc015`）的 CLI 交互与判定边界**
   - **选项 A（推荐）**：新增显式开关 `--sc015`（与 `--sc016` 互斥，阈值按 spec 固定为 `2.0 pp` 并带 `1e-9` 浮点容差），在通用对比基础上叠加“同一系统版本核对（`model` / `exp` / `base_model`）”与“全量有效百分比指标最大波动 ≤ 2.0 pp”门禁，且将“部分 run 有分母、部分 run 无分母（`None`）”判为 `FAIL`（PASS 退 0，FAIL/无法判定退 1，输入冲突退 2）；常规模式不开启门禁（正常退出 0），但仍在表中展示“最大波动”列。
   - **选项 B**：不新增 `--sc015` 开关与自动退出码门禁，仅在 `compare.md` 中列出最大波动列，T064 由人工目视核对。

3. **目录型评测集（如 `eval/cases/v1`）后续扩题后对历史 run 的来源核对策略**
   - **背景**：当前 `run-20261120-183952` 记录 `inputs.cases = "eval/cases/v1"`（当时 70 题）；待 T049 向 `v1/` 增补约 20 题后，磁盘目录将变为约 90 题。
   - **选项 A（推荐）**：`--sc016` 保持 T076 原样严格相等（零改动既有契约与测试）；通用对比与 `--sc015` 在确认各 run 之间题号/提问/`gold` 完全一致且磁盘不含诊断来源的前提下，若 `set(run.rows)` 是当前磁盘 `cases` 的真子集则放行并在 `compare.md` 顶部写明提示；若结果包含磁盘不存在的题号则报错（退出 2），若磁盘路径不存在或为空则无法确认（退出 1）。
   - **选项 B**：通用对比也要求 `set(run.rows) == chk.case_ids` 严格相等（T049 扩题后，历史目录型 run 将无法再用 `tu eval compare` 对比）。

4. **是否顺带为通用对比接入 `--reviews <csv>`（SC-009 / SC-010 对比）**
   - **选项 A（推荐）**：支持可选参数 `--reviews <csv>`，直接复用 `report.load_reviews`（天然按 `run_id` 筛选，同一份 CSV 可汇总多个 run 的人工评审），让 SC-001 ~ SC-011 全量指标都能在同一份 `compare.md` 中并排对比；不传时 SC-009/SC-010 显示待评审且在 `--sc015` 中跳过。
   - **选项 B**：T062 暂不接入 `--reviews`，仅对比自动指标（SC-001 ~ SC-008、SC-011）。

---

## 7. 独立复审与验收记录（2026-11-22）

采用单节点高思考独立只读审查员（`gemini-4-neon-high`）执行 2 轮闭环复审，**第 2 轮一致通过**（阻断项 0、非阻断建议 0、无未决分歧）。

### 7.1 每轮问题与处置

- **Round 1（结论：需修改）**
  - **阻断项 1（单元测试相对 §4.2 存在反例与断言遗漏）**：
    1. 位置 1：`check_general_comparable` 与 `align_general_cases` 缺少 KB 不一致、评测集名不一致、`use_system_prompt` 不一致/缺失、诊断集路径与 `source=train_probe`、`case_id` 集合不同、`category` 不一致、`turns[].user` 不一致、空结果集等反例测试 → **已修复**：新增 `test_general_comparability_and_align_negative_cases` 全部覆盖。
    2. 位置 2：3-run 对比单测未显式区分 SC-007 校验前/后（`corrected=0`），且未断言 SC-003/SC-006/SC-007（校验后）及 `## 按类别失败数对比` 精确行 → **已修复**：为 `v1` 构造 `corrected=1, not_found=1, citation_complete=1/2` 分离校验前/后，补齐全部 13 项指标与 6 类失败数表格精确断言。
    3. 位置 3：未覆盖 T064 直接使用的 `--sc015 --save` 路径（PASS/FAIL 落盘与 `manifest.json` 校验） → **已修复**：新增 `test_sc015_save_and_boundary_precision` 覆盖 PASS（退 0，`sc015_passed=true`）与 FAIL（退 1，`sc015_passed=false`）。
  - **非阻断建议 1（SC-015 超限临界区间展示精度防歧义）**：当波动落入 `(0.02 + 1e-9, 0.0205)`（如 `1/49 ≈ 2.04 pp`）时，`.1f` 会显示 `波动 2.0 pp > 2.0 pp` → **已采纳**：新增 `_fmt_sc015_pp`，超限且 `.1f` 与阈值字符串相等时自动提高精度（如 `波动 2.04 pp > 2.0 pp`），并在单测中锁定回归。
- **Round 2（结论：通过）**
  - 逐项核实 Round 1 全部修复与回归，无新增问题。

### 7.2 实测验收证据

- 全量单测：`uv run pytest` → **414 passed, 6 xfailed**（含 `tests/unit/test_compare.py` 27 passed、`test_report.py`、`test_runtime_isolation.py`）。
- 静态检查：`uv run ruff check src tests` → **All checks passed!**。
- 真实历史产物只读抽验：
  - `uv run tu eval compare run-20261117-081504 run-20261118-020130 run-20261120-183627` → 退出 `0`（SC-002 `0.150→0.150→0.100`，SC-003 `0.265→0.188→0.128`，SC-006 `1.000→1.000→0.984`，SC-007 `0.567→0.800→0.770`，10 题多轮状态切换矩阵）；
  - `uv run tu eval compare --sc015 run-20261116-021610 run-20261117-022645` → 退出 `0`（5 项有效指标 `0.0 pp`，`PASS`）；
  - `uv run tu eval compare --sc015 run-20261120-024531 run-20261122-090101` → 退出 `1`（SC-011 `0.000→1.000`，`100.0 pp FAIL`）；
  - `uv run tu eval compare --sc016 run-20261117-022645 run-20261117-081504` → 退出 `0`（条级 `1/60→17/60`、款级 `9/60`、文件子集 `0/30→21/30`，`PASS`，T076 零回归）；
  - 诊断集 `run-20261117-124545` vs `run-20261118-020647` → 退出 `2`。
- 历史产物哈希锁：`shasum -a 256 -c artifacts/logs/t075/01/output.sha256` → **25/25 OK**。
