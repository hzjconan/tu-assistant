# T071 执行单 · 运行 `quickstart.md` 全部验证场景（V1–V7 + US4）并记录结果

- **状态**：已拍板定稿（待实施）— 用户确认按全部推荐项实施（`1A 2A 3A`：V4/V5 采用历史产物指纹核验 + 现行代码只读重渲染/对比 + 1.5B 实机 `tu chat /save`；V6 采用 7B + `tu ui --temperature 0.0` `gradio_client` 全 6 步实机验证并附真实浏览器可选人工复核清单；报告落盘 `docs/experiments/T071-quickstart-verification.md` 覆盖 V1–V7 + US4 并更新 `docs/experiments/README.md`）
- **对应任务**：`specs/001-legal-clause-assistant/tasks.md` Phase 7 — **`T071`**（单项推进，不合并 `T072` / `T073` / `T074`）
- **Git 基线**：`0c65847`（`main`，工作区干净；`T070` 已定稿 `docs/demo-scenarios.md`）
- **活跃产物基线**：
  - 冻结 7B 演示模型：`exp-20261116-resume500`（`adapters/adapters.safetensors` SHA-256 `b62a7d0e86f490d946fb69d795d80707f2b3386c1cbb0a0529e6adef2ae18930`，基座 `mlx-community/Qwen2.5-7B-Instruct-4bit` 已完整缓存本机）
  - 1.5B 流程验证模型：`exp-20261114-120250`（基座 `mlx-community/Qwen2.5-1.5B-Instruct-4bit` 权重与分词器已缓存本机，14,342 s 训练完成）
  - 活跃知识库：`artifacts/kb/kb-20261119-045641.sqlite`（SHA-256 `40d4ea70333404ccd9724fccddc09c51311de0123ea9416a37549fd7742f13bb`，24 篇法规 / 3,809 条记录 / 67 条已确认关联：`liability_for` 26 + `references` 41）
  - 其余 3 份历史知识库 SHA-256：
    - `kb-20261113-071600.sqlite`: `3330a30fff7e37064ed3645b77470e59857659058d96ec1afaeb186679b30176`
    - `kb-20261113-091537.sqlite`: `d509305f8793ee26e1485f0704a62b9c7716f0170a0da749c55a038fe36bb22a`
    - `kb-20261113-093057.sqlite`: `e6a964968c69b7cc2ba8192a6338868487760abcfb1934d6a871b3b0f668ef80`
  - 评测与对比证据：`run-20261123-051432` / `run-20261123-053832` + `compare-20261123-145054`（T064 全 98 题 SC-015 `0.0 pp` PASS）、`run-20261117-022645` vs `run-20261117-081504`（SC-016 PASS）、`run-20261117-085921`（1.5B 60 题评测）
  - 自动化基线：`uv run --offline --no-sync pytest` **462 passed, 6 xfailed**（其中 `tests/unit` 457 passed / 6 xfailed，`tests/integration` 5 passed），`ruff check src tests` 全绿，T075 `output.sha256` 25/25 OK
- **不可逾越的红线**：
  1. **严禁读取 `inputs/` 目录下任何文件内容**：不得打开、grep 或运行会向对话/日志输出 `inputs/` 条文正文的命令（V2 抽查须采用零正文泄漏的 `tu kb diff --summary-only` 与输出管道 `shasum` 核验）；
  2. **运行时零外连 / 数据不出域**：`tu serve model`、`tu chat`、`tu ui` 全程 `HF_HUB_OFFLINE=1`、严格监听 `127.0.0.1`、不调用外部大模型 API，全部验证提示词使用虚构人物与单位；
  3. **历史产物与配置零污染**：V2 入库严禁写入仓库默认 `artifacts/kb/`（防止 `configs/app.yaml` 中 `kb.version: null` 自动切库劫持）；严禁改动 4 份历史 `.sqlite`、冻结模型权重、历史评测 run 及 T075 `output.sha256` 覆盖的 25 项文件；验收结束前必须确保 `artifacts/serve/current.json` 恢复指向冻结 7B 模型 `exp-20261116-resume500` 且 8080/7860 端口完全释放；
  4. **验收门禁前不落账**：完成独立复审闭环并获用户明确确认前，不得勾选 `tasks.md`，不得执行 `git commit` 或 `git push`。

---

## 上篇：面向用户决策

### 1. 推荐任务编号与选择理由

**推荐本轮优先推进单项 `T071`（运行 `quickstart.md` 全部验证场景并记录结果）**，Phase 7 剩余 4 项任务建议按 **`T071 → T073 → T072 + T074`** 顺序收尾。

| 候选任务 | 核心内容 | 依赖关系与排序理由 |
|---|---|---|
| **`T071`（本次推荐）** | 运行 `quickstart.md` 全部验证场景（V1–V7 + US4）并记录结果 | **POC 最后一项实机端到端验证任务**：① `T070` 刚定稿 `docs/demo-scenarios.md` 10 分钟黄金主线，正式解锁 V6 全 6 步实机验证，并可顺势补齐 `T069` 留待 `T071` 的实机验证项；② 先完成全链路端到端验证，才能确认当前 `HEAD`（含 `T066–T070` 全部改动）零退化，把真实实测数据与结论喂给后续文档任务，避免先写文档再返工。 |
| `T073` | 撰写 `docs/learning/07-serving-demo.md` + 更新术语表 | 已有 `[L7.1]`–`[L7.3]`；待 `T071` 跑完 V4/V6 实机联调后，可直接引用定稿的 `docs/demo-scenarios.md`、实机延时/内存表现与“训练/演示互斥原因”，无占位符。 |
| `T072` | 更新 `README.md` | 此前 `3b944c9` 已刷过一版；留待 `T071` 验证报告与 `T073`/`T074` 章节路径全部落盘后一次性更新文档导航与验证入口，避免反复改动索引。 |
| `T074` | 撰写 `docs/learning/08-lessons-and-next.md` | POC 总复盘终章（踩坑汇总、V1–V7 总结、T078 已知缺陷登记、POC 说明/没说明什么、正式阶段 R12），必须压轴收尾。 |

