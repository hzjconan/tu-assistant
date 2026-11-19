# T052 执行单评审意见

**评审对象**　[T052-article-synthesis-handoff.md](T052-article-synthesis-handoff.md)（未修改原文件）

**评审时仓库状态**　HEAD `ffe78be`，KB `kb-20261113-093057`（24 个文件），外部合成模型 `deepseek-chat`（`configs/synth.yaml`），训练基座 `Qwen2.5-7B-Instruct-4bit` / 调试用 `Qwen2.5-1.5B-Instruct-4bit`，`max_seq_length: 2048`（`configs/train/*.yaml`）。

**结论**　方向合理，但需要先解决第 1、2 节两项阻断问题，并对第 3、6 节的取舍作出决定，再进入实施。第 8 节给出建议的实施步骤，供实施方修订原执行单时参考。

---

## 1. 阻断：样本长度与训练窗口

### 1.1 两层长度限制

| 层 | 计数口径 | 约束 |
|---|---|---|
| 生成侧 | DeepSeek 的输出 token | 调用参数 `max_tokens`（现有生成器为 2500～3000）及 deepseek-chat 自身输出上限（以 DeepSeek 当前文档为准，本次未核实） |
| 训练侧 | **Qwen tokenizer + chat template** 计数 | `max_seq_length: 2048`，超出部分在训练时截断 |

训练侧必须用被训练模型（Qwen）的 tokenizer 计数，不能用 DeepSeek 返回的 usage。E001 实测现有数据集最长样本为 2,015 token，同样按 Qwen 口径计数。

### 1.2 实测数据（评审时用 Qwen2.5-7B tokenizer 测得）

| 项目 | 结果 |
|---|---|
| 12 对已确认 `liability_for` 关系，每对"依据标记+原文 + 责任标记+原文"合计 | 最少 92 / 中位 130 / 最多 181 token |
| 现行 system prompt（`build_system_prompt()`） | 135 token |
| 普通中文叙述 | 约 1.9 字/token |

据此估算单篇文章（单违法行为）：案例约 300 字、以案说法分析约 250 字、普法提示约 200 字、标题与段落标记若干，再加约 130 token 的引用块，合计约 **500～600 token**。含两项违法行为的篇章再加约 250～300 token。

> 更正：上一轮口头评审估计"每篇 600～900 token"，偏高。实测后结论不变，但边界更清楚。

| 请求 | 估算总长（含 system、user、模板开销） | 判断 |
|---|---|---|
| 1 篇 | 约 700～900 | 安全 |
| 2 篇 | 约 1,200～1,500 | 安全 |
| 3 篇（默认） | 约 1,700～2,100 | **贴近或超过 2048**，含多违法篇时大概率超出 |
| 10 篇 | 约 5,500～6,500 | 远超，必然截断 |

截断发生在助手消息尾部，丢掉的正好是后几篇和结束位置。模型学不到"写满 N 篇后停止"，篇数控制会被教坏。

### 1.3 原执行单的缺口

- 第 3.1 步要求覆盖 1～10 篇并"全部篇章放在同一条助手消息中"，未考虑训练窗口。
- 第 5 步称"10 篇上限可由第 4 步覆盖"，但第 4 步使用固定响应客户端，只能验证解析与检查逻辑，不能证明 DeepSeek 能一次产出 10 篇，也不能证明样本可训练。

### 1.4 需要实施方（或用户）选定的方案

| 方案 | 做法 | 代价 |
|---|---|---|
| A（建议） | 训练样本只覆盖 1～3 篇，并在合成提示中给每篇设长度预算（如案例 ≤250 字、分析 ≤200 字、提示 ≤150 字）；4～10 篇的大篇数请求留给运行时分批生成（归 T056） | T056 需实现分批；模型没见过 >3 篇的整段输出 |
| B | 为文章样本提高 `max_seq_length`（如 4096 或 8192） | 显存与训练时长上升，需在 M1 Pro 32GB 上实测（7B 已需 `--grad-checkpoint`），影响 T075 时间预算 |
| C | 重复出现的引用标记不带原文（citation-format §1 允许），压缩长度 | 只能省下少量 token，不能单独解决 10 篇问题 |

无论选哪种，都应在保留样本前**按 Qwen tokenizer + chat template 实测 token 数**，超过训练窗口的丢弃并记 `too_long`。

---

## 2. 阻断：样本类别字段应为 `meta.type`

原执行单第 1 步写 `meta.kind=article`（照 `contracts/datasets.md`）。实际流水线都按 `meta.type` 判断类别：

