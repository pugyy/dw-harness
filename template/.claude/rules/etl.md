---
paths:
  - "**/{ddl,insert}_*.sql"
---

# ETL 开发规范（MaxCompute 侧）

- 建表文件 `ddl_[表名].sql`，插入文件 `insert_[表名].sql`
- 分区字段 `partition_dt STRING`，yyyyMMdd，禁止命名 `dt`
- `INSERT OVERWRITE` 按分区幂等；回填走 `dw plan backfill` 预演
- 受保护对象见 `.claude/dw/harness.json` `protected_objects`
- 改表优先 `dw plan ddl` 生成 ALTER 候选；类型收窄需显式 `--allow-narrowing` 并记录迁移决定