---

### 2. 待用户拍板的决策清单

请审阅以下 3 项取舍并直接回复选择（例如 `1A 2A 3A`）：

1. **决策 1：V4（1.5B 全流程）与 V5（7B 演示模型与评测）的验证方式**
   - **1A（推荐）**：**不重跑数小时合成/训练与 42 分钟重复评测**，采取「**历史产物指纹核验 + 现行代码只读重渲染/对比 + 1.5B 实机 `tu chat` 冒烟**」：
     - **V4（1.5B）**：核验 `ds-kb-20261119-045641-8247`、`eval/cases/v1`（98 题）、`exp-20261114-120250`（14,342 s）及 `run-20261117-085921`（在现行代码上只读重跑 `tu eval report`），并**实机启动 1.5B 服务跑通 `tu chat` 2 轮对话 + `/save <tmp>/v4-out.md` + `/new` + `/quit`**（补齐命令行对话与 Markdown 导出实测，约 1–2 分钟）；
     - **V5（7B）**：核验 `exp-20261116-resume500` 与 `T064` 两轮冷启动 98 题评测产物指纹（已核对 `git diff bea2d97..HEAD -- src/` 确认推理与评测正常主路径未变），并在现行代码上只读重跑 `tu eval report`、`tu eval compare --sc015 --reviews`（0.0 pp PASS）与 `--sc016`（PASS）。
     - *理由*：避免重复消耗外部 API 费用与 18+ 小时训练/评测时间，同时把 V4 此前缺少留档的 `tu chat /save` 实机链路与 V5 全部只读命令在最新 `HEAD` 上跑实。
   - **1B**：在 1A 基础上，额外对 1.5B 模型在隔离临时 `--artifacts` 目录实机跑 1 次 2 题冒烟评测（`eval/cases/smoke/smoke.jsonl`，约 30 秒，测完删除），现场验证现行 `HEAD` 的 `tu eval run` 端到端链路。
     - *理由*：仅多花约 1 分钟，即可补齐现行 `HEAD` 下 `tu eval run` 的实时运行实证，且隔离目录零污染仓库 `artifacts/`。
   - **1C**：对 7B 演示模型在现行 `HEAD` 上完整重跑 98 题 `tu eval run`（单轮约 21 分钟，两轮约 42 分钟）。
     - *理由*：距 `T064` 仅隔 1 天且评测主路径未变，重复耗时收益极低（不推荐）。

2. **决策 2：V6（Gradio 演示界面）实机验证的覆盖层级**
   - **2A（推荐）**：**实机启动 7B 服务（`exp-20261116-resume500`）+ `tu ui --temperature 0.0`**，由实施方通过 `gradio_client` + HTTP 探针**端到端自动跑通 `docs/demo-scenarios.md` 10 分钟黄金主线全部 6 步**（含 Step 3 关联补全与意图切换、Step 4 路线 A 普法文章生成/修改/下载 `.md` 逐字节核对、Step 5 脱敏/15 篇硬拒/`not_found` 删除、Step 6 双拒答、零外链样式表与 `127.0.0.1` 监听）；并在汇报验收时提供 2 分钟**真实浏览器人工可选复核清单**（排版视觉、浏览器点击下载、关闭标签页实感），由用户按需确认后结项。
     - *理由*：用确定性断言彻底测透完整 6 步端到端链路，同时坦诚标注自动化客户端与真实浏览器点击的边界，不阻塞自动化闭环。
   - **2B**：仅执行 `gradio_client` + HTTP 实机全 6 步自动验证，在报告中如实注明“未做人工浏览器点击”，直接进入独立复审与验收。
     - *理由*：零人工浏览器操作成本，推进最快。
   - **2C**：在 2A 基础上，**阻塞等待**用户本人在真实浏览器中手动走完黄金主线（含刷新/关闭标签页及回复后等待 >5 分钟再点击下载验证 `delete_cache=(600, 7200)`）后再落盘终版报告进入复审。
     - *理由*：将 `T069` 备忘的全部浏览器人工项一次性 100% 实测清零，但需用户中途实操约 10–15 分钟。

3. **决策 3：验证结果落盘路径与 `quickstart.md` 末尾 US4 小节的纳入范围**
   - **3A（推荐）**：新建 **`docs/experiments/T071-quickstart-verification.md`**（并在 `docs/experiments/README.md` 补录一行索引），**完整覆盖 `quickstart.md` 全部 8 个小节：V1–V7 + 末尾「知识库更新与版本切换（US4）」**（运行 `tests/integration/test_kb_update.py` + 只读 `tu kb diff --summary-only`）。
     - *理由*：沿用 `T064-eval-repeatability.md` / `T075-article-training.md` 同目录命名规范；覆盖 `T068` 增补的 US4 小节确保整份 `quickstart.md` 无遗漏。
   - **3B**：新建 `docs/experiments/T071-quickstart-verification.md`，仅记录 `V1–V7`（US4 小节仅用一句话回指 `T068` 验收记录）。
     - *理由*：严格贴合 `tasks.md` T071 字面“V1–V7”，篇幅略短。

---

## 下篇：面向实施方的零歧义施工图

> **实施前提**：须待用户对上篇 3 项决策拍板并由设计节点（或主会话）将状态更新为 `已拍板定稿（待实施）`、折叠落选分支后，方可动手施工。

### 3. 现状锚点与只读实测陷阱预警

#### 3.1 复用与对齐的代码/文档锚点

