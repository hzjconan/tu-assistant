# T053 执行单 · 普法文章修改请求样本合成

**状态**　已完成（2026-11-19，经 3 轮内部独立只读复审 + 1 轮第三方外部模型复审通过并由用户确认收口）。起点为 `2bd43e3`（T019 第二批导入完成）。

### 用户审阅决议（2026-11-19）

1. **修改类型范围**：POC 首批只做 `plainer`（更通俗）与 `swap_subject`（换违法主体），不做 `single`。
2. **窗口策略**：选**方案 A**（仅 1–2 篇初稿，完整输出修改稿），通过三道关卡硬锁 ≤2048 token（入口预筛初稿 ≤1,050 tok + 提示词控篇幅 + 终稿 tokenizer 硬校验 >2048 丢弃）。
3. **T078 时机**：将 T078 标记为 `[Post-POC / 正式阶段]` 移出 POC 范围；KB 与旧数据集保持不动以维护 v1 / SC-016 基线，在 T057 清单与 T074 收尾文档中登记已知缺陷，演示脚本避开该文件款号。
4. **初稿池做法（做法 A）**：先在新 KB `kb-20261119-045641` 上补跑一小批 1–2 篇初稿，经用户确认 3–4 条，加上规范化为显式 `第1款` 的 T052 保留候选 2、3，凑齐 5–6 条不同法规初稿后跑 T053 试生成。

## 为什么下一个做 T053

1. **处在剩余工作的关键路径上。** 剩余链路是 T053 → T057（合入数据集）→ T075（7B 续训 12–14 h，外加复评）。T057 的任务要求合入 “T052、T053 样本”，T052 已完成，现在只差 T053。T075 是剩余耗时最长、且会占用整台机器的环节，越早开始越好。
2. **前置条件已经满足。** T077 修正后的新 KB `kb-20261119-045641` 共有 26 对可用责任关系，同文件多违法候选组合从 2 组增加到 20 组。T019 两批审阅已导入，T077 提到的 “T057 前必须导入” 的写入窗口问题也已处理。T053 的修改轮以 T052 初稿为输入，素材口径不需要再变。
3. **与其他候选比较：**

| 候选 | 为什么不先做 |
|---|---|
| T054–T056 身份信息检查、篇数接入 | 只涉及运行时，不进入训练数据，不在训练链路上。可以在 T075 训练的那晚并行做：写代码和跑单元测试不需要大内存，但不能同时起 7B 推理服务。 |
| T078 上海工伤办法款号顺延 +1 | 已登记为 “不阻塞 POC”。该文件的关联在 T019 第二批被 `reject`，**文章素材不会用到它**，所以不影响 T053。但它**会影响 T057**：知识类样本会把错误款号训进 T075。T057 开工前需要你决定 T078 是先做还是接受（见 §6 决策 3）。 |
| T049 多违法/意图确认评测题 | 需要你逐题审阅，不在训练链路上。可以和 T075 并行。 |
| Phase 5/6（T061–T074） | 依赖 T075 产出的最终演示模型。 |

## 1. 实施边界

- 在 `src/tu_assistant/synth/articles.py` 中新增 `generate_revisions(...)`（名称可在实施时调整），输入为**已通过人工复审的初稿样本**，输出多轮修改样本。正式接入 `tu synth sft` 和配比归 T057。
- 一条样本的结构为 `system → user（写文章）→ assistant（初稿）→ user（修改要求）→ assistant（修改稿）`。训练配置是 `mask_prompt: true`，**loss 只计最后一段 assistant**，所以初稿只是上下文，不会重复训练。
- 历史中的初稿要按运行时的样子呈现：`to_openai_messages` 回填的是**交付文本**，有引用时末尾会追加 `DISCLAIMER`，也可能追加 “相关条款（系统补充）”。初稿在历史中的形式要与 `process_turn` 的产出一致，以免训练和推理的分布不同。
- `meta.type=article`，`kind` 用 `revise_<类型>` 区分。`meta` 记录 `parent`（初稿样本标识，供 T057 把初稿和修改稿划到同一侧）、修改类型、逐篇计划、clause_ids 和 tokens。

## 2. 修改类型（首批）

