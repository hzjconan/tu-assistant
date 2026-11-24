# T071 验证记录 · `quickstart.md` 全部验证场景（V1–V7 + US4）

- **验证日期**：2026-11-24
- **对应任务**：`specs/001-legal-clause-assistant/tasks.md` Phase 7 — **`T071`**
- **代码 Git 基线**：`0c65847`（`main`，含 `T066`–`T070` 全部改动）
- **活跃知识库**：`artifacts/kb/kb-20261119-045641.sqlite`（24 篇法规 / 3,809 条记录 / 67 条已确认关联：`liability_for` 26 + `references` 41）
- **验证模型**：
  - 冻结 7B 演示模型：`exp-20261116-resume500`（基座 `mlx-community/Qwen2.5-7B-Instruct-4bit`）
  - 1.5B 流程验证模型：`exp-20261114-120250`（基座 `mlx-community/Qwen2.5-1.5B-Instruct-4bit`）
- **总体结论**：**V1–V7 与 US4 全部 8 个场景均通过验收**（其中 V6 Step 4 第 2 轮如实记录冻结 7B 父模型在简短改稿指令下将三段压缩为单段 `## 普法提示` 的路线 A 模型行为边界，UI 与 Markdown 导出链路 100% 逐字节一致，经用户拍板按选项 A 如实留档；另附 2 分钟真实浏览器可选人工复核清单）。

## 验证总览表

| 场景编号 | 对应 `quickstart.md` 章节 | 验证方式 | 实测关键结果 | 判定 |
|---|---|---|---|---|
| **V1** | 单元测试（确定性逻辑） | 现场新跑 | `457 passed, 6 xfailed`（4.37 s，退出码 0） | **PASS** |
| **V2** | 文档入库 | 隔离新跑（`--artifacts /tmp/...`） | 24 篇 / 3,809 条 / 问题 24 个；`kb diff` 0 变化；`kb show` 哈希一致（0 字节正文泄漏） | **PASS** |
| **V3** | 出处校验 | 现场新跑 | `4 passed`（0.02 s，覆盖 `ok / corrected / not_found / incomplete` 与幂等） | **PASS** |
| **V4** | 全流程调通（1.5B） | 历史复核 + 只读复验 + 实机 `tu chat` | `exp-20261114-120250`（14,342 s）+ `tu eval report` 退出码 0；实机 `tu chat` 2 轮 + `/save` 6,621 B + `/new` | **PASS** |
| **V5** | 演示模型（7B）与评测 | 历史复核 + 现行 `HEAD` 只读复验 | 适配器哈希一致；`tu eval report`、`--sc015`（`0.0 pp` PASS）、`--sc016`（PASS）全通过 | **PASS** |
| **V6** | 演示界面（7B + `tu ui`） | 实机 `gradio_client` + HTTP 探针 | 黄金主线 Step 1–6 全通，下载 `.md` 逐字节一致（如实记入 Step 4 第 2 轮模型压缩边界） | **PASS**（附边界说明） |
| **V7** | 数据合规检查 | 现场新跑 + 实机证据 | `106 passed`（`test_runtime_isolation` 3 + `test_anonymize` 75 + `test_ui` 28）+ `SC-011=2/2` + V6 脱敏 | **PASS** |
| **US4** | 知识库更新与版本切换 | 现场新跑 + 只读复验 | `test_kb_update.py` `1 passed`（0.22 s）；`tu kb diff` 3,809 条 0 原文变化、关联 35→67 | **PASS** |

---

## 1. V1：单元测试（确定性逻辑）