| 锚点文件与行号 | 精确职责与实测事实 |
|---|---|
| `specs/001-legal-clause-assistant/quickstart.md:15-116` | 本任务唯一验收蓝本：V1（单元测试）、V2（文档入库）、V3（出处校验）、V4（1.5B 全流程）、V5（7B 与评测）、V6（Gradio 演示界面）、V7（数据合规检查）及 US4（知识库更新与版本切换） |
| `docs/demo-scenarios.md:55-71` | V6 实机操作的唯一权威主线：10 分钟黄金主线 Step 1–6（`cand-001` + `p1-0003`、`mv-002`、`intent-010` 3 轮、6.1 合同留存 + 通俗化修改 + 导出 `.md`、`article-010` 脱敏 + 15 篇硬拒 + `refusal-001` 拦截、`refusal-003` + 域外拒答） |
| `src/tu_assistant/cli.py:42-56,102-127,149-168` | `tu kb import <dir> --artifacts <dir>`、`tu kb show <title> <article_no> [--kb-version] [--artifacts]`、`tu kb diff <v1> <v2> --summary-only` |
| `src/tu_assistant/kb/ingest.py:1-4,131-223` | `import_directory` 严格不打印文件名或条文正文，`parse_report.md` 仅输出文件序号、条款数与问题编号 |
| `src/tu_assistant/cli.py:395-441` | `tu serve model --exp <exp_id>`：只允许 `127.0.0.1` / `localhost`，写入 `artifacts/serve/current.json`（`model="default_model"`）并启动 `mlx_lm.server` |
| `src/tu_assistant/cli.py:1295-1459` | `tu chat`（`/save <path>`、`/new`、`/quit`）与 `tu ui`（仅允许 `127.0.0.1`，支持 `--temperature 0.0`、`--no-inbrowser`） |
| `src/tu_assistant/ui/app.py:333-452` | Gradio 6.31.0 演示界面；只读实测暴露 3 个端点：`/_on_send`（submit）、`/_on_send_1`（send_btn）、`/_on_reset`（new_btn）；`analytics_enabled=False`、系统字体（`_stylesheets == []`）、`delete_cache=(600, 7200)` |
| `tests/unit/test_runtime_isolation.py:1-59` | V7 入口测试（3 passed）：仅覆盖端点白名单与运行时包零外部客户端 AST 检查，**不含** FR-030 脱敏与 UI 本地隐私检查 |
| `docs/experiments/T064-eval-repeatability.md:1-109` | V5 官方基线证据（`run-20261123-051432` / `053832`、`compare-20261123-145054`、SC-015 `0.0 pp` PASS、SC-016 PASS） |
| `artifacts/logs/t075/01/output.sha256` | 25 项 T075 只读哈希锁清单，全程不得破坏 |

#### 3.2 只读实测发现的 7 处环境/工程陷阱与必须采用的写法

1. **陷阱 1（V2 直接入库污染 `artifacts/kb/` 并劫持 `kb.version: null`）**：
   - *踩坑表现*：`configs/app.yaml:21` 默认 `kb.version: null`（自动取 `artifacts/kb/` 最新时间戳库）。若直接照抄 `uv run tu kb import inputs/project/001`，会在仓库 `artifacts/kb/` 生成无已确认关联（0 条）且无 T077 `第1款` 标记的裸新库，导致后续 `tu ui` / `tu chat` / `tu eval` 静默切到裸库、FR-019 关联补全失效。
   - *必须采用的写法*：创建临时目录 `TMP_V2=$(mktemp -d /tmp/t071-v2-XXXXXX)`，传入 `--artifacts "$TMP_V2"` 执行导入；验证完毕立即 `rm -rf "$TMP_V2"`，并复检仓库 `artifacts/kb/` 4 份历史 `.sqlite` 哈希零变化。
2. **陷阱 2（V2 `tu kb show` 直接打印正文触犯 `inputs/` 红线）**：
   - *踩坑表现*：直接运行 `uv run tu kb show "中华人民共和国工会法" 51` 会把源于 `inputs/project/001` 的条文正文输出到终端与对话上下文，触犯 `AGENTS.md` 红线。
   - *必须采用的写法*：
     - 用 `uv run --offline --no-sync tu kb diff artifacts/kb/kb-20261113-093057.sqlite "$TMP_V2/kb/<new_ver>.sqlite" --summary-only`（`kb/diff.py` 保证 0 字节正文泄漏）全量证明 24 篇法规、3,809 条记录 **新增 0 / 删除 0 / 原文变化 0 / 原文未变 3,809**；
     - 对 `tu kb show "中华人民共和国工会法" 51`，仅通过管道计算字节数与 SHA-256，与 `kb-20261119-045641` 的 `tu kb show` 哈希比对（已实测该条为单款 `第五十一条`、121 字符，两库 `number_text` 与正文完全一致），**严禁向终端或报告打印任何条文正文**。
3. **陷阱 3（V4 1.5B 会覆写 `artifacts/serve/current.json` 且离线缓存检查差异）**：
   - *踩坑表现*：① 运行 `tu serve model --exp exp-20261114-120250` 会覆写 `artifacts/serve/current.json`；② 实测本机 1.5B HF 缓存缺 `.gitattributes`/`README.md`，直接调 `huggingface_hub.snapshot_download(..., local_files_only=True)` 会报错，但权重与分词器文件完整，`mlx_lm` 在 `HF_HUB_OFFLINE=1` 下可离线加载。
   - *必须采用的写法*：严格按 **先 V4（1.5B）→ 停服 → 再 V6（7B `exp-20261116-resume500`）→ 停服** 顺序执行，并在结束前核验 `artifacts/serve/current.json` 中 `exp == "exp-20261116-resume500"`；启动模型服务一律加 `HF_HUB_OFFLINE=1`。
4. **陷阱 4（若选 1B：隔离目录跑 `tu eval run` 缺 KB 与 `serve/current.json`）**：
   - *踩坑表现*：`cli.py:1038-1046` 中 `tu eval run --artifacts <tmp>` 会同时从 `<tmp>/kb/` 解析 KB、从 `<tmp>/serve/current.json` 解析模型名；传空目录会直接失败。
   - *必须采用的写法*：若按决策 1B 跑 1.5B 冒烟评测，需在 `$TMP_V4_EVAL` 中先建 `kb/` 与 `serve/` 子目录并只读软链 `kb-20261119-045641.sqlite` 与 `artifacts/serve/current.json`，跑完验证报告后立即 `rm -rf "$TMP_V4_EVAL"`。
