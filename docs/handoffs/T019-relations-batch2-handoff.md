# T019 执行单 · 第二批条款关联（`references` / `exception_of`）人工审阅与收口

**状态**　已完成（2026-11-19，用户完成第二批人工审阅并确认收尾，已在 [tasks.md](../../specs/001-legal-clause-assistant/tasks.md) 勾选 T019，并登记解析跟进任务 T078）。起点为 `bf0d65b`，目标可写新 KB 为 `kb-20261119-045641`（导入后合计 67 条已确认：`liability_for` 26、`references` 41），基准历史 KB `kb-20261113-093057` 全程只读不动。

**任务编号**　**[T019](../../specs/001-legal-clause-assistant/tasks.md)**（接续 [T077](T077-relation-clause-handoff.md#64-收尾落实记录2026-11-19用户确认) 已完成的第一批 `liability_for`，完成后关闭 T019 及整个 Phase 2 基础层）。

## 为什么现在做 T019（第二批）

1. **趁 `kb-20261119-045641` 尚在可写窗口内一步定型**：该 KB 目前未被任何数据集或评测 run 引用，可直接事务化导入第二批；若等 T057 建完数据集再补，则会被防误写保护拦截，不得不再次派生新 KB。
2. **清除旧库遗留的 4 条 `references` 错边，清零 Phase 2**：当前新库沿用的 23 条 `references` 中已查明有 4 条错款/漏项旧边；清完后 T057 重建数据集时 `knowledge.relation_samples` 的全部关系样本均为干净数据，Phase 2 全部任务也随之收口。
3. **工具链现成、审阅负担可控**：沿用 T077 已验证的 DeepSeek 离线预审 + 四态 `review` + 事务化 `confirm` + `data/relation-reviews/` 归档链，人工只需重点复核分歧与整条展开项。

---

## 0. 第二批数据现状（只读核查，未触碰 `inputs/`）

对照 `kb-20261119-045641.sqlite` 当前已确认的 23 条 `references` 与全量规则抽取 `kb-20261119-045641-relations_pending.jsonl` 中的 60 条非 `liability_for` 候选（`references` 60、`exception_of` 0）：

| 类别 | 条数 | 明细 / 说明 |
|---|---:|---|
| 待撤销旧错边（`revoke` 候选） | **4** | `be21194cc551533d:a44:p1 → a46:p1:i5`（明指第一项）、`a44:p1 → a46:p1:i6`（明指第四、五项）、`f603773a50aeb8a5:a116:p1 → a146:p1`（明指第三款）、`a214:p1 → a225:p1`（明指第二款） |
| 新增 `references` 候选 | **41** | 其中 `explicit_item` **3**、`explicit_paragraph` **2**（对应上述 4 条旧错边的精确修正，另含《工伤保险实施办法》等新增明指款/项）、`single_paragraph_article` **2**、`whole_article_expanded` **34**（整条引用多款条文按款展开） |
| 旧库沿用且新规则仍命中 | **19** | `single_paragraph_article` 9、`whole_article_expanded` 9、`explicit_paragraph` 1（一并送 DeepSeek 做健康复核，若查出误确认旧边则提示补充撤销） |
| 可选人工补充项（待拍板） | **2** | 第一批因非法律责任而 `reject` 的《公司法》第 154 条第 2/3 款 → 第 100 条（“认股书应当载明……所列事项”），按语义属 `references`（`origin="manual"`） |

---

## 1. 需要用户确认的两项小取舍（拍板后再执行）

1. **是否把《公司法》第 154 条第 2/3 款 → 第 100 条（2 条）按 `relation_type="references", origin="manual"` 纳入第二批审阅清单？**
   - 推荐：**纳入**（在审阅文件末尾列为 2 行由你最终决定 `confirm`/`reject`，不涉及 `liability_for`、不影响普法文章与 SC-005）。
2. **`references` 中 34 条 `whole_article_expanded`（整条展开）的审阅标准**：
   - 与 `liability_for` 相同，按实质相关性逐款判断：若 `to` 条款（如“依照本法第 X 条规定办理/计算/解除”）确实适用于该款内容则 `confirm`；若某款属于纯程序/定义/与 `to` 条款明显无关（如只引用该条第 1 款的实体条件、不涉及第 2 款的附则）则 `reject`。
   - 先用 DeepSeek 离线预审（`temperature=0`、`input_source="kb_clause"`，共约 66 次调用、费用 < ¥0.1，只产预审报告不自动改库），将所有分歧项和 `uncertain` 项单独标红供你重点复核。

---

## 2. 实施步骤

### 第 1 步　生成第二批审阅清单与 DeepSeek 离线预审报告

1. 在 `scripts/t019/` 下编写轻量准备与预审脚本（复用 `kb/relations.py` 与 `synth/llm.py`，严禁触碰 `inputs/`，不改动 `src/` 核心逻辑）：
   - 产出差异审阅文件 `artifacts/kb/kb-20261119-045641-batch2-references_review.jsonl`（45 条 + 可选 2 条手动项，初始 `decision` 全部为 `pending`，附 `suggested_decision`、`evidence`、`scope`）；
   - 产出全量对照表 `artifacts/logs/t019/batch2_candidates_diff.md`（引文摘要 ≤15 字）。
2. 运行 DeepSeek 离线预审（覆盖第二批全部待审行 + 库内沿用的 19 条旧 `references` 复核）：
   - 产出 `artifacts/logs/t019/batch2_prescreen.md` 与 `batch2_prescreen.jsonl`（记录模型、用量与逐条预审理由，不改动数据库，不自动写入 `decision`）；
   - 若沿用的 19 条旧 `references` 中查出疑似错边或纯无关提及，单列一节提示用户是否追加 `revoke`。
3. 在临时目录复制 `kb-20261119-045641` 做试导入演练（验证撤销 + 新增 + 幂等），**正式新 KB 保持不动**。

### 第 2 步　人工关卡（T019 第二批审阅拍板）

1. 用户审阅 `artifacts/logs/t019/batch2_prescreen.md`（重点复核分歧项、`uncertain` 项及整条展开款），或通过终端交互核对：
   ```bash
   uv run tu kb relations review artifacts/kb/kb-20261119-045641-batch2-references_review.jsonl --kb-version kb-20261119-045641
   ```
2. 用户确认逐条最终决定（`confirm` / `revoke` / `reject` / `pending`）后，再进入第 3 步正式导入。

### 第 3 步　正式导入、归档入库与下游对账

1. 执行事务化差异导入：
   ```bash
   uv run tu kb relations confirm artifacts/kb/kb-20261119-045641-batch2-references_review.jsonl --kb-version kb-20261119-045641 --batch batch2-references
   ```
2. **人工审阅源文件入库**：将最终审定的 `kb-20261119-045641-batch2-references_review.jsonl` 复制到 `data/relation-reviews/`，核对其 SHA-256 与 `artifacts/kb/kb-20261119-045641/manifest.json` 中最新 `relation_imports` 记录的 `file_sha256` 逐字一致。
3. **下游对账**（产物写入 `artifacts/logs/t019/batch2_reconcile.md`）：
   - 核对 `kb-20261119-045641` 最终已确认关系数：`liability_for` 保持 **26** 条零改动，`references` 按审定结果更新，4 条旧错边已撤销；
   - 运行 `knowledge.relation_samples` + `check_sample`，确认全部已确认关系 100% 通过校验（零 `citation_mismatch`、零 `citation_text_wrong`）；
   - 核对 `synth/articles._materials` 仍为 `eligible=26`、`paragraph_mismatch=0`；
   - 核对历史旧 KB `kb-20261113-093057` 及全部 18 个历史产物文件 SHA-256 仍为 0 改动（对照 `artifacts/logs/t077/baseline_hashes.json`）。

### 第 4 步　文档更新、回归验证与收尾提交

1. 更新学习文档 [03-knowledge-base.md](../learning/03-knowledge-base.md) L3.4 中的实际已确认关系数字（补齐 `references` 最终确认数），并简述 `references` 与 `liability_for` 在整条展开人工审阅标准上的异同。
2. 在本执行单末尾追加实施记录与验收结果。
3. 跑全量 `uv run pytest`、`uv run ruff check src tests scripts/t019 scripts/t077` 与 `uv run tu eval compare --sc016 run-20261117-022645 run-20261117-081504`。
4. 经用户确认后勾选 [tasks.md](../../specs/001-legal-clause-assistant/tasks.md) 中的 **T019** 并做本地 `git commit`（不 `git push`）。

---

## 3. 验收标准

- [x] 第二批审阅清单覆盖全部 4 条旧 `references` 错边与 41 条新增候选（及用户确认的可选 2 条手动项），DeepSeek 预审报告已归档且未绕过人工确认。
- [x] 用户审定后的第二批已事务化导入 `kb-20261119-045641`：4 条旧错边已撤销、`liability_for` 26 条零变动，最终审定 JSONL 已入库 `data/relation-reviews/` 且 SHA-256 与新 KB `manifest.json` 一致。
- [x] `knowledge.relation_samples` + `check_sample` 在最终新 KB 上 100% 通过；`synth/articles._materials` 保持 `eligible=26, paragraph_mismatch=0`；18 个历史文件 SHA-256 全部 0 改动。
- [x] `uv run pytest`、`uv run ruff check` 与 `tu eval compare --sc016` 全通过；学习文档已同步更新；全程未读取 `inputs/`；勾选 T019 与本地提交均经用户确认。

---

## 4. 实施记录与验收结果（2026-11-19）

### 4.1 预审、审定与导入对账

- **准备与预审**：`scripts/t019/prepare_batch2.py` 生成 47 行差异审阅清单（4 条待撤销旧错边 + 41 条规则新增 + 2 条手动 `references` 补充），并在临时副本通过撤销/新增/幂等/坏行回滚演练；`scripts/t019/prescreen_batch2.py` 对 47 条待审行 + 19 条库内沿用旧 `references` 共 66 条跑完 DeepSeek 离线预审（`input_source="kb_clause"`，`temperature=0`，报告 `artifacts/logs/t019/batch2_prescreen.md`）。
- **人工审定结果**：
  - `revoke` **4 行**（行 1–4：撤销旧库 4 条漏项/错款 `references` 边）；
  - `confirm` **22 行**（行 5–7、10、13、15–17、27–30、33–38、40、44、46–47，含《公司法》第 154 条第 2/3 款 → 第 100 条）；
  - `reject` **21 行**（行 8–9、11–12、14、18–26、31–32、39、41–43、45，其中行 18–25 共 8 行均属《上海市工伤保险实施办法》，因发现条旨误切问题整组暂拒）。
- **正式导入与归档**：执行 `uv run tu kb relations confirm ... --kb-version kb-20261119-045641 --batch batch2-references`，新 KB 最终 `sqlite_sha256` 为 `40d4ea70333404cc`，库内已确认关系合计 **67 条**（`liability_for` 26 零变动 + `references` 41）。审定文件归档至 [data/relation-reviews/kb-20261119-045641-batch2-references_review.jsonl](../../data/relation-reviews/kb-20261119-045641-batch2-references_review.jsonl)（SHA-256 `a579e73cee9c7926`，与新 KB `manifest.json` 逐字一致）。
- **下游核验**（`scripts/t019/reconcile_batch2.py` → `artifacts/logs/t019/batch2_reconcile.md`）：
  - `knowledge.relation_samples` + `check_sample`：**67 / 67** 全部通过（0 丢弃）；
  - `synth/articles._materials`：`eligible=26`、`paragraph_mismatch=0`；
  - 18 个历史基线文件 SHA-256 全部 **0 改动**。

### 4.2 顺带发现的新解析问题（已登记 T078）

- 人工抽查行 18 时发现《上海市工伤保险实施办法》第 27 条 `p1` 为括号小标题“（鉴定程序）”。经 `scripts/t019/diagnose_heading_p1.py` 全库扫描并委托 DeepSeek 诊断（`artifacts/logs/t019/p1_heading_diagnosis.md`），确认全库 24 篇中仅此 1 篇（63/63 条）存在括号条旨被切为 `p1` 导致款号整体顺延 +1 的问题。
- 因该文件涉及 `eval/cases/v1/reviewed.jsonl` 的 5 道正式评测题（含 SC-016 基线 `cand-039`），不在 T019 内顺带改 `parse.py`，已登记为 [tasks.md](../../specs/001-legal-clause-assistant/tasks.md) 的 **T078**（不阻塞当前 POC 演示）。

### 4.3 回归验证

- `uv run pytest`：**181 passed, 6 xfailed**；
- `uv run ruff check src tests scripts/t019 scripts/t077`：全通过；
- `uv run tu eval compare --sc016 run-20261117-022645 run-20261117-081504`：PASS（1→17/60、9/60、0→21/30，退出码 0）。