| 类型 | 用户问法示例 | 修改稿要求 | 自动校验 |
|---|---|---|---|
| `plainer` 更通俗 | “语言再通俗一些”“写得更口语化点” | 篇数、案情事实、责任主体和引用不变，只改叙述和分析的措辞 | 引用 ID 集合与初稿相同；每篇 `###` 主体相同；每篇文本与初稿不完全一样；在 T052 的 `_validate` 下通过 |
| `swap_subject` 换违法主体 | “换一个违法主体”“把单位换成医院” | 只在条款主体范围内更换主体类型、人物和情节；条款要求固定主体时（例如义务落在经营者），改为换行业或手段 | 引用 ID 不变；每篇 `###` 主体与初稿不同；在 T052 的 `_validate` 下通过 |

T053 只做以上两类。“只改其中一篇（`single`）”“改篇数”“换主题”留给后续数据迭代。

## 3. 训练窗口策略（已定：方案 A，三道关卡硬锁 ≤2048）

实测新 KB `kb-20261119-045641` 全部 26 对责任关系（单对引文最长 200 tok，中位数 147 tok），1 篇修改约 900–1,500 tok，2 篇修改约 1,600–1,840 tok，3 篇修改约 2,150–2,300 tok（超 2048）。

- **入口预筛**：只接收 1 篇或 2 篇初稿（3 篇初稿记 `unsupported_article_count` 跳过），且初稿自身编码 ≤1,050 token（超限记 `draft_too_long` 跳过）。
- **提示词控篇幅**：延续 T052 篇幅上限（案例 ≤150 字、分析 ≤80 字、普法提示 ≤80 字），要求篇幅与初稿相当、不大幅扩写。
- **终稿硬校验**：用训练同款 Qwen tokenizer 对整段 5 条 `messages` 精确计数，只要 `> 2048` 一律记 `too_long` 丢弃。

## 4. 实施步骤

1. **初稿来源（做法 A）。** 只用人工复审保留的初稿，**禁止直接读取各批 `samples.jsonl`**（T057 前置条件 4）。先在新 KB `kb-20261119-045641` 上补生成一小批 1–2 篇初稿（6–8 个请求），挑出 3–4 条经用户确认；复用 T052 的保留候选 2、3 时先按新 KB 将多款第 1 款标记规范化为显式 `第1款`（正文与条文原文不动）。
2. **生成。** 外部模型输入初稿全文、修改类型、新 KB 素材原文（同 T052，`input_source="kb_clause"`），输出修改稿。用户修改问句从多样化模板池中抽取，避免重复单一问句模板（T052 §8.4 第 4 条）。
3. **校验。** 复用 T052 的 `_validate`（结构、依据/责任归属、原文），再按 §2 的类型逐项检查。对多轮样本的**每一轮 `user` 消息分别执行** v1 评测问句去重（避免两轮拼接稀释 Jaccard 漏检），并用训练 tokenizer 做整段 ≤2048 长度检查。丢弃原因记录到请求和篇序。
4. **单元测试**（`tests/unit/test_synth_articles.py`）：`plainer` 与 `swap_subject` 正例；历史轮 `DISCLAIMER`/关联补全回填；旧初稿标记规范化；反例覆盖 3 篇初稿、初稿超长、整段超长、引用被改动、通俗化未改文本、通俗化改了主体、换主体未换主体、截断、单轮问句与 v1 重合、`parent` 元数据追溯。（“通俗化时事实/法律含义被悄悄改变”属语义判断，由第 6 步人工复审把关。）
5. **小批试生成。** 基于 5–6 条确认初稿跑 10–12 个请求，均匀覆盖 `plainer` 和 `swap_subject`、1 篇和 2 篇。产物放在 `artifacts/synth/articles/<run>/`，含全文、计数、丢弃原因、长度分布和复现命令。
6. **人工复审。** 逐条对照初稿和修改稿：通俗化是否改变了案情事实或法律含义，换主体后构成要件和责任主体是否仍然成立，普法提示是否仍然写给职工（FR-029）。人工结论与自动检查结果分开记录。
7. **学习文档。** 在 `docs/learning/04-training-data.md` 中新增 **[L4.5.2] 多轮修改样本与 `mask_prompt`**：为什么初稿只做上下文、窗口怎样分配、`parent` 为什么要和初稿划到同一侧。