- **执行命令**：`uv run --offline --no-sync pytest tests/unit`
- **实测结果**：`457 passed, 6 xfailed in 4.37s`（退出码 `0`）。
- **覆盖说明**：全套 20 个单元测试模块覆盖中文数字转换（`test_numbers.py`）、法律条款切分与校验（`test_parse.py`）、引用解析与四态出处校验（`test_citation.py`）、身份信息自动脱敏（`test_anonymize.py`）、追问计数与编排（`test_orchestrator.py`）、篇数护栏（`test_article_count.py`）、评测指标/报告/对比（`test_metrics.py`、`test_report.py`、`test_compare.py`）、知识库差异与配置（`test_kb_diff.py`、`test_kb_config.py`）、运行时隔离与 Gradio UI（`test_runtime_isolation.py`、`test_ui.py`）。全部 6 个 `xfailed` 均归属于 `tests/unit/test_article_eval.py::test_refusal_known_limitations`，与基线一致。

---

## 2. V2：文档入库（隔离执行与零正文泄漏核验）

- **隔离原因**：`configs/app.yaml` 默认 `kb.version: null`（自动取 `artifacts/kb/` 最新时间戳库）。若直接向仓库默认 `artifacts/kb/` 执行 `tu kb import`，会生成 0 条已确认关联的新库并静默劫持活跃库 `kb-20261119-045641`。因此本次严格使用临时目录 `--artifacts /tmp/t071-v2-XXXXXX` 隔离导入，测完即删。
- **实测统计**：
  - 导入命令：`uv run --offline --no-sync tu kb import inputs/project/001 --artifacts "$TMP_V2"`
  - 输出摘要：`kb_version=kb-20261124-051752  文件 24 篇 / 条款 3809 条 / 问题 24 个`，同步生成 `kb-20261124-051752-parse_report.md`（仅含统计与问题编号，无正文）。
- **全量零正文泄漏比对**：
  - `uv run --offline --no-sync tu kb diff artifacts/kb/kb-20261113-093057.sqlite "$NEW_KB" --summary-only`
  - 结果：`现行文件：24 篇 -> 24 篇 | 现行条款：3809 条 -> 3809 条 | 新增 0 条 / 删除 0 条 / 原文变化 0 条 / 原文未变 3809 条 | 编号写法变化 1026 条 | 已确认条款关联：35 条 -> 0 条`。
- **单条抽查（零正文回显）**：
  - 对 `tu kb show "中华人民共和国工会法" 51`（隔离新库 vs 活跃库 `kb-20261119-045641`）仅通过管道比对字节数与 SHA-256：`bytes=381`、`hash_match=YES`（`sha256_prefix=cb25ce6f28d4db4c`），退出码 `0`，全程 0 字节条文正文进入终端或报告。
- **清理复核**：删除 `$TMP_V2` 后，仓库 `artifacts/kb/` 4 份历史 `.sqlite` 的 SHA-256 与前置基线 100% 一致。

---

## 3. V3：出处校验

- **执行命令**：`uv run --offline --no-sync pytest tests/integration/test_citation_verify.py`
- **实测结果**：`4 passed in 0.02s`（退出码 `0`）。
- **验证要点**：覆盖 `ok`（正确引用保留）、`corrected`（原文有误替换为知识库原文）、`not_found`（不存在编号删除并替换为 `〔此处引用未通过校验，已删除〕`）、`incomplete`（裸引用记录）四种结论，以及二次校验 `corrected=0, not_found=0` 幂等性，交付原文 100% 与知识库一致。

---

## 4. V4：全流程调通（1.5B）

按拍板决议 1A，不重跑数小时合成与训练，采用「历史产物清单核验 + 现行代码只读渲染 + 1.5B 实机 `tu chat /save` 闭环」：

