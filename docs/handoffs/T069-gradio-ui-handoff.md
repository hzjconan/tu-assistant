# T069 执行单 · Gradio 本地演示界面与 `tu ui`（Phase 7）

**状态：已验收完成（2026-11-23，经初版 2 轮独立复审、第三方二轮评审修订、`reviewer-v2` 2 轮终审及最终代码实机 V6 联调重跑通过，用户已确认收口）。** 基于主线提交 `fb31f4c`（Phase 1–6 已全部收口，仅 `T078` 移出 POC 至正式阶段）。本执行单面向 Phase 7 首项任务 **T069**：基于现有 `Assistant` 协议（`TrainedAssistant`）与 `configs/app.yaml` 统一配置底座，落地 `src/tu_assistant/ui/app.py` 与 `tu ui` 命令，提供仅监听 `127.0.0.1` 的本地网页演示界面（多轮对话、新会话、保存当前回复为 Markdown），满足 `quickstart.md` V6 与 `spec.md` FR-009 / FR-032 / FR-033。

> **合规与红线声明**：
> 1. 设计与实施全过程**严禁读取 `inputs/` 目录下任何文件**（包括直接读取、grep 或运行任何输出其内容的脚本）；
> 2. **运行时隔离与数据不出域（宪章原则 III/IV、FR-033）**：`src/tu_assistant/ui/` 严禁导入 `openai` 或 `tu_assistant.synth.*`（持续通过 `tests/unit/test_runtime_isolation.py` 静态检查）；UI 强制写死 `share=False`、禁用 Gradio 遥测与外链字体、默认仅监听 `127.0.0.1`；模型端点继续经 `TrainedAssistant.from_config` 强制校验 `runtime.allowed_hosts`；
> 3. **会话仅存内存与清理（FR-009）**：会话上下文仅驻留内存，不写入仓库或 `artifacts/`；点击「新会话」立即调用 `assistant.close(session_id)` 释放上下文并删除控制器临时目录中的 `.md` 文件，关闭或刷新标签页后由 Gradio 6 标记关闭并在约 1 小时（`STATE_TTL_WHEN_CLOSED=3600`）后触发 `delete_callback` 回收，退出进程时全部清理；Gradio 下载缓存副本由 `delete_cache=(600, 7200)` 到期或退出进程时统一清除；
> 4. **历史产物只读保护**：严禁修改 `artifacts/kb/` 下既有 SQLite 知识库、历史数据集、已训权重、历史评测目录及 `artifacts/logs/t075/01/output.sha256` 锁定的 25 项文件；知识库全程以只读模式（`mode=ro`）打开；
> 5. **收口门禁**：在用户明确拍板本执行单前不得写业务代码；实施完成后须走独立只读复审闭环（最多 5 轮），经用户最终确认前不得勾选 `specs/001-legal-clause-assistant/tasks.md` 或 `git commit`。

---

## 1. 推荐任务编号与选择理由

**推荐任务：`T069`（实现 Gradio 演示界面 `src/tu_assistant/ui/app.py` 与 `tu ui`：多轮对话、新会话、保存当前回复为 Markdown；只监听 `127.0.0.1`）。**

### 1.1 为什么优先做 T069（对比 Phase 7 其余全部未完成任务 T070–T074）

Phase 1–6 除已移出 POC 的 `T078` 外已全部清零，当前全部剩余 POC 任务均为 Phase 7（`T069–T074`）：

| 候选任务 | 当前状态与前置依赖 | 优先级判断 |
|---|---|---|
| **`T069`（推荐）** | `src/tu_assistant/ui/` 当前仅空 `__init__.py`；所有上游底座（`TrainedAssistant.from_config`、`session_config_from`、`export_markdown`、`kb.version` 只读加载、篇数与脱敏护栏）已在 Phase 4 & 6 全部稳定 | **唯一剩余代码实现任务，阻塞全阶段收尾**：先落地可运行的网页界面，才能确定界面交互步骤、跑通 V6 验收并如实沉淀收尾文档 |
| **`T070`**（演示场景脚本 `docs/demo-scenarios.md`） | 需对齐界面操作步骤（发消息、新会话、导出 `.md`）与 T075 路线 A 演示边界（US1 实时咨询 + 限定 US2 预审单篇） | 依赖 `T069` 的界面形态与按钮文案确定后再编写，避免先写脚本再因 UI 调整返工 |
| **`T071`**（运行 `quickstart.md` V1–V7 并记录结果） | 依赖 V6（`uv run tu ui`）真实可用，且按 V6 要求需“按准备好的演示场景操作” | 必须排在 `T069`（及理想情况下 `T070`）之后 |
| **`T072`**（更新 `README.md`） | 需汇总最终常用命令（含 `tu ui` 参数）与文档索引（含 `docs/demo-scenarios.md`、第 7/8 章学习文档） | 应留待 `T069–T071` 完成后一次性收口 |
| **`T073`**（完整撰写 `docs/learning/07-serving-demo.md`） | 当前仅有 `[L7.1]`，需涵盖模型服务、对话编排、演示界面与“训练与演示不能同时进行” | 需在 `T069` 落地后结合真实 UI 实现与服务架构统一成章（本次先补 `[L7.2]` 记录 UI 工程要点，完整整合留给 `T073`） |
| **`T074`**（撰写 `docs/learning/08-lessons-and-next.md`） | 全 POC 复盘、踩坑汇总与正式阶段清单（含 T078 已知缺陷登记） | POC 最终收尾章节，须在 `T071` 全量验证通过后收笔 |

### 1.2 为什么推荐单做 T069，不与 T070 合并？

- `T069` 是纯工程交付（UI 控制器、Gradio 界面、CLI 入口、SQLite 跨线程/异常回滚修复、单元测试与 V6 联调），验收口径清晰确定；
- `T070` 属于面向项目方的演示剧本设计（需结合 T075 路线 A 边界审定每条咨询与普法文章演示话术），偏内容审校与人工定稿；拆分推进可让代码复审与剧本审稿各得其所，避免混在同一轮复审中互相拖累。若用户希望一步合并，第 6 节决策 1 提供备选方案。

