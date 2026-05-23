---
paths:
  - "**/*insert*.sql"
  - "**/*_di.sql"
  - "**/*_df.sql"
  - "**/*_dws.sql"
  - "**/*_ads.sql"
---

# ETL 开发规范（按文件路径自动加载）

## 强制规则

- 必须有 partition_dt 分区字段
- INSERT OVERWRITE 前检查分区是否存在
- 不允许跨库 JOIN（除非明确标注原因）
- INSERT 必须包含 PARTITION (partition_dt = '...')
- 金额字段类型 DECIMAL(20,4)，禁止 DOUBLE
- 禁止 SELECT *，必须明确字段列表
- UPDATE/DELETE 必须包含 WHERE 条件

## 命名规范

- 建表文件: `ddl_[表名].sql`
- 插入文件: `insert_[表名].sql`
- SR 建表: `ddl_sr_[表名].sql`
