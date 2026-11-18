# E002 执行记录

按 [E002](./E002-eval-served-base-model.md) 第 2 节"行动方案"执行，每完成一步追加一条。
原始日志与脚本保存在 `artifacts/logs/e002/`（不进 git）。下文命令保留执行时的原始路径；
脚本受版本管理的同名副本在 `scripts/experiments/e002/`，复现请用后者。

记录模板：

```markdown
## 步骤 N：<标题>

- 时间：YYYY-MM-DD HH:MM:SS → HH:MM:SS
- 命令：
  ```bash
  <原样执行的命令>
  ```
- 关键输出：<摘要>
- 验收：通过 / 未通过。依据：<…>
- 偏差与处理：<无 / 说明>
- 原始日志：`artifacts/logs/e002/<文件>`
```

---

## 执行中止（后台 agent 权限不足，未完成任何步骤）

- 时间：无法采集（`date` 亦被拒）
- 现象：本次后台执行中 `exec` 仅放行只读命令（`ls`/`cat`/`cd`/`grep`/`echo`）；
  下列命令全部被自动拒绝（含工作区内路径）：`date`、`lsof`、`ps`、`pgrep`、
  `uv run`、`python`/`python3`/`.venv/bin/python`、`curl`、`nohup`、`mkdir`、`cp`、`rm`、`pkill`、`kill`；
  `/tmp` 整个目录在沙箱范围外。
- 影响：步骤 0 的进程/端口检查与 pytest、步骤 1 的 pytest+ruff 验收、步骤 2–5 的
  服务启动/A/B 冒烟/评测、步骤 4 的 ckpt4000 副本目录（mkdir/cp）均无法执行；
  按方案"大面积被拒则停下"的要求中止，未改动任何源码。
- 处理建议：在主会话前台执行，或为本会话补授上述命令；`ps`/`pgrep`/`lsof`/`date`
  需一并授权（E002 步骤 0 原文用到 `ps aux`）。
- 已核实的静态事实（供续跑参考）：
  - `artifacts/serve/current.json` 仍为旧格式 `{"model": "mlx-community/Qwen2.5-7B-Instruct-4bit", ...}`；
  - `exp-20261116-resume500/adapters/` 含 `0004000_adapters.safetensors` 等 16 个检查点
    及最终 `adapters.safetensors`+`adapter_config.json`；
  - `scripts/check_safetensors_finite.py` 存在；ckpt500 副本的 manifest 可作 ckpt4000 模板；
  - `/tmp/ab.py` 无法确认（/tmp 在沙箱外），续跑时按步骤 2 重写并存档到 `artifacts/logs/e002/scripts/`。

---

## 执行中止（第 3 次后台执行：`.devin/config.local.json` 已配置，但关键命令仍被拒）

- 时间：约 2026-11-17 12:29–12:30（`date` 仍被拒，以本文件写入后的 mtime 近似）
- 现象：本次只读命令已放行并实测通过——`ls`、`cat`、`echo`、`ps`、`wc`、
  `git status`（推断为会话内既有授权或内置安全名单）；但 E002 工作流必需的命令
  全部被自动拒绝：`date`、`pgrep`、`lsof`、`curl`、`env`、`python3`、
  `uv run`（`uv run python -c` / `uv run pytest` 均拒）、`pkill`。
  `mkdir`/`cp`/`rm`/`nohup` 未逐一试探，同类命令预计同样被拒。
- 影响：步骤 0 的 `lsof -i :8080` 与 `uv run pytest` 无法验收；步骤 1 的
  pytest/ruff 验收、步骤 2 的服务启动与 A/B（curl）、步骤 3–5 评测、步骤 4 的
  ckpt4000 副本（mkdir/cp）、服务停止确认（lsof/pkill）均无法执行。
  按方案"大面积被拒则停下"的要求中止，未改动任何源码与 artifacts。
