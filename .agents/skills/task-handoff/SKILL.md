---
name: task-handoff
description: >-
  Draft or revise a task handoff document in docs/handoffs/ using a high-thinking
  designer node (e.g. gemini-4-neon-xhigh via single-node swarm) before writing
  any implementation code. Use this skill whenever the user asks to plan the
  next step, draft a task handoff/design, or revise an existing handoff based on
  user or external model review feedback.
---

# Task Handoff Drafting & Revision

收到“推进下一步”、起草某个 task 执行单，或根据用户/外部模型审稿意见修改执行单时，按本规范执行。本规范不绑定特定 CLI，支持自动降级。

## 绝对红线

- **严禁读取 `inputs/` 目录下的任何文件**（除非用户明确书面授权读取范围）。
- **设计阶段只写执行单**：仅创建或更新 `docs/handoffs/<task>-handoff.md`，**不得改动业务代码、测试、知识库或历史产物**。
- **未经用户明确同意不得开工**：汇报执行单及待确认决策点后立即停步，等待用户拍板后再进入代码实现。
- **不做内部二次审稿**：写完执行单直接汇报给用户，由用户决定直接拍板、发外部模型复审或另开终端复审。

## 派发策略（高思考设计 + 跨 CLI 降级）

1. **首选 · 单节点高思考设计师（适用于支持精确指定模型的工具，如 Antigravity 的 `swarm`）**：
   - 若当前主会话运行在较轻档位（如 `gemini-4-neon-medium`），通过 `swarm` **仅拉起 1 个设计节点**：
     - `name="designer"`、`model="gemini-4-neon-xhigh"`（若不可用则顺次降级至 `gemini-4-neon-high` 或同系列最高可用思考档位）、`workspace="inherit"`（不建 worktree，严禁并发拉起多个节点）。
   - 在 `brief` 中明文约束：
     - 先做只读摸底，严禁读取 `inputs/`；
     - 只允许创建或修改 `docs/handoffs/<task>-handoff.md`，严禁修改任何其他文件；
     - 完成后在公告板汇报执行单路径、推荐理由与待确认决策点。
   - **保留上下文以承接修改（关键）**：初稿完成后**不要 `kill` `designer`**！让其留在公告板上进入 `waiting` 休眠状态（不消耗额度且完整保留摸底上下文）。
   - **后续审稿修改**：若同一会话内用户贴回自己或外部模型的审稿意见要求修改执行单，主会话**直接转发给休眠中的 `@designer`**（复用同一 `gemini-4-neon-xhigh` 节点与上下文），由它核实意见、原地修订执行单并逐条回应；若处于新会话、原 `designer` 不存在，则读取已落盘的执行单与审稿意见后新拉 1 个 `designer` 修订。
   - **回收时机**：直到用户明确同意按执行单开始实施（或明确取消该执行单）时，再立刻 `swarm(action="kill", name="designer")` 回收节点，并用 `git status` 确认未误改其他文件，随后由主会话（`medium`）接手编码实现。
2. **降级 · 当前会话直接起草**：
   - 若当前主会话本身已是同等或更高思考档位（如 `gemini-4-neon-xhigh`），或当前 CLI 不支持单节点精确指定模型，则直接在当前会话按下方规范完成摸底、起草与修订。

## 执行单起草与核实标准

起草 `docs/handoffs/<task>-handoff.md` 前必须先对仓库做只读摸底（不凭记忆编造数字或接口）：
1. 核对 `specs/001-legal-clause-assistant/tasks.md` 的依赖关系、前置条件与未完成项；
2. 核对相关上游执行单（如已存在的目标 task 备忘、最近完成 task 的遗留备忘）；
3. 核对涉及源码、当前活跃 KB/数据集/评测集版本及真实统计数据；
4. 执行单须清晰包含：
   - **推荐任务编号与选择理由**（对比其他候选为何优先做它）；
   - **实施边界与约束**（涉及模块、与现有接口/口径的对齐、历史产物只读保护、运行时隔离）；
   - **具体实施步骤与确定性验收方法**（不把无法确定的语义判断写进单元测试，不出现前后章节自相矛盾）；
   - **学习文档更新点**（`docs/learning/` 对应 `[L章.节]`）；
   - **待用户拍板的决策清单**（范围、窗口/配比、风险取舍，逐项给出选项与推荐理由）。

## 汇报给用户的格式

起草或修订完成后，在对话中精简汇报：
1. **执行单链接**（clickable `file://` 路径）；
2. **为什么优先做这个任务**（或本轮按审稿意见修改了哪些要点、对有异议条目的说明）；
3. **需要用户拍板的决策清单**（编号列出，便于用户直接回复或转交外部模型审稿）；
4. 明确说明**尚未改动任何代码，等待确认后再动手**。
