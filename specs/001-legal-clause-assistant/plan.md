# Implementation Plan: 工会法律条款智能助手（条款咨询与普法文章生成）— POC

**Branch**: `001-legal-clause-assistant`（当前在 `main` 上开发） | **Date**: 2026-11-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-legal-clause-assistant/spec.md`

## Summary

为工会工作人员构建一个私有部署的法律助手：多轮对话确认意图后，提供条款咨询与普法文章生成，
所有条款引用必须标明出处且与知识库逐字一致。

**当前阶段为 POC**：30–50 篇文档，原则是**尽量快、只用开发者本机**，目标是跑通全流程、做出可演示的版本以获得认可。
模型效果优化和 1000 篇规模的验证留到正式阶段（research R12）。

技术路线（项目方已确定）：以 Qwen2.5-7B-Instruct 为基座，通过**一次指令微调（SFT）**把知识库内容和对话行为训进模型参数，
推理时不检索；模型输出经过确定性的**出处校验层**按编号查条款库、纠正原文、拦截不存在的引用。详见 [research.md](./research.md)。

## Technical Context

**Language/Version**: Python 3.12（uv 管理，锁定依赖）

**Primary Dependencies**:
- 训练与推理：mlx-lm 0.32（本机 QLoRA 训练；`mlx_lm.server` 提供 OpenAI 兼容接口）
- 基座：Qwen2.5-7B-Instruct（演示用）、Qwen2.5-1.5B-Instruct（调试流程用），均为 Apache 2.0，使用 4bit 版本（research R2）
- 文档解析：python-docx、pdfplumber、beautifulsoup4
- 外部大模型（仅离线合成训练数据）：`openai` 客户端，提供方可配置，默认 DeepSeek
- 界面：typer（命令行）、Gradio（本地网页演示界面）

**Storage**: SQLite（知识库，按版本存文件）；JSONL（评测集、训练数据、评测结果）；会话只在内存中

**Testing**: pytest（单元测试覆盖确定性逻辑；集成测试覆盖校验层与评测流程）

**Target Platform**: 开发、训练、推理、演示全部在开发者本机：macOS Apple Silicon（M1 Pro / 32GB，MLX）。
项目方的 RTX 5090 工作站为可选加速器，默认不使用（research R11）

**Project Type**: Python 单体项目（库 + 命令行 + 本地网页界面）

**Performance Goals**: 仅作参考（spec SC-013）。本机实测 7B 生成约 35 tok/s：咨询回答约 10–20 秒，3 篇普法文章约 1 分钟

**Constraints**: 运行时不得调用外部服务（端点白名单）；输出条款原文 100% 与知识库一致（校验后）；
长样本训练须开梯度检查点（实测 7B 长样本峰值 23GB → 11.5GB）；不使用云 GPU；
本机训练时不能同时演示

**Scale/Scope**: 知识库 30–50 篇；评测集 60–80 题；训练数据约 2–4M token；7B 训一轮约一晚（research R10）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 是否符合 | 依据 |
|---|---|---|
| I. 条款准确与出处可溯（不可豁免） | ✅ | 统一引用格式 + 出处校验层：找不到的引用删除，原文不一致的替换为知识库原文，裸引用记为失败（research R5、contracts/citation-format.md）；知识库是唯一权威来源 |
| II. 不编造，可拒答（不可豁免） | ✅ | 拒答与"信息不足时追问"作为 SFT 样本类型训练，并有独立评测类别（R3、R9）；免责提示由编排层固定追加（R6） |
| III. 用户数据不出域（不可豁免） | ✅ | 会话只在内存中；运行时端点白名单；外部客户端只存在于离线合成模块并有测试检查；评测不调用外部服务；评测集与训练数据只来自公开资料或合成（R4、R7、R9）；普法文章身份信息检查（R6） |
| IV. 自有模型，私有部署 | ✅ | 运行时由自训模型在本机提供能力；基座为 Apache 2.0；外部大模型只用于离线合成训练数据（R2、R4、R7）；训练数据与配置随实验清单保存，可复现训练 |
| V. 评测驱动决策 | ✅ | 评测集先于训练建立（实施顺序 P0）；评测与训练数据用不同提示词生成并去重（R4）；每次训练实验关联评测记录（data-model：ExperimentRun）。POC 不做技术选型决策，选型对比留到正式阶段（R12） |
| VI. 简单优先，可复现 | ✅ | 一次 SFT、不检索、不做约束解码、不做 DPO、只用本机；每个产物带清单（数据、知识库、基座、超参、种子、评测集版本）；同一套命令在正式阶段可扩展到 1000 篇 |
| 数据与合规约束 | ✅ | 知识库只收项目方提供的文件；维权文书、地方性法规不在范围内 |
| 开发流程与质量门禁 | ✅ | 确定性逻辑有单元测试（quickstart V1、V3、V7）；模型行为变更附回归评测 |

**Phase 1 设计后复查**：data-model、contracts、quickstart 未引入新的偏离，上表结论不变。无需填写 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/001-legal-clause-assistant/
├── spec.md
├── plan.md              # 本文件
├── research.md          # Phase 0：技术决策
├── data-model.md        # Phase 1：数据模型
├── quickstart.md        # Phase 1：验证指南
├── contracts/
│   ├── citation-format.md   # 引用格式与输出结构
│   ├── system-interface.md  # 系统接口与模型端点
│   ├── cli.md               # 命令行工具
│   └── datasets.md          # 训练数据格式
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2（/speckit-tasks 生成）
```

