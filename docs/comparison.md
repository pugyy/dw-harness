# 传统方式 vs Harness / Conventional Approach vs. Harness

## 核心对比 / Core Comparison

| 维度 / Dimension | 传统提示词方式 / Conventional | dw-harness 方式 / With Harness |
|------|----------------|-----------------|
| 字段口径 / Field definitions | 靠对话历史，compact 后容易丢 / Relies on conversation history, lost after compact | 写入 `CLAUDE.md` 和 context 文件 / Persisted in `CLAUDE.md` and context files |
| SQL 规范 / SQL conventions | 靠模型记忆 / Relies on model memory | hook 自动检查 / Hook auto-checks |
| 危险 DDL / Dangerous DDL | 靠人工提醒 / Relies on manual reminders | PreToolUse hook 阻断 / PreToolUse hook blocks |
| 大量输出 / Large output | 堆进主 context / Piled into main context | subagent 只返回摘要 / Subagent returns summaries |
| 流程标准 / Process consistency | 每次重新说明 / Re-explained every time | 8 个 skills 固化 / Locked in via 8 skills |
| 路径规范 / Path-scoped rules | 全量塞进提示词 / All loaded into prompt | path-scoped rules 按需加载 / Loaded on demand by path |

---

## 四类典型问题 / Four Typical Problems

### 字段口径遗忘 / Forgotten Field Definitions

现象：对话开始时说明 `amount` 单位是千元，compact 后模型生成 SQL 时误按元处理。

What happens: You tell Claude `amount` is in thousands. After compact, it generates SQL treating it as ones.

做法：把字段口径写入 `.claude/CLAUDE.md` 的"本次迭代约束"，上线后沉淀为长期规则或 context 摘要。

Fix: Write field definitions into `.claude/CLAUDE.md` under "iteration constraints". After release, promote to long-term rules or context summary.

### SQL 规范遗漏 / Missed SQL Conventions

现象：模型偶尔生成 `SELECT *` 或忘记 `PARTITION`。

What happens: The model occasionally generates `SELECT *` or forgets `PARTITION`.

做法：`validate_sql.py` 在写入 `.sql` 后自动检查，失败时阻断并把错误返回给 Claude 修正。

Fix: `validate_sql.py` auto-checks after writing `.sql`. On failure, blocks and feeds the error back to Claude for correction.

### 危险操作 / Dangerous Operations

现象：调试时 Bash 命令里带了 `DROP TABLE`、`TRUNCATE TABLE`。

What happens: Debugging Bash commands contain `DROP TABLE` or `TRUNCATE TABLE`.

做法：`block_dangerous_ddl.py` 在 Bash 执行前读取 `tool_input.command`，危险语句直接 `deny`。

Fix: `block_dangerous_ddl.py` reads `tool_input.command` before Bash execution. Dangerous statements are denied outright.

### Context 膨胀 / Context Bloat

现象：血缘查询、自测结果、数据比对样本把主对话撑满，后续推理质量下降。

What happens: Lineage queries, test results, and comparison samples flood the main conversation, degrading later reasoning.

做法：让 `dw-explorer`、`data-quality-checker`、`data-comparator` 在独立 context 中运行，主对话只接收摘要。

Fix: Run `dw-explorer`, `data-quality-checker`, `data-comparator` in isolated contexts. Main conversation only receives summaries.

---

## 结论 / Conclusion

Harness 的价值不是让 AI "更聪明"，而是把确定性环节从模型记忆中移出来。

The value of Harness is not making AI "smarter". It's extracting deterministic steps from model memory.

- 规范执行交给 hook / Convention enforcement goes to hooks
- 项目约束交给文件 / Project constraints go to files
- 大输出交给 subagent / Large output goes to subagents
- 标准流程交给 skill / Standard workflow goes to skills