1. **历史产物清单核验**：
   - 当前最新活跃 SFT 数据集 `artifacts/datasets/ds-kb-20261119-045641-8247/manifest.json`（`2026-11-19` 生成）存在且可追溯 `kb-20261119-045641`；
   - 评测集 `eval/cases/v1/` 共 98 题覆盖全部 7 类；
   - 1.5B 实验 `artifacts/train/exp-20261114-120250/manifest.json`（`2026-11-14` 基于当时 `artifacts/datasets/latest` 训练）完整记录基座 `mlx-community/Qwen2.5-1.5B-Instruct-4bit`（`Apache-2.0`）、`iters=28986`、`epochs=2`、`seed=42`、`grad_checkpoint=true`、`duration_s=14342`、`returncode=0`；
   - 现行代码只读执行 `uv run --offline --no-sync tu eval report run-20261117-085921` 退出码 `0`，正常渲染 60 题报告（`SC-002=0.017`、`SC-003=0.038`、`SC-006=0.922`、`SC-007` 校验前 `0.017` / 校验后 `0.538`）。
2. **1.5B 实机 `tu chat` + `/save` 闭环**：
   - 启动 `HF_HUB_OFFLINE=1 uv run --offline --no-sync tu serve model --exp exp-20261114-120250`（就绪于 `127.0.0.1:8080`）；
   - 通过 `uv run --offline --no-sync tu chat` 发送 2 轮对话（第 1 轮“我们单位领导不让搞工会”，第 2 轮“想了解法律规定，公司以生产忙为由拒绝员工依法组建工会，该如何维权？”），随后执行 `/save /tmp/t071-v4-out.md`、`/new`、`/quit`；
   - **第 1 轮实际行为**：1.5B 模型收到模糊开场后未主动反问，直接输出了带《工会法》引用块的结构化咨询答复（符合 `quickstart.md`“1.5B 的效果不作要求，只验证流程”的定位）；
   - **第 2 轮 `/save` 导出文件校验**：`/save` 仅导出最后一轮 assistant 回复；实测 `/tmp/t071-v4-out.md` 存在且为合法 UTF-8，大小 `6,621 bytes`（`2,369 chars`），包含完整引用块与文末免责声明；验证后删除临时文件并停服，确认 `8080` 端口释放。

---

## 5. V5：演示模型（7B）与评测

按拍板决议 1A，采用「历史产物指纹复核 + 现行 `HEAD` 只读重跑报告与对比命令」：

1. **产物指纹与代码变更核验**：
   - `artifacts/train/exp-20261116-resume500/adapters/adapters.safetensors` SHA-256 为 `b62a7d0e86f490d946fb69d795d80707f2b3386c1cbb0a0529e6adef2ae18930`（与冻结基线完全一致）；
   - `git diff --stat bea2d97..HEAD -- src/` 共改动 11 个文件（`+1535/-239`，涵盖 `kb/diff.py`、`kb/store.py`、`kb/ingest.py`、`ui/app.py`、`chat/assistant.py`、`chat/orchestrator.py`、`citation/verify.py`、`cli.py`、`config.py` 及 `eval/runner.py` / `eval/compare.py` 只读打开 KB 调整），未改动评测计分、出处校验本体与正常推理主路径逻辑（历史基线详见 [T064-eval-repeatability.md](./T064-eval-repeatability.md)）。
2. **现行 `HEAD` 只读重跑结果**：
   - `uv run --offline --no-sync tu eval report run-20261123-051432 --reviews eval/reviews/t064-reviews.csv`：退出码 `0`，完整输出 `SC-001=0.900 (9/10)`、`SC-002=0.121`、`SC-003=0.188`、`SC-007` 校验前 `0.405` / 校验后 `0.669`（共 163 处引用）、`SC-009=0.000 (0/9)`、`SC-010` 跳过（多篇实得 `<2` 篇）、`SC-011=2/2`；
   - `uv run --offline --no-sync tu eval compare --sc015 run-20261123-051432 run-20261123-053832 --reviews eval/reviews/t064-reviews.csv`：退出码 `0`，98 题两轮独立冷启动 12 项有效指标最大波动 **`0.0 pp`**（各分类失败数差值全为 `0`，**SC-015 PASS**）；
   - `uv run --offline --no-sync tu eval compare --sc016 run-20261117-022645 run-20261117-081504`：退出码 `0`，条级 `1/60 → 17/60`（`p=4.45e-05`）、款/项级 `9/60 = 15.0%`、基座未知文件子集 `0/30 → 21/30`（`p=3.58e-09`），**SC-016 总判定 PASS**。

