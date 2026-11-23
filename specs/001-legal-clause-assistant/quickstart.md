# Quickstart: 验证指南（POC）

**Feature**: `001-legal-clause-assistant` | **Plan**: [plan.md](./plan.md)

本文列出可运行的验证场景，用于证明各功能端到端可用。全部在开发者本机运行。命令定义见 [contracts/cli.md](./contracts/cli.md)。

## 前置条件

- macOS（Apple Silicon，≥32GB 内存）
- 已安装 uv；在仓库根目录执行 `uv sync`
- 项目方提供的法律文档已入库：`inputs/project/001/`（排除文件在 `inputs/excluded/`）
- 数据合成需要外部大模型 API Key：`export TU_EXTERNAL_LLM_API_KEY=...`
- 下载模型：`export HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1`

## V1. 单元测试（确定性逻辑）

```bash
uv run pytest tests/unit
```

**预期**：条款拆分、中文数字转换、引用解析、出处校验（ok / corrected / not_found / incomplete 四种结论）、
身份信息检查、追问计数、端点白名单校验全部通过。

## V2. 文档入库

```bash
uv run tu kb import inputs/project/001
uv run tu kb show "中华人民共和国工会法" 51
```

**预期**：生成新的 `kb_version` 与 `parse_report.md`；抽查的条款原文与源文件逐字一致；
编号缺失或重复的条款出现在问题清单中（FR-001、FR-005）。

## V3. 出处校验

```bash
uv run pytest tests/integration/test_citation_verify.py
```

**预期**：对一段含正确引用、原文有误的引用、不存在的条款号、裸引用的样例输出，
校验后交付内容的条款原文 100% 与知识库一致，不存在的引用被删除并标注（宪章原则 I、FR-007）。

## V4. 全流程调通（1.5B）

```bash
uv run tu synth sft --kb-version <ver>
uv run tu synth evalcases --kb-version <ver> --n 60
uv run tu eval cases review eval/cases/candidates/candidates.jsonl
uv run tu eval cases promote eval/cases/candidates/candidates.jsonl
uv run tu train --config configs/train/debug-1.5b.yaml
uv run tu serve model --exp <exp_id>
uv run tu chat
uv run tu eval run --exp <exp_id> --kb-version <ver> --cases eval/cases/v1
```

对话示例：先输入"我们单位领导不让搞工会"，确认系统追问意图；再说明"想了解法律规定"并补充案情。

**预期**：训练完成并生成实验清单（含数据版本、基座、超参、种子）；对话中先追问且问题数 ≤5（FR-010、FR-011）；
回答使用引用块格式并附免责提示；`/save out.md` 生成 Markdown 文件（FR-032）；评测报告能产出全部指标。
1.5B 的效果不作要求，只验证流程。

## V5. 演示模型（7B）与评测

```bash
uv run tu train --config configs/train/demo-7b.yaml
uv run tu serve model --exp <exp_id>
uv run tu eval run --exp <exp_id> --kb-version <ver> --cases eval/cases/v1
```

**预期**：评测报告覆盖 spec SC-001 ~ SC-011，引用准确率分校验前 / 校验后两列（FR-034）；
同一模型重复运行，指标波动 ≤2 个百分点（SC-015）。POC 阶段指标只与目标值对照，不作为验收条件。

## V6. 演示界面

```bash
uv run tu ui
```

在浏览器中按准备好的演示场景操作：模糊开场 → 追问 → 咨询回答；生成 3 篇普法文章 → 要求修改 → 保存为 Markdown。

**预期**：多轮对话流畅；引用块格式正确；普法文章使用虚构名称；保存的 `.md` 文件内容与界面一致。

## V7. 数据合规检查

```bash
uv run pytest tests/unit/test_runtime_isolation.py
```

**预期**：运行时代码不导入外部大模型客户端；模型端点不在白名单时拒绝启动；
普法文章中不出现会话里用户提供的单位与人名（宪章原则 III、FR-030、SC-011）。

## 知识库更新与版本切换（US4）

```bash
# 1. 文档新增、修改或删除后整批重新导入，生成新 kb_version
uv run tu kb import <新文档目录>

# 2. 对比新旧知识库版本（只输出条款编号与变化类型，不输出条文正文）
uv run tu kb diff <旧kb_version> <新kb_version>

# 3. 在 configs/app.yaml 中设置 kb.version（或保留 null 自动使用最新版本），无需修改代码
# 4. 运行基于公开测试样例的知识库更新集成测试
uv run pytest tests/integration/test_kb_update.py
```

**预期**：`tu kb diff` 准确列出新增、删除、原文变化的条款编号；修改 `configs/app.yaml` 中的 `kb.version` 后，出处校验层与对话编排层立即加载指定版本的知识库并引用新原文（FR-003、FR-004）。

> **重要提示 1：`kb.version: null` 自动切库与未确认关联的过渡期风险**
> - `tu kb import` 每次从零新建 SQLite 知识库，刚导入完成的新库中**已确认条款关联为 `0` 条**（`clause_relations` 中 `confirmed=1` 的记录需经 `extract -> review -> confirm` 导入后才存在；若是从旧版无 `第1款` 标记的库迁移，还需按需执行 `tu kb derive`）。
> - 当 `configs/app.yaml` 保持默认的 `kb.version: null` 时，一旦运行 `tu kb import` 产生更新的时间戳版本，`tu chat`、`tu eval run`、`tu synth sft`（在不显式传 `--kb-version` 时）会立即自动切换到这个尚无已确认关联的新库。
> - **操作建议**：在新库尚未走完关联抽取与人工确认、或正在进行同版本评测对比期间，应先在 `configs/app.yaml` 中将 `kb.version` 显式锁定为当前稳定版本号（如 `"kb-20261119-045641"`），待新库关联确认就绪后再切换。
>
> **重要提示 2：知识更新需重训（research R1 风险）**
> - **立即生效的部分（出处校验层）**：切换 `kb.version` 后，若模型引用的条款编号在新版本中原文已修订，校验层会立即将其替换为新原文（`verdict=corrected`）；若该条款已在新版本中删除，校验层会立即拦截并删除该引用块（`verdict=not_found`）。
> - **不会自动生效的部分（模型参数记忆）**：由于 POC 采取“把法规知识训进模型参数、推理时不检索知识库”的路线（research R1），仅更新 SQLite 知识库不会改变模型权重。对于新入库的文件或新增条款，未重训的模型无法在回答中主动识别并引出；对于适用条件或法律责任发生实质变更的条款，模型仍可能按旧记忆给出过时的分析或选错条号。
> - **完整更新链路**：当法规发生实质性新增、修订或废止时，除了执行 `tu kb import`（及按需 `tu kb derive`）与 `tu kb diff` 外，**必须重新抽取并人工确认条款关联**（`tu kb relations extract` → `tu kb relations review/confirm`，因为 `tu synth sft` 的关系样本与运行时的确定性关联补全均依赖已确认关联）→ 重新合成或刷新训练数据集（`tu synth sft --kb-version <新版本>`）→ 重新微调模型（`tu train`）→ 用评测集完成回归评测（`tu eval run`，对应 spec SC-014）。
