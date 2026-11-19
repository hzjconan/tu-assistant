# T057 执行单 · 普法文章与新版条款关系合入数据集

**状态**　实施中（2026-11-19 用户确认按 7 项推荐选项开工；起点 commit `897413e`）。

---

## 0. 为什么下一个做 T057

1. **位于 POC 剩余关键路径的最前端。**
   当前剩余主链路为：`T057（合入数据集）→ T075（从 exp-20261116-resume500 续训 7B，14–15 h，外加 A/B 冒烟与 v1 SC-016 回归复评）→ Phase 5（T061–T065 评测对比与重复评测）→ Phase 7（T069–T074 演示与收尾）`。
   T052（初稿合成）与 T053（修改请求合成）均已通过复审收口，唯一卡住 T075 启动的就是 T057。T075 是后续最耗时且独占 32GB 统一内存的环节，越早交付 T057 就能越早开训。
2. **前置依赖全部就绪。**
   - 新 KB `kb-20261119-045641.sqlite` 已完成派生与 T019 两批人工确认，共 **67 条**已确认关联（**26 对 `liability_for` + 41 条 `references`**，撤销旧错边 10 条、`paragraph_mismatch=0`），`relation_samples` 67/67 校验通过。
   - 已有 **20 条**经人工复审的文章存量（去重后 8 条初稿 + 12 条修改稿），以及 `t053-v1.1` 修改提示词与 `normalize_draft_markers`、`draft_id` 等工具函数。
   - T078 已于 2026-11-19 经用户确认标为 `[Post-POC / 正式阶段]` 移出 POC，不阻塞 T057，仅需在数据集 manifest 中登记已知缺陷。
3. **与其他未完成任务对比：**

| 候选任务 | 为什么不先做 |
|---|---|
| **T054–T056**（`anonymize.py` 身份信息检查、单测、编排层接入篇数与匿名化） | 纯运行时逻辑，**不进入训练数据**，不在 T075 前置链路上。可留到 T075 挂机训练的 14–15 h 期间并行编码和跑单元测试（纯 CPU 轻量任务，训练期间不起本地 7B 推理服务即可）。 |
| **T049**（多违法行为与意图确认评测用例约 20 题） | 需用户逐题审阅，不在训练链路上，可与 T075 并行或在复评前补齐。 |
| **T059**（7B 演示模型首训与再训） | 首训与 SC-016 判定已完成，文章合入后的再训明确拆分至 T075，需待 T075 完成后收口。 |
| **Phase 5（T061–T065）** 评测报告、对比与 SC-015 重复评测 | T064 重复评测与最终对比报告依赖 T075 产出的最终演示 adapter。 |
| **Phase 6（T066–T068）** 知识库 diff 与版本配置 | 与训练链路独立，可穿插于 T075 训练期间或之后完成。 |
| **Phase 7（T069–T074）** Gradio 界面、演示脚本与收尾 | 依赖 T075 最终模型与 T054–T056 运行时能力。 |

---

## 1. 原有 5 条前置核对清单（完整保留与落点映射）

本执行单完整继承并落实此前在 T052、T053 复审中登记的 5 条前置核对：

| 原清单条目 | 核对要点 | 本文落点 |
|---|---|---|
| **1. 核对素材及责任关系** | 对照 T077 修正结果，列出 KB 版本、确认过的依据/责任 ID 和可合写纠纷；每种组合用小样核对行为主体、适用条件与救济，记录实际使用组合与频次 | §2.2、§3.1、§5 步骤 1 |
| **2. 按案例做跨请求去重** | 划分前汇总初稿与修改稿，仅比对 `## 案例` 段（忽略公共引文），以 T052 住宿默认三篇与显式两篇为已知近重复对照，确认换标题/换姓名后仍可检出；记录筛除数与人工复核结果；初稿与修改稿同侧划分；可换主体条款验主体差异、固定主体条款验手段/情节差异 | §3.4、§4.2、§5 步骤 4、§6 |
| **3. 覆盖自然问法** | 覆盖显式篇数（1/2/3/4 篇）、未指定篇数（默认 3 篇）、模糊“几篇”及“用户自带案情”表达；独立问句确认对应成稿并记录各类数量；`eval/cases/v1` 只用于去重与评测 | §3.3、§5 步骤 2、§6 |
| **4. 交付前留证 & 禁读未审原批** | 提交素材覆盖、去重前后分布、问法覆盖、样本位置并标明经人工复核样本；**禁止直接整批并入各批原始 `samples.jsonl`** | §3.1、§4.5、§5 步骤 4–7 |
| **5.1 `t053-v1.1` 首批抽查** | 新增两条 `swap_subject` 约束（不脱离法定主体范围、普法提示保持面向职工）须在扩量第一小批先抽查验证 | §3.3、§5 步骤 3 |
| **5.2 `parent` 统一对齐与同侧划分** | 对全部初稿统一调用 `articles.draft_id()` 计算键，确保初稿与其全部修改稿划在同一侧（同 `train` 或同 `valid`），且复用旧库样本保持原 `train`/`valid` 归属 | §4.2、§5 步骤 2B/6、§6 |
| **5.3 修复 `_infer_meta` 多轮文章判型** | 修复 `len(messages) > 3` 先判 `intent` 导致 5 消息 T053 样本被误判的问题（同时不误伤 104 条“中途变卦写文章”的 `intent` 样本，并还原 `relation_*` 标记） | §4.1、§5 步骤 2B、§6 |
| **5.4 按文件均衡覆盖** | 避免文章过度集中于 `a98741e9ca9f6fa1`（T053 试批占 5/12=42%），均衡覆盖全部 6 部法规、不触发 `balance_by_doc` 20% 截断；注意《工会法》等法定主体要件贴合度 | §3.2–3.3、§4.4、§5 步骤 3 |
| **5.5 已知限制留痕** | 在新数据集 `manifest.json` 登记 T078 已知缺陷、当前 26 对 `liability_for` 无未引用出边（历史轮系统补充由单测覆盖）及《劳动法》《劳动合同法》缺 `liability_for` 的文章素材范围限制 | §2.2、§4.4、§5 步骤 2B/6 |

---

## 2. 仓库现状摸底与数据基底设计

### 2.1 复用旧数据集、基线无污染核实与刷新 67 条新 KB 关系样本

- **复用起点**：`artifacts/datasets/ds-kb-20261113-093057-8410`，去重基础样本共 **8,410** 条（原 `train.jsonl` 去重 **7,569** 条、`valid.jsonl` **841** 条，`train ∩ valid = 0`）：
  - 原 `train`（7,569）：`knowledge` 5,402、`consult` 878、`general` 815、`intent` 378、`refusal` 96；
  - 原 `valid`（841）：`knowledge` 598、`consult` 102、`general` 99、`intent` 29、`refusal` 13。
