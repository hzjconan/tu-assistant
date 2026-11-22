# T056 执行单 · 对话编排接入普法文章数量控制

**状态：已完成并通过 3 轮独立只读复审与用户确认验收（2026-11-22）。** 基于提交 `5571479`。本执行单承接 Phase 4 / US2 收口，聚焦在 `src/tu_assistant/chat/orchestrator.py` 及相关入口落地确定性的普法文章数量控制（默认 3 篇、单次上限 10 篇，读取 `SessionConfig`），在保持 `v2-short` system prompt 与既有咨询/演示基线零回归的前提下完成 T056。

---

## 1. 推荐任务编号与选择理由

**推荐任务：T056（补齐普法文章数量控制，收口 Phase 4 / US2 代码交付）。**

| 候选任务 | 当前状态与前置条件 | 为何 T056 优先 |
|---|---|---|
| **T056（推荐）** | 身份信息检查接线已随 T054/T055 验收落地，仅剩文章数量控制待办；无外部依赖与训练开销 | 纯确定性编排与单测，一轮即可收口 US2 全部代码任务；可复用刚验收的意图与实体抽取上下文；落地后冻结 `chat/orchestrator.py` 行为，避免后续 Phase 5/7 返工 |
| **T049（US1 补写 ~20 题评测集）** | 需合成/编写多违法行为与多轮意图脚本并由用户逐题人工审阅 | 人工审阅周期长，不阻塞编排收口，可在编排稳定后集中推进 |
| **Phase 5（T061–T065，US3 评测报告与对比）** | 含完善报告、通用 `tu eval compare`、人工评审模板及 **T064（7B 重复评测 2 次验证 SC-015）** | 若在 T056 改动编排前先做 T064 重复评测，T056 落地后编排行为变化会使评测基线失配而返工；应先固定编排再做 Phase 5 |
| **Phase 6（T066–T068，US4 知识库维护）** | 独立模块，可任意穿插 | 与当前 US2 主线无直接耦合，优先级低于 US2 闭环 |
| **Phase 7（T069–T074，Gradio UI 与收尾）** | `tasks.md` 明确依赖 US1 与 US2；T069 直接调用 `TrainedAssistant` 与 `SessionConfig` | 先将 `default_article_count` / `max_article_count` 接通并稳定接口，Gradio UI 与演示脚本无需二次返工 |

### 顺带核对：T059 状态（仅供用户决定是否核销，T056 实施不越界）

经只读核对 `specs/001-legal-clause-assistant/tasks.md`（L163–L167）、`docs/experiments/poc-training-summary.md`、`specs/001-legal-clause-assistant/research.md`（R13）与 `docs/experiments/T075-article-training.md`：
- T059 核心目标（7B 首训 → 评测 → 再训 → POC 验收）已实质完成：`exp-20261116-resume500` 零 NaN 完训 8,421 iter，E003 B1 完成追加 1 epoch 对照训练，`tu eval compare --sc016 run-20261117-022645 run-20261117-081504` 三项 PASS（条级 1→17/60，款级 9/60，基座未识别文件子集 0→21/30），用户已于 2026-11-18 判定 POC 训练目标达成；合入文章样本的续训已单列为 T075 并按路线 A 结项勾选 `[x]`。
- 唯一与 T059 描述字面（`评测（quickstart V5）`）关联的遗留项是 V5 中的“同一模型重复运行，指标波动 ≤2 个百分点（SC-015）”，该工作在 `tasks.md` 中已明确拆分至 Phase 5 的 **T064**。
- **边界声明**：T056 实施本身不触碰任何训练配置、适配器权重或历史评测 run；是否现在核销 T059 或留待 T064 完成后核销，列入第 6 节由用户拍板。

---

## 2. 背景与现状核对

### 2.1 只读基线与活跃产物

- **代码基线**：`5571479`（全量测试基线 282 passed / 6 xfailed，`ruff` 全绿）。
- **活跃知识库**：`kb-20261119-045641`（24 份文件、3,809 条记录、67 条已确认关联）；60 题咨询基线旧 KB：`kb-20261113-093057`。
- **冻结演示模型**：`exp-20261116-resume500`（最终 adapter SHA-256 前缀 `b62a7d0e86f4`）。
- **历史评测基线**：
  - 60 题条款识别：`run-20261117-081504`（条级 17/60、款级 9/60、SC-016 PASS）。
  - 10 题普法文章：`run-20261122-090101`（T054 接线后父模型实测：SC-011 **2/2**、引用冲突暂缓交稿 **0 轮**、文章篇数符合 **3/9**［005/006/010］、范围外正确拒答 **1/1**［007］、范围内误拒 **4/9**［001–004］）。
