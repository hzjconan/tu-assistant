# T070 执行单 · 准备 POC 现场演示场景脚本（`docs/demo-scenarios.md`）

- **状态**：已拍板定稿（待实施）— 用户确认按全部推荐项实施（`1A 2A 3A`：迁入 `docs/demo-scenarios.md` 并删除根目录 `poc_demo.md`；本轮单项推进 `T070`；严格忠于冻结模型与 T075 路线 A 实测事实，单设规格对照与边界说明表）
- **对应任务**：`specs/001-legal-clause-assistant/tasks.md` Phase 7 — **`T070`**（单项推进，不合并 `T071`–`T074`）
- **Git 基线**：`ca3a4ed`（`main`，工作区干净）
- **活跃产物基线**：
  - 冻结 7B 演示模型：`exp-20261116-resume500`（`adapters/adapters.safetensors` SHA-256 前缀 `b62a7d0e86f4`，基座 `mlx-community/Qwen2.5-7B-Instruct-4bit`）
  - 活跃知识库：`artifacts/kb/kb-20261119-045641.sqlite`（24 篇法规、3,809 条记录、67 条已确认关联：`liability_for` 26 + `references` 41）
  - 基准评测证据：`run-20261123-051432` / `run-20261123-053832`（T064 全 98 题 SC-015 `0.0 pp` PASS）、`run-20261117-022645` vs `run-20261117-081504`（SC-016 PASS）、`run-20261117-124545`（E003 探针集）、`artifacts/logs/t075/route-a/`（路线 A 三条预审短文）
  - 自动化基线：`uv run --offline --no-sync pytest` 462 passed / 6 xfailed，`ruff check src tests` 全绿，T075 `output.sha256` 25/25 OK
- **不可逾越的红线**：
  1. **严禁读取 `inputs/` 目录下任何文件**（包括工具读取、grep 或任何输出其内容的脚本）；
  2. **运行时零外连 / 数据不出域**：演示启动与操作指引必须严守 `127.0.0.1`、无外部 API 调用、全部演示案情使用虚构人物与单位；
  3. **历史产物只读保护**：严禁改动 `artifacts/` 下任何既有 KB、模型权重、评测 run 及 `artifacts/logs/t075/01/output.sha256` 清单覆盖的 25 项文件；
  4. **验收门禁前不落账**：完成独立复审闭环并获用户明确确认前，不得勾选 `tasks.md`，不得执行 `git commit` 或 `git push`。

---

## 上篇：面向用户决策

### 1. 推荐任务编号与选择理由

**推荐本轮优先推进单项 `T070`（编写并定稿 `docs/demo-scenarios.md`）**，Phase 7 剩余 5 项任务建议按 **`T070 → T071 → T073 → T072 + T074`** 顺序收尾。

| 候选任务 | 核心内容 | 依赖关系与排序理由 |
|---|---|---|
| **`T070`（本次推荐）** | 准备演示场景脚本 `docs/demo-scenarios.md` | **Phase 7 唯一上游阻塞点**：① `T071` 的 V6 明确要求“在浏览器中按准备好的演示场景操作”，必须先锁版剧本；② 仓库根目录已在 `fbea9d1` 提交了 `poc_demo.md`（277 行），与 `tasks.md` 规范路径 `docs/demo-scenarios.md` 存在**单源真相冲突**，且经只读核查发现 5 处具体瑕疵/缺口，亟需一次性规范化收口。 |
| `T071` | 运行 `quickstart.md` V1–V7 验证并记录结果 | 强依赖 `T070` 定稿作为 V6 实操清单；且涉及本机真机启动 7B 服务/UI 跑测与 V2 `--artifacts` 隔离（防 `kb.version: null` 被裸库劫持），与纯文档剧本收口拆开执行更稳妥、避免返工。 |
| `T073` | 撰写 `docs/learning/07-serving-demo.md` + 术语表 | 已有 `[L7.1]`–`[L7.3]`；待 `T070`/`T071` 完成后可顺带串联定稿演示脚本、V6 实测体验与“训练/演示互斥原因”，无需占位符。 |
| `T072` | 更新 `README.md` | 已在 `3b944c9` 更新了一版；最终文档导航需一次性纳入 `docs/demo-scenarios.md`、V1–V7 验证记录与学习文档第 7/8 章，宜放后段收口避免反复改索引。 |
| `T074` | 撰写 `docs/learning/08-lessons-and-next.md` | POC 最终总复盘章（踩坑汇总、V1–V7 结论、T078 已知缺陷登记、POC 说明/没说明什么、正式阶段 R12），必须放最后。 |

---

### 2. 待用户拍板的决策清单

请审阅以下 3 项取舍并直接回复选择（例如 `1A 2A 3A`）：