---

## 2. 仓库现状与 Gradio 环境实测摸底

以下信息均经只读检查源码与本机 uv 环境实测确认（未读取 `inputs/`）：

### 2.1 仓库与产物基线

- **Git 基线**：`HEAD = fb31f4c`（`feat(T066-T068): implement kb diff, config-driven kb.version switch, and update e2e test`），工作区干净；
- **测试与校验基线**：`tasks.md` T068 验收记录为全量 `uv run pytest` **434 passed / 6 xfailed**，`ruff` 全绿；本轮已复核 `shasum -a 256 -c artifacts/logs/t075/01/output.sha256` **25/25 OK**；
- **活跃运行基线**：
  - 知识库：`artifacts/kb/kb-20261119-045641.sqlite`（24 篇法规、3,809 条款行、67 条已确认关联）；
  - 冻结演示模型：`exp-20261116-resume500`（`artifacts/serve/current.json` 当前指向 `{"model": "default_model", "base_model": "mlx-community/Qwen2.5-7B-Instruct-4bit", "exp": "exp-20261116-resume500", "endpoint": "http://127.0.0.1:8080/v1"}`）；
  - UI 目录：`src/tu_assistant/ui/` 目前仅有空文件 `__init__.py`；`src/tu_assistant/cli.py` 尚未注册 `tu ui` 命令。

### 2.2 本机 uv 环境 Gradio 实测结果（关键 API 差异预警）

虽然 `pyproject.toml` 声明 `gradio>=5.9.0`，但本机 uv 锁定的实际安装版本为 **`gradio 6.31.0`**。通过只读 `uv run --offline --no-sync python -c ...` 实测，确认了以下 **5 处 Gradio 6 关键行为**（避免按 Gradio 4/5 记忆写错 API）：

1. **`gr.Chatbot` 已移除 `type` 与 `show_copy_button` 参数，且 `preprocess` 会结构化改写消息内容**：
   - `gr.Chatbot.__init__` 不再接受 `type="messages"`（传之必报 `TypeError`），原生只接受 OpenAI 风格字典列表 `list[MessageDict | Message]`（`{"role": "user"|"assistant", "content": "..."}`）；
   - 复制按钮参数改为 `buttons=["copy"]`（支持 `'share' | 'copy' | 'copy_all'`，注意严禁启用 `'share'`）；
   - **重要实测发现**：向 `gr.Chatbot.postprocess` 传入 `[{"role": "user", "content": "你好"}]` 正常渲染，但经 `gr.Chatbot.preprocess` 传回 Python 回调时，`content` 会被转成多模态块列表 `[{'text': '你好', 'type': 'text'}]`。因此 **UI 绝不应把 `gr.Chatbot` 作为状态源读回解析字符串**，而应在独立 `gr.State` 中维护纯文本对话历史（`list[dict[str, str]]`），每次仅单向输出给 `gr.Chatbot`。
2. **`gr.Blocks` 与 `Blocks.launch` 的参数迁移**：
   - 实测在 `gr.Blocks(theme=...)` 传参会触发 Gradio 6 弃用警告：`The parameters have been moved from the Blocks constructor to the launch() method in Gradio 6.0: theme. Please pass these parameters to launch() instead.`；因此 `theme` 与 `css` 必须传给 `demo.launch(...)`；
   - `show_api` 已从 `launch()` 移除，底部链接改由 `footer_links=[]` 控制；
   - `gr.Blocks(analytics_enabled=False, delete_cache=(600, 7200), title=...)` 可关闭启动/初始化遥测与版本检查线程，并按 2 小时有效期清理 Gradio 自身缓存副本（避免现场演示讲解超过 5 分钟再点下载出现 404，退出进程时框架以 `age=None` 全部清除）。
3. **零外部网络请求（遥测 + Google Fonts 实测验证）**：
   - `gradio.analytics.analytics_enabled()` 默认读取 `os.getenv("GRADIO_ANALYTICS_ENABLED", "True") == "True"`；在导入 `gradio` 前执行 `os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")` 并配合 `gr.Blocks(analytics_enabled=False)` 可彻底关闭遥测与后台版本检查；
   - `gr.themes.Default()` 与 `gr.themes.Soft()` 默认内置 `GoogleFont`（加载外部 `fonts.googleapis.com` 样式表，离线或国内环境会拖慢首屏且产生外连）；实测 `gr.themes.Soft(font=[gr.themes.Font("system-ui"), "sans-serif"], font_mono=[gr.themes.Font("ui-monospace"), "monospace"])` 的 `_stylesheets == []`，实现**零外链静态资源**。
4. **标签页关闭/刷新时的会话回收机制（`gr.State.delete_callback`）**：
   - 核对本机 `gradio 6.31.0` 源码（`routes.py:1523`、`state_holder.py:78-82`、`route_utils.py:1224-1228`）：浏览器标签页关闭或刷新后，框架先标记 `is_closed=True` 并将保留时间强制设为 `STATE_TTL_WHEN_CLOSED = 3600` 秒（约 1 小时后由 `_delete_state` 协程在 asyncio 事件循环线程同步调用 `delete_callback(value)` 回收）。因此：点「新会话」与进程退出为**立即释放**，关闭/刷新页面为**最迟约 1 小时由框架回收**，且 `cleanup_session` 必须非阻塞获取互斥锁（拿不到锁时交给守护线程异步清理）以避免卡死事件循环。
5. **`gr.DownloadButton` 机制**：
   - `gr.DownloadButton.postprocess(value: str | Path | None)` 将本地文件路径封装为 `FileData(path=str(value), orig_name=Path(value).name)`；当 `value` 已绑定文件路径且 `interactive=True` 时，用户点击一次即可直接触发浏览器下载 `.md` 文件。

### 2.3 摸底发现的 2 处底层并发/异常隐患（必须处理）

