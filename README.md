# tu-assistant

工会法律条款智能助手（POC）：把项目方提供的公开法律文档"训进"自有的
本地模型，提供多轮对话咨询（识别条款+引用出处）与普法文章生成。
运行时不调用任何外部服务；条款出处由确定性校验层兜底。

> 当前为 POC 阶段：24 篇语料、单机本机运行，目标是跑通全流程。
> 需求与设计见 `specs/001-legal-clause-assistant/`。

## 仓库内容

- `src/tu_assistant/` — 全部代码（kb 解析与差异对比、引用校验、合成、训练、评测与报告对比、对话编排、Gradio 演示界面、CLI）
- `inputs/project/001/` — 24 篇公开法律语料（已入库 git）
- `inputs/excluded/` — 4 篇经评估排除的文件及决定依据（spec Clarifications）
- `configs/` — 应用（含 `kb.version`、`runtime`、`session`）、合成、训练配置
- `eval/cases/` — 评测用例（`smoke/` 冒烟集与 `v1/` 98 题全 7 类评测集）与人工评审模板 `eval/review-template.csv`
- `data/relation-reviews/` — 人工审阅确认的条款关联归档
- `docs/learning/` — 配套学习文档（原理讲解，按 [L章.节] 编号）
- `specs/`、`docs/`、`AGENTS.md` — 规格、计划、执行单与约定

**不在仓库**：`artifacts/`（KB sqlite、数据集、适配器、评测输出——
全部是生成物，按下述步骤重新生成）；`.env`（API Key）。

## 前置条件