1. **决策 1：根目录现有 `poc_demo.md` 的处置方式（消除双源漂移）**
   - **1A（推荐）**：以 `poc_demo.md` 为基础升级修正后迁入规范路径 `docs/demo-scenarios.md`，并**删除根目录 `poc_demo.md`**（后续 `T072` 在 `README.md` 显著位置链接 `docs/demo-scenarios.md`）。
     - *理由*：严格对齐 `tasks.md` T070 交付路径，彻底消除两份演示脚本日后漂移；经 `git grep` 确认当前仓库无任何文件引用 `poc_demo.md`。
   - **1B**：将完整正文迁入 `docs/demo-scenarios.md`，同时把根目录 `poc_demo.md` 缩减为不超过 10 行的跳转说明页指向 `docs/demo-scenarios.md`。
     - *理由*：兼容外部快捷记忆或既有习惯，且正文仍维持单源真相。
   - **1C**：新建 `docs/demo-scenarios.md` 并保持根目录 `poc_demo.md` 原样不动。
     - *理由*：不删除历史提交文件，但会遗留双份脚本维护漂移（不推荐）。

2. **决策 2：本轮范围粒度（单项 `T070` vs 合并 `T070 + T071`）**
   - **2A（推荐）**：本轮**仅实施单项 `T070`**（完成 `docs/demo-scenarios.md` 编撰与确定性只读脚本核查），定稿验收后再独立推进 `T071`（V1–V7 全量验证与真机 V6 跑测记录）。
     - *理由*：先让用户审定对外演示路线、边界措辞与场景选编，避免真机跑完 V6 再因剧本微调返工；且单项任务边界纯粹，轻量模型实施与独立复审闭环最干净。
   - **2B**：合并 `T070 + T071`，同一执行单内完成剧本落盘并真机跑完 V1–V7 验证与记录。
     - *理由*：少一轮任务交接，但需一次性跨越文档定稿、V2 隔离验证、V4/V5 复核与 7B 实机 UI 联调，单轮变更与复审跨度较大。

3. **决策 3：对 `tasks.md` T070 两处能力落差（“模糊开场→追问”与“生成 3 篇普法文章”）的剧本呈现方式**
   - **3A（推荐）**：**严格忠于冻结模型 `exp-20261116-resume500` 与 T075 路线 A 实测事实**——黄金主线展示已 100% 实测稳定的路径，文末单设“规格对照与 POC 边界说明表”诚实交代落差：
     - 多轮演示主线使用 `intent-010`（模糊开场 → 补充案情与 FR-019 系统关联补全 → 中途意图切换写普法文章），并如实标注冻结模型在模糊开场第 1 轮倾向直接给出初步依据而非主动反问（见 `docs/learning/06-evaluation.md [L6.9]`）；
     - 普法文章主线严格遵循 T075 路线 A，演练“给定案情与已核准法条的单篇预审生成（合同留存）→ 对话通俗化修改 → 点击「保存当前回复为 Markdown」核对导出”，叠加 `article-010` 多轮身份自动脱敏（FR-030）与“15 篇超上限毫秒级硬拒”（FR-028，展示默认 3 篇 / 上限 10 篇确定性护栏）；不在主线承诺开放“一次生成 3 篇”。
   - **3B**：在 3A 基础上，额外在备选/边界区增设 `article-001`（开放“写 3 篇拖欠工资普法文章”）作为“能力边界现场对照”示例，展示 T056 默认 3 篇附注生效后模型虽能产出 3 篇故事但存在标题格式瑕疵，用于向项目方直观解释为何 POC 采取路线 A、正式阶段推进数据多样化与检索评估。

---

## 下篇：面向实施方的零歧义施工图

> **实施前提**：须待用户对上篇 3 项决策拍板并由设计节点（或主会话）将状态更新为 `已拍板定稿（待实施）`、折叠落选分支后，方可动手施工。

### 3. 现状锚点与只读实测陷阱预警

#### 3.1 复用与对齐的代码/文档锚点