5. **陷阱 5（`gradio_client 2.7.2` 调 Gradio 6.31.0 的真实端点名与返回值）**：
   - *踩坑表现*：`ui/app.py` 未显式命名 `api_name`，盲猜 `/predict` 或 `/chat` 会报端点不存在；且 `gr.State` 不需要客户端显式传入。
   - *必须采用的写法*：经只读实测，`create_ui_app` 的真实端点为 `/_on_send`（或 `/_on_send_1`）与 `/_on_reset`；调用 `client.predict(message, api_name="/_on_send")` 返回 4 元组 `(chatbot_history, cleared_input, download_filepath, status_md)`，调用 `client.predict(api_name="/_on_reset")` 清空会话；验证导出时直接读取返回的 `download_filepath`（即 Gradio 通过 `/gradio_api/file=...` 实际下载的缓存文件）与最后一轮 `assistant` 回复逐字节比对。
6. **陷阱 6（V7 单跑 `test_runtime_isolation.py` 无法覆盖 `quickstart.md` 全部 3 条预期）**：
   - *踩坑表现*：`quickstart.md:89-90` 的 V7 预期包含“不导入外部客户端 + 端点白名单拒绝 + 普法文章不出现用户提供的单位与人名（FR-030 / SC-011）”，但 `test_runtime_isolation.py` 只有前两项的 3 个用例。
   - *必须采用的写法*：V7 必须以 `tests/unit/test_runtime_isolation.py` 为主命令，**并显式联跑** `tests/unit/test_anonymize.py`（75 passed）与 `tests/unit/test_ui.py`（28 passed，覆盖 `127.0.0.1` 主机校验、零遥测、`share=False`、零外链字体），再汇总实测 `SC-011 = 2/2`（`run-20261123-051432`）与 V6 Step 5 `article-010` 脱敏证据。
7. **陷阱 7（本机 Metal GPU / 本地回环端口监听与进程清理）**：
   - *踩坑表现*：Apple Silicon Metal 推理与绑定 `127.0.0.1:8080`/`7860` 在隔离沙箱中可能触发 `No Metal device available` 或绑定失败；且忘记停服会留下后台进程占满 7B 内存。
   - *必须采用的写法*：仅对需要 Metal GPU 或监听本机回环端口的实机命令（`tu serve model`、`tu ui`、`tu chat`、`gradio_client` 探针）按运行环境要求申请本机执行权限，纯单测/只读校验保持常规执行；每阶段结束立刻向服务进程发 `SIGINT`/`SIGTERM` 并用 `lsof -iTCP:8080 -iTCP:7860 -sTCP:LISTEN` 确认零残留；严禁同时启动两个模型服务或与训练并行。

---

### 4. 改动范围表与明确不做清单（Non-Goals）

#### 4.1 文件改动表

| 文件路径 | 操作 | 精确职责 |
|---|---|---|
| `docs/experiments/T071-quickstart-verification.md` | **新增** | 本任务核心交付物：完整记录 `quickstart.md` 全部验证场景（V1–V7 + 决策 3 确认的 US4 小节）的执行方式、精确命令、实测数据、断言结果、证据索引与边界说明 |
| `docs/experiments/README.md` | **微调（仅增 1 行）** | 在实验记录总表末尾补录 `T071` 验证记录链接（不改写其他既有行） |

#### 4.2 明确不做清单（Non-Goals）

实施方本次**严禁**执行以下操作：
- 严禁修改 `src/`、`tests/`、`configs/`、`eval/`、`scripts/` 下任何代码、测试、评测集或配置文件（若验证过程中发现真正的代码 Bug，必须**立即停工上报**，不得顺手改源码）；
- 严禁修改 `README.md`（归 `T072`）、`docs/demo-scenarios.md`（`T070` 已定稿）、`docs/learning/` 下任何章节与 `00-glossary.md`（归 `T073` / `T074`）；
- 严禁修改 `specs/001-legal-clause-assistant/tasks.md` 或 `quickstart.md`；
- 严禁向仓库 `artifacts/kb/`、`artifacts/datasets/`、`artifacts/train/`、`artifacts/eval/` 写入任何新文件，或破坏 `artifacts/logs/t075/01/output.sha256` 锁定的 25 项文件；
- 严禁读取 `inputs/` 下任何文件内容或在验证报告中粘贴源于 `inputs/` 的整段条文原文（除已在 `docs/demo-scenarios.md` / `tests/` 公开出现的引用编号与简短核查要点外）。

---

### 5. 文档结构与事实口径契约（`docs/experiments/T071-quickstart-verification.md`）

`docs/experiments/T071-quickstart-verification.md` 必须严格采用以下 **顶部元信息 + 总览表 + `## 1.` 至 `## 8.`（V1–V7 + US4）** 结构，**严禁伪造或抄旧数字**（所有本次新跑的耗时、通过数、命令输出必须来自本次真实执行；所有复核的历史产物必须显式标注“历史产物只读复核 + 现行 `HEAD` 命令复验”）：

