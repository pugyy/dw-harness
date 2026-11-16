---
name: dw-contract
description: >
  表契约操作：校验、编译、与基线 diff、记录破坏性变更的迁移决定。
  适用于新增/修改字段口径、金额单位变更、与基线比对时。
argument-hint: "[contract.json 路径] [--baseline 基线]"
allowed-tools: Read, Write, Edit, Bash(dw contract:*)
---

# dw-contract：契约四件套

```bash
dw contract validate contracts/contract.json        # 结构/币种单位校验
dw contract compile contracts/contract.json         # 生成规范化 .contract.json
dw contract diff contracts/contract.json --baseline baseline.json
dw contract decide contracts/contract.json --baseline baseline.json \
    --approver <人> --reason <原因>                   # 记录迁移决定
```

## 契约字段速记

- 表标识/owner/粒度/business_keys/partition
- 列：type + precision/scale + nullable + caliber(口径) + source
- 金额列：`currency`（CNY…）与 `unit`（fen/yuan/qian_yuan…）必须成对且显式
- quality 阈值 + sla —— DQC 与对账都从这里取数

## 破坏性变更

删列 / 类型收窄 / 金额单位或币种变化 / 键 / 粒度 / 分区变化 = breaking。
`dw check` 会要求对应迁移决定（from_hash → to_hash 绑定），没有就 FAIL。

## 经典案例

`net_amount` 从「分」改「元」：SQL 全绿、类型没变，契约 diff 仍会逮住
`unit_changed` 并要求迁移决定与下游换算方案 —— 这正是契约存在的意义。