- **历史产物只读保护与合规红线**：不修改 `specs/`、`eval/cases/v1/`、历史 KB、历史数据集、已训权重与历史 run；不读取 `inputs/` 下任何文件；运行时严格遵守本机白名单与零外部 LLM 导入约束（`tests/unit/test_runtime_isolation.py`）。

### 2.2 T054/T055 已完成部分 vs T056 剩余缺口

| 模块与位置 | 现状（已核实） | T056 剩余缺口 |
|---|---|---|
| `configs/app.yaml`（L11–L14） | 已定义 `session.max_questions_per_turn: 5`、`session.default_article_count: 3`、`session.max_article_count: 10` | 无缺口（默认篇数与路线 A 演示的协调见第 6 节决策 3） |
| `src/tu_assistant/chat/assistant.py`（L20–L24, L60–L71） | `SessionConfig` 已有 `default_article_count=3`、`max_article_count=10`，并在 `new_session` 中写入 `session.config` | **缺口 1**：未对非法配置（如 `<= 0`、`bool` 传入、`default > max`）做确定性校验 |
| `src/tu_assistant/chat/prompts.py`（L11–L34） | `PROMPT_VERSION = "v2-short"`；`build_system_prompt(max_questions=5, default_article_count=3)` 签名已含 `default_article_count`，但 `SYSTEM_TEMPLATE` 未使用它 | **约束**：`v2-short` 为训练与评测共用模板（`train/dataset.py` L363–L393），**不可修改全局模板正文**，否则破坏训练/推理分布一致 |
| `src/tu_assistant/chat/orchestrator.py`（L45–L143） | 已完成实体抽取、出处校验、关联补全兜底、`classify_turn_intent`、免责声明、`anonymize_article_text` 与 `sanitize_citations` | **缺口 2**：完全未解析用户请求的篇数，完全未消费 `max_article_count`，也未实际消费 `default_article_count`；超上限或非正数请求会直接穿透到模型 |
| `src/tu_assistant/chat/anonymize.py`（L235–L262, L545–L589） | 已有经 3 轮复审的 `_RE_NEGATE_ARTICLE`、`_RE_EXPLICIT_WRITE`、`_RE_EXPLICIT_REVISE`、`_RE_ELLIPTICAL_REVISE`、`_RE_EXPLICIT_CONSULT` | **缺口 3**：`_RE_EXPLICIT_WRITE` 的篇数字符集 `[两二三四五六七八九十\d]+` 未涵盖 `零/〇/百/千` 及负号，且未提供前置用户意图判定 helper 供编排层在调用模型前共享 |
| `src/tu_assistant/cli.py`（L1019–L1034, L1143–L1147） | `tu chat` 已从 `configs/app.yaml` 读取 3 个 `session.*` 字段构造 `SessionConfig`；但 `tu eval run`（L1033）只传了 `SessionConfig(use_system_prompt=not no_system_prompt)` | **缺口 4**：`tu eval run` 未从配置文件透传 `session.max_questions_per_turn`、`session.default_article_count`、`session.max_article_count`，导致 `--config` 修改 session 参数在评测入口不生效 |

### 2.3 T075 路线 A 与 `v2-short` 对齐约束

1. **不能改动全局 `v2-short` system prompt**：`exp-20261116-resume500` 在全部训练样本与 60 题/10 题基线评测中均使用精确的 `v2-short` 文本（`docs/learning/05-training.md` L5.4 已记录过训练/推理 prompt 分布不一致导致的格式与召回退化）。改变全局 system prompt 会扰动全部咨询请求与 SC-016 基线。
2. **尊重 T075 路线 A 的演示现实**：当前冻结父模型未训练文章样本，对 `article-001..004` 开放多篇请求普遍误拒（4/9）；路线 A 演示采用“给定虚构案情与已核准法条的预审**单篇**”，三条彩排提示词（`docs/experiments/T075-article-training.md` L25–L38）均已显式指定“一篇”。因此编排层控制**不得对已明示合法篇数（特别是单篇）的请求造成额外 prompt 漂移**，也不应把“父模型能否一次写出 3 篇高质量差异化文章”错误设为 T056 代码单测条件。

---

## 3. 实施边界与核心设计

### 3.1 核心方案对比：方案 A vs 方案 B

两种方案都包含**前置确定性入口校验**（配置合法性校验 + 写稿请求识别 + 篇数解析 + 非正数/超上限拦截或钳制）；核心差异在于**通过校验后的生成编排方式**：