1. **【必修复】SQLite 只读连接跨线程崩溃（实测复现）**：
   - 实测在主线程调用现有 `open_kb(kb_path, read_only=True)` 后，在工作线程执行查询立即抛出：
     `ProgrammingError('SQLite objects created in a thread can only be used in that same thread...')`；
   - Gradio 事件回调运行在 AnyIO/FastAPI 线程池中，若 `tu ui` 直接使用默认 `TrainedAssistant.from_config(...)`，**用户在网页发出第一条消息即必崩溃**；
   - 本机实测 `sqlite3.threadsafety == 3`（SQLite `3.54.1`，`SERIALIZED` 线程安全模式），且对 `mode=ro` 只读连接传入 `check_same_thread=False` 跨线程查询实测返回 `(3809,)` 正常通过。配合 UI 控制器互斥锁与 `demo.queue(default_concurrency_limit=1)`，可完全杜绝跨线程崩溃与并发竞态。
2. **【建议顺带修复】`orchestrator.py` 模型请求失败时残留悬挂用户消息**：
   - 核查 `src/tu_assistant/chat/orchestrator.py:66-97`：`add_turn(session, Turn(role="user", content=user_message))` 在 `client.chat(...)` **之前**执行；
   - 若本地 `mlx_lm.server` 未启动、超时或返回 5xx，`client.chat(...)` 抛出异常后，该条未得到回复的 `user` 消息会永久残留在 `session.messages` 中；用户启动服务后重试发消息时，发送给模型的 `messages` 会出现两条连续的 `role="user"` 消息，污染多轮对话状态（`tu chat` 与 `tu ui` 均受此影响）；
   - 最小安全修法：在 `orchestrator.py` 的 `process_turn` 写入本轮 `user` `Turn` 前记录 `prev_len`/`prev_intent`/`prev_active`，将后续全链路（含 `client.chat`、`verify_output`、关联补全与脱敏）纳入 `try/except`，任一步骤抛异常均截断回滚 `session.messages[prev_len:]` 并恢复状态后原样抛出（正常路径零改动，见第 6 节决策 4）；UI 同步捕获 `sqlite3.Error` 给出中文提示。

### 2.4 与现有核心接口的衔接核对

- **`TrainedAssistant.from_config(...)`**（`src/tu_assistant/chat/assistant.py:102`）：已支持 `config_path`、`kb_version`、`artifacts_dir`、`temperature`，内部走 `resolve_kb_path` + `open_kb(..., read_only=True)` + `resolve_model_name` + `ModelClient` 白名单校验，并暴露 `kb_version` 只读属性与 `close_kb()`；仅需新增可选 `check_same_thread: bool = True` 透传给 `open_kb`（默认值不变，零破坏）。
- **`session_config_from(cfg)`**（`src/tu_assistant/chat/assistant.py:34`）：统一读取 `session.max_questions_per_turn`（5）、`session.default_article_count`（3）、`session.max_article_count`（10）并在 `SessionConfig.__post_init__` 中 fail-fast 校验合法性。
- **`Assistant.export_markdown(session_id, turn_index=None)`**（`src/tu_assistant/chat/export.py:12`）：直接返回指定轮（默认最后一轮）助手回复的 `Turn.content`（已过出处校验、关联补全、免责声明与文章脱敏），无回复时返回 `""`；天然保证导出的 `.md` 文件与界面展示内容**逐字节一致**（`quickstart.md` V6 预期）。
- **`contracts/citation-format.md §2` 展示口径约束**：`corrected` 结论要求“原文替换为知识库原文（**不提示用户**，记录到指标）”。因此 UI 状态栏**不得向用户展示 `corrected` 修正计数或原稿差异**，仅展示中性状态（如轮次、导出状态、连接异常提示等）。

---

## 3. 实施边界与核心设计

### 3.1 文件变更边界

| 文件路径 | 操作 | 职责 |
|---|---|---|
| `src/tu_assistant/kb/store.py` | **微调** | 为 `open_kb`（及 `open_kb_from_config`）增加可选关键字参数 `check_same_thread: bool = True`，仅在 `sqlite3.connect(..., check_same_thread=check_same_thread)` 透传，默认值 `True` 保持既有调用行为 100% 不变 |
| `src/tu_assistant/chat/assistant.py` | **微调** | 为 `TrainedAssistant.from_config` 增加可选关键字参数 `check_same_thread: bool = True` 并透传给 `open_kb` |
| `src/tu_assistant/chat/orchestrator.py` | **微调（按决策 4）** | `process_turn` 在写入本轮 `user` `Turn` 后以全链路 `try/except` 兜底，任一步骤抛异常均截断回滚悬挂 `user` `Turn` 并恢复 `intent`/`article_task_active` 后原样抛出，正常路径零改动 |
| `src/tu_assistant/ui/app.py` | **新增** | **T069 核心**：实现 `validate_ui_host`、`UISessionState`、`ChatUIController`（纯 Python 可测控制器：会话生命周期、多轮对话、新会话释放、导出 Markdown、临时文件清理、异常兜底与互斥锁）、`create_ui_app`（Gradio 6.31.0 `Blocks` 装配）与 `launch_ui`（安全启动参数封装） |
| `src/tu_assistant/cli.py` | **修改** | 新增 `tu ui` 命令（支持 `--config`、`--artifacts`、`--kb-version`、`--host`、`--port`、`--temperature`、`--inbrowser/--no-inbrowser`），拒绝非本机 host、不暴露 `--share`、`try/finally` 安全关闭 KB 与清理临时导出目录 |
| `tests/unit/test_ui.py` | **新增** | **T069 确定性单元测试与离线冒烟测试**：覆盖 host 白名单拒绝、控制器多轮对话/空输入拦截/会话隔离/`new_session` 与 `delete_callback` 释放、导出 `.md` 逐字节一致与临时文件回收、模型断连/超时异常恢复（含悬挂 user 轮回滚）、多线程通过 `TrainedAssistant.from_config(..., check_same_thread=False)` 访问真实只读 SQLite、`create_ui_app` 离线构造零警告且 `analytics_enabled=False`、`tu ui` CLI 校验与退出码 |
| `docs/learning/07-serving-demo.md`、`00-glossary.md` | **修改** | 在已有 `[L7.1]` 后增补 `[L7.2]`（本地演示界面的工程边界：Gradio 6 状态隔离、SQLite 跨线程约束与本地隐私护栏），并在术语表补充对应条目（锚点准确；完整章节整理仍归 `T073`） |

