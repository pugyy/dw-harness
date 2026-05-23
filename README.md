# dw-harness

> Data Warehouse AI Coding Harness — 面向数仓开发的 Claude Code 工程化模板

`dw-harness` 把数仓 AI 开发中容易靠记忆执行的要求，沉淀成可复用的 Claude Code 项目模板：`CLAUDE.md` 持久化约束、path-scoped rules 按需加载规范、hooks 自动拦截坏 SQL、subagents 隔离高 token 工作、skills 固化 8 步数仓流程。

Maintainer: PIGYY

## 解决的问题

| 痛点 | 常见表现 | Harness 解法 |
|------|----------|-------------|
| AI "失忆" | compact 后忘记字段口径和本轮约束 | `.claude/CLAUDE.md` + `.claude/context/` 持久化 |
| 规范靠记忆 | `SELECT *`、缺少 `PARTITION`、金额字段用 `DOUBLE` | PostToolUse hook 自动检查 SQL |
| 危险操作风险 | Bash 里误执行 `DROP TABLE` / `TRUNCATE TABLE` | PreToolUse hook 阻断危险 DDL |
| Context 膨胀 | 血缘、自测、比对结果撑满主对话 | subagents 只返回摘要 |
| 流程不稳定 | 每次需求都重新讲流程 | 8 个标准化 skills |

## 快速开始

### 1. 验证模板本身

```bash
python tests/run_hook_smoke_tests.py
```

### 2. 复制到你的数仓项目

macOS / Linux:

```bash
git clone https://github.com/PIGYY/dw-harness.git
cp -r dw-harness/template/.claude /your-dw-project/
cd /your-dw-project
claude
```

Windows PowerShell:

```powershell
git clone https://github.com/PIGYY/dw-harness.git
Copy-Item -Recurse .\dw-harness\template\.claude C:\path\to\your-dw-project\
Set-Location C:\path\to\your-dw-project
claude
```

> Hook 命令默认使用 `python`。如果你的机器只有 `python3`，把目标项目 `.claude/settings.json` 里的 `python .claude/hooks/*.py` 改成 `python3 .claude/hooks/*.py`。

### 3. 填写项目上下文

编辑目标项目里的 `.claude/CLAUDE.md`，填入当前表名、版本、node_id、字段口径、本轮禁止修改的表等信息。

## 8 步数仓流程

| 步骤 | Skill 命令 | 核心产出 |
|------|------------|---------|
| Step 1 需求分析 | `/dw-requirement-analysis` | 需求摘要、字段口径草稿、待确认问题清单 |
| Step 2 技术设计 | `/dw-technical-design` | OneData 建模说明、主键/分区/粒度设计 |
| Step 3 ETL 开发 | `/dw-etl` | ODPS DDL、Insert SQL、SR 建表 |
| Step 4 自测 | `/dw-self-test` | 23 项标准自测摘要 |
| Step 5 数据比对 | `/dw-data-comparison` | 差异字段、差异率、结论 |
| Step 6 SR 导入 | `/dw-sr` | SR 建表语句、同步配置、风险分析 |
| Step 7 性能优化 | `/dw-performance-optimization` | SQL 和资源优化建议 |
| Step 8 SLA/DQC | `/dw-dqc` | DQC 规则 JSON、SLA 配置 |

## 项目结构

```text
dw-harness/
├── README.md
├── docs/
│   ├── architecture.md
│   ├── five-layers-defense.md
│   ├── eight-steps-workflow.md
│   ├── skill-commands.md
│   └── comparison.md
├── examples/
│   ├── example_claude_md.md
│   └── sample-sql/
│       ├── bad_select_star.sql
│       └── good_insert.sql
├── template/
│   └── .claude/
│       ├── CLAUDE.md
│       ├── settings.json
│       ├── context/
│       │   └── 0x_conventions.md
│       ├── hooks/
│       │   ├── validate_sql.py
│       │   ├── block_dangerous_ddl.py
│       │   └── inject_context.py
│       ├── agents/
│       │   ├── sql-validator/sql-validator.md
│       │   ├── dw-explorer/dw-explorer.md
│       │   ├── data-quality-checker/data-quality-checker.md
│       │   └── data-comparator/data-comparator.md
│       ├── rules/
│       └── skills/
│           ├── dw-requirement-analysis/SKILL.md
│           ├── dw-technical-design/SKILL.md
│           ├── dw-etl/SKILL.md
│           ├── dw-self-test/SKILL.md
│           ├── dw-data-comparison/SKILL.md
│           ├── dw-sr/SKILL.md
│           ├── dw-performance-optimization/SKILL.md
│           └── dw-dqc/SKILL.md
└── tests/
    └── run_hook_smoke_tests.py
```

默认所有 subagent 使用 `model: opus`，优先保证数仓分析、质量检查和比对结果的可靠性。你可以在目标项目复制模板后，按团队成本要求把只读探索类 agent 调低到 `sonnet` 或 `haiku`。

## Hook 规则

`validate_sql.py` 会在 Claude Code 写入或编辑 `.sql` 文件后自动检查：

- 禁止 `SELECT *`
- `INSERT` / `INSERT OVERWRITE` 必须带 `PARTITION`
- `UPDATE` / `DELETE` 必须带 `WHERE`
- 金额字段不允许 `DOUBLE`，使用 `DECIMAL(20,4)`
- 分区字段统一为 `partition_dt`

`block_dangerous_ddl.py` 会在 Bash 执行前阻断：

- `DROP TABLE`
- `TRUNCATE TABLE`
- `DROP DATABASE`
- `ALTER TABLE ... DROP COLUMN`
- 无 `WHERE` 的 `DELETE FROM`

## 设计目标

下面是该模板希望帮助团队达成的工程目标，不是未经上下文说明的通用 benchmark：

| 维度 | 目标 |
|------|------|
| SQL 规范执行 | 从提示词记忆转为 hook 强制检查 |
| 需求口径沉淀 | 从对话临时约束转为文件持久化 |
| 主 context 压力 | 高 token 操作交给 subagent，只回收摘要 |
| 交付流程 | 8 步标准化，减少每次重复解释 |

## 参考

- Claude Code hooks: https://code.claude.com/docs/en/hooks
- Claude Code skills: https://code.claude.com/docs/en/skills
- Claude Code memory/rules: https://code.claude.com/docs/en/memory

## License

MIT
