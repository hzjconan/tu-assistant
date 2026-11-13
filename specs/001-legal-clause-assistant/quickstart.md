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
uv run tu kb import inputs/project
uv run tu kb show 中华人民共和国工会法 51
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
uv run tu synth sft --kb <ver>
uv run tu train --config configs/train/debug-1.5b.yaml
uv run tu serve model --exp <exp_id>
uv run tu chat
uv run tu eval run --exp <exp_id> --kb <ver> --cases v1
```

对话示例：先输入"我们单位领导不让搞工会"，确认系统追问意图；再说明"想了解法律规定"并补充案情。

**预期**：训练完成并生成实验清单（含数据版本、基座、超参、种子）；对话中先追问且问题数 ≤5（FR-010、FR-011）；
回答使用引用块格式并附免责提示；`/save out.md` 生成 Markdown 文件（FR-032）；评测报告能产出全部指标。
1.5B 的效果不作要求，只验证流程。

## V5. 演示模型（7B）与评测

```bash
uv run tu train --config configs/train/demo-7b.yaml
uv run tu serve model --exp <exp_id>
uv run tu eval run --exp <exp_id> --kb <ver> --cases v1
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