- **顶部元信息**：验证日期、对应任务 `T071`、代码 Git 基线（`0c65847`）、活跃 KB（`kb-20261119-045641`）与冻结模型（`exp-20261116-resume500` / `exp-20261114-120250`）、总体结论（全部场景判定与遗留/可选人工项说明）。
- **验证总览表**：逐行列出 `场景编号 | 对应 quickstart 章节 | 验证方式（现场新跑 / 隔离新跑 / 历史复核+只读复验） | 实测关键结果 | 判定`。
- **`## 1. V1：单元测试（确定性逻辑）`**：记录命令 `uv run --offline --no-sync pytest tests/unit`、实测 `457 passed, 6 xfailed`（并注明 6 个 `xfailed` 归属及全套 20 个单测模块对条款拆分、中文数字、引用解析、四态出处校验、身份信息检查、追问计数、端点白名单的覆盖映射）、耗时与退出码 `0`。
- **`## 2. V2：文档入库（隔离执行与零正文泄漏核验）`**：记录为何采用 `--artifacts <tmp>` 隔离（防 `kb.version: null` 劫持）；记录实测导入统计（24 篇法规 / 3,809 条记录 / 问题数与 `parse_report.md` 摘要）、`tu kb diff` 对比 `kb-20261113-093057.sqlite` 结果（新增 0 / 删除 0 / 原文变化 0 / 原文未变 3,809）、`tu kb show "中华人民共和国工会法" 51` 退出码 `0` + 字节数 + 与活跃库 `shasum -a 256` 一致性（0 字节正文输出），以及清理临时目录后 4 份历史 KB SHA-256 零变化证明。
- **`## 3. V3：出处校验`**：记录 `uv run --offline --no-sync pytest tests/integration/test_citation_verify.py` 实测 `4 passed`、覆盖 `ok / corrected / not_found / incomplete` 四态及二次校验 `corrected=0, not_found=0` 幂等断言、耗时与退出码 `0`。
- **`## 4. V4：全流程调通（1.5B）`**：按已拍板 1A 口径记录——① 合成/评测集/训练历史产物清单核验（`ds-kb-20261119-045641-8247`、`eval/cases/v1` 98 题、`exp-20261114-120250` 训练清单含基座/超参/种子/14,342 s、`run-20261117-085921` 现行代码只读 `tu eval report` 渲染验证）；② 实机启动 `tu serve model --exp exp-20261114-120250` 跑通 `tu chat` 2 轮对话（含 `quickstart.md` 示例“我们单位领导不让搞工会”→ 补充案情 → 引用块/免责声明/追问数 ≤5）+ `/save <tmp>/v4-out.md` 生成合法非空 UTF-8 Markdown 文件 + `/new` + `/quit`。
- **`## 5. V5：演示模型（7B）与评测`**：记录 `exp-20261116-resume500` 与 `T064` 两轮冷启动 98 题产物指纹校验、说明 `git diff bea2d97..HEAD -- src/` 仅涉及知识库维护与 UI/异常回滚未改正常评测推理路径，并记录在现行 `HEAD` 上只读复跑的 3 条命令实测结果：`tu eval report run-20261123-051432 --reviews eval/reviews/t064-reviews.csv`（覆盖 SC-001~SC-011 与校验前/后两列）、`tu eval compare --sc015 ... --reviews ...`（退出码 `0`，12 项有效指标最大波动 `0.0 pp` PASS）与 `tu eval compare --sc016 ...`（退出码 `0`，条级 1→17/60、款级 9/60、未知文件 0→21/30 PASS）。
- **`## 6. V6：演示界面（7B + `tu ui` + 10 分钟黄金主线）`**：记录实机启动 `tu serve model --exp exp-20261116-resume500` + `tu ui --temperature 0.0 --no-inbrowser`、HTTP 首页与 `127.0.0.1` 监听/零外链样式表探针结果、通过 `gradio_client` 逐一跑通 `docs/demo-scenarios.md` Step 1–6 的**逐步骤实测记录表**（每步含发送轮次、实测延迟、命中的关键断言、Step 4 下载 `.md` 文件字节数与逐字一致性结果），并按决策 2 如实标注真实浏览器人工复核边界（含是否已完成人工签收及 T069 备忘的浏览器视觉/关闭标签页/`delete_cache` 时效说明）。
- **`## 7. V7：数据合规检查`**：记录主命令 `uv run --offline --no-sync pytest tests/unit/test_runtime_isolation.py`（`3 passed`）+ 联跑 `tests/unit/test_anonymize.py`（`75 passed`）+ `tests/unit/test_ui.py`（`28 passed`）实测结果，并汇总实机证据（`SC-011 = 2/2`、V6 Step 5 `陈实→甲某` 替换与 `127.0.0.1`/零外链字体/零遥测），确保 V7 三条预期 100% 闭环。
- **`## 8. 知识库更新与版本切换（US4）与全局基线收口`**（若选 3A）：记录 `uv run --offline --no-sync pytest tests/integration/test_kb_update.py`（`1 passed`）与只读 `tu kb diff kb-20261113-093057 kb-20261119-045641 --summary-only` 实测结果；末尾单列全局基线终检结果（全量 `pytest`、`ruff`、4 份历史 KB SHA-256、T075 `output.sha256` 25/25 OK、`artifacts/serve/current.json` 指向 `exp-20261116-resume500`、8080/7860 端口零残留）。

---

### 6. 原子化施工步骤（自底向上，每步可自检）

- **Step 1：前置基线锁定与端口检查**
  - 动作：核验工作区干净、4 份历史 KB SHA-256、T075 `output.sha256` 及 8080/7860 端口空闲。
  - 最小验证命令：
    ```bash
    git status -sb && \
      shasum -a 256 artifacts/kb/*.sqlite && \
      shasum -a 256 -c artifacts/logs/t075/01/output.sha256 && \
      (lsof -iTCP:8080 -iTCP:7860 -sTCP:LISTEN || echo "ports 8080/7860 free")
    ```

- **Step 2：执行 V1、V3、V7 与 US4 确定性自动化测试**
  - 动作：分场景独立运行四组确定性测试，记录每组命令的 `passed / xfailed` 数量与耗时。
  - 最小验证命令：
    ```bash
    uv run --offline --no-sync pytest tests/unit
    uv run --offline --no-sync pytest tests/integration/test_citation_verify.py
    uv run --offline --no-sync pytest tests/unit/test_runtime_isolation.py tests/unit/test_anonymize.py tests/unit/test_ui.py
    uv run --offline --no-sync pytest tests/integration/test_kb_update.py
    uv run --offline --no-sync tu kb diff kb-20261113-093057 kb-20261119-045641 --summary-only
    ```