> **严格不在本次修改范围内**：
> - 不修改 `specs/` 下任何文件、`eval/cases/`、`configs/`、`src/tu_assistant/chat/prompts.py`、`src/tu_assistant/chat/anonymize.py`、`src/tu_assistant/chat/article_count.py`、`src/tu_assistant/citation/`、`src/tu_assistant/synth/`；
> - 不改动任何 `artifacts/` 历史产物；
> - 不编写 `docs/demo-scenarios.md`（归 `T070`），不修改 `README.md`（归 `T072`）。

### 3.2 模块分层与交互设计（`src/tu_assistant/ui/app.py`）

#### (1) 纯 Python 控制器：`ChatUIController`
仅依赖 `Assistant` 协议（`contracts/system-interface.md §1`），完全不接触 `ModelClient`、`kb_conn` 或 Gradio 组件类型：

```python
@dataclass
class UISessionState:
    session_id: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)
    export_path: Path | None = None
```

核心方法（全部在内部 `self._lock = threading.Lock()` 保护下执行）：
- **`send_message(state: UISessionState | None, message: str) -> tuple[UISessionState, list[dict[str, str]], str, str | None, str]`**
  - 返回 `(new_state, chatbot_messages, cleared_input, download_filepath, status_md)`；
  - 若 `message.strip()` 为空：不调用 `assistant.send`，保持原历史与导出路径不变，状态提示“请输入问题或需求后再发送”；
  - 若 `state.session_id is None`：懒创建 `state.session_id = assistant.new_session(self._session_config)`；
  - 调用 `reply = assistant.send(state.session_id, message.strip())`；
  - **异常处理（不崩溃、不污染会话）**：捕获连接失败 / 超时 / HTTP 错误（如 `httpx.ConnectError`、`httpx.TimeoutException`、`httpx.HTTPStatusError` 或其他 `RuntimeError`/`OSError`），保留用户输入文本在输入框方便一键重试，历史记录不写入半截失败消息，状态栏给出清晰中文排查指引（含当前端点与 `uv run tu serve model --exp <exp_id>` 启动提示）；
  - 成功时向 `state.history` 追加 `{"role": "user", "content": user_text}` 与 `{"role": "assistant", "content": reply.content}`（传给 `gr.Chatbot` 时做浅拷贝列表），并按决策 2 刷新导出文件（推荐选项 A：调用 `assistant.export_markdown(state.session_id)` 写入隔离临时目录并清理本会话上一份旧临时文件，返回最新 `.md` 路径供 `gr.DownloadButton` 一键下载）；
  - 状态栏展示中性信息：如当前助手回复轮次（第 N 轮）及友好提示（绝不展示 `corrected` 修正计数）。
- **`reset_session(state: UISessionState | None) -> tuple[UISessionState, list[dict[str, str]], str, None, str]`**
  - 在互斥锁内调用 `_cleanup_session_locked(state)` 立即释放旧 `session_id`（`assistant.close(old_sid)`）并删除旧控制器临时导出文件；
  - 返回全新空的 `UISessionState()`、空对话列表 `[]`、清空输入框 `""`、`DownloadButton(value=None, interactive=False)` 与状态提示“已开启新会话（上一会话上下文已从内存释放）”。
- **`export_current_reply(state: UISessionState | None) -> tuple[UISessionState, Path | None, str]`**
  - 统一复用导出逻辑（选项 A 下由 `send_message` 内部复用；选项 B 下绑定「生成导出文件」按钮）：通过 `assistant.export_markdown(sid)` 拿取最后一轮 Markdown，非空时写入 `self._export_dir / f"tu-reply-{sid}-turn{n}.md"`（UTF-8），删除该会话此前遗留的旧临时文件并更新 `state.export_path`；无回复时返回 `None` 与提示“当前会话暂无可保存的回复”。
- **`cleanup_session(state: UISessionState | None) -> None`**
  - 作为 `gr.State(delete_callback=controller.cleanup_session)` 回调（在关闭/刷新页面约 1 小时过期后由 Gradio `_delete_state` 协程在事件循环线程触发）：先尝试 `self._lock.acquire(blocking=False)`，拿到锁则直接清理 `session_id` 与控制器临时文件，拿不到锁则交给守护线程异步清理，绝不阻塞 asyncio 事件循环。
- **`cleanup_all() -> None`**
  - 进程退出（`finally`）时关闭全部残留活跃会话并清理整个独立临时导出目录（`TemporaryDirectory.cleanup()`）。

#### (2) Gradio 6.31.0 界面布局与事件接线（`create_ui_app` & `launch_ui`）

- **模块顶部隐私防线**：在延迟或顶层 `import gradio` 之前执行 `os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")`，避免 `import gradio` 触发外连遥测。
- **界面布局（面向 V6 现场投屏演示，简洁无冗余）**：
  1. **顶部说明条**（`gr.Markdown`）：标题“工会法律条款智能助手（POC 本地演示）”，一行显示当前只读信息：`知识库版本`、`模型端点`、`追问上限 / 文章篇数配置`，以及简短合规说明（“会话仅保存在本机内存中：点击「新会话」立即释放，关闭或刷新页面后最迟约 1 小时由框架回收，退出进程时全部清理；回答仅供参考，不构成法律意见”）；
  2. **主对话区**（`gr.Chatbot`）：`label="对话记录"`、`height=520`、`render_markdown=True`、`buttons=["copy"]`、`autoscroll=True`、`placeholder="请输入工会法律问题或普法文章需求，例如：我们单位领导不让搞工会"`；
  3. **输入与发送区**（`gr.Row`）：
     - `gr.Textbox`（`lines=2, max_lines=6, show_label=False, placeholder="输入消息，按 Enter 发送（Shift+Enter 换行）"`）；
     - `gr.Button("发送", variant="primary")`；
  4. **会话操作与导出条**（`gr.Row`）：
     - `gr.Button("新会话", variant="secondary")`；
     - `gr.DownloadButton("保存当前回复为 Markdown", variant="secondary", interactive=False)`（若选决策 2 选项 B，则改为「生成 Markdown 文件」`gr.Button` + `gr.DownloadButton` 联动）；
     - 轻量状态提示（`gr.Markdown`），展示当前会话状态或模型未启动的中文排查提示；
  5. **会话状态组件**：`state = gr.State(value=None, delete_callback=controller.cleanup_session)`；
  6. **并发队列**：`demo.queue(default_concurrency_limit=1)`，确保本机 M1 Pro 单推理服务有序排队且浏览器自动展示生成中进度条（适配 7B 单轮 10–20s / 文章 30–60s 生成耗时）。