| 用途 | 位置 |
|---|---|
| train 侧过采样系数 | `src/tu_assistant/train/dataset.py:161` |
| manifest 原始与有效计数 | `dataset.py:316-318` |
| 是否要求带引用 | `src/tu_assistant/cli.py:475` |
| 文档注释中的类别列表（含 `article`） | `dataset.py:6` |

现有生成器的写法都是 `{"type": "<类别>", "kind": "<子类>", "doc_id": ..., "clause_ids": [...]}`。

**要求**：写 `meta.type="article"`；`kind` 记子类（如 `n1`、`n3_default`、`multi_violation`）；带上 `doc_id`（`balance_by_doc` 使用）。建议另记一条：`contracts/datasets.md` 与代码的 `type/kind` 用法不一致，留待用户决定是否改合同文档，本任务不改。

---

## 3. 需决定：素材池规模与评测覆盖

实测 KB 中已确认关系：

| relation_type | 数量 | 涉及文件 |
|---|---|---|
| `liability_for` | 12 对（from 12 条、to 12 条，各不重复） | 6 个 |
| `references` | 23 条 | — |

v1 文章评测题 10 道，gold 条款与这 12 对 `liability_for` 关系的**交集为 0**（如 article-001 拖欠工资所涉条款均不在已确认关系中）。

影响：

1. 不会污染评测集。但这批样本能教的主要是文章格式和行为，不会让模型更熟悉评测题涉及的条款。T075 复评时文章类指标的提升只能来自格式迁移，执行单应写明这一预期。
2. 12 对素材要同时支撑"同题多篇有实质差异"和"同场景两项违法"，多样性很紧。多违法组合还要求两对关系能在同一场景成立，可选组合更少。

需决定：先从 `artifacts/kb/kb-20261113-093057-relations_pending.jsonl` 再人工确认一批 `liability_for` 关系、扩充素材，还是接受 12 对、先做小批验证。扩充时要排除 v1 gold 条款，或明确接受条款层面的重叠。确认关系属于需用户审阅的事项，实施方不应自行把 pending 改为 confirmed。

---

## 4. 建议：引用原文的强制范围

citation-format §1 允许省略原文（校验层自动补入，`citation/verify.py:170-172`），并要求"再次提到须重复完整标记，可不带原文"。原执行单第 3.3 步要求"只写出处、漏了引文即丢弃"，方向正确（训练样本应示范完整原文，与知识样本一致），但范围需写清：

- **必须带原文**：每篇、每项违法行为下 `**法律依据**`、`**法律责任**` 段内首次出现的引用块；
- **可不带原文**：同篇中重复出现的标记（如普法提示里复述）；
- 检测方法：用 `citation/parse.parse_citations` 读取**原稿**的 `quoted_text`，为 `None` 即缺原文。不能只看 `check_sample` 或 `verify_output` 的 `ok`，因为自动补入原文的引用也判为 `ok`。

---

## 5. 建议：依据与责任对调需按段落归属检查

`synth/check.check_sample` 只检查"期望 ID ⊆ 已引用 ID"，看不出引用放在哪个位置，依据与责任对调或放错行为都能通过。需要新写一层结构检查：

1. 用 `eval/metrics.extract_articles` 拆篇（与 T058 评测口径一致），篇数不等于请求篇数则记 `article_count_mismatch`；
2. 每篇检查 `## 案例`、`## 以案说法`、`## 普法提示` 三段齐全，缺段记 `article_section_missing`（同时记篇序号）；
3. `## 以案说法` 下按 `### <主体>：<行为>` 切成违法行为项，每项内再按 `**法律依据**`、`**法律责任**` 切段；
4. 每项的法律依据段解析出的 clause_id 应为该项素材的 `from_clause_id`，法律责任段应为 `to_clause_id`；对调记 `liability_basis_swapped`，缺段记 `liability_missing`；
5. 再调用现有 `check_sample`（`require_citation=True`、`expected_clause_ids=`全部预期 ID），复用 `citation_not_found`、`citation_text_wrong` 等原因。

生成侧需要把"第 k 篇第 j 项 → (from, to)"的计划随样本记录在 `meta` 中（如 `meta.plan`），供上述检查和人工复审使用。`meta` 不进训练 JSONL（datasets.md），不影响训练。

---

## 6. 需决定：默认篇数是否可配置

`chat/prompts.build_system_prompt` 接受 `default_article_count` 参数，但模板里没有使用（`prompts.py:27-34`）。运行时 orchestrator 把配置值传进去也不起作用（`chat/orchestrator.py:56`）。