### Source Code (repository root)

```text
pyproject.toml
configs/
├── app.yaml                 # 运行时配置：模型端点、白名单、max_questions_per_turn 等
├── synth.yaml               # 合成：外部大模型提供方、提示词版本、改写倍数
└── train/                   # 训练配置：debug-1.5b.yaml、demo-7b.yaml
src/tu_assistant/
├── kb/                      # 文档解析、条款拆分、入库校验、条款关联、SQLite 存储
├── citation/                # 引用解析与出处校验
├── chat/                    # 会话、编排、提示词、身份信息检查、Markdown 导出
├── runtime/                 # 模型端点客户端（含白名单校验）
├── synth/                   # 训练数据与评测候选用例合成（唯一使用外部客户端的模块）
├── train/                   # 数据集构建、MLX 训练封装、实验清单
├── eval/                    # 评测用例、运行器（含固定对话脚本）、指标、报告
├── cli.py                   # tu 命令入口
└── ui/                      # Gradio 本地演示界面
tests/
├── unit/
├── integration/
└── fixtures/                # 公开法条片段，用于测试
eval/cases/                  # 版本化评测集（提交 git）
inputs/                      # 项目方文档（不提交 git）
artifacts/                   # 知识库版本、数据集、适配器、评测结果（不提交 git）
```

**Structure Decision**: 单体 Python 项目。模型通过 OpenAI 兼容接口访问，正式阶段换成 vLLM 或加入检索对照组时，
kb、citation、chat、eval 无需改动。

## 实施顺序

| 阶段 | 内容 | 完成标准 |
|---|---|---|
| P0 基础 | 项目骨架；文档入库与条款拆分；出处校验层；评测运行器与指标；评测集 v1（60–80 题，人工校验） | quickstart V1–V3 通过；评测集 v1 定稿 |
| P1 调通流程 | 训练数据合成；用 1.5B 训练；命令行对话；跑一次评测 | V4 通过：入库 → 合成 → 训练 → 对话 → 评测全流程跑通 |
| P2 演示模型 | 用 7B 训练（一到两晚）；评测；按评测结果调整数据再训一次 | V5 通过；评测报告 |
| P3 演示界面 | Gradio 多轮对话 + 保存 Markdown；准备演示场景 | V6 通过；可对外演示 |

全部在本机完成。若 P2 中"每次改数据都要等一晚"成为瓶颈，再考虑接入 5090（research R11）。

## 需要项目方提供或确认

1. **30–50 篇法律文档**，其中 **1–2 份样例**尽早提供（P0 开始前）：验证条款拆分规则（research R8）。
2. **外部大模型 API Key**（P1 合成数据前）：默认 DeepSeek，可更换；费用约 ¥20–50（research R4）。

## Complexity Tracking

无偏离，无需填写。
