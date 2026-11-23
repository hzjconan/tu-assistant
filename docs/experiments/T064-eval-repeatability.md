# T064 实验记录 · 7B 演示模型重复评测（SC-015）与全 98 题基线

- **日期**：2026-11-23
- **任务**：`T064`（US3 重复评测稳定性验证，同步满足 `T059` / quickstart V5 核销条件）
- **结论**：**SC-015 `PASS`** —— 冻结 7B 演示模型 `exp-20261116-resume500` 在活跃 KB `kb-20261119-045641` 与全 7 类 98 题 `eval/cases/v1` 上经两次独立冷启动评测，**98/98 题输出逐字 100% 一致**，全部 12 项有效指标（含人工终审 `SC-009`）最大波动均为 **`0.0 pp`**（远低于 `≤ 2.0 pp` 阈值）；单次完整评测耗时约 **21 分钟**（21 分 06 秒 / 20 分 56 秒，远低于 1 个工作日）。

---

## 1. 锁定输入指纹与运行配置

- **代码基线**：Git HEAD `bea2d97fc5f5868c9ac6da460d83922eac4fcedb`（评测期间 `src/`、`tests/`、`configs/`、`eval/cases/v1/` 零改动）
- **冻结 7B 演示模型**：`exp-20261116-resume500`（基座 `mlx-community/Qwen2.5-7B-Instruct-4bit`）
  - 适配器路径：`artifacts/train/exp-20261116-resume500/adapters/adapters.safetensors`
  - SHA-256：`b62a7d0e86f490d946fb69d795d80707f2b3386c1cbb0a0529e6adef2ae18930`
- **活跃知识库**：`artifacts/kb/kb-20261119-045641.sqlite`
  - SHA-256：`40d4ea70333404ccd9724fccddc09c51311de0123ea9416a37549fd7742f13bb`（24 篇法规、3,809 条记录、67 条已确认关联；对 98 题 `gold_clause_issues=[]`）
- **评测集**：`eval/cases/v1`（共 98 题 / 116 轮，全 7 类：`clause_id` 60、`article` 10、`multi_violation` 10、`intent` 10、`refusal` 3、`false_refusal` 2、`exception` 3）
- **推理配置**：纯本机离线推理（`HF_HUB_OFFLINE=1`，`127.0.0.1:8080`，`temperature=0.0`，`use_system_prompt=True`，两轮间优雅关闭并重启 `tu serve model` 消除进程内 `LRUPromptCache` 冷热不对称）

---

## 2. 两轮独立冷启动执行与 E002 路由冒烟

| 轮次 | `run_id` | 服务启动与冒烟 | 评测起止（本机时间） | 墙钟耗时 | 产物与完整性 |
|---|---|---|---|---|---|
| **Run 1** | `run-20261123-051432` | 冷启动 `tu serve model`，`ab.py 0` 通过（`两次输出相同: False`，`default_model` 含 `〔` 与日期标签） | `13:14:32` → `13:35:38` | 21 分 06 秒 | `case_count=98`，`gold_clause_issues=[]`，`config.model="default_model"` |
| **Run 2** | `run-20261123-053832` | 优雅停服并重检输入哈希后重新冷启动，`ab.py 0` 再次通过 | `13:38:32` → `13:59:28` | 20 分 56 秒 | `case_count=98`，`gold_clause_issues=[]`，`config.model="default_model"` |

- **两轮逐字一致性核验**：
  - 98/98 题 `final_raw` 逐字完全一致；
  - 98/98 题全部轮次 `turns[].content` 逐字完全一致（含 10/10 普法文章题）；
  - 逐题通过/失败状态零变化。

---

## 3. 普法文章评审流程（离线 DeepSeek 初审 + 人工终审）

遵循宪章原则 III/IV 与双文件防重复计数隔离：

