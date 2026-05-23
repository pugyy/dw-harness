# 传统方式 vs Harness

## 核心对比

| 维度 | 传统提示词方式 | dw-harness 方式 |
|------|----------------|-----------------|
| 字段口径 | 靠对话历史，compact 后容易丢 | 写入 `CLAUDE.md` 和 context 文件 |
| SQL 规范 | 靠模型记忆 | hook 自动检查 |
| 危险 DDL | 靠人工提醒 | PreToolUse hook 阻断 |
| 大量输出 | 堆进主 context | subagent 只返回摘要 |
| 流程标准 | 每次重新说明 | 8 个 skills 固化 |
| 路径规范 | 全量塞进提示词 | path-scoped rules 按需加载 |

## 四类典型问题

### 字段口径遗忘

现象：对话开始时说明 `amount` 单位是千元，compact 后模型生成 SQL 时误按元处理。

做法：把字段口径写入 `.claude/CLAUDE.md` 的“本次迭代约束”，上线后沉淀为长期规则或 context 摘要。

### SQL 规范遗漏

现象：模型偶尔生成 `SELECT *` 或忘记 `PARTITION`。

做法：`validate_sql.py` 在写入 `.sql` 后自动检查，失败时阻断并把错误返回给 Claude 修正。

### 危险操作

现象：调试时 Bash 命令里带了 `DROP TABLE`、`TRUNCATE TABLE`。

做法：`block_dangerous_ddl.py` 在 Bash 执行前读取 `tool_input.command`，危险语句直接 `deny`。

### Context 膨胀

现象：血缘查询、自测结果、数据比对样本把主对话撑满，后续推理质量下降。

做法：让 `dw-explorer`、`data-quality-checker`、`data-comparator` 在独立 context 中运行，主对话只接收摘要。

## 结论

Harness 的价值不是让 AI “更聪明”，而是把确定性环节从模型记忆中移出来：

- 规范执行交给 hook
- 项目约束交给文件
- 大输出交给 subagent
- 标准流程交给 skill