- 已核实的静态事实（供续跑参考，2026-11-17 探测）：
  - `ps aux` 输出中无 mlx_lm 进程残留；
  - `artifacts/serve/current.json` 仍是旧格式
    `{"model": "mlx-community/Qwen2.5-7B-Instruct-4bit", "exp": "exp-20261116-resume500", "endpoint": "http://127.0.0.1:8080/v1"}`；
  - 步骤 1 的三处改动均未做：`cli.py:340-347` 仍写 `{"model": base, ...}`；
    `runtime/client.py:40` 仍为 `model: str = "default"`；
    `eval/runner.py:196-200` config 仍缺 `exp`/`base_model`；
  - `exp-20261116-resume500/adapters/0004000_adapters.safetensors` 存在，
    `exp-20261116-resume500-ckpt4000/` 副本目录尚未创建；
  - `artifacts/logs/e002/scripts/` 目录存在（空）。
- 处理建议：`.devin/config.local.json` 的 `Exec(...)` 允许规则对后台子 agent
  似乎未生效（或被内置安全名单覆盖）——放行的全是只读命令。请在主会话前台
  执行本方案，或确认 allow 规则对后台 agent 的适用方式后重试。

---

## 步骤 0：前置检查

- 时间：2026-11-17 16:11:56 → 16:12:40
- 命令：
  ```bash
  ps aux | grep -E "mlx_lm" | grep -v grep
  lsof -i :8080
  uv run pytest tests/unit -q
  ```
- 关键输出：ps/lsof 均无输出（rc=1）；pytest 输出 58 个 `.`，全部通过。
- 验收：通过。无残留 mlx 进程，8080 空闲，58 项单元测试全绿。
- 偏差与处理：无。
- 原始日志：本步输出短小，直接记录在案，未另存文件。

---

## 步骤 1：修复客户端的模型名

- 时间：2026-11-17 16:13 → 16:16
- 命令：（源码编辑，非 shell 命令；验收命令如下）
  ```bash
  uv run pytest tests/unit -q
  uv run ruff check src tests
  grep -n '"default_model"' src/tu_assistant/cli.py src/tu_assistant/runtime/client.py
  ```
- 改动：
  1. `src/tu_assistant/cli.py`（serve_model，约 337–348 行）：`current.json` 改写为
     `{"model": "default_model", "base_model": <基座名>, "exp": ..., "endpoint": ...}`，
     并补充注释说明 mlx_lm.server 的 default_model 路由语义。
  2. `src/tu_assistant/cli.py` `_model_name`：逻辑未动（仍读 current.json 的 `model`）。
  3. `src/tu_assistant/runtime/client.py:40`：`ModelClient` 的 `model` 默认值
     `"default"` → `"default_model"`。
  4. `src/tu_assistant/eval/runner.py`（write_manifest 前，约 186–197 行）：读取
     `artifacts/serve/current.json`，manifest config 增加 `exp`（缺失时回退 exp_id）
     与 `base_model`。
  5. 新增 `tests/unit/test_served_model_name.py` 4 个用例：current.json→default_model、
     显式配置覆盖、ModelClient 默认值、mock httpx 检查请求体 model 字段。
- 关键输出：pytest 62 个 `.` 全过（58+4）；ruff `All checks passed!`；
  grep 在 cli.py:337/343 与 client.py:40 命中。
- 验收：通过。三项验收条件全部满足。
- 偏差与处理：无（改动点与 E002 一致；`_model_name` 按要求未动）。
- 原始日志：输出短小，记录在案。

---

## 步骤 2：A/B 冒烟验证（7B 训满版 exp-20261116-resume500）

- 时间：2026-11-17 16:14 → 16:18
- 命令：
  ```bash
  HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1 \
    nohup uv run tu serve model --exp exp-20261116-resume500 \
    > artifacts/logs/e002/serve-7b-resume500.log 2>&1 &
  for i in $(seq 1 60); do curl -s -o /dev/null -w "%{http_code}" \
    http://127.0.0.1:8080/v1/models | grep -q 200 && break; sleep 3; done
  cat artifacts/serve/current.json
  uv run python artifacts/logs/e002/scripts/ab.py
  ```