| 锚点文件与行号 | 精确职责与事实 |
|---|---|
| `poc_demo.md:1-277` | 2026-11-24 已提交的现场演示初稿（含启动命令、5 类提示词、边界说明与 4 文件 79 MB 换机迁移包），作为本次迁入 `docs/demo-scenarios.md` 的素材底稿 |
| `src/tu_assistant/ui/app.py:340-392` | Gradio 6 演示界面精确文案：标题 `工会法律条款智能助手（POC 本地演示）`；按钮：`发送`、`新会话`、`保存当前回复为 Markdown`；状态提示：`已完成第 N 轮回复。点击「保存当前回复为 Markdown」可下载本轮回复。`、`已开启新会话（上一会话上下文已从内存释放）。`；导出文件名：`tu-reply-<session_id>-turn<N>.md`（`app.py:166`） |
| `src/tu_assistant/cli.py:1376-1458` | `tu ui` 真实参数：`--config`、`--artifacts`、`--kb-version`、`--host`（仅允许 `127.0.0.1`）、`--port`（默认 `7860`）、`--temperature`（默认 `0.7`）、`--inbrowser/--no-inbrowser` |
| `src/tu_assistant/chat/article_count.py:314` | 实测 `decide_article_count("请帮我写 15 篇关于劳动合同签订的普法文章。", None)` 精准返回 `action='rejected'`，精确提示文案：`单次最多支持生成 10 篇普法文章（默认 3 篇），当前请求为 15 篇。请将篇数调整至 1–10 篇后重新发送。` |
| `src/tu_assistant/chat/anonymize.py` | 实测 `extract_user_entities` 对 `poc_demo.md` 5.1 方式 A（`陈实` / `启明电子厂`）和方式 B（`王明` / `晨光制造公司`）均 100% 精准抽取；`run-20261123-051432` 中 `article-010` 第 2 轮触发 `person_replacements=2`（`陈实` → `甲某`），第 3 轮续写自动为 `乙某`，`SC-011 = 2/2` |
| `docs/experiments/T075-article-training.md:19-42` | T075 路线 A 约定与三条预审彩排提示词及原稿审阅注意事项（含引文行末解释分段、合同稿删除多余投诉渠道、身份证稿恢复案情时间点） |
| `docs/experiments/T064-eval-repeatability.md:49-72` | 冻结 7B 模型全 98 题最新官方口径（SC-015 `0.0 pp` PASS、SC-016 `1/60→17/60` & `9/60` & `0/30→21/30`、SC-007 校验前 `0.405` → 校验后 `0.669`、已定位 `0.589 → 0.973`） |
| `specs/001-legal-clause-assistant/tasks.md:70,224` | T078 约束（演示脚本**必须避开《上海市工伤保险实施办法》款号**）与 T070 原文要求 |
| `specs/001-legal-clause-assistant/quickstart.md:73-81` | V6 验收口径（下游 T071 将按 `docs/demo-scenarios.md` 的主线逐项实操验证） |

#### 3.2 摸底实测发现的 5 处陷阱与必须采用的写法

1. **陷阱 1（条款口径 C 缺款号 `incomplete`）**：
   - *踩坑表现*：`poc_demo.md:115` 写 `〔《中华人民共和国社会保险法》（2018-12-29）第五十八条〕`，该条在 `kb-20261119-045641.sqlite` 含 3 款（`第1款`–`第3款`）；用 `verify_output` 校验纯编号块时会返回 `verdict='incomplete'`。
   - *必须采用的写法*：在 `docs/demo-scenarios.md` 中将 `mv-002` 该处依据写为 `〔《中华人民共和国社会保险法》（2018-12-29）第五十八条第1款〕`，并括号说明“模型原稿引用整条但逐字写对第 1 款原文，由出处校验层按 T077 口径 C 唯一定位至第 1 款，`ok`”，确保全剧本所有 `〔...〕` 引用块在 `kb-20261119-045641.sqlite` 中 **0 `not_found`、0 `incomplete`**。
2. **陷阱 2（`poc_demo.md` 章节编号重复）**：
   - *踩坑表现*：`poc_demo.md:228` 与 `poc_demo.md:236` 均使用 `## 六、`，目录层级混乱。
   - *必须采用的写法*：统一采用清晰的阿拉伯数字或中文序号层级，全文严禁出现重复的一级/二级章节编号，并用确定性脚本检查。
3. **陷阱 3（对模糊开场反问与 3 篇普法文章做过度承诺）**：
   - *踩坑表现*：实测 `run-20261123-051432` 中 10 道 `intent` 用例第 1 轮 `question_count` 全为 `0`；且路线 A 下父模型未合入文章续训权重，开放多篇（如 `article-002`/`003`/`004`）会触发误拒。若剧本按 `tasks.md` 字面承诺“发模糊句模型必定反问”或“稳定生成 3 篇高质量普法文章”，现场演示必然翻车。
   - *必须采用的写法*：所有场景的“预期表现”必须严格与 `run-20261123-051432` / `run-20261117-124545` / `artifacts/logs/t075/route-a/` 实测结果一致；在黄金主线与边界对照表中明示上述两项真实边界。
4. **陷阱 4（相对路径因目录迁移断链）**：
   - *踩坑表现*：`poc_demo.md` 位于仓库根目录，内部引用路径（如 `docs/experiments/T075-article-training.md`、`artifacts/logs/t075/route-a/reply-1.md`）若原样复制到 `docs/demo-scenarios.md`，全部相对路径会断链。
   - *必须采用的写法*：迁入 `docs/demo-scenarios.md` 后，指向 `docs/` 内文档用 `./experiments/...`、`./learning/...`，指向仓库根目录下的文件用 `../artifacts/...`、`../specs/...`、`../configs/...`，并注意 `artifacts/` 已被 `.gitignore` 忽略（在说明中标注“仅本机产物目录存在”，不要把忽略产物当成跨机必然存在的 Git 链接），最后用脚本检查全部受 Git 管理文件的相对链接 0 断链。