- **安全启动参数（`launch_ui`）**：
  - `validate_ui_host(host)` 校验监听地址（按决策 3，默认并严格限定 `"127.0.0.1"`，拒绝 `0.0.0.0`、局域网 IP 及任意非本机地址）；
  - `demo.launch(...)` 显式写死：
    - `server_name=host`（显式传参，覆盖可能存在的 `GRADIO_SERVER_NAME` 环境变量）
    - `server_port=port`（默认 `7860`，与 `tu serve model` 默认 `8080` 不冲突）
    - `share=False`（硬编码禁止公网穿透）
    - `inbrowser=inbrowser`（默认 `False`）
    - `footer_links=[]`（精简演示页面底部）
    - 不额外传 `allowed_paths=[export_dir]`（`tempfile.gettempdir()` 已在 Gradio 默认允许范围内且下载走缓存副本，避免将全部标签页的导出临时目录暴露至 `/file=` 路由）
    - `theme=gr.themes.Soft(font=[gr.themes.Font("system-ui"), "sans-serif"], font_mono=[gr.themes.Font("ui-monospace"), "monospace"])`（零外部字体请求）
    - `css=...`（微调居中宽度与引用块可读性，放在 `launch()` 而非 `Blocks()` 以符合 Gradio 6 API）。

#### (3) CLI 入口：`tu ui`（`src/tu_assistant/cli.py`）

```text
uv run tu ui
  [--config configs/app.yaml]
  [--artifacts <path>]
  [--kb-version <ver>]
  [--host 127.0.0.1]
  [--port 7860]
  [--temperature 0.7]
  [--inbrowser / --no-inbrowser]
```

启动流程（严格 fail-fast + 资源回收）：
1. 先调用 `validate_ui_host(host)`：非法 host 红色报错并 `raise typer.Exit(2)`（不加载模型/知识库）；
2. 校验 `port`（`1 <= port <= 65535`）与 `temperature`（`>= 0.0`），非法则报退出码 2；
3. 加载 `cfg = load_app_config(config)` 与 `scfg = session_config_from(cfg)`（非法 `session.*` 配置提前报错退出码 2）；
4. 调用 `TrainedAssistant.from_config(config, kb_version=kb_version, artifacts_dir=artifacts, temperature=temperature, check_same_thread=False)`：
   - 若 `kb.version` 不存在或非法（`KBError`）→ 红色报错并退出码 2，绝不静默建空库；
   - 若 `runtime.model_endpoint` 不在 `runtime.allowed_hosts`（`EndpointNotAllowedError`）→ 红色报错并退出码 2；
5. 在 `try ... finally` 中构造控制器与 `Blocks`、打印本机访问地址、当前知识库版本与模型端点，并调用 `launch_ui(...)`；`finally` 保证无论正常退出还是 `Ctrl+C`，都执行 `controller.cleanup_all()` 与 `assistant.close_kb()`。

---

## 4. 实施步骤与确定性验收方法

### 4.1 实施步骤

1. **底层线程安全与异常回滚小修**：
   - 修改 `src/tu_assistant/kb/store.py`（`open_kb`、`open_kb_from_config` 新增 `check_same_thread: bool = True`）与 `src/tu_assistant/chat/assistant.py`（`TrainedAssistant.from_config` 透传 `check_same_thread: bool = True`）；
   - 按决策 4 在 `src/tu_assistant/chat/orchestrator.py` 的 `process_turn` 全链路补上异常回滚悬挂 `user` `Turn` 与会话状态；
2. **实现 `src/tu_assistant/ui/app.py`**：
   - 实现 `validate_ui_host`、`UISessionState`、`ChatUIController`、`create_ui_app`、`launch_ui`；
   - 保持对 `Assistant` 协议的纯接口依赖，零外部 LLM 导入，零外链字体与遥测；
3. **接入 `src/tu_assistant/cli.py` 的 `tu ui` 命令**：
   - 对齐 `tu chat` 的 `--config` / `--artifacts` / `--kb-version` 解析口径，叠加 `--host` / `--port` / `--temperature` / `--inbrowser` 参数校验与 `finally` 资源清理；
