---
name: dw-etl
description: >
  Step 3/8 数仓 ETL 开发：生成 MaxCompute 建表 DDL、INSERT SQL，
  并由 hook 做写后规范反馈。适用于契约定稿后开始写表和任务 SQL。
argument-hint: "[表名] [分区日期]"
allowed-tools: Read, Write, Edit, Bash(dw lint:*)
---

# Step 3: ETL 开发

## 执行流程

1. 按契约生成 `ddl_[表名].sql`（字段/类型/注释与契约一致）
2. 生成 `insert_[表名].sql`（OVERWRITE + 显式 PARTITION）
3. 写文件后 PostToolUse hook 自动给出规范反馈（写后反馈，非拦截）
4. 自查一把确定性校验：

```bash
dw lint ddl_[表名].sql insert_[表名].sql
```

## 模板

```sql
INSERT OVERWRITE TABLE [表] PARTITION (partition_dt = '[yyyyMMdd]')
SELECT [显式字段列表]
FROM [上游]
WHERE partition_dt = '[yyyyMMdd]';
```

## 强制规范（hook 复核）

- 禁 `SELECT *` / `t.*`（`COUNT(*)` 例外）
- INSERT 必须带 PARTITION；金额 `DECIMAL(20,4)` 禁 `DOUBLE`
- 注释三段式：业务含义 | 数据来源 | 计算逻辑
- 金额单位继承契约声明，不做隐式换算

## 交付物

`ddl_[表名].sql`、`insert_[表名].sql`（如需同步：`ddl_sr_[表名].sql` 留给 Step 6）
