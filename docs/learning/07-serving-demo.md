# 07 推理与演示：模型服务、对话编排与演示界面

> 本章伴随 Phase 4 收口与 Phase 7 实施逐步补全（完整章节由 T073 整理）。当前已写入 `[L7.1]`、`[L7.2]`。

---

## [L7.1] 对话编排层的确定性护栏：文章数量控制如何与微调模型协作

在把自训模型接入真实对话时，常会遇到一个核心设计问题：**哪些要求应该写进提示词交给模型，哪些边界必须由外层 Python 代码确定性守住？**

以本项目 FR-028（“用户可以指定生成的普法文章数量，默认 3 篇，单次上限 10 篇”）在 T056 中的落地为例，我们拆解三个关键工程决策。

### 1. 为什么不改全局 `v2-short` system prompt？

早在 `[L5.4]` 中我们验证过：**训练时和推理时的 system prompt 分布必须一致**。当前冻结的 7B 演示模型（`exp-20261116-resume500`）全部训练样本和 60 题基线评测都使用同一份 ≤200 字的 `v2-short` 模板（`src/tu_assistant/chat/prompts.py`）。

如果直接把“默认写 3 篇，最多 10 篇”硬塞进全局 `SYSTEM_TEMPLATE`：
- 所有普通咨询请求（包括 60 题评测集）都会多出一段训练时从未见过的指令，可能扰动已达标的 SC-016 基线；
- 已经明示写 1 篇的路线 A 演示提示词也会受到不必要的上下文漂移。

**做法**：保持 `v2-short` 正文一字不动；只在编排层判定当前轮次属于“未指定篇数的写稿请求（`use_default`）”时，向**当轮发往模型的临时请求副本**末尾附注一句轻量篇数指令，既不修改 `session.messages` 中用户的原话，也对咨询路径、修改轮和已明示篇数的请求实现 **0 字节扰动**。

### 2. 确定性代码 vs 模型能力边界怎么划分？

和此前已经落地的**出处校验层**（`[L3.5]`）、**身份信息脱敏层**（`[L6.3]`）一样，文章数量控制也遵循“**确定性护栏守底线，模型负责语言与内容**”的分工：

| 层次 | 负责什么 | 能否 100% 确定 |
|---|---|---|
| **确定性代码**（`chat/article_count.py` + `chat/orchestrator.py`） | 配置合法性校验（`default/max` 必须为正整数且 `default <= max`）；解析阿拉伯/中文数字与显式区间；剥离法律引文、屏蔽案情干扰与序数词（如“修改第 2 篇”）；拦截 `<= 0` 或 `> max_article_count` 的请求并毫秒级返回提示；保留首轮实体登记；透传 `app.yaml` 配置到 `tu chat` 和 `tu eval run` | **100% 确定**（可用单元测试完全锁死） |
| **微调模型**（`exp-20261116-resume500`） | 根据指令实际产出对应篇数，并保证各篇在主体、场景、情节上有实质差异（SC-010） | **概率性**（受训练数据与模型容量制约，如未训文章的父模型在开放多篇题上易误拒） |

注意两点细微的隔离：
- **硬拒文案与 SC-008 域外拒答隔离**：超限提示避免使用“无法生成”“超出本知识库”等 `detect_refusal` 关键词，防止评测时把“参数超上限”误统计为“知识库范围外拒答”；
- **实体抽取优先于硬拒早退**：即便用户在首轮说“我叫周岚，在栖梧样例厂工作，帮我写 15 篇普法文章”被超限拦截，编排层仍先登记了 `周岚` / `栖梧样例厂`，下一轮用户改成“写 1 篇”时依然能正确脱敏。

### 3. “入口拦截 + 单次调用” vs “编排层按篇循环”的取舍

实现多篇生成有两条路线：
- **方案 A（本项目 POC 采用）：入口拦截 + 单次调用轻量指令**。始终只发 1 次模型请求，与 T052/T057 训练样本（单轮输出多篇、`---` 分隔）的分布一致，延迟可控（不翻倍），`raw_content`、出处校验、关联补全、脱敏和既有评测单测均保持原子语义。
- **方案 B（正式阶段备选）：编排层按篇循环调用（`for i in range(n)`）**。虽然能把“调用次数”也变成确定的，但在 7B 本地推理环境下延迟会成倍增加（10 篇可能耗时数分钟），而且模型训练时从未见过“现在只写第 2 篇并避开第 1 篇主体”的拆轮指令，容易格式退化，还会让 `raw_content` 和多轮续改上下文变得复杂。