- 若"默认 3 篇"固定不变：T052 样本全部按 3 篇默认，执行单写明 `app.yaml` 的 `session.default_article_count` 对模型无效。
- 若需要可配置：参照 `max_questions` 的做法（research R6），T052 生成时随机取默认篇数并写入 system prompt。这需要修改共享模板，会影响 `PROMPT_VERSION`、训练与运行时一致性，以及已有数据集的复用，应先征得用户同意。T056 只能在运行时传值，不能替代训练数据。

建议 POC 先选前者，在执行单中写明。

---

## 7. 其他小问题

- 原执行单写了"v1 题不进合成提示"。单跑时仍建议对产出调用 `train/dataset.dedup_against_eval`（对照 `eval/cases/v1/` 的问句）并记录剔除数，与 T057 口径一致。
- 学习文档 `docs/learning/04-training-data.md` 的 L4.8 是"可以继续问的问题"，L4.9 接在其后阅读顺序别扭。建议放在 L4.5 质量关卡附近（如 L4.5.1），或把 L4.8 顺延，由用户定。
- 第 5 步依赖外部 API Key 与服务条款确认（tasks.md:275）。原执行单已写降级方案（无凭据时交本地验证、真实产出标"待验"），保留即可。
- 单次请求 3 篇时，DeepSeek 输出可能被 `max_tokens` 截断。应把 `max_tokens` 设在约 4,000 以上，并检测 `finish_reason == "length"`，截断的直接丢弃（记 `llm_truncated`）。现有 `ExternalLLM.chat` 不返回 `finish_reason`，可退而依赖拆篇和结构检查兜底，或小幅扩展客户端。扩展时需保持 `usage` 记账与 `input_source` 断言不变。

---

## 8. 建议的实施步骤

以下为对原执行单第 1～6 步的修订建议。实施仍需用户审阅同意后进行。

### 第 0 步　先确定取舍（需用户确认）

1. 长度方案：A / B / C（第 1.4 节），建议 A；
2. 素材：12 对先行，或先扩充已确认关系（第 3 节）；
3. 默认篇数：固定 3 篇，或可配置（第 6 节），建议固定。

以下步骤按"方案 A + 12 对先行 + 固定默认 3 篇"编写。若选其他方案，相应调整第 2、3 步的篇数范围和 system prompt 部分。

### 第 1 步　接口与样本形态

- `src/tu_assistant/synth/articles.py` 提供 `generate(kb_conn, llm, cfg, *, n_requests=...) -> list[dict]`，签名风格与 `dialogs.generate`、`consult.generate` 一致；同时返回或暴露 `CheckStats`，便于单跑时查看丢弃原因。
- 样本 `messages = [system, user, assistant]`：
  - system 用 `build_system_prompt(max_questions=rng.randint(2, 6))`，与现有行为样本一致；
  - user 只给口语化主题和可选篇数，不出现法规名称或条款编号；
  - assistant 为全部篇章，篇间用独立一行 `---`。
- `meta = {"type": "article", "kind": <子类>, "doc_id": <主素材文件>, "clause_ids": [...], "n_requested": N, "plan": [...], "max_questions": q}`。

### 第 2 步　素材与场景计划（确定性部分，不调用外部模型）

1. 从 KB 读取 `relation_type='liability_for' AND confirmed=1` 的关系，取出依据、责任两条条款的 ID、文件名、版本和**完整原文**（用 `synth/knowledge._canonical_text` 的口径，含项）。缺任一条款则跳过并记 `material_unresolved`。
2. 请求篇数分布：未指定（默认 3）、指定 1、指定 2、指定 3，各占一定比例，比例写入 `configs/synth.yaml` 的新段（如 `behavior.article_*`）。T052 单跑时可以在入口参数中给出，避免改动 T057 范围内的配置读取逻辑。
3. 每个请求生成"篇计划"：每篇指定违法主体类型（用人单位、个人、工会工作人员等，按条款适用范围）、当事人身份、手段、情节轻重，同一请求内各篇至少有一个维度不同。
4. 多违法篇：从同一文件内（或已人工认定可共场景）的两对关系中组合，计划中写明每项的主体、行为和 (from, to)。找不到可共场景组合时如实记录，不硬凑。
5. `user` 主题由模板生成或由 DeepSeek 根据条款改写为口语。调用 DeepSeek 时 `input_source="kb_clause"`，提示中只含 KB 条款与合成指令，不含 v1 题目与 `inputs/` 内容。

### 第 3 步　生成与逐条检查

