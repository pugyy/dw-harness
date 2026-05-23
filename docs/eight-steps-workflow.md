# 八步标准流程 / 8-Step Standard Workflow

数仓研发流程 / DW development workflow:

```text
需求分析 -> 技术设计 -> ETL 开发 -> 自测 -> 数据比对 -> SR 导入 -> 性能优化 -> SLA/DQC
Analysis  -> Design   -> ETL Dev  -> Test -> Compare  -> SR Import-> Perf Tune -> SLA/DQC
```

所有步骤都通过 `.claude/skills/<command>/SKILL.md` 注册，命令名以目录名为准。

All steps are registered via `.claude/skills/<command>/SKILL.md`. The command name matches the directory name.

---

## 流程分类 / Step Categories

适合主会话处理的步骤 / Steps handled directly in the main session:

- 需求分析 / Requirement analysis
- 技术设计 / Technical design
- SR 导入 / SR import
- SLA/DQC

适合通过 hooks 或 subagents 处理的步骤 / Steps handled via hooks or subagents:

- ETL 开发：写 SQL 后自动触发 hook / ETL development: hooks trigger on SQL write
- 自测：交给 `data-quality-checker` / Self-test: handled by `data-quality-checker`
- 数据比对：交给 `data-comparator` / Data comparison: handled by `data-comparator`
- 性能优化：血缘和 DDL 探索交给 `dw-explorer` / Performance tuning: lineage and DDL via `dw-explorer`

---

## Step 1: 需求分析 / Requirement Analysis

命令 / Command: `/dw-requirement-analysis`

输出 / Output:

- 需求摘要，不超过 5 行 / Requirement summary, max 5 lines
- 字段口径草稿 / Field definition draft
- 待确认问题清单 / Open questions list
- 字段变更单草稿 / Field change list draft

---

## Step 2: 技术设计 / Technical Design

命令 / Command: `/dw-technical-design`

输出 / Output:

- OneData 表命名 / OneData table naming
- 主键、粒度、周期 / Primary key, granularity, frequency
- 分区字段：`partition_dt string` / Partition field: `partition_dt string`
- 字段类型和特殊约束 / Field types and special constraints

---

## Step 3: ETL 开发 / ETL Development

命令 / Command: `/dw-etl`

输出 / Output:

- `ddl_[表名].sql`
- `insert_[表名].sql`
- `ddl_sr_[表名].sql`

自动护栏 / Auto guardrails:

- 写入 `.sql` 后，`validate_sql.py` 自动检查规范 / `validate_sql.py` auto-checks after writing `.sql`
- 如果出现 `SELECT *`、缺少 `PARTITION`、金额字段 `DOUBLE` 等问题，hook 返回阻断结果 / Issues like `SELECT *`, missing `PARTITION`, or `DOUBLE` on money fields trigger blocking

---

## Step 4: 自测 / Self Test

命令 / Command: `/dw-self-test`

推荐调用 / Suggested prompt:

```text
用 data-quality-checker subagent 对 [表名] 执行 23 项标准自测，
partition_dt = '[日期]'，只返回未通过项目和总结。

Run 23-item standard self-test on [table] via data-quality-checker subagent,
partition_dt = '[date]', only return failed items and summary.
```

---

## Step 5: 数据比对 / Data Comparison

命令 / Command: `/dw-data-comparison`

参数 / Parameters:

- 新表和参考表 / New table and reference table
- 分区日期 / Partition date
- 比对字段 / Fields to compare
- 容差：金额类默认 `0.01%` / Tolerance: money fields default to `0.01%`

输出只保留差异摘要，不把全量样本塞回主对话。Only diff summaries come back, not full sample data.

---

## Step 6: SR 数据库导入 / SR Database Import

命令 / Command: `/dw-sr`

重点检查 / Key checks:

- `DECIMAL` 精度 / Precision
- Key 选择 / Key selection
- 分区数量 / Partition count
- `DISTRIBUTED BY HASH` 分桶数 / Bucket count
- `DATETIME` 字段存储方式 / DATETIME field storage

---

## Step 7: 性能优化 / Performance Tuning

命令 / Command: `/dw-performance-optimization`

重点检查 / Key checks:

- 是否全表扫描 / Full table scan?
- 分区裁剪是否生效 / Partition pruning working?
- JOIN 是否合理 / JOINs sensible?
- 是否存在数据倾斜 / Data skew?
- 是否存在小文件问题 / Small file problem?

---

## Step 8: SLA/DQC

命令 / Command: `/dw-dqc`

输出 DQC 配置 JSON，覆盖完整性、准确性、一致性、时效性规则。

Outputs DQC config JSON covering completeness, accuracy, consistency, and timeliness rules.
