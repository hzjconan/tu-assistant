# AGENTS.md

## 项目约定

- 开发流程：spec-kit（SDD）。当前 feature：`specs/001-legal-clause-assistant/`；项目原则见 `.specify/memory/constitution.md`。
- 当前阶段：POC（30–50 篇文档，尽量快，只用开发者本机 M1 Pro / 32GB）。

## 用户偏好（必须遵守）

- **新任务先写执行单。** 收到“推进下一步”、起草或按审稿意见修改执行单等安排时，必须按 `.agents/skills/task-handoff/SKILL.md` 在 `docs/handoffs/` 写明建议的任务编号、选择理由、实施步骤、验收方法与待决策项（支持单节点高思考模型起草并保上下文承接修订），并在对话中说明为何优先做它。等用户审阅并明确同意实施后，再回收设计节点并动手写代码。
- **任务完成前走独立复审闭环。** 每个 task 实现完成、向用户汇报验收前，必须按 `.agents/skills/task-review-loop/SKILL.md` 执行「实现 → 独立只读复审 → 核实/修复或提异议 → 再复审」闭环（最多 5 轮）。无论双方一致通过还是满 5 轮中止，都先把完整结果汇报给用户（用户会再提交另一模型复审）；在用户明确确认前，不得勾选 `tasks.md` 或 `git commit`。
- **不得读取 `inputs/` 目录下的任何文件**（项目方提供的法律文档），包括用工具读取、grep、或运行会输出其内容的脚本。
  如确有需要，先征得用户同意并商量读取范围（目的是避免对话上下文过长）。
- 文档（规格、计划等）的提交须经用户审阅同意；未经明确要求不得 `git push`。
- 用户正在通过本项目学习模型训练：实施时同步维护 `docs/learning/` 学习文档，知识点用 `[L章.节]` 编号，便于用户按编号追问。

## 环境

- Python 用 uv 管理。
- 本机下载 Hugging Face 模型需设置：`HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1`（直连和 xet 传输极慢）。
- 本机训练长样本须开 `--grad-checkpoint`（实测 7B 长样本峰值 23GB → 11.5GB）。