1. **离线初审草稿**：通过 `scripts/experiments/t064/deepseek_review_articles.py`（调用 `synth.llm.from_config`、`deepseek-chat`、`temperature=0.0`、`seed=42`、`input_source="eval_case"`，不侵入 `src/`、零触碰 `inputs/`）仅发送虚构题目/`rubric`、KB 公开法条与本地模型交付稿，产出草稿 CSV `artifacts/logs/t064/reviews-deepseek-draft.csv`（`reviewer="deepseek-chat-draft"`）与审阅单 `artifacts/logs/t064/article-review-sheet.md`（因 10 题两轮逐字一致，按决策 3a-A 共 10 次 API 调用：`prompt_tokens=10,396`、`completion_tokens=1,970`）。
2. **人工复核纠偏与终审落盘**：逐题核对原文后，发现 DeepSeek 对 `article-009` 误将第 1 轮普通咨询轮（`expect_articles=[None, 3]`）出现当事人名记为身份泄露（第 2 轮文章已改用虚构名，无泄露），人工修正该题 `comment` 归因为“第 2 轮仅出 1 篇、标题不符标准二级三段式、错引工会法第 22 条且缺欠薪条款”。终审结果写入受 Git 管理的 [`eval/reviews/t064-reviews.csv`](../../eval/reviews/t064-reviews.csv)（仅含 `reviewer="user"`，覆盖两轮共 20 行）。
3. **维度与 `SC-010` 口径**：
   - `correctness`（9 题）：`0 pass / 3 minor_issue (001, 006, 008) / 6 fail (002, 003, 004, 005, 009, 010)` → **`SC-009 = 0.000 (0/9)`**；
   - `diversity`（5 道多篇题 `001–004, 009`）：5 题在多篇生成轮次经自动拆篇实得篇数均为 `0`（`< 2` 篇），按决策 3b-A 不填 `diversity` 行，避免把拒答/未拆篇误计为“实质重复”，两轮 `SC-010` 同为 `None`（在 `--sc015` 中跳过）；
   - `other`（应拒答题 `article-007`）：`fail`（仅套用通用功能拒答话术，未说明证券期货超出知识库范围；不影响 SC-009/SC-010 数值，计入失败清单）。

---

## 4. 全 98 题指标汇总与 SC-015 稳定性判定

正式落盘对比目录：`artifacts/eval/compare-20261123-145054/`（`compare.md` + `manifest.json`，`sc015_passed=true`，`inputs.reviews="eval/reviews/t064-reviews.csv"`）。

| 编号 | 指标 | Run 1 (`051432`) | Run 2 (`053832`) | 最大波动 | SC-015 判定 | POC 目标（仅参考） |
|---|---|---|---|---|---|---|
| SC-001 | 意图确认率（≤3 轮） | `0.900`（9/10） | `0.900`（9/10） | `0.0 pp` | **PASS** | ≥90%（3 轮内） |
| SC-002 | 条款识别召回率 | `0.121`（n=88） | `0.121`（n=88） | `0.0 pp` | **PASS** | ≥90% |
| SC-003 | 条款识别精确率 | `0.188`（n=62） | `0.188`（n=62） | `0.0 pp` | **PASS** | ≥85% |
| SC-004 | 多违法行为识别率 | `0.150`（n=10） | `0.150`（n=10） | `0.0 pp` | **PASS** | ≥85% |
| SC-005 | 关联条款完整率 | `0.000`（n=2） | `0.000`（n=2） | `0.0 pp` | **PASS** | ≥90% |
| SC-006 | 出处标注完整率 | `0.919`（147/160） | `0.919`（147/160） | `0.0 pp` | **PASS** | 100% |
| SC-007（校验前） | 引用准确率（全分母） | `0.405`（66/163） | `0.405`（66/163） | `0.0 pp` | **PASS** | 100% |
| SC-007（校验后） | 引用准确率（全分母） | `0.669`（109/163） | `0.669`（109/163） | `0.0 pp` | **PASS** | 100% |
| SC-008（范围外） | 范围外正确拒答率 | `0.500`（2/4） | `0.500`（2/4） | `0.0 pp` | **PASS** | ≥95% |
| SC-008（误拒） | 范围内误拒率 | `0.043`（4/94） | `0.043`（4/94） | `0.0 pp` | **PASS** | ≤5% |
| SC-009 | 普法文章正确性（人工终审） | `0.000`（0/9） | `0.000`（0/9） | `0.0 pp` | **PASS** | ≥90% |
| SC-010 | 普法文章实质重复率 | `-`（实得 `<2` 篇） | `-`（实得 `<2` 篇） | `-` | 跳过 | ≤10% |
| SC-011 | 普法文章身份无泄露率 | `1.000`（2/2） | `1.000`（2/2） | `0.0 pp` | **PASS** | 100% |
| 对照 | SC-007（已定位·校验前 / 后） | `0.589` → `0.973`（109/112） | `0.589` → `0.973`（109/112） | — | — | 排除 `incomplete` |
| 分布 | 引用判定（ok/corr/nf/inc） | `66 / 43 / 3 / 51` | `66 / 43 / 3 / 51` | — | — | 非门禁 |
| 辅助 | 引用冲突暂缓交稿 / 篇数符合 | `0 轮` / `3/9` | `0 轮` / `3/9` | — | — | 非门禁 |