5. **陷阱 5（触碰 T078 缺陷或 `inputs/` 原文）**：
   - *踩坑表现*：自行编造新法条示范时误引《上海市工伤保险实施办法》款号，或为校验引文去读取 `inputs/`。
   - *必须采用的写法*：全剧本**严禁出现《上海市工伤保险实施办法》任何条/款/项引用**；仅复用已验证的虚构案情与 `kb-20261119-045641.sqlite` 只读校验结果，全程不触碰 `inputs/`。

---

### 4. 改动范围表与明确不做清单（Non-Goals）

#### 4.1 文件改动表

| 文件路径 | 操作 | 精确职责 |
|---|---|---|
| `docs/demo-scenarios.md` | **新增** | 本任务核心交付物：POC 现场演示主线剧本（兼作 `T071` V6 实操验收脚本）、5 大能力分类备选提示词库、UI/CLI 操作与 Markdown 导出核对步骤、规格对照与能力边界说明、换机迁移打包指南 |
| `poc_demo.md` | **删除（1A）** | 迁入 `docs/demo-scenarios.md` 后删除根目录旧草稿，彻底消除双源漂移 |

#### 4.2 明确不做清单（Non-Goals）

实施方本次**严禁**执行以下操作：
- 严禁修改 `src/`、`tests/`、`configs/`、`eval/`、`scripts/` 下任何代码、测试或配置文件；
- 严禁修改 `README.md`（归 `T072`）；
- 严禁修改 `docs/learning/` 下任何学习文档或 `00-glossary.md`（归 `T073` / `T074`）；
- 严禁修改 `specs/001-legal-clause-assistant/tasks.md` 或 `quickstart.md`（未获用户确认不得勾选任务）；
- 严禁运行 `tu serve model`、`tu ui` 或 `tu kb import`（实机验证与 V1–V7 跑测归 `T071`，严禁向 `artifacts/` 写入任何新文件）；
- 严禁读取 `inputs/` 目录下任何文件。

---

### 5. 文档结构与事实口径契约（`docs/demo-scenarios.md`）

`docs/demo-scenarios.md` 必须严格采用以下 **顶部元信息 + `## 1.` 至 `## 9.` 共 9 个主章节**结构（二级标题编号 `1.`–`9.` 唯一、连续、无重复）：

- **顶部元信息与合规声明**（一级标题 `# ` 下方导语块，不占 `##` 编号）
   - 明确写明：冻结模型 `exp-20261116-resume500`、活跃知识库 `kb-20261119-045641`（24 篇法规 / 3,809 条记录 / 67 条已确认关联）、推荐启动温度 `--temperature 0.0`（与 T064 SC-015 `0.0 pp` 评测基线逐字一致；路线 A 普法短文如需措辞微调可用默认 `0.7`）。
   - 显式声明三条纪律：
     1. 全部案情均为**虚构案例与虚构人名/单位**，不涉及任何真实当事人隐私；
     2. 严守数据不出域（仅本机 `127.0.0.1` 运行，零外部 API 调用）；
     3. 全剧本按 `T078` 约定**避开《上海市工伤保险实施办法》任何款号**。

1. **`## 1. 启动准备与界面操作速查（双终端）`**
   - 终端 1：`uv run tu serve model --exp exp-20261116-resume500`（就绪标志：`Starting httpd at 127.0.0.1 on port 8080...`）。
   - 终端 2（Gradio 网页，推荐）：`uv run tu ui --temperature 0.0 --inbrowser`（以及默认温度备选 `uv run tu ui --inbrowser`）；另注明备选 CLI `uv run tu chat`（`/new`、`/save <路径.md>`、`/quit`）。
   - 精确对齐 `src/tu_assistant/ui/app.py` 界面控件与操作规范：
     - 切换场景前点击 **`新会话`**（状态栏显示 `已开启新会话（上一会话上下文已从内存释放）。`）；
     - 粘贴提示词后按 Enter 或点击 **`发送`**；
     - 回复完成后状态栏显示 `已完成第 N 轮回复。点击「保存当前回复为 Markdown」可下载本轮回复。`，点击 **`保存当前回复为 Markdown`** 下载 `tu-reply-<session_id>-turn<N>.md`，打开核对内容与界面一致；
     - 若模型服务未启动，界面会提示中文连接指引，启动终端 1 后直接重发即可；演示结束在两终端按 `Ctrl+C` 停止。

