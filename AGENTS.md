# AGENTS.md

## 项目约定

- 开发流程：spec-kit（SDD）。当前 feature：`specs/001-legal-clause-assistant/`；项目原则见 `.specify/memory/constitution.md`。
- 当前阶段：POC（30–50 篇文档，尽量快，只用开发者本机 M1 Pro / 32GB）。

## 用户偏好（必须遵守）

- **不得读取 `inputs/` 目录下的任何文件**（项目方提供的法律文档），包括用工具读取、grep、或运行会输出其内容的脚本。
  如确有需要，先征得用户同意并商量读取范围（目的是避免对话上下文过长）。
- 文档（规格、计划等）的提交须经用户审阅同意；未经明确要求不得 `git push`。
- 用户正在通过本项目学习模型训练：实施时同步维护 `docs/learning/` 学习文档，知识点用 `[L章.节]` 编号，便于用户按编号追问。

## 环境

- Python 用 uv 管理。
- 本机下载 Hugging Face 模型需设置：`HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1`（直连和 xet 传输极慢）。
- 本机训练长样本须开 `--grad-checkpoint`（实测 7B 长样本峰值 23GB → 11.5GB）。