因此 POC 阶段选择方案 A；未来正式阶段若换用更大模型、充裕 GPU，且确有突破单次 `max_tokens` 生成 6–10 篇长文的业务需求，再评估引入方案 B。

---

## [L7.2] 本地演示界面的工程边界：Gradio 6 状态隔离、SQLite 跨线程约束与本地隐私护栏

把命令行里跑通的 `tu chat` 包装成浏览器里可演示的 `tu ui`（T069），看起来只是套一层网页壳，但真落地时会立刻遇到 4 个从单线程 CLI 切到多线程 Web 界面特有的工程边界。

### 1. 为什么 UI 只通过 `Assistant` 协议交互？

`src/tu_assistant/ui/app.py` 中的 `ChatUIController` 只依赖 `Assistant` 协议（`new_session` / `send` / `export_markdown` / `close`），完全不接触 `ModelClient`、SQLite 连接或 Gradio 组件类型：
- **复用全部护栏**：网页端天然共享出处校验、关联条款补全、篇数上限拦截、文章身份信息脱敏与免责声明，不重复写业务规则；
- **可独立单测**：控制器可以直接用轻量 Stub 跑毫秒级确定性单元测试，不需要每次起浏览器或 7B 模型；
- **面向正式阶段零改动替换**：后续如果引入检索对照组 `RetrievalAssistant`，只要实现同一协议，`tu ui` 无需改动一行交互代码。

### 2. Gradio 6 的线程模型与 SQLite `check_same_thread` 踩坑

命令行 `tu chat` 从头到尾在同一个主线程运行，所以 `sqlite3.connect(...)` 默认的 `check_same_thread=True` 不会报错。但 Gradio 基于 FastAPI/AnyIO 线程池分发网页回调：
- 知识库连接在 `tu ui` 启动时的**主线程**打开，用户发消息时的回调却跑在**工作线程**中；如果不放开线程检查，发出第一条消息就会立刻抛出 `sqlite3.ProgrammingError`；
- 本机 SQLite 为 `SERIALIZED` 线程安全模式（`sqlite3.threadsafety == 3`），且运行时知识库以只读 URI（`mode=ro`）打开，无写竞争；我们在 `open_kb` / `TrainedAssistant.from_config` 增加默认仍为 `True` 的可选参数 `check_same_thread`，仅在 `tu ui` 传 `False`，并叠加 `ChatUIController` 互斥锁与 `demo.queue(default_concurrency_limit=1)` 单并发队列，彻底避免跨线程报错和本机 M1 Pro 单推理服务并发争抢。
- 另外，Gradio 6.31.0 中 `gr.Chatbot` 传回 Python 回调时会把字符串包装成多模态块列表，因此不应把 `Chatbot` 当状态源读回解析，而应由独立 `gr.State` 维护纯文本历史、单向输出给 `Chatbot`。

### 3. 会话“只存内存”在 Web 场景怎么做才算真落实？（FR-009）

Web 服务进程是常驻的，不能像 CLI 那样靠进程退出自动丢弃状态，更不能用全局 Python 变量存对话历史（否则打开两个浏览器标签页会互相串话）：
- **按标签页隔离**：每个标签页绑定独立的 `gr.State(value=None, delete_callback=controller.cleanup_session)`，内部只存 `session_id`、纯文本历史与临时导出文件路径；
- **三道释放时机与真实边界**：
  - 点击「新会话」：**立即**调用 `assistant.close(old_sid)` 并删除控制器临时目录里的旧 `.md`；
  - 关闭或刷新标签页：Gradio 6 不会立刻触发 `delete_callback`，而是先在 `routes.py` 把会话标为 `is_closed=True`，并由 `state_holder.py` 强制将保留时间设为 **`STATE_TTL_WHEN_CLOSED = 3600` 秒**，因此**最迟约 1 小时**由框架后台循环回收；
  - 退出 `tu ui` 进程：`finally` **立即**调用 `cleanup_all()` 释放全部残留会话并销毁控制器临时目录，Gradio 也会在退出时清空自身缓存副本（`age=None`）；
