# E003 执行记录

按 [E003](./E003-memorization-vs-exposure.md) 第 3 节逐步记录。原始日志、脚本及结果在
`artifacts/logs/e003/`，不进 git。每条记录包含起止时间、原样命令、输出摘要、验收与偏差。
下文命令保留执行时的原始路径。2026-11-18 起：脚本受版本管理的同名副本在 `scripts/experiments/e00x/`；
探针集移到 `eval/diagnostics/train-probe-v1.jsonl`。副本已核对：`sc016.py`、`probe_stats.py`、
`compare_epoch2.py`、`review_stats.py`、`build_probes.py` 重跑结果与存档输出一致。

## A0：复现训练样本顺序

- 时间：2026-11-17 20:06:47 → 20:43:21。
- 命令：`grep -n 'np.random' .venv/lib/python3.12/site-packages/mlx_lm/lora.py .venv/lib/python3.12/site-packages/mlx_lm/tuner/{trainer.py,datasets.py}`；
  `uv run python artifacts/logs/e003/scripts/unseen_order.py > artifacts/logs/e003/unseen-order.txt`；
  `uv run python artifacts/logs/e003/scripts/unseen_loss.py > artifacts/logs/e003/unseen-loss.txt 2>&1`。
- 关键输出：共 8,921 条；原训练前 500 条全被续训的前 8,421 条重复覆盖，尾部 500
  条一次也未被访问；位置和行号见 `unseen_ids.json`（非隐私原文）。
  训满版 adapter 对随机已训 500 条的 assistant-token 加权 loss 为 **0.475149**，
  漏训 500 条为 **0.564894**（高约 0.090，19%）。
- 验收：通过。顺序重建与 loss 对照均支持漏训假设，纳入 P3 分布内留出对照；
  但 loss 高可能含样本难度波动，不把差值单独当因果证明。
- 偏差与处理：本机 MLX `CacheDataset.itemlen()` 返回的是原始字典长度，
  所有 train 样本只有 `messages` 键，排序为原始 JSONL 顺序而非 token 长度；
  实际复现使用 `np.random.seed(42)`、`permutation(8921)`。
- 原始日志：`artifacts/logs/e003/unseen-order.txt`、`artifacts/logs/e003/unseen-loss.txt`；
  脚本 `artifacts/logs/e003/scripts/unseen_order.py`、`unseen_loss.py`。

## A1：生成训练原题探针

- 时间：2026-11-17 20:07:17 → 20:43:40（A0 后补 P3）。
- 命令：`uv run python artifacts/logs/e003/scripts/build_probes.py > artifacts/logs/e003/probe-build.txt`；
  `uv run pytest tests/unit -q`；`uv run ruff check src tests`。
- 命令（续）：`uv run python artifacts/logs/e003/scripts/build_probes.py --include-p3 > artifacts/logs/e003/probe-build.txt`；
  `uv run python -c 'from tu_assistant.eval.cases import load_cases; cases=load_cases("eval/cases/probe/train-probe-v1.jsonl"); print("loaded",len(cases),"unique",len(set(x.case_id for x in cases)))'`。
- 关键输出：P1 52 题，覆盖 gold 38/60（已知曝光 gold 55 个）；P2 100 题、
  P3 223 题，合计 375/375 唯一。P1K 无需触发（覆盖 ≥30）。
  从探针集前 5 条抽查问句前 15 字及由脚本解析的 gold ID；
  未输出原文或完整问句。
- 验收：通过；单测 63/63，ruff 全绿；A0 确认后已加入 P3。
- 偏差与处理：`note` 保留 train.jsonl 行号供复核；探针集是生成数据，
  不能当成人工审定的 v1 评测集。
- 原始日志：`artifacts/logs/e003/probe-build.txt`；
  `eval/cases/probe/train-probe-v1.jsonl`；脚本 `artifacts/logs/e003/scripts/build_probes.py`。

## A2：adapter 冒烟与原题评测

- 时间：2026-11-17 20:44:19 → 21:24:35。
- 命令：`lsof -i :8080`；
  `env HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1 uv run tu serve model --exp exp-20261116-resume500 > artifacts/logs/e003/serve-7b-resume500.log 2>&1`；
  `env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1 uv run tu serve model --exp exp-20261116-resume500 > artifacts/logs/e003/serve-7b-resume500.log 2>&1`；
  `curl -sf --max-time 4 http://127.0.0.1:8080/v1/models >/dev/null`；
  `uv run python artifacts/logs/e002/scripts/ab.py > artifacts/logs/e003/ab-7b-resume500.txt 2>&1`；
  `uv run tu eval run --cases eval/cases/probe/train-probe-v1.jsonl --kb-version kb-20261113-093057 --exp exp-20261116-resume500 > artifacts/logs/e003/eval-7b-resume500.log 2>&1`。
- 关键输出：A/B 同一题，`default_model` 含标准〔和日期版本，
  基座名不含，两者不相同；375 道探针全部生成，run `run-20261117-124545`。
  manifest `model=default_model`、`exp=exp-20261116-resume500`、`base_model=7B`，
  `gold_clause_issues=[]`。