- **历史基线去重核实（SC-016 基线有效性确认）**：
  - 实测发现 `cli.py:synth_sft` 默认 `--eval-cases eval/cases` 因 `load_cases()` 非递归只加载了 **0 题**（`ds-8410/manifest.json` 的 `dedup_against: "v1"` 属硬编码标记，并未真正载入 v1 问句）。
  - 但对 `ds-8410` 全部 **8,410** 条样本重新对照 `eval/cases/v1`（60 题 `reviewed.jsonl` + 10 题 `articles.jsonl` = **70 题 / 74 条用户问句**）执行整段与逐轮（`_eval_overlap_any_turn`）去重，实测重合数均为 **0**。结论：**`exp-20261116-resume500` 的 SC-016 基线（条级 17/60、款级 9/60、文件 21/30）未被评测题污染，基线完全有效**；T057 修复默认路径并在 manifest 中如实记录实际加载的评测问句数。
- **目标 KB**：`artifacts/kb/kb-20261119-045641.sqlite`（较旧库 `kb-20261113-093057` 补齐 787 条多款条文首款 `第1款` 标记；已确认关联从 35 条更新为 **67 条**：`liability_for` 26 + `references` 41；对比旧库保留 25、**撤销旧错边 10**、新增 42）。
- **摸底实测两项关键变化**：
  1. **旧关系样本残留（共 18 条：原 `train` 17 条、原 `valid` 1 条）**：`ds-8410` 因抽稀至 6,000，残留 18 条旧 `relation_samples`（含 **7 条已撤销错边**：5 条错款 `liability_for` + 2 条已撤销 `references`；另 1 条《妇女权益保障法》第 43 条因旧答漏子项在当前校验层被判 `citation_text_wrong`）。
     - **清理与刷新方案（确定性、零误伤）**：新增 `--refresh-relations` 流程，按 `knowledge.relation_samples` 的三条确定性问句正则精确剔除全部旧关系样本（`^违反《.+》.+要承担什么法律责任？$`、`^《.+》.+有没有例外情形？$`、`^哪些条款引用了《.+》.+？$`，实测精准命中 18/18，对 2 条问句含“要承担什么法律责任？”的 `consult` 长案情样本零误伤），再调用 `knowledge.relation_samples(conn, titles)` 注入新 KB 全部 **67 条**关系样本（实测 67/67 通过新 KB `check_sample`，`dropped=0`）。
     - **防 `thin_knowledge` 误删新关系 & 保护原 `valid`**：去 18 补 67 后，`knowledge` 为 `6,000 - 18 + 67 = 6,049 > knowledge_max(6000)`（超 49 条）。须改造 `thin_knowledge`：① 将 `meta.kind` 以 `"relation_"` 开头的样本设为**必保组（pinned）**，67/67 全部锁定保留；② 裁减超出配额的 49 条时，**仅从 `meta.split != "valid"` 的普通 `knowledge` leftover 中裁减**，既保证条款覆盖数不降，又不扰动原 `ds-8410` `valid` 留出集（原 `valid` 的 597 条普通 `knowledge` 全部保留）。
  2. **68 条历史 `consult` 样本在新校验口径下淘汰（原 `train` 63 条、原 `valid` 5 条）**：用当前 `verify_output` + `kb-20261119-045641` 对 `ds-8410` 全量执行 `check_sample`，这 68 条均因引用“单款含多项”条文时旧答漏项/加换行/改写子项触发 `citation_text_wrong`（按法规分布：《职业病防治法》21、《安全生产法》12、《保障农民工工资支付条例》11、《工会法》5、《劳动法》4、《社会保险法》4、《法律援助法》3、《劳动合同法》3、其余 5 部各 1）。保留 `consult` 仍有 **912 条**（占原 93.1%）。推荐接受自然淘汰并在 `manifest.json` 中记录淘汰样本的按法规分布（备选方案见 §8 决策 3）。

### 2.2 新 KB 26 对 `liability_for`、20 组多违法组合与 v1 素材范围说明

`kb-20261119-045641.sqlite` 经 `articles._materials` 实测共有 **26 对**可用责任关系（`paragraph_mismatch=0`），分布于 **6 部现行法规**：

| 法规（`doc_id`） | 可用 `liability_for` 对数 | 同文件多违法组合数 | 现有已审初稿数 | 现有已审修改稿数 |
|---|---:|---:|---:|---:|
| 中华人民共和国妇女权益保障法（`a98741e9ca9f6fa1`） | 6 | 9 | 4（含 T052 3 篇） | 5 |
| 上海市集体合同条例（`40124ed5e360acee`） | 5 | 7 | 1 | 2 |
| 中华人民共和国公司法（`f603773a50aeb8a5`） | 5 | 0（同指 `a186:p1`） | **0（空缺）** | **0（空缺）** |
| 中华人民共和国工会法（`4b6c1f293f717293`） | 4 | 3 | 2 | 4 |
| 女职工劳动保护特别规定（`cd730370ca29c4df`） | 4 | 0（同指 `a13:p1`） | **0（空缺）** | **0（空缺）** |
| 上海市就业促进条例（`c2699265cef115bb`） | 2 | 1 | 1 | 1 |
| **合计** | **26** | **20** | **8** | **12** |

- **20 组多违法组合说明**：《妇女权益保障法》中 `a26:p1`（住宿经营者报告义务）与 `a43:p1` / `a48:p1/p2/p3`（招聘/孕产期侵权）共 4 组较易出现硬凑场景。扩量前须按前置核对 1 导出全清单并审定“可自然共场景”白名单（见 §8 决策 4）。
- **与 `eval/cases/v1/articles.jsonl` 的素材范围差异（已知限制登记）**：实测 `kb-20261119-045641` 中，《中华人民共和国劳动法》（`3296db5b22b8ea1d`）仅有 `references: 5`、`liability_for: 0`；《中华人民共和国劳动合同法》（`be21194cc551533d`）仅有 `references: 19`、`liability_for: 0`。而 v1 的 10 道文章评测题 gold 集中在这两部法。POC 不在 T057 重开 T019 人工关联审阅，而是将“文章训练素材仅覆盖已确认 26 对 `liability_for` 的 6 部法规，不含《劳动法》《劳动合同法》”作为已知限制登记进新数据集 `manifest.json` 的 `known_issues`（由 T075 检验文章骨架与修改行为向这两部法知识的跨法规泛化能力，正式阶段补建关联后再扩充；见 §8 决策 7）。

---

## 3. 文章样本扩量、问法对齐与跨请求去重设计

### 3.1 现有已审存量盘点（禁读原始 `samples.jsonl`）

严格只使用经人工复审并固化的 `candidates.jsonl`：
- `artifacts/synth/articles/t052-implementation-review/candidates.jsonl`（3 条）：
  - **仅取第 1 行** `20261118-154620-743804:req1`（`n3_default`，1,182 tok，妇女权益保障法 `a26:p1->a81:p1`，入库前统一经 `normalize_draft_markers` 规范化；第 2、3 行已规范化并入 `t053-new-drafts/candidates.jsonl`，不重复计入；去留见 §8 决策 5）。