- 关键输出：
  - `current.json`：`{"model": "default_model", "base_model": "mlx-community/Qwen2.5-7B-Instruct-4bit", "exp": "exp-20261116-resume500", ...}`；
  - `default_model`：含〔=True，含日期版本=True，一句结论 + 标准引用块
    （《劳动合同法》（2012-12-28）第二十四条第2款）；
  - 基座名：含〔=False，含日期版本=False，先列 5 个追问再给通识分析（"第23条第1款"风格）；
  - 两次输出相同：False。
- 验收：通过。两条验收条件均满足（〔+日期标签；两次输出明显不同）。
- 偏差与处理：
  - `/tmp/ab.py` 仍存在但写死了 7B 基座名；为兼容 1.5B 等其它 exp，
    重写为 `artifacts/logs/e002/scripts/ab.py`（从 current.json 读 base_model，
    可选 case_index 参数），符合方案"重写并存档"的要求；
  - 服务日志按执行记录要求存 `artifacts/logs/e002/`（方案示例写 /tmp/serve.log）。
- 原始日志：`artifacts/logs/e002/serve-7b-resume500.log`、`artifacts/logs/e002/ab-7b-resume500.txt`、`artifacts/logs/e002/scripts/ab.py`

---

## 步骤 3：重新评测 7B 训满版（exp-20261116-resume500，主结果）

- 时间：2026-11-17 16:18 → 16:23（评测本身约 4 分钟）→ 停服务确认 16:23
- 命令：
  ```bash
  uv run tu eval run --cases eval/cases/v1/reviewed.jsonl \
      --kb-version kb-20261113-093057 --exp exp-20261116-resume500
  uv run python artifacts/logs/e002/scripts/eval_stats.py artifacts/eval/run-20261117-081504
  pkill -f "mlx_lm.server"; lsof -i :8080; pgrep -fl mlx_lm
  ```
- 关键输出：
  - `run_id=run-20261117-081504`，60 条用例；
  - manifest config：`{"model": "default_model", "use_system_prompt": true,
    "exp": "exp-20261116-resume500", "base_model": "mlx-community/Qwen2.5-7B-Instruct-4bit"}`；
  - report.md：条款召回 0.150，精确率 0.265，引用准确率（校验前/后）0.567/0.567，
    引用判定 ok=34 corrected=0 not_found=1 incomplete=25；
  - 统计：含〔 60/60，含日期标签 60/60，gold 全中 9，仅命中文件 18，
    先追问 0，上海文件题 22 题中全中 1、召回 0.045；
  - `lsof -i :8080` 与 `pgrep -fl mlx_lm` 均无输出，服务已停。
- 验收：通过。manifest 的 model/exp 正确；含〔题数 60（非 0），adapter 生效。
- 偏差与处理：
  - 评测耗时约 4 分钟，短于方案预估的 10–20 分钟（模型已在内存中预热、输出较短），不影响结论；
  - 新增统计脚本 `artifacts/logs/e002/scripts/eval_stats.py`（上海文件题按 KB 中
    title 含"上海"的 6 个文件界定，gold 涉及其中 5 个、共 22 题，与 E002 一致）。
- 原始日志：`artifacts/logs/e002/eval-7b-resume500.log`、
  `artifacts/logs/e002/stats-run-20261117-081504.txt`、`artifacts/logs/e002/scripts/eval_stats.py`、
  `artifacts/eval/run-20261117-081504/`（results.jsonl/report.md/manifest.json）

---

## 步骤 4a：重新评测 7B ckpt-500（exp-20261115-124801-ckpt500）

