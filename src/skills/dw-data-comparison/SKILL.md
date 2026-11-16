---
name: dw-data-comparison
description: >
  Step 5/8 数据比对：新旧表/上下游键级对账，产出可复跑的对账证据，
  只回收差异摘要。适用于自测通过后与基线数据核对。
argument-hint: "[表名] [分区日期] [基线表]"
context: fork
allowed-tools: Read, Grep, Glob, Bash(dw reconcile:*, dw check:*)
---

# Step 5: 数据比对（键级对账）

## 执行流程

1. 固定比较双方：表/分区/业务键/度量列/容差（单位换算按契约）
2. 跑确定性对账并存证据：

```bash
dw reconcile --spec reconcile_[表].json --save-evidence
```

3. 预检（空键/重复键/缺失分区）失败先修数，再做键级比较
4. 只把差异摘要交回主对话

## 对账 spec 要点

- `keys`：业务键（契约 `business_keys`）
- `metrics`：列 + `abs_tol` + `rel_tol` + 双方 `unit`（按契约换算到最小单位）
- 零基线：一侧为 0 时任何非零差都算 FAIL；NULL==NULL 视为相等，NULL vs 值单列

## 交付物

- `reconcile_[表].json`（spec，进仓库）
- `.claude/dw/evidence/reconcile-[表].json`（证据，`dw check` 复核）