4. **编写确定性单元测试与离线冒烟测试（`tests/unit/test_ui.py`）**（绝不把概率性的 LLM 语义生成写进单元测试）：
   - **安全与隔离**：
     - `validate_ui_host` 放行 `127.0.0.1`（及按决策 3 决定是否放行 `localhost`），拒绝 `0.0.0.0`、`192.168.1.10`、`example.com`、空字符串；
     - `tests/unit/test_runtime_isolation.py` 扫描 `src/tu_assistant/ui/app.py` 全绿；
     - `tu ui` 在 `app.yaml` 配置非法 `runtime.model_endpoint` 或不存在的 `kb.version` 时以退出码 2 拒绝启动，且不建 0 字节空 `.sqlite`；
   - **会话与多轮交互（Stub `Assistant`）**：
     - 空消息 / 纯空白输入不调用 `assistant.send`，不污染历史；
     - 多轮对话复用同一 `session_id`，`history` 严格按 `[{"role": "user", "content": ...}, {"role": "assistant", "content": ...}]` 顺序累加；
     - 两个独立 `UISessionState`（模拟双标签页）拥有互不干扰的 `session_id`、历史与导出文件；
     - 点击「新会话」调用旧会话的 `assistant.close(old_sid)`、删除旧临时 `.md` 文件并清空界面状态；下一轮重新分配新 `session_id`；
     - `delete_callback`（模拟关闭标签页）自动调用 `assistant.close(sid)` 并删除对应临时 `.md` 文件；
   - **Markdown 导出一致性（FR-032）**：
     - 导出文件路径位于独立临时目录（不在仓库内、不在 `artifacts/` 下），文件名以 `.md` 结尾；
     - 导出文件 UTF-8 内容与 `assistant.export_markdown(sid)` 及界面最后一轮助手回复内容**逐字节相等**（含全角引用标记 `〔《…》〕`、`> ` 引文与免责声明）；
     - 连续多轮发送后旧临时文件被自动清理（不堆积残留）；无回复时导出为空且按钮禁用；
   - **异常恢复与跨线程验证**：
     - 模拟 `client.chat` 抛出 `httpx.ConnectError` / `httpx.ReadTimeout` / `httpx.HTTPStatusError`，以及后续 `verify_output` 抛 `sqlite3.Error`、`anonymize_article_text` 抛异常：UI 返回友好中文提示、不崩溃、不写入错误消息到历史；且（按决策 4）底层 `session.messages` 无残留悬挂 `user` 轮、`intent`/`article_task_active` 一并回滚，恢复正常后重试可正常续聊；
     - 真实构造临时只读 SQLite KB + `TrainedAssistant.from_config(..., check_same_thread=False)`，在独立工作线程（`threading.Thread`）调用 `controller.send_message(...)`，验证零 `sqlite3.ProgrammingError`、出处校验与文章脱敏全链路生效；
   - **Gradio 6 离线装配冒烟**：
     - 用 Stub `Assistant` 调用 `create_ui_app(...)`，断言返回 `gr.Blocks` 实例、`analytics_enabled is False`、`delete_cache == (600, 7200)`、构造过程零 `(UserWarning, DeprecationWarning, FutureWarning)`；
     - mock `Blocks.launch` 验证 `launch_ui` 显式传入 `server_name="127.0.0.1"`、`share=False`、`footer_links=[]`、不传 `allowed_paths` 且 `theme._stylesheets == []`；
   - **CLI 参数与退出码测试**：
     - `CliRunner` 调用 `tu ui --host 0.0.0.0` 返回退出码 2；
     - `CliRunner` 调用 `tu ui --config <tmp_app.yaml>`（monkeypatch `launch_ui`），验证正确解析 `kb.version`、`session.*`、透传 `port`/`temperature`，并在退出后执行 `close_kb()` 与临时目录清理；
5. **全量自动化门禁与只读基线核查**：
   - `uv run --offline --no-sync pytest` 全部通过（无新增失败或告警回归）；
   - `uv run --offline --no-sync ruff check src tests` 全绿；
   - `shasum -a 256 -c artifacts/logs/t075/01/output.sha256` 25/25 OK；
   - `git status` 确认无任何意外改动或临时文件泄漏。
6. **本机真实服务 V6 端到端联调验收（验收时执行，单独记录）**：
   - 启动冻结 7B 演示模型：`uv run tu serve model --exp exp-20261116-resume500`（`127.0.0.1:8080`）；
   - 启动本地界面：`uv run tu ui`（`http://127.0.0.1:7860`），确认终端仅监听 `127.0.0.1`、无公网链接、显示 `kb-20261119-045641`；
   - 在本机通过浏览器（或通过本机回环请求 + 界面操作）逐项核对 V6 流程：
     1. **模糊开场 → 追问 → 咨询回答**：输入“我们单位领导不让搞工会” → 确认收到追问 → 补充具体案情与咨询意图 → 确认渲染带 `〔《…》〕` 与 `> ` 引文块及文末免责声明；
     2. **点击「新会话」**：确认界面清空、不再沿用上一会话上下文；
     3. **路线 A 普法文章生成 → 要求修改 → 导出 `.md`**：输入 T075 路线 A 彩排提示词之一（如合同留存或扣身份证单篇提示）→ 再发一句修改要求（如“语言再通俗一些”）→ 点击「保存当前回复为 Markdown」→ 核对下载的 `.md` 文件 UTF-8 内容与页面最后一轮回复**逐字一致**且不含真实身份信息；
   - 结束后关闭 `tu ui` 与 `tu serve model`，确认 7860 / 8080 均已释放、临时导出目录已自动删除、`artifacts/` 无新增脏文件。
7. **更新学习文档**：
   - 在 `docs/learning/07-serving-demo.md` 紧接 `[L7.1]` 增补 `[L7.2]`，在 `docs/learning/00-glossary.md` 补录术语并核对锚点。
8. **走独立只读复审闭环（`.agents/skills/task-review-loop/SKILL.md`）**：
   - 最多 5 轮复审通过后，向用户汇报全部测试、V6 联调记录与复审结果，等待用户最终确认后再勾选 `tasks.md` 并提交。

---

## 5. 学习文档更新点

- **`docs/learning/07-serving-demo.md`**（保留原有 `[L7.1]` 原文与锚点不动；完整章节统筹仍留待 `T073`）：
  - 新增 **`## [L7.2] 本地演示界面的工程边界：Gradio 6 状态隔离、SQLite 跨线程约束与本地隐私护栏`**，用本次真实摸底与实现讲清楚 4 个初学者易踩的工程点：
    1. **为什么 UI 只通过 `Assistant` 协议交互**：命令行 `tu chat`、网页 `tu ui` 和评测运行器复用同一套编排与护栏，后续换检索版（`RetrievalAssistant`）时 UI 零改动；
    2. **Gradio 6 的线程模型与 SQLite `check_same_thread` 踩坑**：解释为何单线程 CLI 正常的代码搬到 Web 线程池立刻触发 `ProgrammingError`，以及 `mode=ro` + `check_same_thread=False` + 互斥锁/单并发队列为何能安全兜底；
    3. **会话“只存内存”在 Web 场景怎么做才算真落实**：区分全局 Python 变量（多标签页串话）与 `gr.State`（按标签页隔离：点击「新会话」与进程退出立即释放，关闭/刷新标签页后最迟约 1 小时由框架 `STATE_TTL_WHEN_CLOSED=3600` 触发 `delete_callback` 非阻塞回收，并说明 Gradio 下载缓存副本的 `delete_cache=(600, 7200)` 生命周期）；
    4. **本地演示的“隐形外连”排查**：除 `share=False` 和只绑 `127.0.0.1` 外，还要关掉框架默认遥测（`GRADIO_ANALYTICS_ENABLED=False` / `analytics_enabled=False`）和外链字体（`GoogleFont` → 系统字体），并避免多余的 `allowed_paths` 扩大 `/file=` 暴露面。