---

## 6. V6：演示界面（7B + `tu ui` + 10 分钟黄金主线）

实机启动 `HF_HUB_OFFLINE=1 uv run --offline --no-sync tu serve model --exp exp-20261116-resume500` 与 `uv run --offline --no-sync tu ui --temperature 0.0 --no-inbrowser`，通过 HTTP 探针与 `gradio_client`（端点 `/_on_send`、`/_on_reset`）依次跑通 [docs/demo-scenarios.md](../demo-scenarios.md) 10 分钟黄金主线全部 6 步：

| 步骤 | 实测场景 | 实测延迟 | 关键断言与实测结果 | 判定 |
|---|---|---:|---|---|
| **服务与隐私探针** | `GET http://127.0.0.1:7860/` + `current.json` | <0.1 s | HTTP 200；HTML 不含 `fonts.googleapis.com` / `fonts.gstatic.com`；仅监听 `127.0.0.1:7860` 与 `127.0.0.1:8080`；`current.json` 指向 `exp-20261116-resume500` | **PASS** |
| **Step 1** | `3.1`（`cand-001`）+ `3.9`（`p1-0003`） | 3.3 s / 2.2 s | 均精准命中目标法条（《劳动合同法》第二十四条第 2 款、《上海市职工代表大会条例》第六条）、含 `\n> ` 原文与免责声明 | **PASS** |
| **Step 2** | `4.1`（`mv-002`） | 34.1 s | 跨《劳动法》《社会保险法》两部法律，交付正文经 `verify_output` 二次复核 6 处引用 `corrected=0, not_found=0` | **PASS** |
| **Step 3** | `5.1`（`intent-010` 第 1–3 轮） | 2.8 s / 4.0 s / 19.7 s | 第 2 轮命中《工会法》第四十七条并由编排层自动追加 `**相关条款（系统补充）**`（第五十五条）；第 3 轮成功切换为三段式普法短文 | **PASS** |
| **Step 4** | `6.1`（路线 A 合同留存初稿 → 通俗化修改 → 下载 `.md`） | 9.5 s / 2.3 s | 第 1 轮（324 字）完整输出“案例 / 以案说法 / 普法提示”三段与《劳动合同法》第十六条；第 2 轮下载文件 `tu-reply-...-turn2.md`（163 B）合法 UTF-8 且与页面回复**逐字节完全一致**（见下方边界说明） | **PASS**（附边界） |
| **Step 5** | `7.1` 方式 A（`article-010`）+ `7.2`（15 篇）+ `7.4`（`refusal-001`） | 3.0 s+12.0 s / 91 ms / 4.4 s | `article-010` 第 2 轮不含 `陈实` 与 `启明电子厂`；15 篇毫秒级逐字返回 `单次最多支持生成 10 篇普法文章（默认 3 篇），当前请求为 15 篇。请将篇数调整至 1–10 篇后重新发送。`；个税伪造引文被替换为 `〔此处引用未通过校验，已删除〕` | **PASS** |
| **Step 6** | `7.3`（`refusal-003` + 离婚抚养权） | 3.0 s / 3.0 s | 两轮均明确拒答并引导回工会法律咨询或普法文章，不含咨询免责声明 | **PASS** |

