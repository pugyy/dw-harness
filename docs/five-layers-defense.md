# 五层防御体系 / Five Layers of Defense

核心思路：把容易被 AI 忘掉的东西写进文件，把必须执行的检查写进 hook，把高 token 工作交给 subagent。

The core idea: persist things AI tends to forget into files, enforce mandatory checks in hooks, offload high-token work to subagents.

---

## 第一层：CLAUDE.md 持久化约束 / Layer 1: CLAUDE.md Persistence

目标文件 / Target file: `.claude/CLAUDE.md`

适合写入 / Good for:

- 当前开发表、版本、node_id / Current table, version, node_id
- 本轮禁止修改的表 / Tables that must not be modified this iteration
- 字段口径和特殊业务约束 / Field definitions and special business constraints
- 数仓全局 SQL 规范 / Global DW SQL conventions

建议控制在 100 行以内，避免把过程日志写进去。Keep under 100 lines. Don't dump process logs here.

---

## 第二层：context 摘要文件 / Layer 2: Context Summary Files

目标目录 / Target directory: `.claude/context/`

`0x_conventions.md` 存放跨步骤复用的核心规则。`inject_context.py` 会在 compact 后把该文件内容通过 `additionalContext` 重新交给 Claude，同时把 compact summary 记录到 `last_compact_summary.md`。

`0x_conventions.md` stores cross-step rules. After compact, `inject_context.py` re-injects the content via `additionalContext` and saves the compact summary to `last_compact_summary.md`.

长期稳定规则仍应优先放在 `.claude/CLAUDE.md` 和 `.claude/rules/`。Long-term rules should still go in `.claude/CLAUDE.md` and `.claude/rules/`.

---

## 第三层：Hooks 自动验证 / Layer 3: Hook Auto-Validation

目标目录 / Target directory: `.claude/hooks/`

| Hook | 脚本 / Script | 作用 / Purpose |
|------|------|------|
| PostToolUse | `validate_sql.py` | 写入/编辑 SQL 后检查规范 / Check SQL conventions after write/edit |
| PreToolUse | `block_dangerous_ddl.py` | Bash 执行前阻断危险 DDL / Block dangerous DDL before Bash execution |
| PostCompact | `inject_context.py` | 重注入数仓规范，并记录 compact 摘要 / Re-inject rules, record compact summary |

`validate_sql.py` 读取 Claude Code 传入的 stdin JSON，取出 `tool_input.file_path`，只检查 `.sql` 文件。

Reads stdin JSON from Claude Code, extracts `tool_input.file_path`, only checks `.sql` files.

阻断规则 / Blocking rules:

- `SELECT *`
- `INSERT` / `INSERT OVERWRITE` 缺少 `PARTITION` / Missing `PARTITION`
- `UPDATE` / `DELETE` 缺少 `WHERE` / Missing `WHERE`
- 金额字段使用 `DOUBLE` / Money field uses `DOUBLE`
- 分区字段使用 `dt` 而不是 `partition_dt` / Partition field uses `dt` instead of `partition_dt`

---

## 第四层：Subagents 上下文隔离 / Layer 4: Subagent Context Isolation

默认所有 agent 使用 `model: opus`，先保证复杂数仓任务的准确性。成本敏感时，可以把 `sql-validator`、`dw-explorer` 调整为 `sonnet` 或 `haiku`。

All agents default to `model: opus` for reliability. For cost-sensitive teams, downgrade `sql-validator` and `dw-explorer` to `sonnet` or `haiku`.

适合交给 subagent 的工作 / Work suitable for subagents:

| 工作 / Work | 推荐 agent / Recommended agent |
|------|------------|
| 表结构、DDL、血缘探索 / Table structure, DDL, lineage | `dw-explorer` |
| SQL 语法和规范复核 / SQL syntax and convention review | `sql-validator` |
| 23 项标准自测 / 23-item standard self-test | `data-quality-checker` |
| 新旧表数据比对 / Old vs. new table comparison | `data-comparator` |

主对话只接收摘要，不接收全量执行日志、样本数据和长 DDL。The main conversation only receives summaries, not full logs, sample data, or long DDL.

---

## 第五层：Skills + Rules 标准化流程 / Layer 5: Skills + Rules Standardization

Skills 放在 / Skills are located at:

```text
.claude/skills/<skill-name>/SKILL.md
```

当前模板的 8 个 skill / The template's 8 skills:

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

Rules 放在 / Rules are located at:

```text
.claude/rules/*.md
```

Path-scoped rules 只在 Claude 读取匹配文件时加载，例如 `etl-rules.md` 只对 `insert*.sql`、`*_di.sql`、`*_df.sql` 等路径生效。

Path-scoped rules only load when Claude reads matching files. For example, `etl-rules.md` only applies to `insert*.sql`, `*_di.sql`, `*_df.sql`, etc.
