---
name: dw-self-test
description: >
  Step 4/8 数仓自测：以隔离上下文执行 23 项标准自测并只回收摘要，
  防止大量检查输出污染主对话。适用于 ETL 完成后验证数据质量。
argument-hint: "[表名] [分区日期]"
context: fork
agent: dw-harness:data-quality-checker
allowed-tools: Read, Grep, Glob, Bash(dw lint:*), Bash(dw check:*)
---

# Step 4: 自测（fork 隔离运行）

## 23 项标准自测

- 完整性 8：主键非空 / 分区数据量 / 必填字段 / 外键关联 / 去重对比 / 空值率 / 枚举值域 / 重复记录
- 准确性 6：金额容差(≤0.01%) / 数值范围 / 日期合理 / 字符串长度 / 类型一致 / 业务规则
- 一致性 5：上下游量级 / 口径一致 / 汇总vs明细 / 标志位联动 / 跨表口径
- 时效性 4：产出时间(SLA 次日08:00) / 分区完整 / 增量连续 / 更新频率

## 执行要点

- 阈值以契约 `quality` 为准（不是拍脑袋）
- 能确定性化的项（空值/重复/量级波动）优先转成 DQC 规则：`dw dqc gen`
- 无数据权限的项标注 UNVERIFIED，不得当 PASS 汇报

## 交付物

`04_self_test.md`：23 项 PASS/FAIL/UNVERIFIED 表 + 未通过项明细（摘要 ≤40 行回主对话）