## 5. 验收

- `uv run pytest tests/unit/test_synth_articles.py`、全量 `uv run pytest`、`uv run ruff check src tests` 全部通过。
- 小批产物中，每种类型至少有一条人工复审保留的样本，整段 ≤2048 token，`parent` 能追溯到已保留的初稿。
- 统计请求数、保留数、各丢弃原因的计数和 token 分布。
- 独立复审通过并经你确认后，再勾选 T053 并提交。

## 6. 决策结论（已确认）

1. **修改类型范围**：只做 `plainer` + `swap_subject`，不做 `single`。
2. **窗口策略**：方案 A（1–2 篇初稿、完整修改稿、三道关卡硬锁 ≤2048）。
3. **T078 时机**：标为 `[Post-POC / 正式阶段]` 移出 POC，不动 KB 与旧数据以保 v1 / SC-016 基线；T057/T074 登记已知缺陷，演示脚本避开该文件款号。
4. **初稿池做法**：做法 A（先补 3–4 条新 KB 1–2 篇初稿并经用户确认，加规范化后的 T052 旧候选 2、3，凑齐 5–6 条初稿跑 T053 试生成）。

---

## 7. 实施与试生成记录（2026-11-19）

### 7.1 代码与文档变更
- `src/tu_assistant/synth/articles.py`：新增 `generate_revisions`、`normalize_draft_markers`、`draft_id`、`_history_assistant_text`（与 `orchestrator.process_turn` 一致，回填关联补全与 `DISCLAIMER`）、`_eval_overlap_any_turn`（逐轮 + 整段评测问句去重）、`_validate_revision`（复用 `_validate`，按 `plainer`/`swap_subject` 校验文本变化、逐项 `###` 主体及 `swap_subject` 正文旧主体残留 `actor_residual`）及三道 ≤2048 窗口关卡。试生成复审后在 `REVISION_TYPE_RULES["swap_subject"]` 补充两条提示词约束（不得脱离原条款法定主体范围、普法提示保持面向普通职工），版本更新至 `t053-v1.1`。
- `scripts/sample_article_revisions.py`：小批试生成脚本，记录原始回复、统计、丢弃原因、token 分布与清单。
- `scripts/curate_t053_candidates.py`：可复现的筛选、校订与全量复验脚本，从原始 `samples.jsonl` 与 T052 `candidates.jsonl` 生成并校验两份 `candidates.jsonl`。
- `tests/unit/test_synth_articles.py`：补齐 T053 全部正反例与 `REVISION_USER_PROMPTS` 无 v1 重合断言。
- `docs/learning/04-training-data.md`：新增 `[L4.5.2] 多轮修改样本与 mask_prompt`。
- `docs/handoffs/T057-article-dataset-handoff.md`：登记 T053 复审带入的 5 项前置核对。
- `specs/001-legal-clause-assistant/tasks.md`：将 T078 标记为 `[Post-POC / 正式阶段]`。

### 7.2 做法 A 第 1 步 · 新 KB 初稿池
- 复现命令：`uv run --env-file .env python scripts/sample_articles.py --kb artifacts/kb/kb-20261119-045641.sqlite --requests 8 --modes 1 2 --out artifacts/synth/articles/t053-new-drafts`
- 自动校验：保留 **8/8**（`dropped=0`，token 725–960）。
- 人工复审与校订（见 `artifacts/synth/articles/t053-new-drafts/review.md`，由 `scripts/curate_t053_candidates.py` 可复现生成）：保留 **5 条**（Req 1、2、5、6、8；微调：Req 1“某人力资源服务公司”、Req 5 问句与标题“被降薪停工”、Req 8 第 1 篇标题“酒店恐担责”），退回 **3 条**（Req 3、7 主体误套政府/村居委会条款；Req 4 将车间主任当成高管）。
- 合并规范化带 `第1款` 的 T052 保留候选 2、3 后，形成 **7 条确认初稿池**：`artifacts/synth/articles/t053-new-drafts/candidates.jsonl`（token **723–960**，均 ≤1,050，全部通过新 KB `_validate`）。