- `artifacts/synth/articles/t053-new-drafts/candidates.jsonl`（7 条已审初稿：`n1` 3 条、`n2` 4 条，723–960 tok）。
- `artifacts/synth/articles/t053-revisions-trial/candidates.jsonl`（12 条已审修改稿：`revise_plainer` 7 条、`revise_swap_subject` 5 条，1,314–1,804 tok，`parent` 12/12 指向 `t053-new-drafts/candidates.jsonl`）。
- **去重后存量**：**8 条初稿 + 12 条修改稿 = 20 条**（实测与 `eval/cases/v1` 70 题 74 问句零重合）。

### 3.2 扩量目标与法规均衡（推荐标准档取下限：约 48 条）

在兼顾审稿工作量、6 部法规全覆盖以及对齐 `eval/cases/v1/articles.jsonl`（含 4 篇要求 `article-004` 与用户自带案情 `article-005/006`）的前提下，推荐扩量至 **约 48 条经人工复审的文章样本**（基准规划 **24 初稿 + 24 修改稿**，需新增人审 ~35 条；轻量档见 §8 决策 1）：

| 维度 | 存量（20 条） | 本次新增目标（经人审保留） | 合库目标（~48 条） |
|---|---:|---:|---:|
| **初稿总数** | 8 | **16–18**（发 ~24–28 请求） | **24–26** |
| — 显式 1 篇（主题，含单篇多违法） | 3 | 2–3 | 5–6 |
| — **用户自带案情 1 篇（`n1_case`）** | 0 | **2–3** | **2–3** |
| — 显式 2 篇（`n2`） | 4 | 2–3 | 6–7 |
| — 显式 3 篇（`n3`） | 0 | 3 | 3 |
| — 未指定篇数默认 3 篇（`n3_default`） | 1 | 2–3 | 3–4 |
| — 模糊“几篇”默认 3 篇（`n3_vague`） | 0 | 3 | 3 |
| — **显式 4 篇（`n4`，不进修改轮）** | 0 | **2–3** | **2–3** |
| **修改稿总数（仅 1–2 篇初稿）** | 12 | **12–14**（发 ~16–20 请求） | **24–26** |
| — `revise_plainer` | 7 | 5–6 | 12–13 |
| — `revise_swap_subject` | 5 | 7–8（含首批 6–8 条抽查） | 12–13 |
| **6 部法规分布** | 缺 2 部；妇女法 9/20 (45%) | 重点补《公司法》《女职工特别规定》《集体合同》《就业促进》 | **6 部全覆盖，每部在文章子集占 10%–26%（≤30%）** |

> 注：全库分母约 8,390 条，`balance_by_doc` 20% 上限约 1,678 条/文件（当前最大文件《公司法》仅 1,212 条 = 14.4%），全库 `balance_by_doc` 不会截断任何文章样本；文章子集自身通过上述配比避免偏向单一法规。

### 3.3 对齐 v1 文章评测题的自然问法、扩展 `n4` / `n1_case` 与 `t053-v1.1` 抽查

1. **扩展 `COUNT_MODES`、`SCENARIOS` 与自然问法模板池（`src/tu_assistant/synth/articles.py`）**：
   - 将 `SCENARIOS` 由 3 条扩至 **6–8 条**（补充主体类型、行业形态、事后投诉/调解、电子证据留痕等差异维度），同时将 `COUNT_MODES` 扩展为 `(None, 1, 2, 3, 4)`——确保 `rng.sample(SCENARIOS, 4)` 合法且降低跨请求雷同；
   - **4 篇预算核实**：现有 3 篇初稿 1,167–1,366 tok，4 篇初稿约 **1,500–1,750 tok ≤ 2,048**，由 `count_tokens(messages) > max_length` 硬门兜底；且 `generate_revisions` 已限定 `len(meta_plan) in (1, 2)`，`n4` 不进入修改稿生成。
   - **分桶自然问法模板池**（全部模板经单测断言对 `eval/cases/v1` 74 问句零重合）：
     - `n1`（显式 1 篇）：“请围绕“{topic}”写1篇普法文章。” / “帮我写一篇关于“{topic}”的以案说法文章。” / “围绕“{topic}”出一篇给工友看的普法宣传稿。”
     - `n2`（显式 2 篇）：“请围绕“{topic}”写2篇普法文章。” / “围绕“{topic}”写两篇以案说法的普法文章，场景要有区分。”
     - `n3`（显式 3 篇）：“请围绕“{topic}”写3篇普法文章。” / “帮我写三篇讲“{topic}”的普法宣传文章。”
     - `n3_default`（未指定篇数，默认 3 篇）：“请围绕“{topic}”写普法文章。” / “帮我写一下关于“{topic}”的以案说法普法宣传文章。”
     - `n3_vague`（模糊篇数，默认 3 篇）：“帮我写几篇关于“{topic}”的普法宣传文章。” / “围绕“{topic}”写几篇以案说法文章，发给职工看。”（对应 `article-001`）
     - `n4`（显式 4 篇）：“给我写4篇讲“{topic}”的以案说法文章，场景要有区分度。” / “请围绕“{topic}”写四篇普法宣传文章。”（对应 `article-004`）
2. **新增“用户自带案情 → 写文章”模式（`n1_case`，对应 `article-005`/`006`）**：
   - 在 `articles.py` 中新增 `from_case` 路径（`input_source="kb_clause"`，**绝不读取 `inputs/`**）：
     - 外部 LLM 根据 KB 依据+责任条款原文，首行输出 `用户案情：<1–2 句日常口语虚构纠纷，不含法规名/书名号/条号，人物单位一律虚构>`，第二行起输出对应的 1 篇完整普法文章；
     - 代码用多样问句包装 `用户案情`（如 `"写一篇普法文章：{case_brief}"` / `"帮我把这个事写成1篇以案说法：{case_brief}"`），确定性校验：① `用户案情` 非空、无书名号/法规名/裸条号；② 正文通过 `_validate`；③ 整段 ≤ 2,048 tok；④ 与 `eval/cases/v1` 零重合；
     - `meta.kind = "n1_case"`，人工复审额外核对：用户案情与文章 `## 案例` 事实一致、人物/单位全虚构（注：`article-009`/`010` 的“先咨询再转写文章”已有 `ds-8410` 中 104 条中途转文章 `intent` 样本提供多轮基础，保护人名替换由运行时 T054–T056 `anonymize.py` 兜底）。
3. **`t053-v1.1` 首批抽查（前置核对 5.1）**：
   - 在新确认的 1–2 篇初稿（覆盖《公司法》《女职工劳动保护特别规定》《集体合同条例》《工会法》）上，**先单独跑 6–8 个 `swap_subject` 请求**至 `artifacts/synth/articles/t057-v11-spotcheck/`。
   - 人工逐条核查 `t053-v1.1` 新增两条约束（不脱离原条款法定主体范围、普法提示保持面向职工）是否生效，达标后再补跑余量修改稿。

### 3.4 跨请求案例近重复检测（放宽告警阈值，宁可多提示人工）