- **避免 `delete_callback` 阻塞事件循环**：Gradio 的 `_delete_state` 协程每秒在 asyncio 事件循环线程同步调用 `delete_all_expired_state()`。如果 `cleanup_session` 阻塞等待互斥锁，恰逢另一标签页正在跑 30–60 秒的 7B 推理，整个事件循环会被卡死；因此 `cleanup_session` 先 `acquire(blocking=False)`，拿不到锁时交给守护线程异步清理；
- **导出缓存副本的生命周期**：`gr.DownloadButton` 会把控制器写出的 `.md` 复制一份到 Gradio 自己的缓存目录供浏览器下载。该副本不归控制器删除（点「新会话」不会立刻删掉缓存副本），而由 `delete_cache=(600, 7200)`（每 10 分钟清理超过 2 小时的缓存，兼顾现场演示讲解时长不 404）或进程退出时由框架统一删除；
- **全链路异常回滚**：`orchestrator.py` 在写入本轮 `user` 消息前记录长度，无论后续是 `client.chat(...)` 断连超时，还是 `verify_output` / 知识库查询抛出 `sqlite3.Error`，都会把本轮悬挂的 `user` 消息和会话意图状态完整回滚，避免重试时污染多轮上下文。

### 4. 本地演示的“隐形外连”排查

做到“数据不出域（FR-033）”不能只看 `127.0.0.1` 和 `share=False`，还要堵住框架自带的隐形外网请求与不必要的文件暴露面：
- **关闭遥测**：在 `import gradio` 之前设置 `GRADIO_ANALYTICS_ENABLED=False`，并传入 `gr.Blocks(analytics_enabled=False)`；
- **去掉外链字体**：Gradio 默认主题内置 `GoogleFont`（加载外部字体样式表），改为本机系统字体 `gr.themes.Soft(font=[gr.themes.Font("system-ui"), "sans-serif"], font_mono=[gr.themes.Font("ui-monospace"), "monospace"])`，实测 `_stylesheets == []`；
- **严格监听与最小文件暴露面**：`validate_ui_host` 只放行 `127.0.0.1`（拒绝 `0.0.0.0`、局域网 IP 及 `localhost` 解析歧义），`launch()` 显式传 `share=False`、`footer_links=[]`；由于 `tempfile.gettempdir()` 本来就在 Gradio 默认允许范围且浏览器下载走缓存副本，不额外传入 `allowed_paths=[export_dir]`，避免把所有标签页的导出临时目录暴露到 `/file=` 路由。

---

## [L7.3] 基于底座模型加载训练后权重：动态挂载 Adapter vs 合并权重（Fuse）

用 LoRA / QLoRA 微调结束后，训练目录（如 `artifacts/train/<exp>/adapters/`）里保存的**不是一个完整的新模型**，而是体积很小的**增量补丁（adapter）**。要让它真正跑起来，必须把它和原始底座模型（如 `mlx-community/Qwen2.5-7B-Instruct-4bit`）组合加载。

### 1. 训练产物里到底有什么？

进入任意一次训练的 `adapters/` 目录，通常只有两类核心文件：
- `adapter_config.json`：记录 LoRA 的结构元数据，比如 `rank`（秩 $r$）、`scale`（缩放系数 $\alpha/r$）、注入了哪些层（`num_layers`）等；加载器需要靠它先在底座模型的对应线性层旁搭好低秩分支的架子。
- `adapters.safetensors`（以及各 checkpoint 如 `0000100_adapters.safetensors`）：只存低秩矩阵 $A$ 和 $B$ 的参数权重，体积通常只有几十 MB（对比 4bit 7B 底座的 ~4.3 GB）。

前向推理时，每一处挂载了 LoRA 的线性层等价于：

$$y = W_0 x + \text{scale} \cdot B(A x)$$

其中 $W_0$ 是冻结的底座权重，$A, B$ 是训练得到的增量权重。如果底座换成了别的版本或架构不匹配，形状或语义对不上，加载就会直接报错或输出乱码。

### 2. 两种加载方式：动态挂载 vs 合并权重（Fuse）

在 `mlx-lm` 生态里，基于底座模型使用训练后权重有两种主流做法：

