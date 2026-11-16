---
name: dw-technical-design
description: >
  Step 2/8 数仓技术设计：OneData 建模、表名粒度/主键/分区设计、
  字段类型约束沉淀到表契约。适用于需求分析完成后进入建模阶段。
argument-hint: "[表名或主题]"
allowed-tools: Read, Grep, Glob, Write, Bash(dw contract:*)
---

# Step 2: 技术设计

## 执行流程

1. OneData 命名：`[层级]_[域]_[主题]_[粒度]_[周期]`（如 `dws_trade_order_di`）
2. 确定主键、粒度、分区（`partition_dt string yyyyMMdd`）
3. 把 Step 1 的口径草稿固化进契约并校验：

```bash
dw contract validate contracts/contract.json
dw contract compile contracts/contract.json
```

4. 金额列在契约中分开声明 `currency` 与 `unit`（CNY 的分/元/千元是三种不同契约事实）

## 交付物

- `02_design.md`：建模决策（表/主键/粒度/分区/上游依赖）
- 通过校验的契约 + 编译产物 `.contract.json`

## 规则

- 输出 ≤60 行；细节写契约，不写会话
- 禁改表必须登记到 `harness.json` 的 `protected_objects`