- **`docs/learning/00-glossary.md`**（在 `## 硬件与工具` 中增补 2 条，均链接到 `[L7.2]` 准确锚点）：
  - `会话状态隔离（gr.State）`：Web 框架按浏览器标签页隔离的内存状态容器；点「新会话」或进程退出立即释放，关闭/刷新标签页后最迟约 1 小时由框架触发销毁回调回收。
  - `SQLite 线程亲和（check_same_thread）`：Python `sqlite3` 默认禁止跨线程复用连接对象；在多线程 Web 服务中复用只读连接需显式放开并加锁或按线程隔离。

---

## 6. 待用户拍板的决策清单

以下 4 项请您确认（全部均已给出推荐项与理由；确认后即可回收设计节点并开始编码）：

1. **交付范围：单做 `T069` vs 合并 `T069 + T070`**
   - **选项 A（推荐）：单做 `T069`**（Gradio 演示界面 + `tu ui` + 单元测试 + V6 实机联调）。界面交互与按钮定型后再起草 `T070` 演示剧本，代码复审边界清晰。
   - **选项 B：合并 `T069 + T070`**，同一轮交付界面代码与 `docs/demo-scenarios.md` 演示脚本。

2. **Markdown 导出交互方式（FR-032 + FR-009 权衡）**
   - **选项 A（推荐）：每轮回复后自动刷新 `gr.DownloadButton`，一键直接下载最新回复 `.md`**。每会话仅在隔离系统临时目录保留当前最新 1 份临时 `.md`（绝不写入仓库或 `artifacts/`），新回复自动覆盖旧文件，点击「新会话」/退出进程立即删除、关闭页面后最迟约 1 小时由框架回收（Gradio 下载缓存副本由 `delete_cache=(600, 7200)` 到期或进程退出时清除）；现场演示点击一次即下载，最流畅。
   - **选项 B：按需两步导出**（先点「生成导出文件」按钮再点下载链接）。在用户点击导出前磁盘 0 临时文件，但演示每次导出需点击两次。
   - *补充确认*：是否只需导出“当前会话最后一轮回复”（与 `tu chat /save` 及 `tasks.md`“保存当前回复为 Markdown”一致，**推荐**），还是额外增加“下拉选择导出历史某一轮”控件？

3. **UI 监听主机策略与模型服务未启动时的启动行为**
   - **监听主机**：
     - **选项 A（推荐）：严格只允许 `127.0.0.1`**（字面对齐 `tasks.md` T069“只监听 127.0.0.1”，杜绝 `localhost` 在 macOS 解析到 IPv6 `::1` 的歧义，拒绝 `0.0.0.0` 及任意其他主机；`share=False` 写死）。
     - **选项 B**：与 `tu serve model` 一致，默认 `127.0.0.1`、同时允许 `localhost`。
   - **模型服务未启动时**：
     - **选项 A（推荐）：允许 `tu ui` 启动**（启动时仍严格校验 `kb.version` 与 `runtime.allowed_hosts` 白名单，不合法即退出码 2），当用户发消息且 `mlx_lm.server` 未就绪时在界面给出清晰中文启动提示，方便演示时先开界面或中途重启模型服务。
     - **选项 B**：`tu ui` 启动时强制探测本地模型端点，未启动则直接报错退出。

4. **是否顺带纳入 `orchestrator.py` 的“模型调用异常回滚悬挂用户消息”最小修复**
   - **选项 A（推荐）：纳入本次最小修复**。当 `client.chat(...)` 因断连/超时抛异常时，自动弹出 `process_turn` 刚写入的未配对 `user` `Turn` 后原样抛出，防止重试时出现连续两条 `user` 消息污染多轮对话（正常路径零改动，同时惠及 `tu chat` 与 `tu ui`）。
   - **选项 B**：不改动 `orchestrator.py`，仅在 `ui/app.py` 捕获异常后提示用户点击「新会话」重置。（注：`kb/store.py` 只读连接增加可选 `check_same_thread` 为 Gradio 多线程运行必选项，不受此选项影响。）

---

## 7. 实施与独立复审记录（2026-11-23）

### 7.1 用户拍板决策
4 项决策均按**选项 A（推荐）**落地：单做 `T069`；每轮回复后刷新 `gr.DownloadButton` 一键下载最新一轮回复 `.md` 并由独立临时目录自动覆盖与清理；`--host` 严格仅允许 `127.0.0.1`（`share=False` 写死）且允许 `tu ui` 先行启动并在断连时界面友好提示；顺带纳入 `orchestrator.py` 的异常回滚悬挂 `user` `Turn` 最小修复。