- 时间：2026-11-17 16:19 → 16:56（含一次服务崩溃重试）
- 命令：
  ```bash
  # ckpt4000 副本（步骤 4 中间点准备，在步骤 3 评测期间完成）
  uv run python artifacts/logs/e002/scripts/ckpt4000_setup.py
  uv run python scripts/check_safetensors_finite.py \
    artifacts/train/exp-20261116-resume500-ckpt4000/adapters/adapters.safetensors

  HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1 \
    nohup uv run tu serve model --exp exp-20261115-124801-ckpt500 \
    > artifacts/logs/e002/serve-7b-ckpt500.log 2>&1 &
  uv run python artifacts/logs/e002/scripts/ab.py
  uv run tu eval run --cases eval/cases/v1/reviewed.jsonl \
      --kb-version kb-20261113-093057 --exp exp-20261115-124801-ckpt500
  # 崩溃后重启服务重跑：
  nohup uv run tu serve model --exp exp-20261115-124801-ckpt500 \
    > artifacts/logs/e002/serve-7b-ckpt500-retry.log 2>&1 &
  uv run python artifacts/logs/e002/scripts/ab.py
  uv run tu eval run --cases eval/cases/v1/reviewed.jsonl \
      --kb-version kb-20261113-093057 --exp exp-20261115-124801-ckpt500
  pkill -f "mlx_lm.server"; lsof -i :8080
  ```
- 关键输出：
  - A/B（两次一致，temperature=0 确定性输出）：`default_model` 含〔+日期标签，
    输出〔《劳动合同法》（2012-12-28）第四十一条第3款〕（格式已学到，条款定位错）；
    基座名输出无〔、先列 5 个追问；两次输出不同；
  - **首次评测在第 8 个请求处崩溃**：`RemoteProtocolError: Server disconnected
    without sending a response`，服务进程无声消失（serve 日志止于
    "Prompt processing progress: 42/42"，无 traceback；系统日志无 python
    被杀/崩溃记录，内存充足，疑似 MLX/Metal 层瞬时崩溃）。删除空 run 目录后
    重启服务重跑成功；
  - `run_id=run-20261117-082903`，60 条；manifest config model=default_model、
    exp=exp-20261115-124801-ckpt500；
  - report.md：条款召回 0.000，精确率 0.000，引用准确率 0.033/0.467，
    判定 ok=1 corrected=13 not_found=3 incomplete=13；
  - 统计：含〔 29/60，日期标签 30/60，gold 全中 0，仅文件 8，先追问 0，沪召回 0；
  - `lsof -i :8080` 无输出，服务已停。
- 验收：通过（重试后）。manifest model/exp 正确；A/B 两条均满足；
  含〔29（非 0），adapter 生效（且明显不同于训满版，符合"早期点"预期）。
- 偏差与处理：
  - 评测耗时约 25 分钟（ckpt500 输出普遍偏长）；
  - 首次评测服务崩溃为瞬时故障，重试即恢复，原因未明（无崩溃报告）。
    若后续复现需单独排查，本轮按成功重试记录；
  - ckpt4000 副本脚本 `artifacts/logs/e002/scripts/ckpt4000_setup.py`（仿
    scripts/_ckpt500_setup.py），校验 tensors=392 non_finite=0。
- 原始日志：`artifacts/logs/e002/serve-7b-ckpt500.log`（崩溃）、
  `serve-7b-ckpt500-retry.log`、`ab-7b-ckpt500.txt`、`ab-7b-ckpt500-retry.txt`、
  `eval-7b-ckpt500.log`（崩溃）、`eval-7b-ckpt500-retry.log`、
  `stats-run-20261117-082903.txt`、`scripts/ckpt4000_setup.py`、
  `artifacts/eval/run-20261117-082903/`

---

## 步骤 4b：评测 7B 中间点 ckpt4000（exp-20261116-resume500-ckpt4000，用户确认加做）

- 时间：2026-11-17 16:56 → 16:58
- 命令：
  ```bash
  HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1 \
    nohup uv run tu serve model --exp exp-20261116-resume500-ckpt4000 \
    > artifacts/logs/e002/serve-7b-ckpt4000.log 2>&1 &
  uv run python artifacts/logs/e002/scripts/ab.py
  uv run tu eval run --cases eval/cases/v1/reviewed.jsonl \
      --kb-version kb-20261113-093057 --exp exp-20261116-resume500-ckpt4000
  pkill -f "mlx_lm.server"; lsof -i :8080
  ```
