---
name: dw-check
description: >
  发布前统一验收：跑 dw check 汇总 lint/契约/DDL/DQC/对账证据，
  输出四态（PASS/FAIL/UNVERIFIED/N-A）报告。适用于合并/上线前最后关口。
argument-hint: "[表名] [--env dev|prod] [--partition yyyyMMdd]"
allowed-tools: Read, Glob, Bash(dw check:*)
---

# dw-check：验收关口

```bash
dw check --table db_a.dws_trade_order_di --env dev --partition 20261115 \
    --sql insert_dws_trade_order_di.sql --contract contracts/contract.json \
    --ddl ddl_dws_trade_order_di.sql --dqc dqc_dws_trade_order_di.json \
    --baseline baselines/contract.v1.json \
    --out-json .claude/dw/check_report.json --out-md .claude/dw/check_report.md
```

## 四态语义

- PASS：确定性检查通过
- FAIL：已知失败（优先级最高，压过缺证据）
- UNVERIFIED：证据缺失/过期/输入已变（必须带原因；严格模式退出码 2）
- N/A：本变更集不适用（如无基线的首版契约）

## 规则

- 退出码：0 可过 / 1 有失败 / 2 有未验证（strict）
- 本地体验模式 `--mode local` 允许未验证项过，但报告保留原状态与理由
- 报告可直接贴 PR（Markdown 表）
- 模型只解释报告、提处理方案；放行由退出码与策略决定