2. **`## 2. 10 分钟现场黄金主线（兼作 quickstart V6 验收清单）`**
   - 用一张紧凑总览表 + 6 步串联操作（每步标明“动作 → 对应下方编号 → 预计耗时 → 核心看点 → 验收检查点”），确保 10 分钟内完整覆盖 `tasks.md` T070 与 `quickstart.md` V6 全部维度：
     1. **Step 1 · 精准条款咨询 + 上海地方条例**（选 3.1 `cand-001` 竞业限制 + 3.9 `p1-0003`《上海市职工代表大会条例》第六条）：展示国家法与基座原本零命中的上海地方规章学习成效（SC-016）。
     2. **Step 2 · 多违法行为跨法综合认定**（选 4.1 `mv-002` 连续 4 月欠薪 + 入职超一年未办社保未缴社保）：展示跨两部法律、6 处引文经校验层 100% 原文准确兜底。
     3. **Step 3 · 模糊开场 → 多轮深化 → 确定性关联补全 → 中途切换写文章**（选 5.1 `intent-010` 挪用工会经费 3 轮）：展示多轮上下文、`kb-20261119-045641` 自动追加 `**相关条款（系统补充）**`（《工会法》第五十五条，FR-019）、第 3 轮意图切换（FR-013）。
     4. **Step 4 · 限定普法文章生成 → 对话修改 → 导出 Markdown 核对**（选 6.1 合同留存单篇 + 第 2 轮“语言再通俗一些，适合贴在工厂车间宣传栏” + 点击 **`保存当前回复为 Markdown`** 打开 `.md` 核对）：遵循 T075 路线 A 完成 US2 端到端闭环与 FR-032 导出验收。
     5. **Step 5 · 确定性安全与业务护栏三连击**（选 7.1 方式 A `article-010` 多轮身份自动脱敏 `陈实→甲某` + 7.2 写 15 篇毫秒级硬拒 + 7.4 `refusal-001` 伪造个税法条被校验层拦截为 `〔此处引用未通过校验，已删除〕`）：展示不依赖模型概率的硬底线。
     6. **Step 6 · 功能/域外明确拒答**（选 7.3 `refusal-003` 起草劳动仲裁申请书拒答 + 域外问题拒答）：展示 FR-014 / FR-022 边界守护。
   - **硬约束**：黄金主线每一步必须指明“换场景前先点 `新会话`”，并在 Step 4 后显式写出 Markdown 核对要点（UTF-8 无乱码、含引用块与三段小节、正文与浏览器展示一致）。

3. **`## 3. 场景库一：法律条款精准咨询（国家法律 + 上海地方条例 + 法定例外）`**
   - 承接 `poc_demo.md` 1.1–1.14 全部 14 题（全部已实测 `recall=1.0, precision=1.0, ok=1`），保留每题的用例编号（`cand-*` / `p*-*`）、原样提示词与经 `kb-20261119-045641` 校验通过的实测依据。
   - 明确区分：`3.1–3.8` 来自 `eval/cases/v1`（`run-20261123-051432`）；`3.9–3.14` 来自 E003 探针/留出集（`run-20261117-124545`）。

4. **`## 4. 场景库二：多违法行为综合分析与长案情结构化咨询`**
   - 承接 `poc_demo.md` 2.1（`mv-002`，强烈推荐）与 2.2（`p3-0242`）。
   - **必改修正点**：将 `mv-002` 中《社会保险法》第五十八条标注为 `〔《中华人民共和国社会保险法》（2018-12-29）第五十八条第1款〕`，并括号注明“模型原稿引用整条但逐字写对第 1 款原文，由出处校验层按 T077 口径 C 唯一定位至第 1 款，`ok`”。

5. **`## 5. 场景库三：多轮对话、关联条款自动补全与中途意图切换`**
   - 承接 `poc_demo.md` 3.1（`intent-010`，强烈推荐）、3.2（`intent-002`）、3.3（`intent-001`）。
   - 保留对当前冻结模型模糊开场行为的诚实注记：在 `run-20261123-051432` 中，模糊开场第 1 轮模型倾向直接给出初步依据（而非主动反问），第 2 轮补充案情后收敛至目标法条；其中 `intent-001` 第 1 轮可顺带观察一次 `〔此处引用未通过校验，已删除〕` 拦截。

6. **`## 6. 场景库四：限定普法文章生成、对话修改与 Markdown 导出（T075 路线 A）`**
   - 承接 `poc_demo.md` 4.1（合同留存，附第 2 轮通俗化修改 + 导出 `.md` 核对步骤）、4.2（三年竞业限制核对）、4.3（入职扣身份证）。
   - 完整补充来自 `docs/experiments/T075-article-training.md` 的**现场预审提示**：① 原稿可能把模型解释接在 `>` 引文行末，正式投屏成稿前可分段；② 合同留存稿可能附带额外投诉渠道，身份证稿可能微调时间表述，均以项目方预审稿为准，实时生成措辞（尤其 `temperature=0.7` 时）会有合理波动。

