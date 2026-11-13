# tu-assistant

工会法律条款智能助手（POC）：把项目方提供的公开法律文档"训进"自有的
本地模型，提供多轮对话咨询（识别条款+引用出处）与普法文章生成。
运行时不调用任何外部服务；条款出处由确定性校验层兜底。

> 当前为 POC 阶段：24 篇语料、单机本机运行，目标是跑通全流程。
> 需求与设计见 `specs/001-legal-clause-assistant/`。

## 仓库内容

- `src/tu_assistant/` — 全部代码（kb 解析、引用校验、合成、训练、评测、对话编排、CLI）
- `inputs/project/001/` — 24 篇公开法律语料（已入库 git）
- `inputs/excluded/` — 4 篇经评估排除的文件及决定依据（spec Clarifications）
- `configs/` — 应用、合成、训练配置
- `eval/cases/` — 评测用例（冒烟集已入库）
- `docs/learning/` — 配套学习文档（原理讲解，按 [L章.节] 编号）
- `specs/`、`docs/`、`AGENTS.md` — 规格、计划、约定

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
# 预期：kb_version=kb-<时间戳>  文件 24 篇 / 条款 ~3800 条
# 校验报告：artifacts/kb/<ver>-parse_report.md
```

抽查条款：

```bash
uv run tu kb list                              # 24 部文档及条款数
uv run tu kb show "中华人民共和国劳动法" 24      # 按标题+条号看原文
```

### 2. 条款关联：抽取 → 人工确认 → 入库

```bash
uv run tu kb relations extract
# 生成 artifacts/kb/<ver>-relations_pending.jsonl（约 35 条候选）
uv run tu kb relations review artifacts/kb/<ver>-relations_pending.jsonl
# 交互核对：输入行号看 from/to 条款，回车=true / n=false / s=跳过
uv run tu kb relations confirm artifacts/kb/<ver>-relations_pending.jsonl
```

### 3. 外部大模型合成训练数据（需要 API Key，约一晚）

```bash
# .env 写一行 TU_EXTERNAL_LLM_API_KEY=sk-...（已被 gitignore）
set -a && source .env && set +a && uv run tu synth sft
# 产出 artifacts/datasets/ds-<kb>-<N>/（train/valid + manifest）
# 调试用 --skip-llm 只生成确定性样本
```

### 4. 训练（本机 QLoRA，1.5B 约 1 小时）

```bash
export HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1
uv run tu train --config configs/train/debug-1.5b.yaml
# 产出 artifacts/train/exp-<时间戳>/（adapters/、train.log、manifest.json）
```

### 5. 服务与对话（运行时完全本机，无外部调用）

```bash
uv run tu serve model --exp exp-<时间戳>    # 起 127.0.0.1:8080
# 另开终端：
uv run tu chat                              # /save /new /quit
```

### 6. 评测

```bash
uv run tu eval run --exp exp-<时间戳> --cases eval/cases/smoke
# 产出 artifacts/eval/run-<时间戳>/（results.jsonl、report.md、manifest.json）
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