- **Step 3：执行 V2 隔离文档入库与零正文泄漏核验**
  - 动作：使用 `/tmp` 隔离目录运行 `tu kb import inputs/project/001`，核验 `parse_report.md` 统计表（无正文）、用 `tu kb diff --summary-only` 对比 `kb-20261113-093057.sqlite` 验证 3,809 条 0 变化、用管道哈希核验 `tu kb show "中华人民共和国工会法" 51`（零正文回显），然后删除临时目录并复检 4 份历史 KB 哈希。
  - 最小验证命令：
    ```bash
    TMP_V2=$(mktemp -d /tmp/t071-v2-XXXXXX)
    uv run --offline --no-sync tu kb import inputs/project/001 --artifacts "$TMP_V2"
    NEW_KB=$(ls "$TMP_V2"/kb/kb-*.sqlite | head -n 1)
    uv run --offline --no-sync tu kb diff artifacts/kb/kb-20261113-093057.sqlite "$NEW_KB" --summary-only
    H_TMP=$(uv run --offline --no-sync tu kb show "中华人民共和国工会法" 51 --artifacts "$TMP_V2" | shasum -a 256 | awk '{print $1}')
    H_ACT=$(uv run --offline --no-sync tu kb show "中华人民共和国工会法" 51 --kb-version kb-20261119-045641 | shasum -a 256 | awk '{print $1}')
    B_TMP=$(uv run --offline --no-sync tu kb show "中华人民共和国工会法" 51 --artifacts "$TMP_V2" | wc -c | tr -d ' ')
    echo "V2 kb show bytes=$B_TMP hash_match=$([ "$H_TMP" = "$H_ACT" ] && echo YES || echo NO) sha256_prefix=${H_TMP:0:16}"
    test "$H_TMP" = "$H_ACT" && test "$B_TMP" -gt 0
    rm -rf "$TMP_V2"
    shasum -a 256 artifacts/kb/*.sqlite
    ```

- **Step 4：执行 V4（1.5B 历史产物核验 + 实机 `tu chat` `/save` 闭环）**
  - 动作：
    1. 只读检查 `exp-20261114-120250/manifest.json`、`ds-kb-20261119-045641-8247/manifest.json` 并只读执行 `uv run --offline --no-sync tu eval report run-20261117-085921`（验证退出码 `0` 与指标表输出）；
    2. 后台启动 1.5B 模型服务：`HF_HUB_OFFLINE=1 uv run --offline --no-sync tu serve model --exp exp-20261114-120250`，待 `127.0.0.1:8080` 就绪后，运行 `tu chat` 喂入 2 轮对话（第 1 轮“我们单位领导不让搞工会”，第 2 轮“想了解法律规定，公司以生产忙为由拒绝员工依法组建工会，该如何维权？”）+ `/save /tmp/t071-v4-out.md` + `/new` + `/quit`；
    3. 检查 `/tmp/t071-v4-out.md` 存在、非空、合法 UTF-8，且验证对话输出中含引用块或免责声明且追问数 ≤5，随后删除 `/tmp/t071-v4-out.md`；
    4. 优雅终止 1.5B `tu serve model` 进程，确认 `127.0.0.1:8080` 已释放。
  - 最小验证命令：服务停稳后执行 `lsof -iTCP:8080 -sTCP:LISTEN || echo "8080 free"`。

- **Step 5：执行 V5（7B 产物指纹复核与现行代码只读评测/对比命令）**
  - 动作：校验 7B 适配器哈希、核对 `git diff --stat bea2d97..HEAD -- src/` 确认无评测推理正常路径变动，并在现行代码上只读重跑 3 条评测报告与对比命令（全部输出到 stdout 或 `/tmp` 检查，不写 `artifacts/`）。
  - 最小验证命令：
    ```bash
    shasum -a 256 artifacts/train/exp-20261116-resume500/adapters/adapters.safetensors
    uv run --offline --no-sync tu eval report run-20261123-051432 --reviews eval/reviews/t064-reviews.csv > /tmp/t071-v5-report.md
    grep -E 'SC-001|SC-007|SC-009|SC-011' /tmp/t071-v5-report.md
    uv run --offline --no-sync tu eval compare --sc015 run-20261123-051432 run-20261123-053832 --reviews eval/reviews/t064-reviews.csv | tail -n 15
    uv run --offline --no-sync tu eval compare --sc016 run-20261117-022645 run-20261117-081504
    rm -f /tmp/t071-v5-report.md
    ```

- **Step 6：执行 V6（实机 7B 服务 + `tu ui --temperature 0.0` + 黄金主线 Step 1–6 全量实测）**
  - 动作：
    1. 后台启动 7B 服务：`HF_HUB_OFFLINE=1 uv run --offline --no-sync tu serve model --exp exp-20261116-resume500`，待 `127.0.0.1:8080` 就绪（先核验 `artifacts/serve/current.json` 中 `exp == "exp-20261116-resume500"`）；
    2. 后台启动 UI 服务：`uv run --offline --no-sync tu ui --temperature 0.0 --no-inbrowser`，待 `127.0.0.1:7860` 就绪；
    3. 运行本地 HTTP + `gradio_client` 实测脚本（严格按 §7.1 断言底线执行）：
       - 检查 `GET http://127.0.0.1:7860/` 返回 200、HTML 不含 `fonts.googleapis.com` / `fonts.gstatic.com`、`lsof` 确认仅监听 `127.0.0.1:7860` 与 `127.0.0.1:8080`；
       - 依次执行 `docs/demo-scenarios.md` Step 1–6（每次换场景前调用 `/_on_reset` 并断言历史清空与状态栏含 `已开启新会话`），记录每步延迟、关键输出与全部确定性断言；
       - 在 Step 4（合同留存第 2 轮通俗化修改后）校验 `gradio_client` 返回的下载文件存在、UTF-8 可读、含三段标题与引文块，且与页面最后一轮回复**逐字节一致**；
    4. 按已拍板 2A 验证完毕立即优雅终止 `tu ui` 与 `tu serve model`；
    5. 确认 8080 / 7860 端口全部释放，核对 `artifacts/serve/current.json` 仍指向 `exp-20261116-resume500`。
  - 最小验证命令：停服后执行 `lsof -iTCP:8080 -iTCP:7860 -sTCP:LISTEN || echo "ports free"` 与 `cat artifacts/serve/current.json`。

- **Step 7：撰写 `docs/experiments/T071-quickstart-verification.md` 并更新 `docs/experiments/README.md`**
  - 动作：按第 5 节结构将 Step 1–6 真实观测到的命令、耗时、计数、断言与证据落盘到 `docs/experiments/T071-quickstart-verification.md`，并在 `docs/experiments/README.md` 表格末尾新增一行 `T071` 索引。
  - 最小验证命令：`grep -n '^## ' docs/experiments/T071-quickstart-verification.md`。