1. 一个请求调用一次 DeepSeek，提示包含：篇计划、每篇结构模板（citation-format §4）、每段字数预算、必须在每项下逐字给出的"标记 + 原文"、人物与单位须虚构的要求、面向职工和公众的语言要求。`max_tokens` 约 4,000。
2. 解析返回内容，依次执行检查，任一失败即丢弃整条并记原因：
   - `article_count_mismatch`：拆篇数 ≠ 请求篇数；
   - `article_section_missing`：某篇缺 案例/以案说法/普法提示；
   - `liability_missing` / `liability_basis_swapped`：按第 5 节的段落归属检查；
   - `quote_missing`：首次出现的依据或责任引用在原稿中无原文（第 4 节）；
   - `citation_not_found` / `citation_text_wrong` / `citation_mismatch`：复用 `check_sample`；
   - `too_long`：Qwen tokenizer + chat template 计数 > `max_seq_length`（从训练配置读取，默认 2048）。
3. `meta.clause_ids` 取原稿实际解析出的 clause_id，并校验其包含计划中的全部 ID。
4. 产出后调用 `dedup_against_eval` 对照 v1 问句，记录剔除数。

### 第 4 步　单元测试 `tests/unit/test_synth_articles.py`

使用内存 SQLite 小型 KB（含 2～3 对 `liability_for`）和返回固定文本的假客户端，从 `generate` 入口验证：

| 输入或变体 | 验收结果 |
|---|---|
| 未指定篇数 / 指定 1 篇 / 指定 3 篇 | 分别交付 3 / 1 / 3 篇，各形成一条样本；`meta.type == "article"`；`clause_ids` 与原稿一致 |
| 一篇含两项违法行为 | 两项各自的依据、责任 ID 与计划一致，引用位于对应 `###` 项下 |
| 请求 3 篇只返回 2 篇 | 丢弃，原因 `article_count_mismatch` |
| 第二篇缺 `## 普法提示` 或缺 `**法律责任**` | 丢弃，原因分别为 `article_section_missing`、`liability_missing`，与篇数问题可区分 |
| 依据与责任对调 | 丢弃，`liability_basis_swapped`；即使 `check_sample` 单独能通过 |
| 首次引用缺原文 | 丢弃，`quote_missing`；`verify_output` 自动补入不掩盖缺失 |
| 重复标记不带原文 | **保留** |
| 原文有误 | 丢弃，`citation_text_wrong` |
| 超出训练窗口（构造超长响应，或把窗口参数调小） | 丢弃，`too_long` |
| 素材缺责任条款 | 不产出，记录 `material_unresolved` |

token 计数应可注入（测试中用简单计数函数代替 Qwen tokenizer），单元测试不依赖网络下载。

执行并记录：`uv run pytest tests/unit/test_synth_articles.py`、`uv run pytest`、`uv run ruff check src tests`。

### 第 5 步　小批真实生成（需 DeepSeek 凭据）

- 规模建议 10～20 个请求，至少包含：1 条默认 3 篇、1 条指定 1 篇、1 条指定 2 篇、1 条含多违法篇。
- 产物写到 `artifacts/` 下独立目录（不进 git），记录：生成入口与参数、`llm.meta()`（模型、提示版本、seed、usage）、KB 版本、请求数、保留数、按原因的丢弃统计，以及保留样本的 Qwen token 数分布（最小、中位、最大）。
- 抽查记录中法规原文截断到 15 字以内（沿用 E002/E003 惯例）。
- 无凭据时只交第 4 步结果，真实产出标为"待验"。

### 第 6 步　人工复审与交付

- 复审人逐篇记录：同题各篇在哪些维度上有差异；多违法场景中每项的事实、主体与责任条款是否对应；语言是否通俗；人物与单位是否虚构；FR-027 场景事实是否满足条款构成要件；每条给出"保留或退回"及理由。
- 学习文档新增一节（编号由用户定，见第 7 节），用本次样例说明：引用都能查到，不代表责任归属正确；以及为什么训练样本要受训练窗口约束。
- 在原执行单末尾追加：实际改动、测试结果、样本位置、token 分布、抽查结论、待核验事项。T052 保持待复审，由用户决定勾选与提交。

---

## 9. 原执行单中可保留的部分

- T052（初稿）/ T053（修改）/ T054～T056（运行时身份与篇数）/ T057（并入数据集）的分工；
- 先确定法律依据、再设计场景，找不到依据就跳过并记录原因；
- 整条丢弃而非局部修补，丢弃原因可区分；
- 先小批人工审阅，再占用训练机器。