| 维度 | 方式 A：动态挂载（`--adapter-path` / `adapter_path`） | 方式 B：合并权重（`mlx_lm.fuse`） |
|---|---|---|
| **原理** | 启动时先加载只读底座 $W_0$，再把 $A, B$ 挂到对应层上，推理时实时计算 $W_0 x + \text{scale}\cdot B(Ax)$ | 离线把增量加回底座：$W' = W_0 + \text{scale}\cdot BA$，导出为一个**独立的新模型目录** |
| **磁盘占用** | 极小：多个实验共用同一份本地底座缓存，每个实验只占几十 MB | 较大：每合并一次就多出一份完整模型（7B 4bit 约 4.3 GB） |
| **推理延迟** | 略有一点点额外矩阵乘开销（对本机 POC 基本无感） | 零额外分支开销，与原生底座推理完全一致 |
| **量化注意点** | 底座保持 4bit 量化，LoRA 分支以 fp16/bf16 计算，不损失底座量化精度 | 对 4bit 量化底座执行 fuse 时，需先反量化 → 相加 → 再重新量化（`--de-quantize` 或重定量），可能引入轻微再量化误差 |
| **适用场景** | **实验迭代、A/B 对比、多版本快速切换**（本项目 POC 当前采用） | **正式发布、脱离训练目录独立部署**，或交给不支持动态挂 LoRA 的推理引擎 |

常用命令与 Python API 对照：

```bash
# 方式 A1：命令行直接做单次生成测试（动态挂载）
uv run python -m mlx_lm.generate \
  --model mlx-community/Qwen2.5-7B-Instruct-4bit \
  --adapter-path artifacts/train/<exp>/adapters \
  --prompt "劳动合同试用期最长可以约定多久？"

# 方式 A2：启动 OpenAI 兼容 HTTP 服务（动态挂载，本项目 tu serve model 底层即此命令）
uv run python -m mlx_lm.server \
  --model mlx-community/Qwen2.5-7B-Instruct-4bit \
  --adapter-path artifacts/train/<exp>/adapters \
  --host 127.0.0.1 --port 8080

# 方式 B：合并权重，产出独立模型目录（适合发布交付）
uv run python -m mlx_lm.fuse \
  --model mlx-community/Qwen2.5-7B-Instruct-4bit \
  --adapter-path artifacts/train/<exp>/adapters \
  --save-path artifacts/fused/<exp>
```

在 Python 脚本中直接加载并推理：

```python
from mlx_lm import load, generate

# 动态挂载：同时传入底座名/本地路径 + adapter 目录
model, tokenizer = load(
    "mlx-community/Qwen2.5-7B-Instruct-4bit",
    adapter_path="artifacts/train/<exp>/adapters",
)
text = generate(model, tokenizer, prompt="...", max_tokens=256)
```

### 3. 本项目 `tu serve model` 是怎么串起来的？

本项目采用**动态挂载**路线，把加载细节封装在 [cli.py](file:///Users/hzjconan/workspace/tu-assistant/src/tu_assistant/cli.py#L400-L441) 的 `tu serve model --exp <exp>` 中：
1. 读取 `artifacts/train/<exp>/manifest.json` 里的 `config.base_model`，确保底座模型与训练时严格一致；
2. 检查 `artifacts/train/<exp>/adapters` 目录存在；
3. 写入 `artifacts/serve/current.json`，记录 `model="default_model"`、`base_model`、`exp` 和 `endpoint`，供上游的 `tu chat`、`tu ui` 和评测脚本自动读取并做可追溯记录；
4. 启动 `mlx_lm.server --model <base_model> --adapter-path <adapter>`，仅监听本机 `127.0.0.1`。

> [!IMPORTANT]
> 使用 `mlx_lm.server` 动态挂载时，客户端发请求体里的 `model` 字段必须传 `"default_model"`，才会命中 `--adapter-path` 挂载的微调模型；如果传了具体底座名，服务端会重新加载一个**不带 adapter 的裸底座**（详见 [L5.11](05-training.md#l511-评测前先确认测的是你的模型e002-实录) 的真实踩坑记录）。

---

### 可以继续问的问题

- 为什么在正则解析里要专门排除“写了 15 篇文章”和“修改第 2 篇”？中文自然语言规则护栏的常见误伤类型有哪些？
- 如果未来正式阶段改成“编排层按篇循环”，每篇的脱敏状态和 `raw_content` 评测口径应该怎么设计？
- `gr.Blocks(delete_cache=(600, 7200))` 的过期时长为什么既不能设太短（如 5 分钟）也不能无限大？在现场演示体验与本地隐私留存之间如何权衡？
- 对 4bit 量化底座执行 `mlx_lm.fuse` 时，反量化再重新量化具体会带来什么影响？什么时候值得保留 fp16 底座再 fuse？