| 对比维度 | **方案 A：入口拦截/钳制 + 单次调用轻量指令（推荐）** | **方案 B：入口拦截/钳制 + 编排层按篇循环调用** |
|---|---|---|
| **确定性边界** | 100% 确定性覆盖：配置校验、数字解析、非正数/超限处理、默认篇数透传与附注、咨询与修改轮零误触；实际出篇数与篇间差异（SC-010）诚实归属模型能力边界 | 编排层循环 N 次，看似可强制调用 N 次，但模型单轮仍可能拒答、追问或输出非标准文本；需要启发式早停，且无法赋予未训文章的父模型“独立选条 + 多样化创作”能力 |
| **延迟与 token 成本** | 始终 **1 次**模型调用（单篇 ~10–20s，3 篇 ~40–60s，贴合 SC-013 参考）；唯一限制是单次 `max_tokens=4096` 在 6–10 篇长文时可能触及长度上限 | 循环 N 次且为防重复须把前 `i-1` 篇摘要/正文塞进上下文，prefill 成本随轮次增长；3 篇 ~60–90s，10 篇可达 3–5 分钟且易触发上下文窗口退化 |
| **与 T075 路线 A & 训练分布的对齐** | **高度对齐**：T052/T057 训练的多篇样本本就是“单轮一次输出 1–4 篇（`---` 分隔）”；路线 A 3 条单篇彩排提示词与 `article-002..010` 均零 prompt 扰动 | **分布冲突**：模型训练从未见过“现在只写第 2/3 篇并避开前篇主体 X”的拆轮指令，7B 极易出现复述、格式丢失或误拒；路线 A 演示单篇也完全用不到循环 |
| **与 `verify_output` / 关联补全 / 免责声明的交互** | 单次 `verify_output`、精确 `protected_spans`、单次关联补全去重、文末单次免责声明，零拼接复杂度 | 需逐篇校验或拼合后重算 `protected_spans` 偏移、合并去重多篇 `citations` 与关联补条，还须处理模型自带 `---` 或前导语造成的排版脏块 |
| **与 `anonymize`（FR-030）的交互** | 单次全稿扫描、代称分配稳定，任一处命中核准法条即整轮原子暂缓交稿 | 循环内若把第 `i` 篇原稿直接喂给第 `i+1` 篇会泄露身份，须每篇先脱敏；若第 `k` 篇发生核准引文冲突，前 `k-1` 篇推理算力作废并整轮回滚 |
| **与 `raw_content` / `eval_mode` 的交互** | `raw_content` 严格对应唯一一次模型原生输出，`score_case_output(final_raw, ...)` 语义原汁原味 | `raw_content` 只能人为用 `---` 拼接多次原稿，混入编排层产物，导致 `article_count` 评测失真且掩盖模型原生能力 |
| **与域外拒答（`article-007`）的交互** | 单次调用直接拒答，零多余请求 | 若第 1 次模型给出委婉拒答而未被早停正则命中，会继续无意义地循环请求 2..N 次 |
| **与续改轮（`article-008/010`）的交互** | 自然单轮助手历史，续改无缝承接 | 多次循环拼成的超长助手消息塞入 `session.messages`，后续单轮续改上下文暴涨、行为割裂 |
| **对既有测试契约的影响** | **零破坏**：`tests/unit/test_article_eval.py` 中 6 处模拟“写三篇”仅 mock 1 次 HTTP 返回的既有测试全部天然通过 | **破坏契约**：上述 6 处既有测试全部会因多出 2 次模型请求触发 `StopIteration`，需大规模重写测试语义 |

**结论**：POC 阶段采用 **方案 A** 最符合宪章原则 VI（简单优先、可复现）、训练分布对齐以及路线 A 现实；方案 B 仅在正式阶段大模型/高预算且确需支持 6–10 篇突破单次 `max_tokens` 时再纳入演进评估。

---

### 3.2 超限处理策略对比（`requested > max_article_count`）

对于 `requested <= 0`（如“写 0 篇”“写 -2 篇”），两种策略均直接**硬拒并提示有效范围**（不调用模型）。分歧仅在 `requested > max_article_count`（如上限 10 时请求“写 15 篇”）：

| 维度 | **选项 1：硬拒并提示（推荐）** | **选项 2：钳制到上限并执行** |
|---|---|---|
| **用户体验与资源保护** | 毫秒级返回明确上限提示，不白跑模型；避免用户手误输“50 篇”导致本机 7B 长时间满载并产出截断半成品 | 无需用户重发即可拿到回复，但本机 7B 一次生成 10 篇耗时极长且易触及 4096 `max_tokens` 截断，当前父模型更可能直接误拒 |
| **状态与元数据确定性** | 不调用模型（`client.chat` 调用 0 次），返回固定提示，`citations=[]`、`question_count=0`、`raw_content=None`，不改变原 `session.intent` / `article_task_active` | 需在临时请求注入上限附注并在交付稿首部追加“已按上限 N 篇处理”说明；若模型实际只吐出 0 篇或 2 篇，附注声称“已按上限 10 篇处理”会与实际交付产生矛盾 |
| **与 SC-008 拒答初筛交互** | 提示文案避开 `REFUSAL_ABILITY` / `REFUSAL_SCOPE` 短语（不用“无法生成”“超出了我的知识范围”等），使 `detect_refusal(...)["refused"]` 为 `False`，不与域外知识拒答混淆 | 走正常模型交付与初筛 |

