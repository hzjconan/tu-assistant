# 第 4 章 训练数据：外部 AI 怎么用、产出什么样

> 状态：撰写中。本章先覆盖"数据合成"这一段；训练过程与评测结果
> 在跑完后补充。

## L4.1 为什么需要外部 AI

知识库里有 3,809 条条款原文，但**训练数据一条都没有**。

问题在于：条款是"标准书面语"，用户的问题是"大白话"。要让模型学会
"用户描述场景 → 识别条款"，就需要大量成对的（问法, 答案）样本。
这些问法 KB 里没有，也不可能手写几千条——所以让外部大模型
（DeepSeek）**把条款翻译成用户会问的话**，这一步叫数据合成。

合成只做一件事：**改写表达，不创作知识**。条款原文、条款编号、
引用格式全部来自 KB，DeepSeek 只负责生成问法和答案的组织方式。
这是它能做和不能做的边界——知识只能出自 KB，外部模型只是"写手"。

## L4.2 安全边界：什么地方允许碰外部服务

`src/tu_assistant/synth/` 是整个项目**唯一**允许调用外部大模型的
目录，有三道闸：

1. **Key 只从环境变量读**（`TU_EXTERNAL_LLM_API_KEY`，见
   `synth/llm.py`）；不写配置文件、不进 git、不进清单。
2. **输入来源白名单**：每次调用必须声明 `input_source`，只允许
   `kb_clause / kb_document / eval_case / synthetic_template`——
   也就是只有公开的法规原文和我们自己写的模板能发出去。任何
   其他来源（比如用户对话）在代码层面就被断言拦掉（原则 III）。
   前面连通性测试被拦下来就是它在工作。
3. **每次调用记账**：调用方、模型、提示词版本、token 用量都记进
   manifest，可复现可查账。

运行时（`tu chat`、评测、UI）完全不经过这个模块——还有静态测试
保证运行时代码不 import 外部客户端。

## L4.3 一次调用长什么样

以最典型的"改写问答"（`synth/knowledge.py:paraphrase_samples`）为例，
对每条条款发起一次请求：

下面是程序实际发给 DeepSeek 的一条完整提示词（条款为说明用途的
**虚构条款**，真实运行时是 KB 里的原文）：

```text
你是工会法律领域的训练数据编写员。根据下面的法律条款，写一个自然语言问答样本：
- user：一个工会工作人员可能问的问题或描述的场景（口语化，不出现条款编号
  与法规名称）；
- assistant：简短回答，必须引用如下标记给出条款出处：
  〔《职工权益保护条例》（2020-01-01）第十五条第二款〕
  > 用人单位安排职工加班的，应当按照国家有关规定向职工支付加班费。

条款：用人单位安排职工加班的，应当按照国家有关规定向职工支付加班费。
只输出 JSON：{"user": "...", "assistant": "..."}
```

DeepSeek 可能返回（同样是虚构示例）：

```json
{"user": "我们公司最近天天让加班到九点，一分钱加班费都没给过，
 这样合法吗？",
 "assistant": "不合法。用人单位安排加班应当依法支付加班费。\n\n
 〔《职工权益保护条例》（2020-01-01）第十五条第二款〕\n
 > 用人单位安排职工加班的，应当按照国家有关规定向职工支付加班费。"}
```

程序把这两个字段解析成 `messages` 里的 user/assistant 两条消息，
就得到了一条训练样本。

**条款输入从哪来**：整条链路单一来源，没有第二份条款拷贝——

```text
inputs/project/001/*.txt（项目方提供）
  │  tu kb import：parse.py 切分条款
  ▼
artifacts/kb/kb-<时间戳>.sqlite          ← 唯一权威来源
  │  tu synth sft：open_kb() 打开
  ▼
all_clauses(conn) → Clause 对象（clause_id, text, 条款编号…）
  │  knowledge.generate() 逐条遍历
  ▼
c.text 填入提示词 → DeepSeek → 样本（meta.clause_ids 回记该条款）
```

`tu synth sft` 默认用 `artifacts/kb/` 里时间戳最新的 sqlite
（也可 `--kb-version` 指定）。发给 DeepSeek 的 `c.text` 与出处
校验层比对的、`tu kb show` 看到的是同一份原文。

要点：

- **原文和引用标记是我们拼好发给它的**（`{marker}` 和 `{clause_text}`
  由代码从 KB 填入提示词），它是"照着我们给的权威文本写"，而不是
  "凭它自己记忆里的法律知识写"——外部模型的记忆可能过时、记错编号、
  或根本没学过这些地方性文件。万一它仍写出与 KB 不一致的原文，
  L4.5 的逐字校验会丢弃该样本；
