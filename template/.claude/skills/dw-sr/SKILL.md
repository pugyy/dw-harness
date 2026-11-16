---
name: dw-sr
description: >
  Step 6/8 StarRocks 导入：按契约与 MaxCompute 表结构生成 SR 建表语句、
  同步配置与风险分析。适用于数据需要从 MaxCompute 同步到 SR 时。
argument-hint: "[表名]"
allowed-tools: Read, Write, Glob, Bash(dw lint:*)
---

# Step 6: SR 导入

## 执行流程

1. 从契约/DDL 取字段与类型，生成 `ddl_sr_[表名].sql`
2. 风险矩阵按高→低排序输出（≤20 行）
3. SR 文件自动按 starrocks 方言校验（`*_sr_*` 路径映射）

## 风险矩阵

| 风险项 | 检查内容 | 等级 |
|---|---|---|
| 类型精度 | DECIMAL/DOUBLE → DECIMAL(p,s) 按契约 | 高 |
| Key 模型 | PRIMARY/DUPLICATE/UNIQUE 合理性 | 高 |
| 金额单位 | 与 MaxCompute 侧契约单位是否一致 | 高 |
| 分区数量 | 与源表匹配 | 中 |
| 分桶 | DISTRIBUTED BY HASH 分桶数 | 中 |
| DATETIME | 存储方式（避免全表扫描） | 中 |
| 字符集 | 编码兼容 | 低 |

## 规则

- SR 的 INSERT 可省略分区（引擎合法），本项目默认告警不阻断
- 单位换算在契约 `unit` 声明，不在 SQL 里做隐式转换