**推荐理由**：选项 1（硬拒并提示）在本机 POC 算力、当前父模型多篇能力边界和交互诚实性上全面占优（不会出现“提示已按上限 10 篇处理，正文却只给了 0 篇/1 篇”的自相矛盾）。

---

### 3.3 方案 A 详细设计

#### (1) 配置校验（Fail-Fast）
- 在 `SessionConfig.__post_init__` 与 `article_count.resolve_count_limits(config_dict)` 中统一校验：
  - `default_article_count` 与 `max_article_count` 必须为正整数（严格校验 `isinstance(v, int) and not isinstance(v, bool) and v >= 1`），且 `default_article_count <= max_article_count`；
  - 违反时立即抛出 `ValueError`；
  - `session.config` 未传对应键时保持默认回退 `(3, 10)`，兼容 `new_session({})` 等既有调用。

#### (2) 共享前置意图判定与独立数量解析模块（`src/tu_assistant/chat/article_count.py`）
为避免与 `anonymize.py` 维护两套冲突正则，抽提/共享用户消息前置意图信号（只依赖 `user_message` 和 `article_task_active`）：
1. **写稿触发条件**：
   - 先排除 `_RE_NEGATE_ARTICLE`（如“不要写 15 篇普法文章，只问怎么处理”“单位不让写普法文章合法吗？”）及无写稿信号的纯咨询 `_RE_EXPLICIT_CONSULT`（如“我在公司写了 15 篇文章，克扣稿费合法吗？”）；
   - **新建写稿**（`explicit_write`）：扩展原有 `_RE_EXPLICIT_WRITE` 的篇数字符集，支持 `-?\d+` 以及中文数字 `[零〇一二两三四五六七八九十百千]+`（复用 `kb/numbers.py` 的 `chinese_to_int`，同时保留原有“普法文章/短文/以案说法/整理成……”全部模式）；
   - **修改轮**（`explicit_revise` / `elliptical_revise`）：普通修改请求（如 `article-008` T2 “措辞再通俗一点”、`article-010` T3 “换建筑工地再发我一版”、“再通俗一点”“换个违法主体”）**不触发默认篇数**（`applies=False`）；仅当修改轮中**显式指定新篇数**（如“改成 15 篇”“扩写成 12 篇”“再写 11 篇”）时，才对显式新篇数执行上下限校验。
2. **防案情干扰的数量提取规则**：
   - 提取前先调用 `strip_legal_material(user_message)` 剥离书名号、正式引用标记与条款引文；
   - **限定在写稿动词子句窗口提取**：仅匹配紧随写稿/改篇动词（`写|撰写|生成|出|来|给我|帮我写|帮我生成|帮忙写|起草|整理成|改写成|写成|编成|改成|改为|扩写成|扩写为|再写|再来|多写`）之后、且不跨句末标点与案情冒号（`[^。！？\n：:]{0,16}?`）的篇数表达；
   - 支持形态：
     - 显式整数：`(-?\d+|[零〇一二两三四五六七八九十百千]+)\s*篇`（阿拉伯数字直接 `int()`，中文数字交 `chinese_to_int()` 解析；注意排除“第一篇”“第3篇”这类序数指代，避免把“修改第 2 篇”误判为要生成 2 篇！）；
     - 显式数字区间：`(\d+|[一二两三四五六七八九十百千]+)\s*(?:[-~～到至])\s*(\d+|[一二两三四五六七八九十百千]+)\s*篇`（例如“写 12-15 篇”或“写 5 到 12 篇”，以区间上界校验上限，下界 `<= 0` 判非正数；合法区间走 `use_requested` 不改写原话）；
     - 模糊/未指定（命中 `explicit_write`，但未提取到显式数字，例如“帮我写几篇……”“围绕……写普法文章”“多写几篇……”）：`requested=None`，命中 `use_default`，`target = default_article_count`。
   - **明确覆盖边界**：不猜测“几十篇/上百篇”这类无精确数值的口语约数（因 `max_article_count` 可配置，硬编码约数边界会破坏可配置性），只对精确数字、显式区间与未指定/模糊表达给出 100% 确定性决策。