- 在 `src/tu_assistant/synth/articles.py` 新增 `find_case_near_duplicates(samples, ...)`，在划分前对全部已审初稿与修改稿统一执行：
  1. 仅抽取每篇的 `## 案例` 正文段与 `# 标题`，**忽略 `**法律依据**`/`**法律责任**` 公共引文**；
  2. 对案例段去空白标点，并将虚构人名（`[\u4e00-\u9fff]某` → `<人>`）与虚构单位名（`某[\u4e00-\u9fff]{1,6}(?:酒店|旅馆|宾馆|公司|工厂|厂|医院|学校|机构|中心|集团)` → `<单位>`）脱敏归一化，防止“换标题、换人名、换单位名但情节雷同”逃逸；
  3. 仅比较跨样本对，自动跳过 `revise_plainer` 与其 `parent` 初稿的配对；
  4. **告警阈值设定**：以 T052 已知近重复对照 `candidates-before-r1.jsonl` 行 1 与行 2 为基准（人为替换人名/酒店名后，第 1 篇 `2-gram Jaccard = 0.220`、`SequenceMatcher = 0.517`，第 2 篇 `0.171`、`0.419`；同条款独立样本 `t52:1` vs `t53:req8` 最高仅 `0.128`、`0.274`）。因该检测仅生成人工复核提示、误报代价低而漏报代价高，将默认阈值设为 **`2-gram Jaccard >= 0.15` 或 `SequenceMatcher >= 0.35` 或标题完全相同**（兼顾充裕安全余量与现有非重复对零误报）。
  5. 输出 `dedup_report.md` 交人工裁决剔除，留存筛除数与复核结论；人工同步核查：可换主体条款检验主体差异，固定主体条款检验手段/情节差异。

---

## 4. `dataset.py`、`cli.py` 与 `manifest.json` 工程改动设计

### 4.1 修复 `_infer_meta` 多轮 `article` 判型 & 还原 `relation_*`

摸底 `ds-8410` 发现：**407 条 `intent` 样本中有 104 条属于“中途变卦改写普法文章”**（首轮助手是追问、末轮助手含 `"以案说法"` 与 `"普法提示"`）。同时，落盘 JSONL 不存 `meta`（`contracts/datasets.md`），未来再次 `--reuse-dataset` 时需要保留 `relation_*` 识别能力。

- **精确判型规则（`src/tu_assistant/train/dataset.py:_infer_meta`）**：
  1. 定义 `_is_article_text(text) = ("以案说法" in text and "普法提示" in text)`；
  2. 多轮样本（`messages[0]["role"] == "system"` 且 `len(messages) > 3`）：
     - 当**末轮 `assistant` 与至少一条更早的 `assistant` 均满足 `_is_article_text`**（即“初稿 → 修改要求 → 修改稿”）→ 判为 `"article"`；
     - 否则 → 判为 `"intent"`（实测 407/407 历史 `intent` 全部保持 `"intent"`，12/12 T053 修改稿全部判为 `"article"`）。
  3. 单轮样本保持现有判型顺序，含 `"以案说法"` 且含 `"普法提示"` → `"article"`；
  4. **还原 `relation_*` 的 `meta.kind`**：对 `type == "knowledge"` 的单轮样本，按 `knowledge.relation_samples` 的三条确定性问句正则还原 `meta["kind"]` 为 `"relation_liability_for"` / `"relation_exception_of"` / `"relation_references"`，确保未来复用本数据集时 `thin_knowledge` 依然能自动识别并钉住关系样本。
  5. **未来复用本数据集的文章防丢 `meta` 纪律**：由于 `meta.parent` 无法仅从 `messages` 精确还原，约定并代码强制——
     - 当 `--reuse-dataset` 同时传入 `--articles-file` 时，**自动过滤掉复用库中的旧 `article` 样本**，统一由含完整 `meta` 的固化文件 `t057-curated/*.jsonl` 重新注入；
     - 当仅 `--reuse-only` 不传 `--articles-file` 时，依托 §4.2 的“保留原 `split` 归属”机制，旧文章原样留在原 `train`/`valid` 侧，同样不会跨侧泄漏。

### 4.2 保持复用样本原 `train`/`valid` 归属 + 新增文章按 `parent`/`draft_id()` 同侧划分

**关键防失真设计（针对 T075 从 `exp-20261116-resume500` 续训）**：
`exp-20261116-resume500` 已在 `ds-8410` 的 `train.jsonl` 上训完 1 epoch。若将复用样本全量重新打乱 9:1 划分，新 `valid.jsonl` 中将有约 90% 是续训起点已经见过的训练样本，会导致 T075 的 `val loss` 失真、无法判断过拟合或挑选 checkpoint。

- **实现方案**：
  1. `load_message_samples(dataset_dir, kb_conn=None)`：按 `train` → `valid` 顺序读取并精确去重，在 `meta` 中记录 `meta["split"] = "train" | "valid"`；
  2. `split_train_valid(samples, *, valid_ratio=0.1, seed=42, preserve_split=True)`：
     - **锁定归属样本**（复用样本，带 `meta["split"] in {"train", "valid"}`）：`preserve_split=True` 时**严格保持原 `train`/`valid` 归属**，绝不把旧 `train` 样本划进新 `valid`；
     - **新增样本**（无 `meta["split"]`，包括 67 条新 KB 关系样本与全部新注入文章家族）：
       - 文章样本统一按 `meta.parent`（修改稿）或 `articles.draft_id(sample)`（初稿）聚合成家族，按 `valid_ratio=0.1` **分层整组**划分（家族数 ≥ 2 时至少 1 个完整家族进 `valid`，其余进 `train`）；
       - 非文章新增样本（如 67 条新关系）独立按 `valid_ratio=0.1` 划分（约 60 进 `train`、7 进 `valid`）；
     - 若数据集中全部样本均无 `meta["split"]` 且无文章样本，退化为与原有 `split_train_valid` 兼容行为。
  3. **验收硬门禁**：落盘后对比去除 `system` 消息的 `user+assistant` 规范化序列，断言 **新 `valid` ∩ `ds-8410 train` = 0**，且 **新 `valid` 文章家族 ∩ 新 `train` 文章家族 = 0**。

### 4.3 修复 `dedup_against_eval` 多轮稀释 & `synth sft` 默认评测路径

1. `cli.py:synth_sft` 默认 `--eval-cases` 由 `"eval/cases"` 改为 `"eval/cases/v1"`（加载全部 70 题 / 74 问句），若加载到 0 条问句输出明确警告，并将 `dedup_eval_questions` 与 `dedup_dropped` 写入 `manifest.json`。
2. `dataset.py:dedup_against_eval` 升级为“整段拼接 **或** 任一单轮 `user` 消息 3-gram Jaccard `>= overlap` 即剔除”（与 T053 `_eval_overlap_any_turn` 口径一致）。

### 4.4 `tu synth sft` 接入接口与 `manifest.json` 留痕