7. **`## 7. 场景库五：确定性护栏演示（脱敏、篇数硬拒、拒答与幻觉拦截）`**
   - 承接 `poc_demo.md` 5.1（方式 A `article-010` 多轮真实脱敏 `陈实→甲某` / `乙某`，方式 B 单轮路线 A + `王明`/`晨光制造公司` 脱敏）、5.2（15 篇超上限毫秒级硬拒，**必须写入源码实测精确返回文案**：`单次最多支持生成 10 篇普法文章（默认 3 篇），当前请求为 15 篇。请将篇数调整至 1–10 篇后重新发送。`）、5.3（功能边界 `refusal-003`、域外文章 `article-007`、域外咨询离婚/交通拒答）、5.4（`refusal-001` 个税与 `refusal-002` 民间借贷触发 `not_found` → `〔此处引用未通过校验，已删除〕`）。

8. **`## 8. 现场汇报边界与规格对照表`**
   - 汇总 4 条核心边界（与 `docs/experiments/T064-eval-repeatability.md`、`T075-article-training.md`、`poc-training-summary.md` 严格同源，不得编造或改写任何数字）：
     1. **POC 定位与 SC-016 / SC-015 数据**：60 题条级 `1/60 → 17/60`（p=4.45e-05）、款级 `9/60 = 15.0%`、基座未知文件子集 `0/30 → 21/30`（p=3.58e-09）；全 98 题两轮冷启动 SC-015 波动 `0.0 pp`；不把挑选的演示题当成全库整体召回率（全 98 题 SC-002 `0.121`、SC-003 `0.188`）。
     2. **与 `tasks.md` T070 / `quickstart.md` V6 的两项口径对齐说明**：明确表格列出“模糊开场→追问”和“生成 3 篇普法文章”的规格原意、POC 冻结模型实测现状与现场演示策略（路线 A + 确定性护栏）。
     3. **数据不出域与内存会话释放**：`127.0.0.1`、零遥测/零外链字体、点「新会话」或退出进程立即释放（关闭/刷新标签页后最迟约 1 小时由框架回收）。
     4. **T078 已知缺陷避坑**：全剧本 0 处引用《上海市工伤保险实施办法》款号（该文件括号条旨款号顺延 +1 已登记为 Post-POC 任务 T078）。

9. **`## 9. 换机器演示与最小产物迁移指南`**
   - 承接 `poc_demo.md` 末尾（修正其重复章节号 `## 六、` 为 `## 9.`）的 4 文件最小打包表（约 79 MB：`manifest.json`、`adapters.safetensors`、`adapter_config.json`、`kb-20261119-045641.sqlite`）、`tar` 打包/解压命令与新机镜像下载环境变量（`HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1`）及断网离线说明。

---

### 6. 原子化施工步骤（自底向上，每步可自检）

- **Step 1：基线核验与锚点确认**
  - 动作：只读核对 `git status -sb`、`docs/demo-scenarios.md` 尚不存在、换机清单 4 个本机产物文件均存在。
  - 最小验证命令：
    ```bash
    git status -sb && ls -lh \
      artifacts/train/exp-20261116-resume500/manifest.json \
      artifacts/train/exp-20261116-resume500/adapters/adapters.safetensors \
      artifacts/train/exp-20261116-resume500/adapters/adapter_config.json \
      artifacts/kb/kb-20261119-045641.sqlite
    ```

- **Step 2：编写 `docs/demo-scenarios.md`**
  - 动作：严格按第 5 节 10 部分结构与事实口径契约写入 `docs/demo-scenarios.md`，完整保留 `poc_demo.md` 的有效提示词，修正《社会保险法》第五十八条第 1 款标注、章节编号重复、相对路径前缀、精确 `article_count` 硬拒文案、UI 控件精准名称、10 分钟黄金主线、T078 避坑声明及规格对照表。
  - 最小验证命令：检查文件非空且二级标题编号 `## 1.` 至 `## 9.` 连续无重复：
    ```bash
    grep -n '^## ' docs/demo-scenarios.md
    ```

- **Step 3：按已拍板决策 1A 删除根目录 `poc_demo.md`**
  - 动作：删除根目录 `poc_demo.md`（`rm poc_demo.md`）。
  - 最小验证命令：`git status -sb` 确认仅有预期文件变更。

- **Step 4：运行确定性脚本全面核查 `docs/demo-scenarios.md`**
  - 动作：执行第 7 节的确定性只读 Python 核查脚本，验证全部引用块、T078 零触碰、相对链接、标题唯一性、UI 文案对齐、脱敏实体抽取与硬拒文案逐字一致。
  - 最小验证命令：见第 7 节核查命令（退出码必须为 `0`，全部断言打印 `OK`）。

- **Step 5：全量回归与只读基线门禁检查**
  - 动作：执行第 7 节全量门禁命令清单（`pytest`、`ruff`、T075 `output.sha256`、`git status`），确认零误改业务代码与历史产物，然后进入 `task-review-loop` 独立只读复审闭环。