- 验收：通过；服务已停止，`lsof -i :8080` 与 `ps ... mlx_lm.server` 无输出。
- 偏差与处理：首次启动未指定离线标志，MLX 加载缓存基座时对 HF 镜像发出一次
  模型元信息 GET（未传入训练数据）；发现后立即停止该服务，改用
  `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` 重启，日志覆盖前者；
  后续服务全程离线。不再调用外部 API。
- 原始日志：`artifacts/logs/e003/serve-7b-resume500.log`、
  `artifacts/logs/e003/ab-7b-resume500.txt`、`artifacts/logs/e003/eval-7b-resume500.log`。

## A3：探针统计与判读

- 时间：2026-11-17 21:24:35 → 21:24:50。
- 命令：`uv run python artifacts/logs/e003/scripts/probe_stats.py run-20261117-124545 > artifacts/logs/e003/probe-stats.txt`；
  `cat artifacts/logs/e003/probe-stats.txt`。
- 关键输出：P1 (52)：文件 41、条 15、款 10；P2 (100)：文件 89、条 28、款 10；
  P3 (223)：文件 173、条 50、款 19。条级 P1=0.288、P2=0.280、P3=0.224，
  v1=0.283；P1 对 v1 的非配对 Fisher p=1，P1 对 P3 p=0.365。
  P1 曝光 1/2/3–5 的条级命中分别为 4/10、2/9、9/33，未见单调关系。
- 验收：通过；同一套宽松解析统计文件/条，严格 `cited_clause_ids` 统计款。
  P1 原题低于 0.3、与 v1 接近，按 §2 决策表先进入 B0，再优先 B1；
  不能由此直接认定容量瓶颈。
- 偏差与处理：P1 覆盖 38 个不同 gold，而 v1 有 60 个，非配对 Fisher
  仅为参考，不能据此作因果推断；P3 问法未见过，但条款可能仍在其他训练样本出现。
- 原始日志：`artifacts/logs/e003/probe-stats.txt`、
  `artifacts/logs/e003/scripts/probe_stats.py`。

## B0：加曝光方案估算

- 时间：2026-11-17 20:45:32 → 20:46:20（先行统计，A3 后判读）。
- 命令：`uv run python artifacts/logs/e003/scripts/exposure_options.py > artifacts/logs/e003/exposure-options.txt`；
  `cat artifacts/logs/e003/exposure-options.txt`。
- 关键输出：当前 train 8,921 条，gold 曝光中位 2、零曝光 5、最多 5；
  抽稀前来源 train 19,195 条（旧过采样配置），中位 5、零曝光 **0**、最多 12。
  B1 完整新 epoch 可使当前每个非零曝光条款的训练访问次数增加约一轮，
  但不补齐 5 个 0；B2 重建预计约 16,350 条，实际曝光取决于重新划分/去重。
- 验收：通过；两方案已有相同口径的可重算曝光数据。
- 偏差与处理：**推翻 E003 原文 B0 的“B2 也补不上 5 个零曝光”**；
  来源训练集包含这 5 个条款。E003 正文已订正该事实。
- 原始日志：`artifacts/logs/e003/exposure-options.txt`、
  `artifacts/logs/e003/scripts/exposure_options.py`。

## B1：追加一个 epoch

- 时间：2026-11-17 21:27:22 → 2026-11-18 09:45:43（训练结束）。
- 命令：`uv run python scripts/check_safetensors_finite.py artifacts/train/exp-20261116-resume500/adapters/adapters.safetensors`；
  `lsof -i :8080`；
  `env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1 uv run python scripts/run_training_guarded.py configs/train/demo-7b-epoch2.yaml artifacts/logs/e003/epoch2-guard.log`。
- 关键输出：配置 `configs/train/demo-7b-epoch2.yaml` 锁定原数据集
  `ds-kb-20261113-093057-8410`（8,921 条），seed=43，8,921 步，
  fp32 注意力+NaN 守卫、grad_checkpoint、500 步存档；旧 adapter
  392 张量全有限，8080 端口空闲；guard 进程 PID 98990，PPID=1，
  已创建 `artifacts/train/exp-e003-7b-epoch2/`。最终迭代 8,921/8,921、
  `returncode=0`，耗时 44,283 秒（12.3 小时）；训练日志中无 NaN；
  最终 adapter 392 个张量全部有限。末次 val loss 0.575
  （该验证 loss 波动较大，不单凭 loss 判断条款定位效果）。
- 验收：训练完成且权重健康；B1 的效果仍须用同一探针及 v1 复评，
  各评测前 A/B，记录输出 manifest 后才可判定。
