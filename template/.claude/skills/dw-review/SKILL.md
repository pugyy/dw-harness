---
name: dw-review
description: >
  上线前 SQL/契约评审清单：字段口径比对、注释三段式、生命周期、
  分区策略、金额单位一致性。适用于提 PR 前自查或人肉评审辅助。
allowed-tools: Read, Grep, Glob, Bash(dw lint:*), Bash(dw contract:*), Bash(dw check:*)
---

# dw-review：上线前评审清单

## 确定性项（先跑命令）

```bash
dw lint <变更的 sql>
dw contract validate contracts/contract.json
dw check --table <表> --mode local     # 完整四态
```

## 人工评审项（逐条过）

- [ ] 字段口径与需求一致（引用契约 caliber，不引用记忆）
- [ ] 金额列币种/单位与上下游契约一致（分/元/千元没有隐式混用）
- [ ] 注释三段式：业务含义 | 数据来源 | 计算逻辑
- [ ] LIFECYCLE / 保留期符合表层级策略
- [ ] 分区策略与回填幂等性（历史分区覆盖有预演）
- [ ] 下游影响已看 `dw impact --table <表>`（未知血缘如实标注）
- [ ] 破坏性变更有迁移决定记录

## 输出

评审结论 + 未决问题清单；不替人拍板，只把证据摆齐。