---

### 7. 确定性核查矩阵与验收门禁

本任务为纯演示剧本类文档任务，**不新增/修改 `tests/` 单元测试**，而以**确定性只读校验脚本 + 既有全量回归门禁**把所有事实口径、引用有效性、防呆约束锁死：

#### 7.1 确定性内容与事实口径核查脚本（必须 100% 通过）

在仓库根目录直接执行以下只读脚本（严禁触碰 `inputs/`、严禁写入任何文件）：

```bash
uv run --offline --no-sync python - << 'EOF'
import re
from pathlib import Path
from tu_assistant.chat.anonymize import AnonymizeState, extract_user_entities
from tu_assistant.chat.article_count import decide_article_count
from tu_assistant.citation.verify import verify_output
from tu_assistant.kb.store import open_kb

doc = Path("docs/demo-scenarios.md")
assert doc.is_file(), "docs/demo-scenarios.md missing"
text = doc.read_text(encoding="utf-8")

# 1. T078 禁区检查：所有演示主线与场景库（## 2. 至 ## 7.）及全部 〔...〕 引用块中 0 处引用《上海市工伤保险实施办法》
m_s2 = re.search(r"^##\s+2\.", text, flags=re.M)
m_s8 = re.search(r"^##\s+8\.", text, flags=re.M)
assert m_s2 and m_s8 and m_s2.start() < m_s8.start(), "Missing ## 2. or ## 8. section boundary"
scenario_body = text[m_s2.start():m_s8.start()]
assert "上海市工伤保险实施办法" not in scenario_body, "Forbidden T078 statute found in demo scenarios!"
print("[OK] T078 statute excluded from all demo scenarios (## 2. - ## 7.)")

# 2. 二级标题检查：连续 1..9 且无重复编号
h2s = re.findall(r"^##\s+(.+)$", text, flags=re.M)
nums = [re.match(r"^(\d+)\.", h).group(1) for h in h2s if re.match(r"^(\d+)\.", h)]
assert nums == [str(i) for i in range(1, 10)], f"Unexpected H2 numbering: {h2s}"
assert len(h2s) == len(set(h2s)), f"Duplicate H2 headings: {h2s}"
print(f"[OK] H2 headings strictly numbered 1..9 ({len(h2s)} sections)")

# 3. 全部 〔...〕 引用块在活跃 KB kb-20261119-045641 中 0 not_found & 0 incomplete，且 0 处指向 T078 法规
conn = open_kb(Path("artifacts/kb/kb-20261119-045641.sqlite"), read_only=True)
checked = 0
invalid = []
for m in re.finditer(r"〔[^〕]+〕", text):
    block = m.group(0)
    if any(k in block for k in ("此处引用未通过校验", "《法规名》", "...")):
        continue
    assert "上海市工伤保险实施办法" not in block, f"Forbidden T078 citation block: {block}"
    vr = verify_output(block, conn)
    assert vr.citations, f"Unparsed citation block: {block}"
    for c in vr.citations:
        checked += 1
        assert c.title != "上海市工伤保险实施办法", f"Forbidden T078 resolved title: {c}"
        if c.verdict not in ("ok", "corrected"):
            invalid.append((block, c.verdict))
conn.close()
assert checked >= 25, f"Too few verified citations: {checked}"
assert not invalid, f"Invalid/incomplete citations in KB: {invalid}"
print(f"[OK] All {checked} citation blocks valid in kb-20261119-045641 (0 not_found, 0 incomplete, 0 T078)")

# 4. 关键 UI 按钮与精确硬拒文案核对
for token in ("新会话", "发送", "保存当前回复为 Markdown", "tu serve model --exp exp-20261116-resume500", "tu ui"):
    assert token in text, f"Missing expected UI/CLI token: {token}"
dec = decide_article_count("请帮我写 15 篇关于劳动合同签订的普法文章。", None)
assert dec.action == "rejected" and dec.notice in text, f"Exact hard-reject notice missing: {dec.notice}"
print("[OK] UI labels and exact article_count hard-reject notice matched")

# 5. 脱敏演示实体可被 anonymize.py 精确抽取
for sample, expect_p, expect_o in (
    ("我叫陈实，在启明电子厂做质检", "陈实", "启明电子厂"),
    ("我叫王明，在晨光制造公司工作", "王明", "晨光制造公司"),
):
    assert sample in text, f"Missing anonymize demo prompt fragment: {sample}"
    st = AnonymizeState()
    extract_user_entities(sample, st)
    names = {(e.name, e.kind) for e in st.entities}
    assert (expect_p, "person") in names and (expect_o, "org") in names, f"Entity miss: {names}"
print("[OK] Anonymize demo prompts verified against extract_user_entities")

# 6. Markdown 相对链接检查（排除 http/https 与纯锚点，非 gitignore 路径必须真实存在）
broken = []
for m in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", text):
    target = m.group(1).split("#", 1)[0].strip()
    if not target or target.startswith(("http://", "https://", "mailto:")):
        continue
    resolved = (doc.parent / target).resolve()
    if not resolved.exists():
        broken.append(target)
assert not broken, f"Broken relative links in docs/demo-scenarios.md: {broken}"
print("[OK] Zero broken relative links")
EOF
```