- **会话重置与清理**：每个场景切换前均调用 `/_on_reset`，全部通过 `chatbot_history == []`、下载路径为 `None`、状态栏含 `已开启新会话` 断言；停服后 `8080` / `7860` 端口零残留。
- **Step 4 第 2 轮模型行为边界说明（用户拍板按选项 A 如实记录）**：在冻结 7B 父模型（路线 A 未合入 T053 修改样本续训）上，发送简短修改指令“语言再通俗一些，适合贴在工厂车间宣传栏。”时，模型将第 1 轮的 324 字三段短文大幅压缩为 57 字单段 `## 普法提示`（省略了 `案例 / 以案说法` 与《劳动合同法》第十六条）；UI 会话流与 `.md` 下载导出功能完全正常（163 字节逐字节一致）。现场演示若需改稿后仍保留完整三段与法条，可在第 2 轮显式注明“保留案例、以案说法、普法提示三个小节和法律依据”。
- **真实浏览器人工可选复核清单（2 分钟）**：本次 V6 通过 `gradio_client` + HTTP 探针完成了全部功能与数据断言，未做真实浏览器人工点击。如需视觉终验，可启动双终端后在浏览器中检查：① 页面排版与中文渲染无乱码；② 点击「保存当前回复为 Markdown」触发浏览器原生下载（临时文件缓存由 `delete_cache=(600, 7200)` 控制，回复后 >5 分钟仍可下载）；③ 关闭/刷新标签页后会话正常重置（由 `gr.State(delete_callback=controller.cleanup_session)` 最迟约 1 小时回收内存）。

---

## 7. V7：数据合规检查

- **主命令与联跑命令**：
  `uv run --offline --no-sync pytest tests/unit/test_runtime_isolation.py tests/unit/test_anonymize.py tests/unit/test_ui.py`
- **实测结果**：`106 passed in 1.59s`（退出码 `0`），其中：
  1. `test_runtime_isolation.py`（`3 passed`）：静态 AST 检查确认 `chat/`、`runtime/`、`ui/`、`eval/` 不导入外部大模型客户端，且配置指向外部地址时启动即拒绝；
  2. `test_anonymize.py`（`75 passed`）：覆盖常见单姓人名与五类单位全称抽取、多轮稳定替换、核准引文区间保护与历史清洗；
  3. `test_ui.py`（`28 passed`）：覆盖 `127.0.0.1` 严格主机校验、`share=False`、`analytics_enabled=False`、零外部字体样式表与会话清理。
- **实机合规证据**：结合 V5 `run-20261123-051432` 中 `SC-011 = 2/2`（引用冲突 0 轮）与 V6 Step 5 `article-010` 实测（`陈实` / `启明电子厂` 均未出现在普法文章交付稿中），`quickstart.md` V7 三条预期全部闭环。

---

## 8. 知识库更新与版本切换（US4）与全局基线收口

### 8.1 US4 验证实测

- **端到端集成测试**：`uv run --offline --no-sync pytest tests/integration/test_kb_update.py` → **`1 passed in 0.22s`**（覆盖修改/删除/新增条款重导、同秒防撞名、`tu kb diff` 反正文泄漏、通过 `configs/app.yaml` `kb.version` 零改代码切库、缺失版本报错防空库及旧库只读保护）。
- **只读版本差异**：`uv run --offline --no-sync tu kb diff kb-20261113-093057 kb-20261119-045641 --summary-only` → `现行文件：24 篇 -> 24 篇 | 现行条款：3809 条 -> 3809 条 | 新增 0 条 / 删除 0 条 / 原文变化 0 条 / 原文未变 3809 条 | 编号写法变化 1026 条 | 已确认条款关联：35 条 -> 67 条（+42 / -10，保留 25）`。

### 8.2 全局基线终检

- **全量测试**：`uv run --offline --no-sync pytest` → **462 passed, 6 xfailed**；
- **静态检查**：`uv run --offline --no-sync ruff check src tests` → **All checks passed!**；
- **T075 哈希锁**：`shasum -a 256 -c artifacts/logs/t075/01/output.sha256` → **25/25 OK**；
- **4 份历史知识库 SHA-256**：全部与前置基线逐字一致，零新增/零修改；
- **运行时状态与端口**：`artifacts/serve/current.json` 已恢复指向 `exp-20261116-resume500`，`8080` 与 `7860` 端口全部释放，零残留进程。