- 要求只输出 JSON，程序解析 `user`/`assistant` 两个字段；
- `rewrite_factor` 控制每条条款重复调用几次——每次模型给出的问法
  不同，这就是"同一知识、多种表达"的多样性来源（factor=4 即
  每条款 4 种问法）。

## L4.4 四类样本与产出格式

`tu synth sft` 一次跑四类生成器：

| 类型 | 用不用 LLM | 干什么 |
|---|---|---|
| recitation 背诵 | 不用（模板拼） | "《X法》第N条内容是什么？"→ 引用块原文。教引用格式和知识本身 |
| paraphrase 改写 | 用 | 上节的机制：口语化问法 → 带引用的回答 |
| dialogs 意图确认 | 用 | 多轮脚本：用户说大白话 → 助手追问 ≤N 个问题 → 确认意图后回答。含"用户中途变卦"等变体 |
| consult 咨询 | 用 | 案情描述 → "违法行为认定"结构化回答（主体/适用条款/分析/法律责任），含多违法行为变体 |
| refusal 拒答 | 模板+LLM 改写 | 范围外问题 → 明确拒答并说明边界 |

每条样本落盘是同一种结构（JSONL 一行）：

```json
{"messages": [{"role": "user", "content": "..."},
              {"role": "assistant", "content": "...（含〔引用块〕）"}],
 "meta": {"type": "knowledge", "kind": "paraphrase",
          "doc_id": "3296db5b…", "clause_ids": ["…:a10:p1"]}}
```

`meta` 是给生成过程记账的备注，**不发给 DeepSeek（提示词里只有
marker 和原文），也不参与训练**——`write_dataset` 写 train.jsonl
时只写 `messages`，meta 被剥掉。它只用于溯源与统计：这条样本教
的是哪份文件的哪条、分布是否均衡、是否与评测集撞车。
`clause_ids` 也不是从模型返回里解析出来的——样本是遍历 Clause
对象逐条生成的，调用时程序就把 `c.clause_id` 记进 meta；模型问法
里故意不含条款编号，本来也无法反推。`check_sample` 再复核答案里
的引用块是否解析到同一条款，两层保证关联不会错。

meta 在生产中的三个落点（写、读、剥）：

```python
# 1) 生成时写入（synth/knowledge.py:106）
samples.append({
    "messages": [{"role": "user", ...}, {"role": "assistant", ...}],
    "meta": {"type": "knowledge", "kind": "paraphrase",
             "doc_id": c.doc_id, "clause_ids": [c.clause_id]},
})

# 2) 均衡/统计时读取（train/dataset.py:65、:113）
doc = s.get("meta", {}).get("doc_id")            # 按文件均衡分桶
counts[s.get("meta", {}).get("type", "unknown")] += 1  # manifest 计数

# 3) 写训练文件时剥掉（train/dataset.py:109）
f.write(json.dumps({"messages": s["messages"]}, ensure_ascii=False) + "\n")
#                                    ^ 注意：只有 messages，没有 meta
```

## L4.5 质量关卡：坏样本不许进训练集

外部模型偶尔会写错：条款编号抄错、原文漏字、引用格式不对。
`synth/check.py:check_sample` 对每条样本的 assistant 输出做
**和运行时出处校验层完全相同的检查**：

- 引用能解析、条款在 KB 里存在、引用原文与 KB 逐字一致 → 保留；
- 否则 → 丢弃并记原因（如 `citation_text_wrong`）。

之后还有两道：`dedup_against_eval`（和评测集逐字重复的训练样本
剔除，防止"背答案"），`balance_by_doc`（任一文件样本占比 ≤20%，
防止大文件主导——民法典时代为它准备的，现在仍是保险）。

## L4.6 数据集落地

`train/dataset.py:write_dataset` 把样本按 9:1 切成
`train.jsonl` / `valid.jsonl`，写进 `artifacts/datasets/ds-<kb>-<N>/`：

- `manifest.json`：kb 版本、生成器信息（provider/模型/提示词版本）、
  种子、各类样本计数——谁、用什么、喂了什么，全部可查；
- `artifacts/datasets/latest` 软链始终指向最新数据集，训练配置的
  `data:` 字段就指向它，换数据集不用改配置。

## L4.7 可以继续问的问题

- 为什么改写问答只改"问法"，答案也要模型写？答案写错了怎么办？
- `check_sample` 和运行时校验是同一套代码吗？为什么强调"相同"？
- 多轮对话样本（dialogs）的"中途变卦"变体在教模型什么？
- 为什么评测集要逐字去重？模型记住评测题会怎样？
- 如果某天外部模型升级了，旧样本还能复现吗？（prompt_version 的作用）