#### 7.2 完整门禁命令清单

```bash
# 1. 上述确定性内容核查脚本（退出码 0）
# 2. 全量既有测试与静态检查（确认零回归）
uv run --offline --no-sync pytest
uv run --offline --no-sync ruff check src tests

# 3. 历史产物哈希锁只读校验（须 25/25 OK）
shasum -a 256 -c artifacts/logs/t075/01/output.sha256

# 4. 变更范围审计（仅限 docs/demo-scenarios.md 与决策 1 指定的 poc_demo.md 变更）
git status -sb
```

---

### 8. 学习文档更新点

- 本任务（`T070`）为纯演示剧本收口，**不修改 `docs/learning/` 下的任何章节或 `00-glossary.md`**（避免与后续 `T073` / `T074` 职责重叠）。
- 本次沉淀的“10 分钟黄金主线 + 规格与实测落差对照表 + T078 避坑声明”将在紧随其后的 **`T073`（`docs/learning/07-serving-demo.md`）** 与 **`T074`（`docs/learning/08-lessons-and-next.md`）** 中直接被引用与总结。

---

### 9. 实施方偏差止损规则

- **可自决微调**：
  - 剧本导语的润色、表格列宽与 Markdown 排版格式调整、备选场景的组内排序（不删减核心用例、不改变任何事实数字与引文编号、不改动决策 1–3 的拍板结论）。
- **必须立即停工上报（严禁擅自绕过）**：
  - 核查脚本发现任何一条 `〔...〕` 引文在 `kb-20261119-045641.sqlite` 中校验为 `not_found` 或 `incomplete`，且无法通过核对既有 `results.jsonl` 确认正确款号；
  - 发现需要修改 `src/`、`tests/`、`configs/`、`README.md`、`docs/learning/` 或 `tasks.md` 才能满足某项核查；
  - 发现任意既有测试失败、T075 `output.sha256` 校验异常，或需要读取 `inputs/` 下文件才能确认某条法条内容；
  - 发现本机 `artifacts/` 缺失换机迁移清单中的任一文件。


---

### 10. 独立复审闭环记录（2026-11-24）

- **复审机制**：单节点独立只读高思考审查员（`reviewer`，Gemini 4 Neon High），共 **2 轮**，**一致通过**（两轮均已比对 `git status --porcelain` 与 `git diff | shasum`，确认审查员字节级零修改、未读取 `inputs/`）。
- **Round 1（需修改：2 项阻断项 + 2 项非阻断建议）**：
  1. **阻断项 1（`docs/demo-scenarios.md:164-165`）**：`mv-002` 中《社会保险法》第五十八条第 1 款实测为口径 C 唯一定位 `ok`（非补齐原文），第九十四条实测为 `corrected`（模型原稿误背社保争议维权条文，由校验层替换为第九十四条刑事责任原文），总计 `ok=4, corrected=2` → **已根因修复**。
  2. **阻断项 2（`docs/demo-scenarios.md:178`）**：`[06-evaluation.md [L6.9]](./learning/06-evaluation.md#l69)` 锚点无效且嵌套方括号绕过正则 → **已改为 `[06-evaluation.md（L6.9）](./learning/06-evaluation.md#l69-用本项目评测结果分析薄弱类别并反推数据改进方向)` 并在复检脚本中补齐 GFM 锚点校验**。
  3. **非阻断建议 1（`docs/demo-scenarios.md:68`）**：Step 6 两条无关拒答题间补齐 `→ 点 新会话 → 发` → **已采纳**。
  4. **非阻断建议 2（`docs/demo-scenarios.md:46`）**：将“页面标题”微调为“页面顶部标题” → **已采纳**。
- **Round 2（通过：阻断项 0，无未决异议）**：
  - 独立复跑增强版确定性核查脚本（25 处 `〔...〕` 全部有效、0 `not_found`/0 `incomplete`/0 T078、H2 严格 `1..9`、UI 与 15 篇精确硬拒文案匹配、脱敏实体抽取、9/9 相对链接及 GFM 锚点全部有效）；
  - 全量门禁：`uv run --offline --no-sync pytest` **462 passed, 6 xfailed**，`uv run --offline --no-sync ruff check src tests` **All checks passed!**，`shasum -a 256 -c artifacts/logs/t075/01/output.sha256` **25/25 OK**；
  - 已顺带同步本执行单第 85、158 行关于 `mv-002` 第五十八条的旧表述。