- **CLI 扩展（`src/tu_assistant/cli.py:synth_sft`）**：
  - `--articles-file <path>`（可重复多次）：仅接收经人工复审并固化的 JSONL 文件；读取时自动过滤复用库中旧 `article` 样本（防重复与丢 `parent`）、校验 `meta.type == "article"`、校验每条修改稿的 `meta.parent` 存在于合入初稿的 `draft_id()` 集合中（拒收孤儿修改稿），并经 `normalize_draft_markers` 对齐新 KB 标记与 `check_sample`。
  - `--refresh-relations`（与 `--reuse-dataset` 配合）：按三条确定性正则剔除复用库旧关系样本，注入当前 `--kb-version` 全部 `relation_samples` 并标记为 `thin_knowledge` 必保。
- **`write_dataset` 与 `manifest.json` 扩展（`src/tu_assistant/train/dataset.py`）**：
  - 支持写入 `known_issues` 与结构化统计：
    - `known_issues`：登记 **3 项**：① **T078**（`doc_id: 9fc301cd90566af9`《上海市工伤保险实施办法》63/63 条括号条旨顺延 +1，POC 维持历史口径保 v1/SC-016 基线，演示避开该文件款号）；② **历史轮“相关条款（系统补充）”分支**（当前 26 对 `liability_for` 均无未引用出边，由单元测试覆盖）；③ **文章素材法规范围限制**（《劳动法》《劳动合同法》在新 KB 仅含 `references` 无 `liability_for`，POC 文章训练素材覆盖 6 部有责任关系的法规，不重开 T019）。
    - `relation_refresh`：移除旧关系数（18）、注入新关系数（67：26 `liability_for` + 41 `references`）、抽稀后实留数（67）。
    - `consult_check_drops`：记录复用 `ds-8410` 在新口径下被 `check_sample` 淘汰的 68 条 `consult` 的按法规分布。
    - `article_stats`：总条数、初稿/修改稿计数、`kind` 分布（`n1`/`n1_case`/`n2`/`n3`/`n3_default`/`n3_vague`/`n4`/`revise_plainer`/`revise_swap_subject`）、法规分布、家族数、`train`/`valid` 家族划分（跨侧泄漏 = 0）、**在 `unify_system_prompts` 之后对落盘 `train.jsonl` / `valid.jsonl` 最终消息核算的 `token_lengths`（min/median/max，均 ≤ 2,048）**、与来源文件清单。
    - `split_integrity`：`preserved_from_reuse: true`、`valid_overlap_with_reuse_train: 0`、`dedup_eval_questions: 74`、`dedup_dropped`。

### 4.5 训练集规模、`train_oversample.article` 与 T075 续训估算

按基准配置（复用 `ds-8410` 并保持原划分 + 新 KB 67 条关系 + **48 条**推荐下限已审文章：24 初稿 + 24 修改稿；非文章过采样沿用 `intent: 2, consult: 2, refusal: 2`）：
- **复用保留**：
  - `train` 侧旧样本：`knowledge` 5,336（5,402 − 17 旧关系 − 49 抽稀）+ `consult` 815（878 − 63）+ `general` 815 + `intent` 378 + `refusal` 96 = **7,440** 条；
  - `valid` 侧旧样本：`knowledge` 597（598 − 1 旧关系）+ `consult` 97（102 − 5）+ `general` 99 + `intent` 29 + `refusal` 13 = **835** 条。
- **新增 9:1 划分**：
  - 67 条新关系样本：60 进 `train`、7 进 `valid`（总 `knowledge` 精准等于 `6,000`）；
  - 48 条文章样本（~24 个家族）：约 43 条进 `train`、5 条进 `valid`。
- **最终划分**：`valid ≈ 847` 条（100% 为 `exp-20261116-resume500` 未见过样本），`base_train ≈ 7,543` 条（非文章过采样后 `8,789` 步，文章 `base_train ≈ 43` 条）。
- **单步耗时基准（M1 Pro / 32GB 实测）**：`ds-8410` 样本均值 **343.5 tok**（中位数 233 tok），`exp-20261116-resume500`（8,421 iter，49,593 s）与 `exp-e003-7b-epoch2`（8,921 iter，44,283 s）均速约 **5.0–5.9 s/iter**；文章样本 723–1,804 tok（均值 ~1,300 tok），在 `--grad-checkpoint` 下单步约 **12–15 s/iter**。

| `train_oversample.article` | 文章有效步数（占比） | 总 `train_size`（1 epoch iters） | T075 续训 1 epoch 预计耗时 | 评估 |
|---|---:|---:|---:|---|
| `4` | ~172（~1.9%） | ~8,961 | **13.5–14.5 h** | 最保守，对咨询基线扰动最小，但多类问法与修改指令曝光偏少 |
| **`6`（推荐）** | **~258（~2.9%）** | **~9,047** | **13.8–15.0 h** | **与 `refusal(2.2%)`–`intent(8.4%)` 比例协调，学稳骨架与修改指令，同时保护 SC-016 基线** |
| `8` | ~344（~3.8%） | ~9,133 | **14.2–15.5 h** | 43 条文章重复 8 遍，轻度过拟合虚构桥段风险上升 |

> **历史只读产物保护与运行时隔离**：
> - 严禁改动历史 KB（`kb-20261113-093057.sqlite`）、历史数据集（`ds-kb-20261113-093057-8410` 等）、历史训练产物（`exp-20261116-resume500` 等）、历史审稿快照（`t052-implementation-review` / `t053-new-drafts` / `t053-revisions-trial`）与 `eval/cases/v1/`。
> - T057 扩量与固化文件一律写入独立目录 `artifacts/synth/articles/t057-*/`；最终数据集写入新目录 `artifacts/datasets/ds-kb-20261119-045641-<N>/` 并更新 `artifacts/datasets/latest` 软链。
> - 严禁读取 `inputs/` 下任何文件；运行时模块（`chat/`、`runtime/`、`ui/`、`eval/`）严禁导入 `synth.llm`（`test_runtime_isolation.py` 强制校验）。
> - T057 **不启动 7B 训练**；T075 续训时另建独立配置（如 `configs/train/demo-7b-t075.yaml`），不改 `demo-7b-resume.yaml`。

---

## 5. 分步实施步骤（含编码与人审并行安排）

1. **步骤 1 · 导出素材与多违法组合白名单（落实前置核对 1）**
   - 用只读脚本导出 `kb-20261119-045641` 的 26 对 `liability_for` 与 20 组同文件多违法组合清单，逐项核对行为主体、适用条件与救济，形成 `artifacts/synth/articles/t057-curated/materials_audit.md` 并锁定高自然度多违法白名单。