3. **决策结构 `ArticleCountDecision`**：
   - `applies: bool`
   - `requested: int | None`
   - `target: int | None`
   - `action: Literal["none", "use_requested", "use_default", "clamped", "rejected"]`
   - `reason: Literal["non_positive", "exceeds_max"] | None`
   - `notice: str | None`

#### (3) `orchestrator.py` 执行时序与零回归保证

```text
user_message
  │
  ├─ 1. extract_user_entities(...)          # 保持在最前！即使本轮超限被拒，首轮披露的真实身份也已登记保护
  ├─ 2. add_turn(session, user)
  ├─ 3. decide_article_count(user_message, session.config, article_task_active=...)
  │      │
  │      ├─ action == "rejected" (若选硬拒策略):
  │      │    不调用 client.chat；保持 session.intent / article_task_active 不变；
  │      │    Turn(content=decision.notice, raw_content=None, citations=[], question_count=0)
  │      │    add_turn(session, assistant) -> return
  │      │
  │      └─ 其余情况（none / use_requested / use_default / clamped）:
  │           messages = to_openai_messages(session, system_prompt)  # system_prompt 始终为原版 v2-short（或 None）
  │           仅当 action in {"use_default", "clamped"} 时，在 messages[-1]["content"] 临时副本末尾附加简短篇数指令
  │           （session.messages 中保存的 user 原话与 system_prompt 均零修改！）
  │
  ├─ 4. client.chat(messages, temperature=temperature)
  ├─ 5. verify_output -> 关联补全兜底 -> classify_turn_intent -> 免责声明 -> anonymize_article_text / sanitize_citations
  │      （若选钳制策略且 action == "clamped" 且未触发 anonymize_blocked，在交付稿首部追加简短钳制说明）
  └─ 6. Turn 记录内部内存字段（不改 Reply/Assistant 公共协议）-> add_turn -> return
```

**临时附注模板（仅在 `use_default` / `clamped` 时附加至请求副本末尾）**：
- `target == 1`：`"\n（篇数要求：请生成 1 篇普法文章；如主题超出知识库范围请直接拒答。）"`
- `target > 1`：`f"\n（篇数要求：请生成 {target} 篇普法文章，每篇以一级标题开始、篇间用 --- 分隔，各篇场景须有实质差异；如主题超出知识库范围请直接拒答。）"`

**零回归核验**：
- 咨询路径（`reviewed.jsonl` 60 题、模糊开场、追问、明确咨询与否定写稿）：`action == "none"`，发往模型的 `messages` 与改造前 **0 字节差异**；
- 明示合法篇数的写稿请求（`article-002..010`、T075 三条彩排提示词）：`action == "use_requested"`，发往模型的 `messages` 与改造前 **0 字节差异**；
- 修改轮（`article-008` T2、`article-010` T3、省略式续改）：`action == "none"`，发往模型的 `messages` 与改造前 **0 字节差异**；
- `use_system_prompt=False` 对照模式：因附注不写进 `system` 角色，仍保证 `all(m["role"] != "system")`，不破坏既有对照实验逻辑。

#### (4) 硬拒提示文案与 SC-008 隔离
- 超上限（`exceeds_max`）：
  `f"单次最多支持生成 {max_count} 篇普法文章（默认 {default_count} 篇），当前请求为 {requested} 篇。请将篇数调整至 1–{max_count} 篇后重新发送。"`
- 非正数（`non_positive`）：
  `f"普法文章生成篇数须为 1–{max_count} 之间的正整数（默认 {default_count} 篇），当前请求为 {requested} 篇。请调整篇数后重新发送。"`
- 确认均不含 `eval/metrics.py` 中 `REFUSAL_ABILITY`（如“无法生成”“不能写”“暂不支持”）和 `REFUSAL_SCOPE`（如“超出本知识库”）短语，不含编号问句，`detect_refusal(...)["refused"]` 恒为 `False`，`extract_articles(...)` 恒为 `[]`。

#### (5) CLI 与 `eval_run` 配置透传补齐
- `src/tu_assistant/cli.py` 的 `eval_run`（L1033）补齐读取 `configs/app.yaml`（或 `--config` 指定路径）的 `session.max_questions_per_turn`、`session.default_article_count`、`session.max_article_count` 透传至 `SessionConfig`，与 `tu chat`（L1143–L1147）行为一致；
- `src/tu_assistant/eval/runner.py` 不修改 `manifest["config"]` 中被 `eval/compare.py`（L174–L225）校验的核心字段，确保与历史 run 的 `--sc016` 可比性零破坏。

