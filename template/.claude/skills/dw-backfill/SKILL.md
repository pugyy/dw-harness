---
name: dw-backfill
description: >
  历史回填预演：目标环境、分区范围、幂等策略、检查点与扫描估算，
  预演阶段只读不落盘。适用于需要重刷历史分区时。
argument-hint: "[表名] [开始分区] [结束分区]"
allowed-tools: Read, Glob, Bash(dw plan:*, dw reconcile:*)
---

# dw-backfill：回填预演（只读）

```bash
dw plan backfill --table db_a.dws_trade_order_di \
    --start 20260101 --end 20261115 --sql insert_dws_trade_order_di.sql --env prod
```

## 预演产出

- 目标环境 / 表 / 分区范围
- 幂等策略：按分区 `INSERT OVERWRITE`，重跑即覆盖，禁与 INSERT INTO 混用
- 检查点：`.claude/dw/backfill/[表].json`（pending/running/done/failed 逐分区）
- 扫描估算：MaxCompute `COST SQL`（预演不执行，估不出显示"未知"）
- 恢复方案：失败分区可幂等重跑；错值回填用修正 SQL 重刷同范围

## 纪律

- 生产回填：预演 → 人工确认 → 走正式调度执行；guard 对 prod 覆盖类操作默认 ask/deny
- 回填期间 DQC 临时降级要在评审中显式记录
- 完成后按分区抽 reconcile 证据，`dw check` 收口
