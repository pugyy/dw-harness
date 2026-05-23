# 数仓全局约定

这些约定用于在 compact 或新会话后快速恢复数仓开发上下文。项目长期规则优先写入 `.claude/CLAUDE.md` 和 `.claude/rules/`，本文件只放跨步骤需要反复提醒的摘要。

## SQL 强制规范

- 禁止 `SELECT *`，必须显式列出字段。
- `INSERT` / `INSERT OVERWRITE` 必须包含 `PARTITION` 子句。
- 分区字段统一使用 `partition_dt STRING`，日期格式为 `yyyyMMdd`。
- 金额字段使用 `DECIMAL(20,4)`，不使用 `DOUBLE`。
- `UPDATE` / `DELETE` 必须包含 `WHERE` 条件。

## 数仓工作流

需求分析 -> 技术设计 -> ETL 开发 -> 自测 -> 数据比对 -> SR 导入 -> 性能优化 -> SLA/DQC。

主对话只保留决策级信息；血缘查询、自测结果、数据比对等高 token 内容交给 subagent，并只返回摘要。