#### (6) 公共接口约束
- **不修改** `contracts/system-interface.md` 定义的 `Assistant` 协议、`SessionConfig` 字段名与默认值、`Reply` 公共字段；
- 仅在 `Turn` 内部按需增加内存审计字段（如 `requested_article_count: int | None = None`、`target_article_count: int | None = None`、`article_count_action: str = "none"`），随 `close()` 销毁，不落盘、不输出日志。

---

## 4. 具体实施步骤与确定性验收方法

### 4.1 实施步骤

1. **配置校验**：在 `src/tu_assistant/chat/assistant.py` 的 `SessionConfig` 中补充 `__post_init__` 合法性校验，并在 `src/tu_assistant/chat/article_count.py` 提供 `resolve_count_limits(config: dict)` 供 `process_turn` 复用。
2. **共享前置意图与数量解析**：
   - 在 `src/tu_assistant/chat/anonymize.py` 扩展 `_RE_EXPLICIT_WRITE` 的数字字符集（兼容 `零〇百千` 与负号）并暴露只依赖用户消息与活跃态的前置意图 helper（复用既有否定/咨询/修改正则，确保 `anonymize.py` 与 `article_count.py` 单一事实来源，无逻辑分叉）；
   - 新增 `src/tu_assistant/chat/article_count.py`，实现 `ArticleCountDecision`、`decide_article_count` 与临时篇数附注构造。
3. **编排层接线**：
   - 更新 `src/tu_assistant/chat/session.py`（`Turn` 增加内存统计字段）；
   - 更新 `src/tu_assistant/chat/orchestrator.py`（按第 3.3 节时序接入 `decide_article_count`、硬拒/钳制路径与临时请求附注）；
   - 更新 `src/tu_assistant/chat/prompts.py` 注释，说明 `v2-short` 对齐约束与篇数控制的实际落点（不改 `SYSTEM_TEMPLATE` 正文）。
4. **CLI 透传补齐**：更新 `src/tu_assistant/cli.py` 的 `eval_run`，从 `cfg` 透传 `session.*` 参数至 `SessionConfig`。
5. **单元测试与回归测试**：新增 `tests/unit/test_article_count.py`，覆盖下方全部确定性矩阵，并确保 `tests/unit/test_orchestrator.py`、`test_anonymize.py`、`test_article_eval.py`、`test_runtime_isolation.py` 全部通过。
6. **学习文档更新**：按第 5 节更新 `docs/learning/`。
7. **独立只读复审闭环**：按 `.agents/skills/task-review-loop/SKILL.md` 执行最多 5 轮「实现 → 独立只读复审 → 修复/核实 → 再复审」，汇报给用户确认后再勾选 `tasks.md` 或 `git commit`。

### 4.2 确定性验收矩阵（不把不可确定的模型生成质量写进单测）

| 验收项 | 验证方式与通过条件 |
|---|---|
| **1. 配置校验** | 合法边界 `(1,1)`、`(3,10)`、`(10,10)` 及 `new_session({})` 缺省回退均通过；非法值 `default<=0`、`max<=0`、`default>max`、`bool` 伪装 `int` 均抛 `ValueError` |
| **2. 数量解析与防误伤** | ① 阿拉伯/中文数字（`1/2/3/4/10`、`一/两/二/三/四/十`、`11/十五/二十/一百`、`0/零/-1`）、显式区间（`2-3 篇` 合法、`5-12 篇`/`12-15 篇` 超限）全部精确解析；② 序数词（“修改第 2 篇”“把第三篇改通俗”）不误判为生成数量；③ 案情/法律材料干扰（“写一篇普法文章：公司克扣 15 篇稿费”→ `1`；“在公司写了 15 篇文章合法吗？”→ `none`；“不要写 15 篇普法文章，只问怎么处理”→ `none`；“写普法文章，依据《某规定》二十篇，案情涉 12 篇稿件”→ `use_default`）；④ `eval/cases/v1/reviewed.jsonl` 全量 60 题负对照 60/60 为 `none`；⑤ `article-001..010` 与 T075 三条彩排提示词逐轮决策符合预期（`001` 为 `use_default(3)`，`002–007/009-T2/010-T2` 与三条彩排为 `use_requested`，`008-T2/010-T3` 与省略续改为 `none`） |
| **3. 编排层端到端（假客户端 + 内存 KB）** | ① 超限/非正数硬拒（若选选项 1）：`client.chat` 调用 0 次，`citations=[]`，`question_count=0`，`raw_content is None`，`detect_refusal["refused"] is False`，`extract_articles == []`，原 `session.intent`/`article_task_active` 不被污染，且首轮披露的真实姓名/单位在下一轮改说“写 1 篇”时仍正确脱敏；② 若选选项 2（钳制）：断言 `target=max`，请求副本带上限附注，交付稿含钳制说明且冲突拦截时仍原子暂缓；③ `use_default` 路径：发给模型的 `system` 保持原版 `v2-short`、`session.messages` 用户原话未篡改、请求副本末尾带配置值附注、`use_system_prompt=False` 时无 `system` 角色，自定义 `(default=2, max=5)` 与 `(default=1, max=1)` 均生效；④ `use_requested` 与咨询路径：发往模型的 `messages` 与改造前逐字节一致 |
| **4. CLI 与配置透传** | 用临时 `app.yaml`（如 `default_article_count: 2, max_article_count: 4`）测试 `tu chat` 与 `tu eval run` 构造 `SessionConfig` 的逻辑，断言自定义配置正确生效且不破坏 `tu eval compare --sc016` 可比性 |
| **5. 离线固定回放回归（确定性零退化）** | ① 旧 KB `kb-20261113-093057` 下重放 `run-20261117-081504`（60 题咨询）：交付正文、意图、条款识别、出处、拒答 **0 差异**；② 新 KB `kb-20261119-045641` 下重放 `run-20261122-090101`（10 题文章）：`002–010` 请求与交付 **0 差异**，`001` 仅请求副本含默认 3 篇附注，SC-011 保持 `2/2` |
| **6. 可选本机父模型冒烟（观察项，非硬门槛）** | 启动父模型（`exp-20261116-resume500`）快速核验 2 条交互：① “写 15 篇关于拖欠工资的普法文章”毫秒级触发上限提示、无模型请求；② `article-001` 原句在默认 3 篇附注下的真实输出（仅作现象记录，不以父模型能否独立出 3 篇为验收门槛） |
| **7. 全量测试、静态检查与只读核查** | `uv run pytest` 全绿（既有 282 passed / 6 xfailed + T056 新增单测）；`uv run ruff check src tests` 全绿；`git status` / `git diff` 确认 `specs/`、`eval/cases/v1/`、`artifacts/` 零改动 |

