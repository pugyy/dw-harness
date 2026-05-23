# 八步标准流程

数仓研发流程：

```text
需求分析 -> 技术设计 -> ETL 开发 -> 自测 -> 数据比对 -> SR 导入 -> 性能优化 -> SLA/DQC
```

所有步骤都通过 `.claude/skills/<command>/SKILL.md` 注册，命令名以目录名为准。

## 流程分类

适合主会话处理的步骤：

- 需求分析
- 技术设计
- SR 导入
- SLA/DQC

适合通过 hooks 或 subagents 处理的步骤：

- ETL 开发：写 SQL 后自动触发 hook
- 自测：交给 `data-quality-checker`
- 数据比对：交给 `data-comparator`
- 性能优化：血缘和 DDL 探索交给 `dw-explorer`

## Step 1: 需求分析

命令：`/dw-requirement-analysis`

输出：

- 需求摘要，不超过 5 行
- 字段口径草稿
- 待确认问题清单
- 字段变更单草稿

## Step 2: 技术设计

命令：`/dw-technical-design`

输出：

- OneData 表命名
- 主键、粒度、周期
- 分区字段：`partition_dt string`
- 字段类型和特殊约束

## Step 3: ETL 开发

命令：`/dw-etl`

输出：

- `ddl_[表名].sql`
- `insert_[表名].sql`
- `ddl_sr_[表名].sql`

自动护栏：

- 写入 `.sql` 后，`validate_sql.py` 自动检查规范
- 如果出现 `SELECT *`、缺少 `PARTITION`、金额字段 `DOUBLE` 等问题，hook 返回阻断结果

## Step 4: 自测

命令：`/dw-self-test`

推荐调用：

```text
用 data-quality-checker subagent 对 [表名] 执行 23 项标准自测，
partition_dt = '[日期]'，只返回未通过项目和总结。
```

## Step 5: 数据比对

命令：`/dw-data-comparison`

参数：

- 新表和参考表
- 分区日期
- 比对字段
- 容差：金额类默认 `0.01%`

输出只保留差异摘要，不把全量样本塞回主对话。

## Step 6: SR 数据库导入

命令：`/dw-sr`

重点检查：

- `DECIMAL` 精度
- Key 选择
- 分区数量
- `DISTRIBUTED BY HASH` 分桶数
- `DATETIME` 字段存储方式

## Step 7: 性能优化

命令：`/dw-performance-optimization`

重点检查：

- 是否全表扫描
- 分区裁剪是否生效
- JOIN 是否合理
- 是否存在数据倾斜
- 是否存在小文件问题

## Step 8: SLA/DQC

命令：`/dw-dqc`

输出 DQC 配置 JSON，覆盖完整性、准确性、一致性、时效性规则。