- **Step 8：运行报告确定性校验脚本**
  - 动作：运行 §7.2 校验脚本，确认章节结构、相对链接与 GFM 锚点 0 断链、全场景判定齐全、无 `inputs/` 原文泄漏与无 T078 误引。
  - 最小验证命令：见 §7.2（退出码必须为 `0`）。

- **Step 9：全量回归与只读基线终检**
  - 动作：执行 §7.3 全部门禁命令，确认零代码回归、历史产物哈希 100% 不变、工作区仅含预期 2 处文档变更，然后进入 `task-review-loop` 独立只读复审闭环。

---

### 7. 确定性核查矩阵与验收门禁

本任务不新增/修改 `tests/` 源码，而通过 **V6 实机硬断言底线 + 报告确定性核查脚本 + 全量既有门禁** 锁死验收质量。

#### 7.1 V6 实机黄金主线确定性断言底线表（严禁仅断言非空或返回 200）

| 步骤 | 输入场景（来自 `docs/demo-scenarios.md`） | 必须通过的确定性断言底线 |
|---|---|---|
| **服务与隐私探针** | `GET http://127.0.0.1:7860/` + `lsof` | HTTP 200；HTML 不含 `fonts.googleapis.com` 与 `fonts.gstatic.com`；仅监听 `127.0.0.1:7860` 与 `127.0.0.1:8080`；`current.json` `exp == "exp-20261116-resume500"` |
| **Step 1** | `/_on_reset` → `3.1`（`cand-001`）→ `/_on_reset` → `3.9`（`p1-0003`） | 回复 1 含 `〔《中华人民共和国劳动合同法》（2012-12-28）第二十四条第2款〕`、`\n> ` 与免责声明；回复 2 含 `〔《上海市职工代表大会条例》（2017-11-23）第六条〕`、`\n> ` 与免责声明 |
| **Step 2** | `/_on_reset` → `4.1`（`mv-002`） | 回复含 `《中华人民共和国劳动法》` 与 `《中华人民共和国社会保险法》` 两部法律引用，且经 `verify_output(..., kb_conn)` 复核 `corrected == 0`、`not_found == 0`（交付原文 100% 与 KB 一致） |
| **Step 3** | `/_on_reset` → `5.1`（`intent-010` 第 1–3 轮） | 第 2 轮命中 `《中华人民共和国工会法》（2021-12-24）第四十七条` 且含 `**相关条款（系统补充）**` 与 `第五十五条`；第 3 轮成功切换为普法短文（含虚构案例结构） |
| **Step 4** | `/_on_reset` → `6.1` 第 1 轮 → 第 2 轮通俗化修改 → 检查下载 `.md` | 第 1/2 轮含“案例 / 以案说法 / 普法提示”三段与《劳动合同法》第十六条；下载文件存在、合法 UTF-8、`Path(dl_path).read_text("utf-8") == last_assistant_reply` **逐字节完全一致** |
| **Step 5** | `/_on_reset` → `7.1` 方式 A（`article-010` 1–2 轮）→ `/_on_reset` → `7.2`（15 篇）→ `/_on_reset` → `7.4`（`refusal-001`） | `article-010` 第 2 轮**不含** `陈实` 且**不含** `启明电子厂`；15 篇请求**逐字返回** `单次最多支持生成 10 篇普法文章（默认 3 篇），当前请求为 15 篇。请将篇数调整至 1–10 篇后重新发送。`；`refusal-001` 含 `〔此处引用未通过校验，已删除〕` |
| **Step 6** | `/_on_reset` → `7.3`（`refusal-003`）→ `/_on_reset` → `7.3`（离婚抚养权） | 两轮均明确拒答（不含文末咨询免责声明 `*以上内容仅供参考，不构成法律意见。*`），并引导回工会法律咨询或普法文章 |
| **重置与清理** | 每次 `/_on_reset` + 进程退出 | 每次 `/_on_reset` 后 `chatbot_history == []`、下载路径为 `None`、状态栏含 `已开启新会话`；停服后 8080/7860 端口零残留 |

#### 7.2 验证报告确定性核查脚本（必须 100% 通过）

```bash
uv run --offline --no-sync python - << 'EOF'
import re
from pathlib import Path

doc = Path("docs/experiments/T071-quickstart-verification.md")
assert doc.is_file(), "T071 verification report missing"
text = doc.read_text(encoding="utf-8")

# 1. 必备场景章节与关键词检查（V1-V7 [+US4]）
for token in (
    "V1", "V2", "V3", "V4", "V5", "V6", "V7",
    "exp-20261116-resume500", "exp-20261114-120250",
    "kb-20261119-045641", "457 passed", "0.0 pp", "PASS",
    "单次最多支持生成 10 篇普法文章",
    "〔此处引用未通过校验，已删除〕",
):
    assert token in text, f"Missing required verification token: {token}"
print("[OK] Core verification tokens and scenario headers present")

# 2. 二级标题编号连续且无重复
h2s = re.findall(r"^##\s+(.+)$", text, flags=re.M)
nums = [re.match(r"^(\d+)\.", h).group(1) for h in h2s if re.match(r"^(\d+)\.", h)]
assert nums == [str(i) for i in range(1, len(nums) + 1)] and len(nums) >= 7, f"Bad H2 numbering: {h2s}"
assert len(h2s) == len(set(h2s)), f"Duplicate H2 headings: {h2s}"
print(f"[OK] H2 headings numbered 1..{len(nums)} without duplicates")

# 3. 相对链接与 GFM 锚点零断链检查
def slugify(h: str) -> str:
    s = h.strip().lower()
    s = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", s)
    return re.sub(r"\s+", "-", s)

broken = []
for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", text):
    raw = m.group(2).strip()
    if raw.startswith(("http://", "https://", "mailto:")):
        continue
    path_part, anchor = (raw.split("#", 1) + [""])[:2]
    target = (doc.parent / path_part).resolve() if path_part else doc.resolve()
    if not target.exists():
        broken.append(raw)
        continue
    if anchor and target.suffix == ".md":
        heads = re.findall(r"^#{1,6}\s+(.+)$", target.read_text(encoding="utf-8"), flags=re.M)
        if anchor not in {slugify(h) for h in heads}:
            broken.append(raw)
assert not broken, f"Broken links/anchors: {broken}"
print("[OK] Zero broken relative links or GFM anchors")

# 4. 核对 docs/experiments/README.md 已索引 T071
idx = Path("docs/experiments/README.md").read_text(encoding="utf-8")
assert "T071-quickstart-verification.md" in idx, "T071 not indexed in docs/experiments/README.md"
print("[OK] docs/experiments/README.md indexes T071")
EOF
```