---

## 5. 学习文档更新点

- **新增章节起步**：创建 `docs/learning/07-serving-demo.md`（按 `docs/learning/README.md` 规划，第 7 章负责“模型服务、对话编排、演示界面”，完整章节由 T073 整理，先按实现进度写入第一节）：
  - **`[L7.1]` 对话编排层的确定性护栏：文章数量控制如何与微调模型协作**
    - 为什么不修改 `v2-short` system prompt（回顾 L5.4 训练/推理分布对齐，区分全局 system 模板与单轮请求副本附注）；
    - 确定性逻辑（解析数字、校验上下限、配置透传、隔离案情干扰）与模型能力边界（多篇实质差异化、未训文章模型的多篇误拒）的划分；
    - “入口拦截 + 单次调用” vs “编排层按篇循环”的工程取舍（延迟、token、训练分布与评测原稿语义）。
- **目录与术语同步**：
  - 更新 `docs/learning/README.md` 中第 7 章状态为 `进行中（已含 L7.1 编排层文章数量控制；完整章节由 T073 整理）`；
  - 在 `docs/learning/00-glossary.md` 按需补充“确定性护栏（Guardrail）”等术语并链接至 `[L7.1]`。

---

## 6. 待用户拍板的决策清单

请逐项确认以下 4 项（如均同意推荐项，可直接回复“按推荐方案实施”）：

1. **多篇生成编排方式**
   - **选项 A（推荐）**：入口拦截/钳制 + 单次调用轻量指令（仅在未指定篇数或钳制时向当轮请求副本追加篇数附注，不改 `v2-short`、不扰动单篇/已明示篇数/咨询路径，兼容 T052/T057 训练分布与全部既有评测单测）。
   - **选项 B**：入口拦截/钳制 + 编排层按篇循环调用（需改造 `raw_content`/`verify_output`/`anonymize` 拼接逻辑与 6 处既有测试，且与当前父模型能力和训练分布冲突，M1 Pro 延迟高）。

2. **超出单次上限（`requested > max_article_count`）的处理策略**
   - **选项 1（推荐）**：**硬拒并提示**——不调用模型，毫秒级返回上限与默认篇数说明，请用户调整篇数后重试（不浪费本机算力、避免 4096 token 截断及“提示按上限处理但父模型未产出对应篇数”的矛盾；文案与 SC-008 域外拒答隔离）。
   - **选项 2**：**钳制到上限并执行**——自动将目标篇数降为 `max_article_count` 后继续调用模型，并在交付稿首部追加“已按单次上限处理”的说明。