- 关键输出：
  - A/B：`default_model` 含〔+日期标签，引用了正确的第二十四条第2款
    （但数字记错："三年"）；基座名输出无〔、先列追问；两次输出不同；
  - `run_id=run-20261117-085434`，60 条；manifest config model=default_model、
    exp=exp-20261116-resume500-ckpt4000；
  - report.md：条款召回 0.083，精确率 0.119，引用准确率 0.700/0.700，
    判定 ok=42 corrected=0 not_found=1 incomplete=17；
  - 统计：含〔 60/60，日期标签 60/60，gold 全中 5，仅文件 24，先追问 0，沪召回 0；
  - `lsof -i :8080` 无输出，服务已停。
- 验收：通过。manifest 正确；A/B 两条件满足；含〔60，adapter 生效。
- 偏差与处理：评测仅约 2 分钟（输出普遍很短）。学习曲线三个点：
  ckpt500 召回 0.000 → ckpt4000 0.083 → 训满 0.150。
- 原始日志：`artifacts/logs/e002/serve-7b-ckpt4000.log`、`ab-7b-ckpt4000.txt`、
  `eval-7b-ckpt4000.log`、`stats-run-20261117-085434.txt`、
  `artifacts/eval/run-20261117-085434/`

---

## 步骤 5：重新评测 1.5B（exp-20261114-120250，两组）

- 时间：2026-11-17 16:59 → 17:08
- 命令：
  ```bash
  HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1 \
    nohup uv run tu serve model --exp exp-20261114-120250 \
    > artifacts/logs/e002/serve-1b5.log 2>&1 &
  uv run python artifacts/logs/e002/scripts/ab.py
  uv run tu eval run --cases eval/cases/v1/reviewed.jsonl \
      --kb-version kb-20261113-093057 --exp exp-20261114-120250
  uv run tu eval run --cases eval/cases/v1/reviewed.jsonl \
      --kb-version kb-20261113-093057 --exp exp-20261114-120250 --no-system-prompt
  pkill -f "mlx_lm.server"; lsof -i :8080
  ```
- 关键输出：
  - A/B：`default_model` 含〔（旧数据训练的"违法行为认定"结构输出），无日期标签；
    基座名输出无〔、风格不同；两次输出不同 → adapter 路径确认；
  - run-20261117-085921（带 v2 system prompt）：召回 0.017，精确率 0.038，
    引用准确率 0.017/0.538；含〔 50/60，日期标签 51/60，全中 1，沪召回 0；
  - run-20261117-090638（无 system prompt）：召回 0.033，精确率 0.074，
    引用准确率 0.450/0.450；含〔 60/60，日期标签 60/60，全中 2，沪召回 0.045；
  - `lsof -i :8080` 无输出，服务已停。
- 验收：通过（附偏差说明）。manifest 两组均正确；adapter 生效。
- 偏差与处理：
  - **A/B 验收条件 1 部分满足**：含〔=True，含日期版本=False。该模型用旧数据训练，
    引用块写法不同（〔后直接换行接 >，版本标签在多数题中其实出现——评测集统计
    51/60 有日期标签）。判定依据"两次输出明显不同 + adapter 风格输出"成立，
    adapter 挂载无歧义，继续执行；
  - 该模型训练数据分布与 7B 不同（旧数据集、95% 无 system prompt），结果表中
    注明非严格对照。
- 原始日志：`artifacts/logs/e002/serve-1b5.log`、`ab-1b5.txt`、
  `eval-1b5-sysp.log`、`eval-1b5-nosysp.log`、`stats-1b5.txt`、
  `artifacts/eval/run-20261117-085921/`、`run-20261117-090638/`

---

## 步骤 6：汇总与判读

- 时间：2026-11-17 17:08 → 17:10
- 命令：
  ```bash
  uv run python artifacts/logs/e002/scripts/eval_stats.py \
    artifacts/eval/run-20261117-081504 artifacts/eval/run-20261117-082903 \
    artifacts/eval/run-20261117-085434 artifacts/eval/run-20261117-085921 \
    artifacts/eval/run-20261117-090638
  ```
