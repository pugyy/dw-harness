---
name: dw-performance-optimization
description: >
  Step 7/8 性能优化：分析 ETL SQL 的分区裁剪、JOIN 策略、数据倾斜与
  扫描预算，输出带证据级别的优化建议。适用于任务上线前或超时排查。
argument-hint: "[表名]"
allowed-tools: Read, Grep, Glob, Bash(dw plan:*)
---

# Step 7: 性能优化

## 执行流程

1. 表结构/血缘交给 `dw-explorer`（防刷屏）
2. SQL 层：全表扫描 / 分区裁剪 / 小表驱动 / 倾斜 / GROUP BY 优化
3. 扫描预算：回填/大范围任务先出预演（`dw plan backfill`，COST SQL 未执行时如实标"未知"）
4. 每条建议标注：来自确定性命令（EXPLAIN/COST SQL）还是静态判断

## 交付物

`07_perf.md`：瓶颈 → 建议（预期收益/改动难度）→ 证据级别（实测 / 静态判断 / 未知）

## 规则

- 不臆造执行计划；拿不到就写 UNVERIFIED
- StarRocks `EXPLAIN ANALYZE` 会实际执行，禁止在预演阶段使用