3. **POC 默认篇数配置（`configs/app.yaml`）与路线 A 单篇演示的协调**
   - **选项 1（推荐）**：`configs/app.yaml` **保持 `default_article_count: 3`、`max_article_count: 10`**（严格对齐 spec FR-028、T056 任务描述与 `eval/cases/v1/articles.jsonl` `article-001` 的 rubric；路线 A 三条彩排提示词均明示“一篇”，天然走 `use_requested(1)` 互不冲突；同时修复 `tu eval run` 从配置读取 `session.*` 透传）。
   - **选项 2**：POC 阶段将 `configs/app.yaml` 改为 `default_article_count: 1`、`max_article_count: 10`（使未指定篇数时也默认引导单篇；注意此项会导致 `tu eval run` 若读配置时 `article-001` 的附注变为 1 篇，与该题 rubric“默认 3 篇”不一致）。

4. **T059（7B 演示模型训练与再训）的核销时机**
   - **选项 1（推荐）**：T059 训练与再训（`exp-20261116-resume500`、E003 B1、SC-016 PASS）已实质完成，且 V5 重复评测已拆分至 T064；本次 T056 确认或验收时**一并勾选核销 T059**（并在 T059 下注明 V5 重复评测追踪见 T064），让 Phase 4 / US2 完整闭环。
   - **选项 2**：保持 T059 未勾选，待 Phase 5 的 T064（重复评测 2 次验证 SC-015）完成后再勾选 T059。


---

## 7. 用户拍板结果（2026-11-22）

1. **多篇生成编排方式**：选 **选项 A**（入口拦截 + 单次调用轻量指令；仅 `use_default` 时向当轮临时请求副本附注篇数，不改 `v2-short` system prompt）。
2. **超出单次上限处理策略**：选 **选项 1**（硬拒并提示，不调用模型，文案与 SC-008 隔离）。
3. **`configs/app.yaml` 默认篇数**：选 **选项 1**（保持 `default_article_count: 3`、`max_article_count: 10`，并补齐 `tu eval run` 透传 `session.*`）。
4. **T059 核销时机**：选 **选项 2**（待 Phase 5 的 T064 跑完后再勾，本次不勾 T059）。

---

## 8. 独立只读复审闭环记录（2026-11-22）

审查方式：单节点高思考只读审查员（`reviewer` / `gemini-4-neon-high`），隔离上下文、全程只读未改动任何文件、未读取 `inputs/`；共 **3 轮**，最终 **一致通过**。

| 轮次 | 结论 | 发现与处置 |
|---|---|---|
| **Round 1** | 需修改 | 发现 4 项阻断项（B1 带空格序数词穿透 `第 2 篇`、B2 单字 `来/出` 构词与复合否定写稿绕过、B3 非法中文数字如 `三零/十十/零零` 误译、B4 活跃文章上下文省略“文章”与单轮 `扩写为 N 篇` 漏拦）及 2 项非阻断建议（清理 `_CN_ALL_DIGITS`、补强非正数/状态不污染/`tu chat` 透传与 60 题 59/60 逐字一致断言）→ **全部认同并修复**，新增回归用例，`pytest` 377 passed / 6 xfailed，`ruff` 全绿。 |
| **Round 2** | 需修改 | 发现 3 项阻断项（R2-B1 `_RE_EXPLICIT_WRITE` 禁止跨逗号导致句内带逗号写稿漏判、R2-B2 `几十篇/数十篇` 被误译为 `10`、R2-B3 序数区间 `第 2-12 篇` 穿透）及 1 项非阻断建议（`_RE_PAST_TENSE_GAP` 补 `发了/发过/寄了/寄过/送了/送过`）→ **全部认同并修复**（恢复句内逗号并将 `_has_non_negated_explicit_write` 改为逐位置推进 `pos = m.start() + 1`、增加 `_NUM_LEFT_GUARD` 与 `_RE_ORDINAL_PREFIX`），补齐 11 条回归用例，`pytest` 388 passed / 6 xfailed，`ruff` 全绿。 |
| **Round 3** | **通过** | 阻断项 **0**。确认 R1/R2 全部缺陷彻底关闭、无回归、合规边界零违背；保留 1 条微一致性备注（`_NUM_LEFT_GUARD` 含 `上近约` 导致 `写约15篇` 与 `写约 15 篇` 分别走 `use_default` 与 `rejected`，均不放行超限，留档备查、不阻塞验收）。 |

### 最终验收证据
- `uv run pytest`：**388 passed, 6 xfailed**（其中 `tests/unit/test_article_count.py` **106 passed, 0 skipped**，包含 60 题咨询离线回放零扰动与 10 题文章离线回放 SC-011 2/2）。
- `uv run ruff check src tests`：**All checks passed!**
- `git status --short` 确认 `specs/`、`eval/cases/v1/`、`configs/app.yaml`、`artifacts/` 零改动；`tasks.md` 中 T056 与 T059 均尚未勾选。