- 关键输出（report.md + 统计脚本合并）：

  | run | 模型 | sysp | 召回 | 精确率 | 引用acc前/后 | 含〔 | 日期 | 全中 | 仅文件 | 沪召回 |
  |---|---|---|---|---|---|---|---|---|---|---|
  | run-20261117-081504 | 7B训满 | v2 | 0.150 | 0.265 | .567/.567 | 60 | 60 | 9 | 18 | .045 |
  | run-20261117-082903 | 7B ckpt500 | v2 | 0.000 | 0.000 | .033/.467 | 29 | 30 | 0 | 8 | .000 |
  | run-20261117-085434 | 7B ckpt4000 | v2 | 0.083 | 0.119 | .700/.700 | 60 | 60 | 5 | 24 | .000 |
  | run-20261117-085921 | 1.5B | v2 | 0.017 | 0.038 | .017/.538 | 50 | 51 | 1 | 17 | .000 |
  | run-20261117-090638 | 1.5B | 无 | 0.033 | 0.074 | .450/.450 | 60 | 60 | 2 | 16 | .045 |

- 判读：7B 训满召回 0.150 < 0.3 → 按 E002 §6 表归入"记忆容量不足"；
  学习曲线仍在上升（0→0.083→0.150）；格式已完全学会（〔60/60），
  瓶颈在"哪条条款适用"的记忆；上海地方文件题召回≈0，
  SFT 基本没把预训练外的新知识教进去。
- 验收：通过。指标齐备，结论写入 E002 §4。
- 偏差与处理：无。
- 原始日志：`artifacts/logs/e002/stats-all.txt`、各 run 的 report.md/results.jsonl

---

## 步骤 7：订正文档

- 时间：2026-11-17 17:10 → 17:20
- 命令：（文档编辑）
  ```bash
  grep -c "E002" docs/experiments/E001-1.5b-citation-failure.md
  grep -n "L5.11" docs/learning/05-training.md
  ```
- 改动：
  1. `E001-1.5b-citation-failure.md`：顶部加"评测结果作废（E002）"醒目提示并
     更新状态行；§2 现象、§3 综合判断、尝试 1 结论、iter500 评测、续训后评测
     及其判读均标注"作废（E002）"并附订正要点，原文保留；§6 汇总表加
     "是否受 E002 影响"列，受影响行注明实测基座与新 run_id。
  2. `E002-eval-served-base-model.md`：状态改为"已完成"；§4 填入 5 个 run 的
     结果表、补充指标与 5 条结论。
  3. `docs/learning/05-training.md`：L5.9"效果"段订正（训练零 NaN 仍成立，
     评测结论改引 E002）；新增 L5.11"评测前先确认测的是你的模型"
     （服务路由机制、反常信号、A/B 冒烟法、可追溯性）。
  4. `specs/001-legal-clause-assistant/tasks.md`：T050/T059 进度注记按新结果订正。
- 关键输出：E001 中 "E002" 命中多处；L5.11 存在（05-training.md:339）；E002 §4 已填。
- 验收：通过。三项验收条件满足。
- 偏差与处理：L5.11 初次插入位置在 L5.10 之前，已移至文件末尾保持编号顺序。
- 原始日志：文档本身即记录。

---

## 步骤 8：收尾

- 时间：2026-11-17 17:20 → 17:22
- 命令：
  ```bash
  pkill -f "mlx_lm.server"; lsof -i :8080; pgrep -fl mlx_lm
  uv run pytest tests/unit -q && uv run ruff check src tests
  git status --short
  ```
- 关键输出：lsof/pgrep 均无输出；pytest 62 项全过；ruff All checks passed；
  git status 23 项改动（含本次：cli.py、runtime/client.py、eval/runner.py、
  tests/unit/test_served_model_name.py、docs/experiments/、
  docs/learning/05-training.md、specs/.../tasks.md；
  artifacts/ 不入 git）。未 commit/push，等用户审阅。
- 验收：通过。
- 偏差与处理：无。
- 原始日志：本记录。

---