### 7.2 实机 V6 端到端联调验收（基于最终修订后代码重跑）
- 在完成第三方 7 项修订（含 `orchestrator.process_turn` 全链路 `try/except` 回滚、移除 `allowed_paths`、`delete_cache=(600, 7200)`）及 `reviewer-v2` 终审后，使用最终代码重新启动本机 7B 冻结演示模型 `uv run --offline --no-sync tu serve model --exp exp-20261116-resume500`（`127.0.0.1:8080`）与 `uv run --offline --no-sync tu ui --port 7860`（`127.0.0.1:7860`）。
- `lsof -iTCP:8080,7860 -sTCP:LISTEN -P -n` 实测确认两个端口均严格仅监听 `127.0.0.1`，无公网链接。
- HTTP 核查确认首页返回 `200`、HTML 中零 `fonts.googleapis.com` 外链、`/config` 返回 `analytics_enabled: false`。
- 通过 `gradio_client` 走完完整 V6 场景并全部通过（**注：本轮联调仅通过 `gradio_client` 走 API 路径，未做真实浏览器点击下载按钮及关闭标签页实操**；真实浏览器操作及“回复生成后过 5 分钟以上再点击下载”留待 `T071` 补验）：
  1. **多轮咨询**：发送模糊开场与具体案情，确认回复含标准 `〔《…》〕` 引用块、`> ` 原文与文末免责声明；
  2. **新会话**：触发重置回调，确认历史清空、导出按钮置为禁用（`value=None, interactive=False`）；
  3. **路线 A 普法文章生成 → 修改 → 导出 `.md`**：输入合同留存彩排提示词并追发“语言再通俗一些”，不传 `allowed_paths` 下系统临时目录 `.md` 正常进入 Gradio 缓存并下载，`tu-reply-b90cb418a2a3-turn2.md`（1038 bytes）与页面最后一轮回复内容**逐字节完全一致**。
- 联调结束后关闭两个后台服务，`lsof` 确认 7860 / 8080 端口全部释放，`artifacts/` 无新增脏文件。

### 7.3 独立只读复审闭环（共 2 轮，一致通过）
独立只读审查员（`reviewer` / Gemini 4 Neon High，隔离上下文、零文件修改、未触碰 `inputs/`）共完成 2 轮复审：
- **Round 1（结论：需修改）**：
  - 阻断项 1：`tests/unit/test_ui.py` 中 `test_create_ui_app_and_launch_ui_params_zero_warnings` 按 `DeprecationWarning` 且 `filename` 含 `"gradio"` 过滤，无法捕获 Gradio 6 对 `Blocks(theme=...)` 发出的 `UserWarning`（且 `filename` 指向调用方源码）。→ **已修复**：改为断言 `create_ui_app(ctrl)` 期间零 `(UserWarning, DeprecationWarning, FutureWarning)`。
  - 阻断项 2：`test_cli_ui_wires_config_and_cleans_up_resources` 未断言 `kb.version`、`session.*` 与 `temperature` 透传。→ **已修复**：spy `TrainedAssistant.from_config` 与 `create_ui_app` 完整断言 `check_same_thread is False`、`temperature == 0.3`、`kb_version`、`session_config (4/3/10)`、`model_endpoint`；并补充 `test_cli_ui_rejects_invalid_session_config` 反例测试。
  - 非阻断建议 1–3（全部采纳）：`cli.py` 用 `math.isfinite(temperature)` 拦截 `nan`/`inf` 并统一捕获 `yaml.YAMLError`；`app.py` `send_message` 异常兜底扩展纳入 `(ValueError, KeyError, IndexError)` 并补第 2 轮 `HTTPStatusError(500)` 保留首轮历史与导出文件且回滚第 2 轮悬挂 `user` 轮的回归测试；`docs/learning/07-serving-demo.md` `[L7.2]` 精确注明 Gradio 6 标签页关闭后的 TTL 清理机制。
- **Round 2（结论：通过）**：阻断项 0、非阻断建议 0，全部修复复核到位且无新回归。审查节点已回收。

#### 第三方评审修订与复审闭环（`reviewer-v2`，共 2 轮，一致通过）
针对第三方评审基于 `gradio 6.31.0` 源码提出的 7 条意见，全部落地修订后由独立只读审查员 `reviewer-v2`（Gemini 4 Neon High）完成 2 轮复审：
- **第三方 7 项修订落地**：
  1. 统一修正 `ui/app.py`、执行单、`07-serving-demo.md`、`00-glossary.md` 对 FR-009 释放时机的表述（点「新会话」与退出进程立即释放，关闭/刷新标签页后最迟约 1 小时由框架 `STATE_TTL_WHEN_CLOSED=3600` 回收）；
  2. `cleanup_session` 改用 `self._lock.acquire(blocking=False)`，拿不到锁时交由守护线程异步清理，避免阻塞 asyncio 事件循环，并补非阻塞单测；
  3. `delete_cache` 调整为 `(600, 7200)`（2 小时），避免演示讲解超 5 分钟点下载 404，并说明 Gradio 缓存副本生命周期；
  4. `orchestrator.py` 的 `process_turn` 扩大为全链路 `try/except` 截断回滚 `session.messages` 及 `intent`/`article_task_active`，`ui/app.py` 补捕获 `sqlite3.Error` 及中文提示；
  5. 移除多余的 `allowed_paths=[export_dir]`（`tempfile.gettempdir()` 已在默认允许范围且下载走缓存副本），同步更新 CLI、单测与 `[L7.2]`；
  6. §7.2 明确注明 V6 联调由 `gradio_client` 完成、未做真实浏览器点击与关闭标签页实操（留待 `T071` 补验）；
  7. 重跑独立复审通过后更新状态行与终验数字。
- **`reviewer-v2` Round 1（需修改）→ Round 2（通过）**：
  - Round 1 揪出 3 项阻断项：执行单 4 处残留旧表述（`L147`/`L226`/`L256`/`L259`）、`_cleanup_session_locked` 与 `cleanup_all` 交错时可能二次调用 `assistant.close(sid)`、以及并发单测轮询竞态窗口；均已彻底修复（`_cleanup_session_locked` 仅在 `sid in self._active_sessions` 时关闭，单测补齐四条件轮询与交错回归，并采纳非阻断建议补齐 `classify_turn_intent` 后抛错的回滚断言）。
  - Round 2 复核阻断项 0、非阻断建议 0，一致通过，审查节点已回收。

### 7.4 最终门禁验证
- `uv run --offline --no-sync pytest` → **462 passed, 6 xfailed**
- `uv run --offline --no-sync ruff check src tests` → **All checks passed!**
- `shasum -a 256 -c artifacts/logs/t075/01/output.sha256` → **25/25 OK**
- `specs/001-legal-clause-assistant/tasks.md` 中 `T069` 已勾选验收。