#### 7.3 完整门禁命令清单

```bash
# 1. 上述报告确定性校验脚本（退出码 0）
# 2. 全量测试与静态检查（须 462 passed, 6 xfailed；ruff 全绿）
uv run --offline --no-sync pytest
uv run --offline --no-sync ruff check src tests

# 3. 历史产物哈希锁与 4 份历史 KB 只读校验
shasum -a 256 -c artifacts/logs/t075/01/output.sha256
shasum -a 256 artifacts/kb/*.sqlite

# 4. 运行时状态与端口清理复核
cat artifacts/serve/current.json
lsof -iTCP:8080 -iTCP:7860 -sTCP:LISTEN || echo "ports 8080/7860 free"

# 5. 变更范围审计（仅限 docs/experiments/T071-quickstart-verification.md 与 docs/experiments/README.md）
git status -sb
```

---

### 8. 学习文档更新点

- 本任务（`T071`）为端到端验收集执行与结果记录，**不修改 `docs/learning/` 下的任何章节或 `00-glossary.md`**（避免与紧随其后的 `T073` / `T074` 职责重叠）。
- 本次实机跑通的 V4/V6 实测延迟、端口/服务协作与全场景结论将在 **`T073`（`docs/learning/07-serving-demo.md`）** 与 **`T074`（`docs/learning/08-lessons-and-next.md`）** 中作为一手数据引用。

---

### 9. 实施方偏差止损规则

- **可自决微调**：
  - 验证报告中的排版样式、表格列宽、耗时保留位数、临时脚本在 `/tmp/` 中的命名与清理方式（不删减任何 V1–V7 [+US4] 必备字段，不改动任何实测数字，不违背决策 1–3 的拍板结论）。
- **必须立即停工上报（严禁擅自绕过）**：
  - V1 / V2 / V3 / V7 / US4 任意一条自动化测试或校验失败，或 V2 隔离导入与 `kb-20261113-093057` 对比出现非零差异；
  - V4 1.5B `tu chat` 或 V6 7B 黄金主线 Step 1–6 中任意一条 §7.1 硬断言未通过（严禁偷偷调低断言、改写 `src/` 代码或跳过某步继续写 `PASS`）；
  - 需要修改 `src/`、`tests/`、`configs/`、`docs/demo-scenarios.md`、`docs/learning/`、`README.md` 或 `tasks.md` 才能通过某项核查；
  - 发现任何历史 KB 哈希变化、T075 `output.sha256` 异常、`artifacts/kb/` 意外新增文件，或需要读取 `inputs/` 目录下文件正文才能完成验证。


---

### 10. 独立复审闭环记录（2026-11-24）

- **复审机制**：单节点独立只读高思考审查员（`reviewer-t071`，Gemini 4 Neon High），共 **2 轮**，**一致通过**（两轮均已比对 `git status --porcelain` 与 `git diff | shasum`，确认审查员字节级零修改、未读取 `inputs/`）。
- **实施期偏差上报与用户拍板**：V6 实机跑测 Step 4 第 2 轮（路线 A 普法短文简短通俗化改稿）触发 §7.1 硬断言（冻结 7B 父模型将 324 字三段短文压缩为 57 字单段 `## 普法提示`，UI 与 `.md` 下载 163 字节逐字节一致）；按 §9 止损上报后用户明确拍板 **选项 A**（不改代码与 `docs/demo-scenarios.md`，在报告中如实记录该路线 A 模型行为边界）。
- **Round 1（需修改：3 项阻断项 + 3 项非阻断建议）**：
  1. **阻断项 1（V1 覆盖说明）**：更正 `test_eval_compare.py` → `test_compare.py`，补齐 20 个单测模块对追问计数（`test_orchestrator.py`）的映射及全部 6 个 `xfailed` 归属 `tests/unit/test_article_eval.py::test_refusal_known_limitations` → **已根治**。
  2. **阻断项 2（V5 `git diff` 表述）**：按真实 `git diff --stat bea2d97..HEAD -- src/` 准确列出 11 个改动文件与 `+1535/-239`（未改动评测计分、出处校验本体与正常推理主路径）→ **已根治**。
  3. **阻断项 3（V4 第 1/2 轮区分）**：移除脚本变量名，严格区分第 1 轮实际行为（1.5B 未反问、直接给出结构化咨询，援引 `quickstart.md` 流程验证定位）与第 2 轮 `/save` 导出文件校验（6,621 bytes / 2,369 chars，合法 UTF-8）→ **已根治**。
  4. **非阻断建议 1–3**：拆分 `delete_cache=(600, 7200)` 与 `gr.State(delete_callback=controller.cleanup_session)` 机制对应；补录 V6 `/_on_reset` 断言；明确 V4 1.5B 训练时间（`2026-11-14`）与最新 SFT 数据集（`2026-11-19`）先后关系；在 V5 补齐 `SC-002=0.121`、`SC-003=0.188`、`SC-010` 跳过说明 → **全部采纳**。
- **Round 2（通过：阻断项 0、非阻断建议 0）**：
  - §7.2 报告确定性核查脚本 4/4 `[OK]`；
  - `uv run --offline --no-sync pytest`：**462 passed, 6 xfailed**；`uv run --offline --no-sync ruff check src tests`：**All checks passed!**；
  - 4 份历史 KB SHA-256 与基线一致、`shasum -a 256 -c artifacts/logs/t075/01/output.sha256` **25/25 OK**、`artifacts/serve/current.json` 指向 `exp-20261116-resume500`、8080/7860 端口空闲。