2. **步骤 2A · 增强 `synth/articles.py`（自然问法、`n4`/`n1_case`、场景扩展、跨请求案例去重）**
   - 扩展 `SCENARIOS`（6–8 条）与 `COUNT_MODES = (None, 1, 2, 3, 4)`；新增分桶自然问法模板池（`n1`/`n2`/`n3`/`n3_default`/`n3_vague`/`n4`）与 `n1_case`（用户自带案情）生成及确定性校验；实现 `find_case_near_duplicates(...)`（阈值 `2g >= 0.15` 或 `seq >= 0.35` 或同标题）；补齐 `tests/unit/test_synth_articles.py`。
3. **步骤 2B · 并行轨道 · 改造 `train/dataset.py`、`cli.py` 与 `configs/synth.yaml`（可与步骤 3 人工审稿并行先做完！）**
   - `dataset.py`：修复 `_infer_meta`（多轮 `article` vs `intent` + `relation_*` 还原）；`load_message_samples` 保留 `meta["split"]`；`dedup_against_eval` 升级为逐轮+整段判定；`thin_knowledge` 钉住 `relation_*` 且优先裁减非 `valid` 侧；`split_train_valid` 支持 `preserve_split=True` + 新增文章按 `parent`/`draft_id()` 分层整组同侧划分；`write_dataset` 支持 `known_issues` 与结构化统计落盘。
   - `cli.py`：`synth sft` 默认 `--eval-cases eval/cases/v1`，新增 `--articles-file`（剔除复用库旧文章 + 强校验 `parent` 完整与新 KB 引用）与 `--refresh-relations`（清旧 18 条 + 注入新 67 条 + 写 `known_issues`/`article_stats`/`consult_check_drops`）。
   - `configs/synth.yaml`：在 `train_oversample` 增加 `article: 6`（按用户拍板值）。
   - 补全 `tests/unit/test_dataset.py` 与 CLI 确定性测试，先跑绿全部单测与 ruff。
4. **步骤 3 · 扩量生成与分步人工复审（含 `t053-v1.1` 首批抽查）**
   - **3a 初稿扩量**：在 `kb-20261119-045641` 上分法规、分模式（补齐《公司法》《女职工劳动保护特别规定》及 `n1_case`/`n3`/`n3_default`/`n3_vague`/`n4`）生成 ~24–28 个新请求至 `artifacts/synth/articles/t057-expand-drafts/`；逐条人工复审并固化通过项（期间可并行执行步骤 2B）。
   - **3b `t053-v1.1` 首批抽查**：用新确认的 1–2 篇初稿跑 6–8 个 `swap_subject` 请求至 `artifacts/synth/articles/t057-v11-spotcheck/`，人工核查两条新约束生效情况。
   - **3c 修改稿余量扩量与人工复审**：抽查达标后补跑余量 `plainer` + `swap_subject` 请求至 `artifacts/synth/articles/t057-expand-revisions/`，逐条人工复审。
5. **步骤 4 · 汇总固化 + 跨请求案例去重 + 人工复核（落实前置核对 2、4）**
   - 编写可复现整理脚本汇总全部人工复审初稿与修改稿（经 `normalize_draft_markers` + 新 KB `_validate`/`_validate_revision` + ≤ 2,048 tok + 逐轮 `eval/cases/v1` 去重），运行 `find_case_near_duplicates` 输出 `dedup_report.md`；人工裁决剔除疑似近重复对后，固化最终文件 `artifacts/synth/articles/t057-curated/{drafts.jsonl,revisions.jsonl}` 与 `coverage_report.md`（素材组合频次、去重前后分布、问法覆盖、法规占比、样本位置）。
6. **步骤 5 · 执行 `tu synth sft` 构建新数据集并做全量确定性验数（含落盘后 token 复核）**
   - 运行 `uv run tu synth sft --kb-version kb-20261119-045641 --reuse-dataset artifacts/datasets/ds-kb-20261113-093057-8410 --reuse-only --refresh-relations --articles-file artifacts/synth/articles/t057-curated/drafts.jsonl --articles-file artifacts/synth/articles/t057-curated/revisions.jsonl --skip-llm`。
   - 对落盘后的 `train.jsonl`、`valid.jsonl` 与 `manifest.json` 执行 §6 全部确定性校验（包括在 `unify_system_prompts` 之后对落盘最终消息重算全量 token 长度并回核 ≤ 2,048）。
7. **步骤 6 · 更新学习文档与独立复审闭环**
   - 更新 `docs/learning/04-training-data.md` 与 `00-glossary.md`（详见 §7）；
   - 按 `.agents/skills/task-review-loop/SKILL.md` 完成内部独立只读复审闭环，汇总全部证据与复审结论汇报用户，经用户确认后再勾选 `tasks.md` T057 并提交。

---

## 6. 确定性验收方法

> 原则：所有语义/法理质量判断（事实是否支撑责任、通俗化是否失真、主体/手段差异是否充分、用户案情与文章一致性、提示是否面向职工）均在步骤 3–4 的**人工复审**与留证报告中把关；自动化单元测试与脚本验收**只覆盖确定性可测条件**。

### 6.1 自动化单元测试与静态检查（全绿）

- `uv run pytest tests/unit/test_dataset.py`：
  1. `_infer_meta`：5 消息 T053 修改稿判为 `"article"`；单轮初稿判为 `"article"`；“模糊开场 → 追问 → 中途改主意写文章 → 普法文章”的 5 消息 `intent` 样本仍判为 `"intent"`；关系问答样本自动还原 `meta.kind = relation_*`；
  2. `load_message_samples` & `split_train_valid`：复用样本携带 `meta.split` 时 100% 保持原 `train`/`valid` 归属（`new_valid ∩ old_train == ∅`）；新增文章样本按 `meta.parent` / `draft_id()` 分层整组同侧划分（跨侧交集为空，跨多种随机种子成立）；
  3. `thin_knowledge`：`relation_*` 样本在 `len(knowledge) > knowledge_max` 时 100% 保留，且裁减优先发生在非 `valid` 侧不破坏原留出集；
  4. `dedup_against_eval`：多轮样本仅单轮 `user` 与评测题高重合时也能被准确剔除；
  5. `write_dataset`：`manifest.json` 正确落盘 `known_issues`、`article_stats`、`relation_refresh`、`split_integrity`、`dedup_eval_questions` 与 `train_oversample.article`。
- `uv run pytest tests/unit/test_synth_articles.py`：
  1. 分桶自然问法模板池覆盖 `n1`/`n1_case`/`n2`/`n3`/`n3_default`/`n3_vague`/`n4`，`n=4` 可正常规划 4 篇且不超 `SCENARIOS`，全部模板对 `eval/cases/v1` 74 问句零重合；
  2. `n1_case` 正反例（含案情带法规名/书名号/裸条号被拒）；
  3. `find_case_near_duplicates`：对替换人名/单位名/标题后的近重复案情对稳定检出（阈值 `2g >= 0.15` 或 `seq >= 0.35`），对不同情节的同条款案情对不误报，对 `revise_plainer` 与其 `parent` 初稿自动跳过；
  4. `synth sft` 对孤儿修改稿（`parent` 缺失对应初稿）确定性报错拒绝；传 `--articles-file` 时自动剔除复用库旧文章防重复。