**按类别失败数（两轮完全一致，合计 88/98）**：`article` 10/10、`clause_id` 51/60、`exception` 3/3、`false_refusal` 2/2、`intent` 10/10、`multi_violation` 10/10、`refusal` 2/3。

---

## 5. 历史基线只读对账与 SC-016 零回归

1. **历史 SC-016 零回归复核**：
   `uv run tu eval compare --sc016 run-20261117-022645 run-20261117-081504` 退出码 `0`：条级 `1/60 → 17/60`（`p=4.45e-05`）、款级 `9/60 = 15.0%`、基座未知文件子集 `0/30 → 21/30`（`p=3.58e-09`），**总判定 PASS**。
2. **原 60 题 `clause_id` 子集对账**（`run-20261117-081504`［旧 KB `kb-20261113-093057`］ vs 本次 Run 1［新 KB `kb-20261119-045641`］）：
   - `SC-002` 召回率：`0.150` → `0.150`（完全一致，失败数均为 `51/60`）；
   - `SC-006` 出处标注完整率：`1.000 (59/59)` → `1.000 (59/59)`；
   - `SC-007` `ok / incomplete` 由 `34 / 25` 变为 `35 / 24`（`SC-003` 分母 `34→35`），源自 T077 升级至 `kb-20261119-045641` 与口径 C 校验层补齐后 1 条原 `incomplete` 引用得以定位为 `ok`。
3. **原 10 题 `article` 子集对账**（`run-20261122-090101`［T054 后/T056 前］ vs 本次 Run 1［T056 后］）：
   - `SC-011` 保持 `1.000 (2/2)`，引用冲突暂缓交稿保持 `0 轮`，文章篇数符合保持 `3/9`；
   - 范围内误拒率由 `4/9 (0.444)` 降至 `3/9 (0.333)`、`SC-007` 校验后由 `5/6 (0.833)` 升至 `8/9 (0.889)`，源自 T056 接入默认篇数轻量附注后 `article-001` 从原先误拒变为产出 3 篇故事与 3 条可校验引用。

---

## 6. 关键复核命令

```bash
# 1. 自动先验 SC-015（不含人工评审）
uv run tu eval compare --sc015 run-20261123-051432 run-20261123-053832 \
  --out artifacts/logs/t064/compare-auto.md

# 2. 带人工终审 CSV 的单轮只读报告副本
uv run tu eval report run-20261123-051432 \
  --reviews eval/reviews/t064-reviews.csv \
  --out artifacts/logs/t064/report-run1-with-reviews.md

# 3. 带人工终审 CSV 的最终 SC-015 对比与落盘
uv run tu eval compare --sc015 run-20261123-051432 run-20261123-053832 \
  --reviews eval/reviews/t064-reviews.csv --save

# 4. 历史 SC-016 零回归与 T075 哈希锁校验
uv run tu eval compare --sc016 run-20261117-022645 run-20261117-081504
shasum -a 256 -c artifacts/logs/t075/01/output.sha256
```
