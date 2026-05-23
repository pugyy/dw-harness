# 五层防御体系

`dw-harness` 的核心思路是：把容易被 AI 忘掉的东西写进文件，把必须执行的检查写进 hook，把高 token 工作交给 subagent。

## 第一层：CLAUDE.md 持久化约束

目标文件：`.claude/CLAUDE.md`

适合写入：

- 当前开发表、版本、node_id
- 本轮禁止修改的表
- 字段口径和特殊业务约束
- 数仓全局 SQL 规范

建议控制在 100 行以内，避免把过程日志写进去。

## 第二层：context 摘要文件

目标目录：`.claude/context/`

`0x_conventions.md` 存放跨步骤复用的核心规则。`inject_context.py` 会在 compact 后把该文件内容通过 `additionalContext` 重新交给 Claude，同时把 compact summary 记录到 `last_compact_summary.md`，方便人工或后续会话回看。

长期稳定规则仍应优先放在 `.claude/CLAUDE.md` 和 `.claude/rules/`。

## 第三层：Hooks 自动验证

目标目录：`.claude/hooks/`

| Hook | 脚本 | 作用 |
|------|------|------|
| PostToolUse | `validate_sql.py` | 写入/编辑 SQL 后检查规范 |
| PreToolUse | `block_dangerous_ddl.py` | Bash 执行前阻断危险 DDL |
| PostCompact | `inject_context.py` | 重注入数仓规范，并记录 compact 摘要 |

`validate_sql.py` 会读取 Claude Code 传入的 stdin JSON，取出 `tool_input.file_path`，只检查 `.sql` 文件。

阻断规则：

- `SELECT *`
- `INSERT` / `INSERT OVERWRITE` 缺少 `PARTITION`
- `UPDATE` / `DELETE` 缺少 `WHERE`
- 金额字段使用 `DOUBLE`
- 分区字段使用 `dt` 而不是 `partition_dt`

## 第四层：Subagents 上下文隔离

默认所有 agent 使用 `model: opus`，先保证复杂数仓任务的准确性。成本敏感时，可以把 `sql-validator`、`dw-explorer` 调整为 `sonnet` 或 `haiku`。

适合交给 subagent 的工作：

| 工作 | 推荐 agent |
|------|------------|
| 表结构、DDL、血缘探索 | `dw-explorer` |
| SQL 语法和规范复核 | `sql-validator` |
| 23 项标准自测 | `data-quality-checker` |
| 新旧表数据比对 | `data-comparator` |

主对话只接收摘要，不接收全量执行日志、样本数据和长 DDL。

## 第五层：Skills + Rules 标准化流程

Skills 放在：

```text
.claude/skills/<skill-name>/SKILL.md
```

当前模板的 8 个 skill：

```text
.claude/skills/
├── dw-requirement-analysis/SKILL.md
├── dw-technical-design/SKILL.md
├── dw-etl/SKILL.md
├── dw-self-test/SKILL.md
├── dw-data-comparison/SKILL.md
├── dw-sr/SKILL.md
├── dw-performance-optimization/SKILL.md
└── dw-dqc/SKILL.md
```

Rules 放在：

```text
.claude/rules/*.md
```

Path-scoped rules 只在 Claude 读取匹配文件时加载，例如 `etl-rules.md` 只对 `insert*.sql`、`*_di.sql`、`*_df.sql` 等路径生效。