- 全量回归与隔离守卫：`uv run pytest` 全量通过（含 `tests/unit/test_runtime_isolation.py`）；`uv run ruff check src tests`。

### 6.2 最终数据集产物确定性核验清单

对落盘后的 `artifacts/datasets/ds-kb-20261119-045641-<N>/` 逐项脚本核验：
1. **防续训验证集失真（硬门禁）**：按去除 `system` 后的 `user+assistant` 序列比对，**新 `valid.jsonl` ∩ `ds-8410/train.jsonl` = 0**；`valid.jsonl` 内部无精确重复；
2. **文章同侧划分零泄漏**：按 `draft_id()` / `parent` 还原文章家族，**新 `valid` 文章家族 ∩ 新 `train` 文章家族 = 0**；
3. **落盘后最终消息长度硬校验**：对 `unify_system_prompts` 之后已落盘的 `train.jsonl` 与 `valid.jsonl` 全部样本（尤其全部文章样本）用 Qwen2.5-7B tokenizer 精确计数，**max_tokens ≤ 2,048**，与 `manifest.json` 中 `article_stats.token_lengths` 完全一致；
4. **关系样本完整性**：去重全集包含 `kb-20261119-045641` 全部 **67/67** 条 `relation_samples`，包含旧 KB 已撤销 10 条错边的样本数为 **0**；
5. **引用与均衡校验**：合入文章样本在新 KB 上 `check_sample` 通过率 **100%**，被 `balance_by_doc` 截断的文章数为 **0**；
6. **评测去重有效**：`dedup_against_eval` 实际加载 `eval/cases/v1` 全部 **70 题 / 74 问句**，最终数据集逐轮重合数为 **0**；
7. **留证与只读保护**：`manifest.json` 包含 3 项 `known_issues`（T078、26 对无额外出边、《劳动法》/《劳动合同法》缺 `liability_for`）、`relation_refresh`、`consult_check_drops`、`article_stats`、`split_integrity`；`artifacts/datasets/latest` 指向新数据集；历史产物零变动。

---

## 7. 学习文档更新点（`docs/learning/`）

实施完成后同步更新：
1. `docs/learning/04-training-data.md`：
   - 新增 **`[L4.5.3] 数据集增量更新、续训留出集保护与跨请求去重`**：用本项目真实数据说明五个工程要点——① 为什么从已有 checkpoint 续训时，复用样本必须锁定原 `train`/`valid` 归属（防验证集失真）；② 知识库修订后如何清理旧错边并在抽稀（`thin_knowledge`）中钉住新关系；③ 为什么“初稿 + 修改稿”必须按家族同侧划分（Group Split 防数据泄漏）；④ 多轮 `article` 与“中途变卦写文章”的 `intent` 在反推 `meta` 时的结构区分；⑤ 中文短案例近重复检测为何必须只比案例段并先脱敏虚构人名/单位；
   - 更新 **`L4.7 当前数据集的真实结果`**：补充 `ds-kb-20261119-045641-<N>` 的实测类别分布、67 条新关系与文章样本占比（保留历史 `ds-kb-20261113-093057-14710` / `8410` 记录作演进对照）。
2. `docs/learning/00-glossary.md`：补充“分组划分（Group Split）”“数据泄漏（Data Leakage）”“续训验证集污染”词条（如有缺漏）。

---

## 8. 待用户拍板的决策清单（7 项）

请在审阅本执行单后对以下 7 项拍板，确认后立即开工实施：

1. **文章样本扩量规模**
   - **选项 A（推荐 · 标准 POC 下限档，约 48 条）**：约 **24 初稿 + 24 修改稿**（含 `n4` 2–3 条与 `n1_case` 2–3 条，需新增人工复审约 35 条）。6 部法规全覆盖（单法规在文章子集 ≤30%），完整覆盖 v1 文章评测问法类型；
   - **选项 B（轻量最小档，30–36 条）**：补齐缺口 2 部法规与显式 3 篇/模糊“几篇”（新增人审约 18–22 条），审稿量更省但部分问法桶样本偏薄。

2. **`train_oversample.article` 训练侧过采样倍数**
   - **选项 A**：`4×`（文章约 172 步 / 占比 ~1.9%，T075 预计 ~13.5–14.5 h）；
   - **选项 B（推荐）**：`6×`（文章约 258 步 / 占比 ~2.9%，T075 预计 ~13.8–15.0 h；与 `refusal`/`intent` 占比协调，既能学稳格式与修改指令又不冲击 SC-016 基线）；
   - **选项 C**：`8×`（文章约 344 步 / 占比 ~3.8%，T075 预计 ~14.2–15.5 h，轻度过拟合虚构桥段风险上升）。

3. **复用 `ds-8410` 时被新校验口径淘汰的 68 条历史 `consult` 样本**
   - 背景：T077 统一含项条文规范原文后，68 条（原 `train` 63 / `valid` 5）触发 `citation_text_wrong`（主要分布：《职业病防治法》21、《安全生产法》12、《保障农民工工资支付条例》11、《工会法》5、《劳动法》4、《社保法》4、其余 11）；保留 `consult` 仍有 **912 条**（93.1%）。
   - **选项 A（推荐）**：按新校验口径自然淘汰，不补跑外部 LLM，并在 `manifest.json` 登记被淘汰样本的按法规分布（确保引文 100% 严格一致、零额外费用与工期）；
   - **选项 B**：额外调用外部 LLM 补生成约 70 条 `consult` 样本填回 980 条；
   - **选项 C**：离线脚本确定性将这 68 条的引文替换为新 KB 规范原文后重跑 `check_sample`，并人工抽查分析段是否遗漏补入的子项要点。

4. **新 KB 20 组同文件多违法组合的筛选方式**
   - **选项 A（推荐）**：步骤 1 先导出 20 组条款明细，人工剔除天然难共场景的组合（如《妇女权益保障法》中“住宿报告 + 招聘/孕产期”4 组），形成约 12–16 组高自然度白名单用于扩量，显著降低人工审稿退回率；
   - **选项 B**：全 20 组无筛选均匀轮询，依赖外部模型自行返回“素材不适用”跳过。

5. **T052 保留候选 1（`20261118-154620-743804:req1`，`n3_default` 住宿三篇）的去留**
   - **选项 A（推荐）**：规范化后保留入库（直接作为现成 `n3_default` 样本，新 KB 校验 6/6 `ok`，与 `t053-new-drafts:req8` 实测案例重合低 `2g=0.128`），并在步骤 4 与全量样本统一跑跨请求案例去重核验；
   - **选项 B**：不复用该条，全部 3 篇初稿均用新 KB + 新自然问法模板重新生成。

6. **【新增】复用 `ds-8410` 旧样本是否保持原 `train`/`valid` 归属**
   - **选项 A（推荐）**：**是**——`load_message_samples` 保留原 `split` 归属，仅新增样本（67 条新关系 + 文章家族）按规则 9:1 划分，验收硬断言“新 `valid ∩ ds-8410 train = 0`”，保证 T075 从 `exp-20261116-resume500` 续训时 `val loss` 真实有效；
   - **选项 B**：否——全量合并后重新随机 9:1 划分（会令新 `valid` 约 90% 为续训起点已训练样本，导致 `val loss` 失真）。