- macOS（Apple Silicon，建议 ≥32GB 内存）；训练推理走 MLX
- 安装 [uv](https://docs.astral.sh/uv/)
- 一个 OpenAI 兼容的外部大模型 API Key（默认 DeepSeek，
  配置见 `configs/synth.yaml`，可换其他 provider）
- （可选）HF 下载加速：`export HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1`

## 复现步骤

### 0. 环境

```bash
uv sync                  # 按 uv.lock 还原环境（Python 3.12）
uv run pytest            # 应全部通过
```

### 1. 语料 → 知识库（确定性，秒级）

```bash
uv run tu kb import inputs/project/001
# 预期：kb_version=kb-<时间戳>  文件 24 篇 / 条款 ~3800 行（当前活跃版本 kb-20261119-045641 含 3,809 行）
# 校验报告：artifacts/kb/<ver>-parse_report.md
```

抽查条款、对比版本与切换版本：

```bash
uv run tu kb list                              # 24 部文档及条款数
uv run tu kb show "中华人民共和国劳动法" 24      # 按标题+条号看原文
uv run tu kb diff <old_ver> <new_ver>          # 对比两版知识库的新增/删除/修改条款（不输出正文）
# 在 configs/app.yaml 中设置 kb.version 即可零改代码切换运行时知识库版本
```

### 2. 条款关联：抽取 → 人工确认 → 入库

```bash
uv run tu kb relations extract --kb-version <ver>
# 生成 artifacts/kb/<ver>-relations_pending.jsonl
uv run tu kb relations review artifacts/kb/<ver>-relations_pending.jsonl --kb-version <ver>
# 交互核对：逐条标记 confirm / revoke / reject / pending
uv run tu kb relations confirm artifacts/kb/<ver>-relations_pending.jsonl --kb-version <ver>
# 当前活跃库 kb-20261119-045641 已完成两批共 67 条已确认关联（liability_for 26 + references 41）
```

### 3. 外部大模型合成训练数据（需要 API Key，约一晚）

```bash
# .env 写一行 TU_EXTERNAL_LLM_API_KEY=sk-...（已被 gitignore）
set -a && source .env && set +a && uv run tu synth sft
# 产出 artifacts/datasets/ds-<kb>-<N>/（train/valid + manifest）
# 调试用 --skip-llm 只生成确定性样本
```

### 4. 训练（本机 QLoRA：1.5B 调试 / 7B 演示模型）

```bash
export HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1

# 1.5B 快速跑通全流程（Qwen2.5-1.5B-Instruct-4bit，约 1 小时）
uv run tu train --config configs/train/debug-1.5b.yaml

# 7B POC 演示模型（Qwen2.5-7B-Instruct-4bit，已开 --grad-checkpoint，M1 Pro 32GB 约 12–14 小时/轮）
uv run tu train --config configs/train/demo-7b.yaml
# 产出 artifacts/train/exp-<时间戳>/（adapters/、train.log、manifest.json）
# 当前冻结的 7B 演示模型为 exp-20261116-resume500
```

### 5. 服务、对话与本地网页演示界面（运行时完全本机，无外部调用）

需要开 **两个终端窗口**，都在项目根目录下运行：

**终端 1：启动本机模型 API 服务（OpenAI 兼容接口，只监听 `127.0.0.1:8080`）**

```bash
# 使用当前冻结的 7B 演示模型（也可替换为其他 exp-<时间戳>）
uv run tu serve model --exp exp-20261116-resume500
```

看到 `Starting httpd at 127.0.0.1 on port 8080...` 即表示模型 API 服务已就绪（首次加载 7B 权重约需几秒）。

**终端 2：启动本地 Gradio 演示界面（只监听 `127.0.0.1:7860`）**

```bash
uv run tu ui
# 启动后自动打开浏览器可加 --inbrowser：
# uv run tu ui --inbrowser
```

看到 `Running on local URL: http://127.0.0.1:7860` 后，在浏览器打开 **`http://127.0.0.1:7860`** 即可使用：
- 支持多轮对话、点击「新会话」立即释放内存上下文、点击「保存当前回复为 Markdown」一键下载最新回复 `.md`；
- 常用可选参数：`--port 7861`（换端口）、`--kb-version <ver>`（临时覆盖 `configs/app.yaml` 的知识库版本）、`--temperature 0.7`（生成温度）；出于数据不出域要求，`--host` 仅允许 `127.0.0.1` 且禁用公网共享；
- 若先启动 `tu ui` 而忘记开终端 1，网页仍可打开，发消息时会给出中文提示，启动终端 1 后直接重试发送即可；
- **关闭方式**：在两个终端里分别按 `Ctrl+C` 停止（退出时会自动释放内存会话与临时导出目录）。

**备选（命令行对话）**：若不想开网页，终端 2 也可直接运行：

```bash
uv run tu chat                              # /save <路径.md> /new /quit
```

### 6. 评测、报告与版本对比

```bash
# 快速冒烟评测
uv run tu eval run --exp exp-20261116-resume500 --cases eval/cases/smoke

# 完整 98 题（全 7 类）v1 评测
uv run tu eval run --exp exp-20261116-resume500 --cases eval/cases/v1
# 产出 artifacts/eval/run-<时间戳>/（results.jsonl、report.md、manifest.json）

# 结合人工评审表重新渲染报告（只读，不改历史 run 目录）
uv run tu eval report <run_id> --reviews eval/reviews/t064-reviews.csv

# 版本对比 / SC-015 重复评测稳定性（≤2 pp）/ SC-016 验收判定
uv run tu eval compare <run1> <run2> --sc015 --reviews eval/reviews/t064-reviews.csv --save
uv run tu eval compare --sc016 <base_run> <trained_run>
```

完整验证场景（V1–V7）见 `specs/001-legal-clause-assistant/quickstart.md`。

## 常见问题

- **推送/下载走代理失败**：本机 127.0.0.1:8002 代理对 git push 会 503，
  需 `env -u http_proxy -u https_proxy git push`；
- **训练长样本爆内存**：配置里 `grad_checkpoint: true` 已默认开；
- **长时间合成时防休眠**：`nohup caffeinate -is -w <合成进程PID> &`。

## 文档导航

| 想了解的 | 看这里 |
|---|---|
| 需求与验收 | `specs/001-legal-clause-assistant/spec.md` |
| 技术决策 | `specs/001-legal-clause-assistant/research.md` |
| 原理讲解（推荐） | `docs/learning/`（从 01-big-picture 开始） |
| 命令清单 | `specs/001-legal-clause-assistant/contracts/cli.md` |
| 项目约定 | `AGENTS.md` |
