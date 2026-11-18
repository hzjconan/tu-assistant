# E002：评测实际调用的是基座模型，没有挂 adapter

- **状态**：**已完成**（2026-11-17 执行，记录见 [E002-run-log](./E002-run-log.md)）；
  **§4 结论 2–4 经 [§6 复审](#6-复审2026-11-17) 修订**，后续检验见 [E003](./E003-memorization-vs-exposure.md)
- **脚本位置**：文中 `artifacts/logs/e002/scripts/*.py` 是执行时的原始路径（不进 git）；
  受版本管理的同名副本在 `scripts/experiments/e002/`，复现请用后者
- **发现日期**：2026-11-17
- **影响范围**：此前所有经 `tu eval run` / `tu chat` 得出的模型效果结论
- **关联文档**：[E001](./E001-1.5b-citation-failure.md)（其中基于评测结果的结论需按本文订正）

---

## 1. 问题

### 1.1 现象（事后回看的反常信号）

- 7B 训满版（`exp-20261116-resume500`，val loss 0.472）与只训了 500 步的 ckpt-500
  （val loss 约 0.89）在 temperature=0 下，**60 题中有 42 题输出逐字相同**；
- 三个模型的输出都没有〔〕引用块，引用写法是基座风格的"《劳动合同法》第23条"；
  训练数据里每条引用都带的 `（YYYY-MM-DD）` 版本标签，**60 题里一次都没出现**；
- 训练 loss 持续下降，评测行为却没有任何变化。

### 1.2 根因

`mlx_lm.server` 只有在请求的 `model` 字段为 **`"default_model"`** 时，才会使用
启动参数 `--adapter-path` 指定的 adapter。如果请求里写的是具体模型名，服务会按
这个名字**重新加载一个不带 adapter 的模型**。

| 位置 | 行为 |
|---|---|
| `.venv/.../mlx_lm/server.py:393-394` | 只为键 `"default_model"` 登记 CLI 的 model 与 adapter |
| `.venv/.../mlx_lm/server.py:477-485` | `load(model_path)`：`adapter_path = self._adapter_map.get(model_path, None)`。模型名不是 `default_model` 时 adapter 为 None，触发重新加载 |
| `src/tu_assistant/cli.py`（`serve_model`，约 338-347 行） | 往 `artifacts/serve/current.json` 写入 `"model": <基座模型名>` |
| `src/tu_assistant/cli.py`（`_model_name`，约 360-371 行） | `runtime.model_name` 为 `default` 时读取 `current.json` 的 `model`，也就是基座模型名 |
| `src/tu_assistant/runtime/client.py:66` | 请求体里 `"model": self.model`，发出的是基座模型名 |

最后一项的由来：最初客户端发的是 `"default"`，服务按"模型名 default"去找模型，返回 404。
当时的修复改成发**具体基座模型名**，404 消失了，但请求从此落到了无 adapter 的基座上。
正确的写法应该是 `"default_model"`。

### 1.3 已完成的验证（2026-11-17）

同一个服务进程（`--model mlx-community/Qwen2.5-7B-Instruct-4bit --adapter-path
artifacts/train/exp-20261116-resume500/adapters`），同一道题（评测集第 1 题，竞业限制期限），
同一个 system prompt，temperature=0，**只改请求里的 `model` 字段**：

| 请求 `model` | 输出要点 | 〔〕块 | 日期版本标签 | 条款 |
|---|---|---|---|---|
| `default_model` | 一句结论 + 标准引用块 | 有 | 有 `（2012-12-28）` | 第二十四条第2款，**命中 gold**（`a24:p2`） |
| `mlx-community/Qwen2.5-7B-Instruct-4bit` | 先追问 5 问再给通识分析 | 无 | 无 | "第23条第1款"（与此前评测里看到的输出一致） |

结论：**训练出的 adapter 是有效的，此前评测测的是基座模型。**

### 1.4 受影响的评测运行

| run_id | 意图评测的对象 | 实际测到的 |
|---|---|---|
| `run-20261113-090033`、`run-20261113-092116` | 冒烟模型 | 基座（1.5B） |
| `run-20261115-025552` | 1.5B 训满（`exp-20261114-120250`） | 基座 1.5B |
| `run-20261115-041717` | 同上，无 system prompt | 基座 1.5B |
| `run-20261116-021610` | 7B ckpt-500 | 基座 7B |
| `run-20261117-022645` | 7B 训满（`exp-20261116-resume500`） | 基座 7B |

### 1.5 结论订正表

| E001 中的结论 | 订正 |
|---|---|
| 1.5B / 7B 条款召回为 0 | **作废**：测的是基座 |
| 尝试 1："mismatch 不是主因" | **作废**：测的是基座 |
| ckpt-500 / 训满版的判读，以及"SFT 路线实锤，建议 RAG" | **作废**：测的是基座 |
| "42/60 与 ckpt-500 逐字相同，行为在 500 步已锁定" | **作废**：两次测的是同一个基座，相同是必然的 |
| fp16 注意力反向溢出根因、fp32 补丁、NaN 守卫、save_every 修复 | **仍成立**：属于训练过程，与评测无关 |
| 数据修复（system prompt 统一、consult 补量、knowledge 抽稀） | 设计仍合理，效果**待重新评测** |

---

## 2. 行动方案

每一步都写明目的、操作、预期结果和验收标准，交给人工或其他 agent 也能独立执行和复核。
所有命令都在仓库根目录 `/Users/hzjconan/workspace/tu-assistant` 下执行。

### 通用约束

- 禁止读取 `inputs/`；禁止读取或输出 `.env`；全程不调用外部 API。
- 同一时间只运行一个模型服务（32GB 内存放不下两个 7B）。
- 抽查输出时，法规原文截断到 15 字以内。

### 执行记录要求

执行过程逐步记录到 [`E002-run-log.md`](./E002-run-log.md)，供事后审阅：

- **每做完一步就追加一条**，不要等全部结束再补写。中途异常退出时，已完成的步骤也有据可查；
- 每条记录包含：
  - 步骤编号与标题；
  - 开始和结束时间（`date "+%F %T"`）；
  - **原样执行的命令**；
  - 关键输出摘要（截取，不贴大段日志）；
  - 验收结果：通过 / 未通过，并写明依据；
  - 偏差与处理：命令改了什么、为什么改，遇到的报错和解决办法；
- 原始日志（服务日志、评测终端输出、统计脚本及其输出）保存到 `artifacts/logs/e002/`，
  不放在 `/tmp`，以免被系统清理。run-log 里写明对应的文件路径；
- 如果新建了统计脚本，同样复制一份到 `artifacts/logs/e002/scripts/`，便于复现；
- 记录中不得出现 `.env` 内容和法规原文（截断规则同上）。

### 步骤 0：前置检查

```bash
ps aux | grep -E "mlx_lm" | grep -v grep     # 预期：无输出
lsof -i :8080                                # 预期：无输出
uv run pytest tests/unit -q                  # 预期：全部通过
```

**验收**：没有残留的 mlx 进程，8080 端口空闲，单元测试全绿。

### 步骤 1：修复客户端的模型名

**目的**：让 `tu chat` / `tu eval run` 请求 `tu serve model` 起的服务时，用的是挂了 adapter 的模型。

**改动**：

1. `src/tu_assistant/cli.py` 的 `serve_model`：`current.json` 改为
   `{"model": "default_model", "base_model": <基座名>, "exp": ..., "endpoint": ...}`，
   基座名保留在 `base_model` 里，供人工查看和写进 manifest。
2. `src/tu_assistant/cli.py` 的 `_model_name`：逻辑不变（仍读 `current.json` 的 `model`），
   读到的就会是 `default_model`。`runtime.model_name` 显式配置成别的值时，仍按配置走，用于调试基座。
3. `src/tu_assistant/runtime/client.py`：`ModelClient` 的 `model` 默认值由 `"default"` 改为 `"default_model"`。
4. `src/tu_assistant/eval/runner.py`：manifest 的 `config` 增加 `exp`、`base_model`
   （从 `current.json` 读取），以后看 manifest 就能知道测的是哪个 adapter。
5. 单元测试（`tests/unit/` 新增或扩展）：
   - `current.json` 的 `model` 为 `default_model` 时，`_model_name` 返回 `default_model`；
   - `ModelClient` 默认请求体里 `model == "default_model"`（mock httpx，或直接检查属性）。

**验收**：

```bash
uv run pytest tests/unit -q          # 全部通过，且新增用例存在
uv run ruff check src tests          # All checks passed
grep -n '"default_model"' src/tu_assistant/cli.py src/tu_assistant/runtime/client.py   # 两个文件都命中
```

### 步骤 2：A/B 冒烟验证（每次评测前都要做）

**目的**：用一道题确认服务确实挂上了 adapter，并且客户端走的是 adapter 路径。

**操作**：

```bash
HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1 \
  nohup uv run tu serve model --exp exp-20261116-resume500 > /tmp/serve.log 2>&1 &
# 轮询直到返回 JSON（7B 加载约 1–2 分钟）
until curl -s http://127.0.0.1:8080/v1/models >/dev/null; do sleep 3; done
cat artifacts/serve/current.json     # 预期 "model": "default_model"
```

然后用评测集第 1 题，分别以 `model=default_model` 和 `model=<基座名>` 各请求一次。
system prompt 用 `build_system_prompt(5)`，temperature=0，max_tokens=400。可以复用 `/tmp/ab.py`；
如果文件已不存在，按以下要点重写：读 `eval/cases/v1/reviewed.jsonl` 第一行的
`input.message`，POST `/v1/chat/completions`，打印"是否含〔"和"是否含 `（YYYY-MM-DD）`"。

**验收**（两条都满足才继续）：
- `default_model` 的输出含〔且含日期版本标签；
- 两次输出**明显不同**。

如果两次相同，说明 adapter 没挂上：停下来排查，不要进入下一步。

### 步骤 3：重新评测 7B 训满版（主结果）

```bash
uv run tu eval run --cases eval/cases/v1/reviewed.jsonl \
    --kb-version kb-20261113-093057 --exp exp-20261116-resume500
```

**预期**：生成新的 `artifacts/eval/run-<id>/`（results.jsonl、report.md、manifest.json），耗时约 10–20 分钟。

**验收**：
- `manifest.json` 中 `config.model == "default_model"`，`exp == "exp-20261116-resume500"`；
- 用 Python 统计 results.jsonl 中 `final_raw` 含〔的题数、含 `（YYYY-MM-DD）` 的题数。
  前者为 0 就说明 adapter 没生效，回到步骤 2。

做完后停掉服务：`pkill -f "mlx_lm.server"`，确认 `lsof -i :8080` 无输出。

### 步骤 4：重新评测 7B ckpt-500（看训练量的作用）

**说明**：本步骤以及可选的中间点评测，**评测的都是已有的模型文件，不做任何训练**。
7B 是一次完整训练，分两段跑完：第一段 `exp-20261115-124801` 跑到第 550 步出现 NaN，
只保住了第 500 步的检查点；第二段 `exp-20261116-resume500` 从这个检查点接着训完
剩余的 8,421 步（下文称"续训"，已完成）。ckpt-500 是整条训练线的早期点，
训满版是终点，两者只有训练步数不同，用来对照"训练量"的作用。

**中间点（用户已确认要做）**：续训期间每 500 步存一次检查点（续训内的第 500…8,000 步，
对应全局第 1,000…8,500 步），全部有效。取续训内的 `0004000_adapters.safetensors`
（全局约第 4,500 步），参照 `exp-20261115-124801-ckpt500` 的做法建副本目录
`artifacts/train/exp-20261116-resume500-ckpt4000/`：复制为 `adapters/adapters.safetensors`，
同时复制 `adapter_config.json`，补一个最小 manifest；先用 `scripts/check_safetensors_finite.py`
校验张量全部有限，再按本步骤评测（同样先做 A/B）。三个点连起来就是一条粗略的学习曲线。

```bash
nohup uv run tu serve model --exp exp-20261115-124801-ckpt500 > /tmp/serve.log 2>&1 &
# 先按步骤 2 做 A/B 验证，再跑评测：
uv run tu eval run --cases eval/cases/v1/reviewed.jsonl \
    --kb-version kb-20261113-093057 --exp exp-20261115-124801-ckpt500
pkill -f "mlx_lm.server"
```

**验收**：同步骤 3。

### 步骤 5：重新评测 1.5B（看模型规模的作用，次要）

注意：1.5B（`exp-20261114-120250`）是用**旧数据集**训的。旧数据里 95% 的样本没有 system prompt，
另外 5% 带的是旧版长 prompt，与现在运行时的 v2 短 prompt 不一致。因此跑两组：

```bash
nohup uv run tu serve model --exp exp-20261114-120250 > /tmp/serve.log 2>&1 &
# A/B 验证后：
uv run tu eval run --cases eval/cases/v1/reviewed.jsonl \
    --kb-version kb-20261113-093057 --exp exp-20261114-120250
uv run tu eval run --cases eval/cases/v1/reviewed.jsonl \
    --kb-version kb-20261113-093057 --exp exp-20261114-120250 --no-system-prompt
pkill -f "mlx_lm.server"
```

**验收**：同步骤 3。结果表中要注明"训练数据分布与 7B 不同，不是严格对照"。

### 步骤 6：汇总与判读

对步骤 3–5 的每个 run 统计以下指标（report.md 里已有的直接取，其余用脚本从 results.jsonl 算）：

| 指标 | 来源 |
|---|---|
| 条款召回率 / 精确率（SC-002 / SC-003） | report.md |
| 引用准确率，校验前 / 校验后（SC-007） | report.md |
| 引用判定分布 ok / corrected / not_found / incomplete | report.md |
| 含〔的题数、含日期版本标签的题数 | 脚本 |
| 命中 gold 条款的题数；只命中 gold 文件、条款不对的题数 | 脚本（`scores.cited_clause_ids` 与 `gold.clauses` 比较） |
| gold 在上海地方文件中的题（共 22 题）的召回 | 脚本（对照 KB 中 doc 标题） |
| 先追问再回答的题数 | 脚本（`RE_QUESTION_LINE`，见 `chat/orchestrator.py`） |

**判读**（对照 spec 中 SC-002 召回 ≥90%、SC-003 精确率 ≥85% 的目标值；POC 阶段只对照，不作验收）：

| 7B 训满版的召回 | 判读 | 下一步方向 |
|---|---|---|
| ≥ 0.6 | SFT 路线基本可行 | 优化训练（见第 3 节），然后推进 US2（普法文章） |
| 0.3 – 0.6 | 有效但不够 | 先做训练侧改进（第 3 节），再评估是否需要 RAG |
| < 0.3 | 记忆容量不足 | 讨论 RAG（E001 尝试 5） |

另外单独观察**上海地方文件题的召回**：这些文件预训练基本没见过，最能说明 SFT 有没有把新知识教进去。

### 步骤 7：订正文档

1. **E001**：在文档开头加醒目提示"评测结果作废，原因与订正见 E002"；
   各尝试中凡基于 `run-20261115-025552` / `-041717` / `run-20261116-021610` / `run-20261117-022645`
   的结论，标注"作废（E002）"；汇总表加一列"是否受 E002 影响"。原文保留，不删除，便于追溯。
2. **E002（本文）**：填写第 4 节的结果和结论，状态改为"已完成"。
3. **`docs/learning/05-training.md`**：
   - L5.9 的"效果"段改写：修复后完整训练零 NaN 这一点仍成立；评测结论改为引用 E002 的新结果；
   - 新增一小节（建议编号 L5.11）"**评测前先确认测的是你的模型**"：
     服务路由机制、A/B 冒烟法、manifest 记录 exp/adapter，以及本次反常信号的识别方法
     （loss 降了但行为不变、不同 checkpoint 输出逐字相同、输出风格与训练数据格式不符）。
4. **`specs/001-legal-clause-assistant/tasks.md`**：T050 / T059 的进度注记按新结果更新。

**验收**：`grep -n "E002" docs/experiments/E001-1.5b-citation-failure.md` 有命中；
L5.11 存在；E002 第 4 节已填写。

### 步骤 8：收尾

```bash
pkill -f "mlx_lm.server"; lsof -i :8080        # 无输出
uv run pytest tests/unit -q && uv run ruff check src tests
git status                                    # 列出改动，等待用户审阅后再提交
```

---

## 3. 训练侧的候选改进（等第 2 节结果出来再选）

仅作备选，**本轮不执行**：

| 方向 | 适用的情况 | 说明 |
|---|---|---|
| 再训 1 个 epoch（**新的训练**：从训满版加载 adapter，把全部数据再过一遍，约一晚） | 召回中等，且学习曲线显示随步数仍在上升 | 当前每条款平均只见过约 1.6 次 |
| 恢复 knowledge 全量（14,240 条，不抽稀） | 上海地方文件题的召回明显偏低 | 冷门知识需要更多重复 |
| 增加 consult 样本 | 只命中文件、条款不对的情况多 | "案情 → 条款"的定位信号还不够 |
| LoRA rank 8 → 16 | 训满后仍然记不住 | 增大可训练容量 |
| SFT + RAG 混合 | 召回 < 0.3 | 架构变更，需回到 spec/plan |

---

## 4. 结果

修复（步骤 1）落地后，按步骤 2–5 重新评测。全部 run 的 manifest 均记录
`model="default_model"`、`exp`、`base_model`；每组评测前 A/B 冒烟确认 adapter 挂载。

| run | 模型 | system prompt | 召回 | 精确率 | 含〔 | 含日期标签 | 上海文件题召回 |
|---|---|---|---|---|---|---|---|
| run-20261117-081504 | 7B 训满（exp-20261116-resume500） | v2 | 0.150 | 0.265 | 60/60 | 60/60 | 0.045（22 题，全中 1） |
| run-20261117-082903 | 7B ckpt-500（exp-20261115-124801-ckpt500） | v2 | 0.000 | 0.000 | 29/60 | 30/60 | 0.000 |
| run-20261117-085434 | 7B ckpt-4000（exp-20261116-resume500-ckpt4000，全局约 4,500 步） | v2 | 0.083 | 0.119 | 60/60 | 60/60 | 0.000 |
| run-20261117-085921 | 1.5B（exp-20261114-120250，旧数据集，非严格对照） | v2 | 0.017 | 0.038 | 50/60 | 51/60 | 0.000 |
| run-20261117-090638 | 1.5B（同上） | 无 | 0.033 | 0.074 | 60/60 | 60/60 | 0.045 |

补充指标（脚本统计，`artifacts/logs/e002/stats-all.txt`）：

- 7B 训满：gold 条款全中 9/60、只命中 gold 文件而条款错 18/60、先追问再回答 0/60；
  引用判定 ok=34 / corrected=0 / not_found=1 / incomplete=25，引用准确率 0.567。
- 学习曲线（7B 同一训练线）：召回 0.000（500 步）→ 0.083（约 4,500 步）→ 0.150（8,921 步），
  仍在上升；ckpt-500 已有〔格式（29/60）但定位全无，ckpt-4000 起格式齐全（60/60）。
- 1.5B adapter 已学会〔格式（带 v2 prompt 50/60、无 prompt 60/60）——E001"几乎不输出引用"
  的标题结论同样是基座行为的误测；但条款定位召回 ≤0.033，容量瓶颈属实。

**结论**（原文保留；结论 2、3、4 及补充指标中"容量瓶颈属实"一句已被 §6 复审修订，以 §6.3 为准）：

1. **此前所有评测结论作废已坐实，且 adapter 是有效的**：修复后三个 7B 检查点
   与一个 1.5B 模型的输出与基座截然不同（〔+日期标签 60/60 vs 0/60），
   E002 的根因判断与修复方向正确。
2. **7B 训满召回 0.150 < 0.3**，按 §6 判读表落入"记忆容量不足"档 →
   **建议转入 RAG（E001 尝试 5）讨论**。与 E001 旧结论方向一致，
   但依据完全不同：不是"没学会格式"，而是"格式全会、条款定位记不住"。
3. **上海地方文件题召回 ≈0**（22 题中全中仅 1）：这些文件预训练基本没见过，
   最能说明 SFT 没把新知识教进去——支持"记忆容量不足"而非"训练量不够"
   之外的解读，但学习曲线仍在上升，再训 epoch（§3 候选）预计收益有限
   （斜率推算难达 0.6 档）。
4. 附带订正：E001 的"行为在 500 步已锁定"（42/60 逐字相同）系同基座重测的
   必然结果；实际三个检查点输出完全不同，训练量是召回的主变量。
5. 执行异常记录：ckpt-500 首评时 mlx_lm.server 在第 8 个请求处无声崩溃
   （RemoteProtocolError，无 traceback、无系统记录），重启后重跑成功，
   原因未明，若复现需单独排查（详见 run-log 步骤 4a）。

## 5. 教训

- **评测前先确认测的是你的模型。** 推理服务可能按请求参数换模型、换 adapter，
  "服务起来了、能返回结果"不代表结果来自你训练的权重。
- **修 bug 时要弄清 API 的语义，不要只看"报错消失了"。** 当时 404 消失了，
  但请求被路由到了另一个模型。
- **反常信号要追到底。** "loss 降了行为不变""不同 checkpoint 输出逐字相同"
  "输出格式不像训练数据"，都是"测的不是这个模型"的强信号。这次它们出现了好几轮，
  都被解释成了模型能力问题。
- （复审补充）**只看一个严格指标容易误判，要拆开看并和基座对比。** 款级召回 0.150
  看上去"几乎没学到"，拆成"文件 / 条 / 款"三级、再和基座比，才看出 SFT 有显著效果，
  瓶颈只在条款级定位。
- （复审补充）**归因要有对应的检验。** "召回 < 0.3 → 记忆容量不足"只是判读表里的
  映射，没有实验区分"容量不足"和"曝光不足"，不能直接拿来做架构决策。

## 6. 复审（2026-11-17）

对 §4 的数据与结论做了独立复核：从各 run 的 `results.jsonl` 重算指标，补了与基座的
同口径对比，并统计 gold 条款在训练集中的曝光次数。

- 脚本：`artifacts/logs/e002/scripts/review_stats.py`
- 输出：`artifacts/logs/e002/review-stats.txt`

### 6.1 核对无误的部分

- 5 个 run 的 manifest 均为 `model=default_model`，`exp`、`base_model` 正确；
- §4 表中的召回、精确率、含〔、日期标签、全中题数、上海题数字，由 results.jsonl
  重算与 `stats-all.txt` 一致；
- 第 1 题（cand-001）训满版确实命中 gold `a24:p2`，与 A/B 记录一致；
- 检查点输出逐字相同的题数：ckpt-500 vs ckpt-4000 为 0/60，ckpt-500 vs 训满为 0/60，
  ckpt-4000 vs 训满为 **5/60**。E001"500 步已锁定"作废成立；§4 结论 4 的"完全不同"
  应为"仅 5/60 相同"。

### 6.2 新发现

**(1) 三级定位：SFT 有显著效果，瓶颈在条款级**

宽松解析（只认 `《文件名》第N条`，〔〕可有可无），基座与 adapter 用同一口径；
"款"为 report 的严格口径。60 题，"沪"为 gold 在上海文件的 22 题。

| 模型 | 文件 | 条 | 款（严格） | 沪：文件 | 沪：条 | 沪：款 |
|---|---|---|---|---|---|---|
| 7B 基座（run-20261117-022645，E002 前误测） | 16 | 1 | 0 | 0 | 0 | 0 |
| 7B ckpt-500 | 15 | 0 | 0 | 1 | 0 | 0 |
| 7B ckpt-4000 | 44 | 11 | 5 | 14 | 2 | 0 |
| **7B 训满** | **45** | **17** | **9** | **14** | **3** | **1** |
| 1.5B 基座（run-20261115-025552，E002 前误测） | 19 | 1 | 0 | 1 | 0 | 0 |
| 1.5B adapter + v2 | 30 | 5 | 1 | 11 | 0 | 0 |
| 1.5B adapter 无 sysp | 38 | 9 | 2 | 12 | 2 | 1 |

- 条级：基座 1/60 → 训满 17/60（Fisher p≈4e-5），提升显著；
- 上海文件定位：基座 0/22 → 训满 14/22。预训练没见过的地方文件，SFT **教进去了"该找哪个文件"**；
- 训满版条级召回 **0.283**，严格款级 0.150。差的 8 题里，5 题条对款错，3 题只写到条
  没写款（该条有多款，被判 incomplete，不计分）。

**(2) gold 条款的训练曝光很低**

按"引用了该条款的 train 样本数"统计（含 consult 的 ×2 过采样副本）：

- 60 个 gold 条款：曝光中位 **2 次**，最多 5 次；**5 个从未出现在训练集中**；
- 上海 gold 的曝光（中位约 2）并不低于非上海 gold；
- 训满版命中题的 gold 曝光为 `[0,1,1,1,1,1,1,4,4]`，未命中题中位 2，
  命中与曝光次数没有明显关系（样本太少，只能说"看不出"）。

**(3) 差异的显著性**

| 比较 | 数据 | p |
|---|---|---|
| 条级：ckpt-4000 vs 训满 | 11/60 vs 17/60 | 0.28 |
| 款级：ckpt-4000 vs 训满 | 5/60 vs 9/60 | 0.39 |
| 款级：训满 沪 vs 非沪 | 1/22 vs 8/38 | 0.14 |

**(4) 训练数据顺序（待核实）**

mlx_lm 在 `lora.run()` 里用 `np.random.seed(42)` 决定数据顺序（`iterate_batches` 的
`np.random.permutation`），续训只加载权重、不恢复迭代位置。如果两段的打乱顺序相同：

- 续训会把第一段跑过的前约 500 个样本再跑一遍；
- 顺序上最后约 500 个样本（约 5.6%）**一次都没训到**。

核实方法与用途见 E003 步骤 A0。

### 6.3 结论修订

| §4 原结论 | 修订 |
|---|---|
| 2. 召回 0.150 < 0.3 → "记忆容量不足" → 建议转 RAG | **证据不足，暂不下结论**。条级召回为 0.283，贴近 0.3 档；"容量不足"和"曝光不足"（gold 中位只见过 2 次）目前分不开。先做 E003 的两项检验再决定是否转 RAG |
| 2. "格式全会、条款定位记不住" | 改为：**格式全会，文件定位 45/60，条级 17/60，款级 9/60**，瓶颈在条款级定位 |
| 3. 上海题召回 ≈0 → "SFT 没把新知识教进去" | **不成立**：上海文件定位从 0/22 提到 14/22，新知识教进去了一部分，缺的是条款级定位。上海与非上海的款级差异 p≈0.14，只能算"偏低的迹象" |
| 3. 学习曲线 → "再训 epoch 收益有限（斜率推算难达 0.6 档）" | **不成立**：只训了 1 个 epoch，曲线上靠后的点见过更多新数据，曲线上升混合了"覆盖"和"重复"两个因素；三个点之间差异不显著（p 0.28–0.39）。不能据此外推再训一轮的收益 |
| 4. "三个检查点输出完全不同" | 改为：ckpt-500 与另两个点 0/60 相同；ckpt-4000 与训满 **5/60** 相同 |
| 补充指标："1.5B……容量瓶颈属实" | **不成立**：1.5B 用旧数据集训练，与 7B 不是对照，只能说"表现更差"，不能归因到容量 |

### 6.4 其他问题

- **引用准确率有两套口径**：report.md 的分母含 incomplete（训满版 34/60=0.567）；
  `metrics.citation_accuracy` 的分母不含 incomplete。§4 用的是前者。
- **ckpt-500 有退化输出**：30/60 题无任何引用，最长一条输出 14,337 字（疑似复读）。
- **E002-run-log 保留了两条"执行中止"记录**（后台权限不足时写入），是否删除待用户决定。

### 6.5 修订后的判读

> 7B SFT 有效：格式 60/60；gold 文件定位从基座的 16/60 提到 45/60（上海文件 0/22 → 14/22）。
> 瓶颈在条款级定位：条级召回 0.283，款级 0.150。gold 条款在训练集中位只出现 2 次，
> 5 个从未出现，"曝光不足"与"容量不足"目前分不开。是否转 RAG，先做
> [E003](./E003-memorization-vs-exposure.md) 的两项检验再定：
> (a) 训练原题记忆测试；(b) 视 (a) 的结果，再训 1 个 epoch 或恢复 knowledge 全量。