7. **【新增】对齐 v1 文章评测题的问法补齐 & 《劳动法》《劳动合同法》素材缺口处理**
   - **选项 A（推荐）**：补齐 **`n4`（2–3 条）** 与 **`n1_case`（用户自带案情 1 篇，2–3 条）** 两小桶（`n4` 不进修改轮）；同时将《劳动法》《劳动合同法》在新 KB 缺 `liability_for` 仅登记进 `manifest.json` 的 `known_issues`，不在 T057 重开 T019 人工关联审阅；
   - **选项 B**：不补 `n4` 与 `n1_case`，维持 1–3 篇纯主题问法（v1 的 `article-004/005/006` 完全依赖零样本泛化）。

---

## 9. 实施与验数记录（2026-11-19）

### 9.1 固化文章池与留证
- 素材与多违法白名单：`artifacts/synth/articles/t057-curated/materials_audit.md`（26 对 `liability_for`，审定 11/20 高自然度多违法白名单）。
- 扩量与人工复审：
  - 扩量初稿批 `t057-expand-drafts`（24 请求，自动通过 19/24，人工保留 12 条）；
  - 《公司法》补跑 `t057-expand-company`（3 请求，3/3 通过，人工保留 2 条）；
  - `t053-v1.1` 首批抽查 `t057-v11-spotcheck`（6 请求，6/6 通过，两条新约束均生效，人工保留 5 条）；
  - 余量修改稿 `t057-expand-revisions-plainer`（6/6 通过，保留 5 条）与 `t057-expand-revisions-company`（2/2 通过，保留 2 条）。
- 可复现固化脚本 `scripts/curate_t057_articles.py` 产出：
  - `artifacts/synth/articles/t057-curated/drafts.jsonl`（22 条初稿，覆盖 26 对 `liability_for` 中的 18 对）与 `revisions.jsonl`（24 条修改稿），合计 **46 条**（22 家族，token 520–1,804）；
  - 全部 6 部法规均衡覆盖（集体合同 12 / 26.1%、妇女法 9 / 19.6%、女职工特别规定 8 / 17.4%、工会法 7 / 15.2%、就业促进 5 / 10.9%、公司法 5 / 10.9%，均 ≤30%）；
  - 全部 7 种初稿问法桶均 ≥2 条（`n1` 6、`n1_case` 2、`n2` 6、`n3` 2、`n3_default` 2、`n3_vague` 2、`n4` 2；修改稿 `revise_plainer` 13 + `revise_swap_subject` 11）；
  - 跨家族近重复告警仅 1 条边缘项（情节独立保留），详见证报告 `dedup_report.md` 与 `coverage_report.md`。

### 9.2 最终数据集 `ds-kb-20261119-045641-8247` 与 §6.2 7 项门禁实测
- 构建命令：`uv run tu synth sft --kb-version kb-20261119-045641 --reuse-dataset artifacts/datasets/ds-kb-20261113-093057-8410 --reuse-only --refresh-relations --articles-file artifacts/synth/articles/t057-curated/drafts.jsonl --articles-file artifacts/synth/articles/t057-curated/revisions.jsonl --skip-llm`
- 结果：`train 8,962`（`article` 252 = 2.81%，`refusal` 176 = 1.96%）、`valid 820`（`article` 4，`refusal` 1）、去重唯一总数 **8,247**（按去 `system` 对话体清理旧库 141 条重复，其中旧 valid 有 23 行 / 19 条唯一对话体与旧 train 重合；为保持与基线一致的拒答权重，经用户拍板将 `train_oversample.refusal` 调至 `4`，并按 `(relation_kind, clause_ids)` 语义锁定全部旧 `train` 关系）。
- **§6.2 7 项硬门禁全通过**：
  1. 新 `valid(820)` ∩ `ds-8410 train` = **0**，`valid` 内部唯一；
  2. 文章家族 `train(20)` ∩ `valid(2)` = **0**（`manifest.json` 落盘 `family_leakage=0`）；
  3. 落盘后全量 8,247 条唯一消息经 Qwen2.5-7B tokenizer 实测 `max_tokens = 2,015 <= 2,048`；46 条文章 `520..1,804` 与 `manifest.json` 精确一致；
  4. 新 KB `kb-20261119-045641` 全部 **67/67** `relation_samples` 在库（`kept_after_thin=67`）；
  5. 文章 `check_sample` 100% 通过，`dropped_by_balance = 0`；
  6. 实际加载 `eval/cases/v1` 全部 **74 问句**，逐轮重合数 = **0**；
  7. `manifest.json` 完整落盘 3 项 `known_issues`、`relation_refresh`、`consult_check_drops`（68 条按法规分布）、`article_stats`、`split_integrity`，`artifacts/datasets/latest` 指向新库。

### 9.3 单元测试与静态检查
- `uv run pytest`：**205 passed, 6 xfailed**（含 `test_runtime_isolation.py`）
- `uv run ruff check src tests scripts/t057_expand_drafts.py scripts/t057_supplement_company.py scripts/curate_t057_articles.py`：**All checks passed**

### 9.4 独立只读复审闭环记录（`task-review-loop`）
- 复审方式：单节点高思考 `swarm` 审查员（`reviewer` / `gemini-4-neon-high`，`workspace="inherit"`，只读约束，已完成并回收）。
- **Round 1（需修改）**：发现 3 项阻断项（`04-training-data.md` L4.7 表格 4 处数字与 `manifest.json` 偏差；`thin_knowledge` 次选分支多条文重复 append 缺陷；`test_thin_knowledge_pins_relations_and_protects_valid_split` 假阳性与缺 CLI 正例/跨 split 去重单测）+ 4 项非阻断建议（按语义签名锁定关系防跨侧语义重合、`manifest.json` 补齐 `kept_after_thin` / `train_families` / `valid_families` / `family_leakage`、token 超限改硬报错等）。
- **Round 2（通过，0 阻断）**：3 项阻断项与 3 项非阻断建议均已修复、重建数据集 `ds-kb-20261119-045641-8247` 并独立复核全部 §6.2 7 项硬门禁、205 passed 单测及 ruff 静态检查通过。
- **外部模型复审（通过，0 阻断）与收尾调整**：外部复审逐字节复现并通过全部 7 项门禁；经用户拍板落实：① `configs/synth.yaml` 将 `train_oversample.refusal` 调至 `4`（`train` 8,874 → 8,962，`refusal` 88 → 176）；② `known_issues` 移入 `configs/synth.yaml` 由 `cli.py` 读取；③ 修正 `t057-v11-spotcheck:req6` 与 `t057-expand-revisions-plainer:req6` 普法提示中第三十八条与第三十九条的权责表述并重建固化文章与最终数据集。
