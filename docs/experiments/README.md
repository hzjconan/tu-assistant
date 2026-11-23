# 实验记录

这里记录训练/评测中遇到的问题、诊断和修复尝试，每个问题一份活文档，按 `E001`、`E002`… 顺序编号（文件名 `E<编号>-<简短英文描述>.md`），新的尝试与结果直接追加到对应文档中。原理性讲解放在 `docs/learning/`。

- 原始日志与产物放 `artifacts/logs/<实验编号>/`（不进 git）；可复用的脚本放 `scripts/experiments/<实验编号>/`（受版本管理）；
- 诊断用的用例集放 `eval/diagnostics/`，不是标准评测集，不得用于 SC 判定（data-model.md §3）。

| 文档 | 内容 | 状态 |
|---|---|---|
| [E001](./E001-1.5b-citation-failure.md) | 1.5B 引用失败、7B 训练 NaN 诊断与 fp32 修复 | 评测结论已被 E002 订正 |
| [E002](./E002-eval-served-base-model.md)（[执行记录](./E002-run-log.md)） | 评测误测基座的根因、修复与重评；§6 复审 | 已完成 |
| [E003](./E003-memorization-vs-exposure.md)（[执行记录](./E003-run-log.md)） | 曝光不足还是容量不足：原题记忆测试、追加训练 | 已收尾 |
| [POC 训练收尾](./poc-training-summary.md) | POC 训练目标判定、POC 下一步、正式阶段的判断 | 待审阅 |
| [T064 重复评测（SC-015）](./T064-eval-repeatability.md) | 7B 演示模型两轮独立冷启动 98 题评测、DeepSeek 初审 + 人工终审与 SC-015 判定（`0.0 pp` PASS） | 已完成 |