- 偏差与处理：E003 预计 9 小时，但前一轮真实训练耗时约 13.8 小时；
  本轮按实际日志跟踪，不提前承诺完成时间。显式设置离线标志避免访问 HF。
  启动后发现原守护器脱钩时漏传第二个 `guard_log` 参数，运行中的守护进程
  实际写 `/tmp/tu-train-guard.log`（21:27:35 已确认记录 training PID 与路径），
  `artifacts/logs/e003/epoch2-guard.log` 为空；已修复启动器供下次使用，
  **本次未重启训练**，已从实际守护日志归档本轮记录。
- 原始日志：`artifacts/logs/e003/epoch2-guard-final.log`、
  `artifacts/train/exp-e003-7b-epoch2/train.log`。

## B1 复评：人工 v1

- 时间：2026-11-18 09:58:05 → 10:07:45。
- 命令：`uv run python scripts/check_safetensors_finite.py artifacts/train/exp-e003-7b-epoch2/adapters/adapters.safetensors`；
  `env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 uv run tu serve model --exp exp-e003-7b-epoch2 > artifacts/logs/e003/serve-7b-epoch2.log 2>&1`；
  `uv run python artifacts/logs/e002/scripts/ab.py > artifacts/logs/e003/ab-7b-epoch2.txt 2>&1`；
  `uv run tu eval run --cases eval/cases/v1/reviewed.jsonl --kb-version kb-20261113-093057 --exp exp-e003-7b-epoch2 > artifacts/logs/e003/eval-7b-epoch2-v1.log 2>&1`；
  `uv run python artifacts/logs/e003/scripts/compare_epoch2.py > artifacts/logs/e003/compare-epoch2-v1.txt`。
- 关键输出：A/B adapter 与基座回答不同（adapter 有〔和日期，基座无）；
  新 run `run-20261118-020130`，manifest `model=default_model`、
  `exp=exp-e003-7b-epoch2`。与 E002 的同 60 题配对比较：
  文件 45/60 → 45/60，条 17/60 → 18/60，款 9/60 → 9/60；
  条级改进 6 题、退步 5 题，配对精确检验 p=1。
  精确率按有引用题为分母 0.265 → 0.188。
- 验收：v1 评测及模型溯源通过；追加训练未在人工集体现出显著改善。
  探针复评尚在进行，不能最终判读 B1。
- 偏差与处理：第一次 A/B 命令被用户中断、尚无结果，重试后完成，
  没有在未验证 adapter 的情况下运行 v1。
- 原始日志：`artifacts/logs/e003/ab-7b-epoch2.txt`、
  `artifacts/logs/e003/eval-7b-epoch2-v1.log`、
  `artifacts/logs/e003/compare-epoch2-v1.txt`。

## B1 复评：探针集及判读

- 时间：2026-11-18 10:06:16 → 10:44:57。
- 命令：`uv run python artifacts/logs/e002/scripts/ab.py > artifacts/logs/e003/ab-7b-epoch2-probe.txt 2>&1`；
  `uv run tu eval run --cases eval/cases/probe/train-probe-v1.jsonl --kb-version kb-20261113-093057 --exp exp-e003-7b-epoch2 > artifacts/logs/e003/eval-7b-epoch2-probe.log 2>&1`；
  `uv run python artifacts/logs/e003/scripts/probe_stats.py run-20261118-020647 > artifacts/logs/e003/probe-stats-epoch2.txt`；
  `uv run python artifacts/logs/e003/scripts/compare_epoch2.py > artifacts/logs/e003/compare-epoch2-all.txt`；
  `uv run pytest tests/unit -q`；`uv run ruff check src tests scripts/run_training_guarded.py`；
  `git diff --check`。
- 关键输出：第二次 A/B 通过；新 run `run-20261118-020647`，375/375 题，
  manifest `model=default_model`、`exp=exp-e003-7b-epoch2`，gold 问题 0。
  条级 P1 15→22/52（配对 p=0.118），P2 28→51/100（p=3.40e-5），
  P3 50→132/223（p=4.32e-21）；严格款级 P2 10→30、P3 19→80。
  v1 条级 17→18/60（p=1），严格款级 9→9，精确率 0.265→0.188。
  测试 63/63 通过、ruff 和 diff check 通过；服务已停，8080 空闲。
- 验收：通过。新增曝光显著提高训练分布上的定位，**未在独立 v1 集合上测到改善**。
  但 60 题统计功效有限，P1 与 v1 的条款集合也不完全相同，不能证明“泛化毫无变化”；
  P3 初次漏训、第二轮首次见题，增益也包含覆盖效应。
- 偏差与处理：按 E003 (b) 判读表落在“探针上升、评测集不升”，
  优先研究多样问法与检索补全；B2（约 17 小时）未执行，
  必须先由用户确认时间窗口、训练起点及超参数。
- 原始日志：`artifacts/logs/e003/ab-7b-epoch2-probe.txt`、
  `artifacts/logs/e003/eval-7b-epoch2-probe.log`、
  `artifacts/logs/e003/probe-stats-epoch2.txt`、
  `artifacts/logs/e003/compare-epoch2-all.txt`、
  `artifacts/logs/e003/scripts/compare_epoch2.py`。
