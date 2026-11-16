---
name: dw-dqc
description: >
  Step 8/8 SLA/DQC：从表契约生成稳定 ID 的 DQC 规则配置并校验漂移。
 适用于任务上线前的质量规则配置。
argument-hint: "[表名]"
allowed-tools: Read, Write, Bash(dw dqc:*), Bash(dw contract:*)
---

# Step 8: SLA / DQC

## 执行流程

```bash
# 按契约生成（9 类规则、稳定 ID：同表同类同列同阈值 => 同 ID）
dw dqc gen --contract contracts/contract.json --out dqc_[表名].json
# 校验配置与契约不漂移
dw dqc check --contract contracts/contract.json --config dqc_[表名].json
```

## 9 类规则（沿用 v1 分类）

完整性：主键非空 / 分区数据量波动 / 必填字段非空
准确性：金额容差(契约 quality) / 数值范围
一致性：联动逻辑 / 上下游一致
时效性：产出 SLA / 数据新鲜度

## 规则

- 阈值来自契约，不在本步临时拍数值
- 修改契约后必须重跑 `dw dqc check`（ID/阈值漂移会 FAIL）