### 7.3 做法 A 第 2 步 · T053 修改试生成
- 复现命令：`uv run --env-file .env python scripts/sample_article_revisions.py --kb artifacts/kb/kb-20261119-045641.sqlite --drafts artifacts/synth/articles/t053-new-drafts/candidates.jsonl --out artifacts/synth/articles/t053-revisions-trial`
- 筛选校订命令：`uv run python scripts/curate_t053_candidates.py`
- 自动校验（`revision_prompt_version=t053-v1.0`）：**14/14 保留**（`plainer` 7/7、`swap_subject` 7/7，`dropped=0`，`reasons={}`）；原始试生成整段 5 条 `messages` 长度 **min 1,317 / median 1,626.5 / max 1,804**（全部 ≤2048）。
- 人工复审与第三方复审校订（2026-11-19 用户确认，与自动校验分开记录，见 `artifacts/synth/articles/t053-revisions-trial/review.md`）：
  - **保留 12/14**（`plainer` 7/7、`swap_subject` 5/7，已写入 `artifacts/synth/articles/t053-revisions-trial/candidates.jsonl`，校订后 token **1,314–1,804**（单篇 1,314–1,592，两篇 1,646–1,804），`parent` 全部追溯至 `t053-new-drafts/candidates.jsonl`）：
    - 第三方复审数据校订：Req 4 改为“以工资收入为主要生活来源的专职教师”（对齐《工会法》第 3 条第 1 款法定要件）；Req 9、Req 10 与初稿 req5 同步将标题/问句“被降薪辞退”改为“被降薪停工”。
  - **退回 2/14**：Req 6（`swap_subject` 换主体为“某建筑劳务公司”，略偏离第 40 条第 4 款“人力资源服务机构”委托主体）、Req 14（`swap_subject` 第 2 篇普法提示写成了面向“旅馆经营者”而非面向职工，偏离 FR-029）。

### 7.4 测试与静态检查
- `uv run pytest tests/unit/test_synth_articles.py`：34 passed
- `uv run pytest`：193 passed, 6 xfailed
- `uv run ruff check src tests scripts/sample_article_revisions.py scripts/curate_t053_candidates.py`：All checks passed

---

## 8. 独立复审闭环记录（2026-11-19）

按 `.agents/skills/task-review-loop/SKILL.md` 执行独立只读复审并吸纳第三方模型复审意见：

- **Round 1（内部只读复审 · 需修改）**：提出 1 项阻断项（`_validate_revision` 对单篇双行为 `swap_subject` 仅换 1 个主体漏检）与 3 项非阻断建议（`normalize_draft_markers` 按 `cit.span` 切片、入口脏初稿预检、单测补强）→ 全部修复并补单测。
- **Round 2（内部只读复审 · 通过）**：原审核员核对全部 4 处修复、测试与 12 条样本，剩余阻断项 = 0。
- **第三方外部模型复审与落地（选 B）**：
  1. 数据校订：修复 Req 4“课时费”→“以工资收入为主要生活来源的专职教师”，同步修复初稿 `req5` 与修改稿 Req 9/10“被降薪辞退”→“被降薪停工”，并新增可复现整理脚本 `scripts/curate_t053_candidates.py`；
  2. 代码加固：在 `_validate_revision` 的 `swap_subject` 分支新增正文旧主体残留检查 `actor_residual`（对 `len(d) >= 3 or d.endswith("某")` 的初稿主体禁止残留于修改稿该篇正文），并补反例单测；
  3. 文档对齐：更正 `docs/learning/04-training-data.md` `[L4.5.2]` 实测 token 区间为 `1,314–1,804`，并将剩余 5 项前置核对登记至 `docs/handoffs/T057-article-dataset-handoff.md`；
  4. **Round 3（内部只读复审 · 通过，剩余阻断项：0）**：原审核员核对 `actor_residual` 校验、反例单测、`scripts/curate_t053_candidates.py`、两份磁盘 `candidates.jsonl`（7/7 + 12/12 PASS，token 723–960 / 1,314–1,804）、测试（34 / 193 passed + 6 xfailed）与三份文档全部一致，无新回归。

**当前状态**：已完成并经用户确认，勾选 `tasks.md` 中的 T053 并提交推送。
