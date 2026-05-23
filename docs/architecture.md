# 架构设计 / Architecture

## 总览 / Overview

```text
用户需求 / User request
  |
  v
Claude Code 主会话 / Main session
  |
  +-- CLAUDE.md / context：保存项目约束和字段口径 / Persist project constraints and field definitions
  +-- rules：按路径加载 SQL/ETL 规范 / Load SQL/ETL rules by path
  +-- skills：触发 8 步标准流程 / Trigger 8-step workflow
  +-- hooks：自动检查 SQL、阻断危险 DDL / Auto-check SQL, block dangerous DDL
  +-- subagents：隔离血缘、自测、比对等高 token 工作 / Isolate high-token work
  |
  v
SQL 产出 + 质量报告 + DQC/SR 配置 / SQL output + quality report + DQC/SR config
```

## 组件职责 / Component Responsibilities

| 组件 / Component | 路径 / Path | 职责 / Responsibility |
|------|------|------|
| 项目记忆 / Project memory | `.claude/CLAUDE.md` | 当前迭代状态、字段口径、全局规范 / Current iteration state, field definitions, global conventions |
| 上下文摘要 / Context summary | `.claude/context/` | 跨步骤复用规则、compact 摘要 / Cross-step rules, compact summaries |
| 自动化护栏 / Automation guard | `.claude/hooks/` | 确定性检查和危险操作阻断 / Deterministic checks and dangerous op blocking |
| 专用 agent / Dedicated agent | `.claude/agents/` | 高 token 工作隔离 / High-token work isolation |
| 路径规则 / Path rules | `.claude/rules/` | 文件路径匹配后的按需规范 / On-demand rules matched by file path |
| 流程技能 / Workflow skills | `.claude/skills/` | 8 步数仓流程 / 8-step DW workflow |

## Hook 数据流 / Hook Data Flow

```text
Claude 写入 SQL / Claude writes SQL
  |
  v
PostToolUse hook
  |
  v
validate_sql.py 读取 stdin JSON / reads stdin JSON
  |
  +-- 通过：exit 0 / Pass: exit 0
  |
  +-- 失败：stderr 输出问题，exit 2 阻断 / Fail: stderr output, exit 2 block
```

## Agent 目录 / Agent Directory

```text
.claude/agents/
├── sql-validator/sql-validator.md
├── dw-explorer/dw-explorer.md
├── data-quality-checker/data-quality-checker.md
└── data-comparator/data-comparator.md
```

四个 agent 默认均使用 `model: opus`。这是偏可靠性的默认配置，适合公开模板；落到团队内部后可以按成本和任务难度调整模型。

All four agents default to `model: opus`. This prioritizes reliability for a public template. Adjust per your team's cost and task requirements.

## Skill 目录 / Skill Directory

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

每个 skill 目录名就是实际 slash command 名称。Each skill directory name is the actual slash command name.

危险 DDL 使用 PreToolUse：

```text
Claude 准备执行 Bash / Claude about to run Bash
  |
  v
block_dangerous_ddl.py 读取 tool_input.command / reads tool_input.command
  |
  +-- 安全：exit 0 / Safe: exit 0
  |
  +-- 危险：返回 permissionDecision=deny / Dangerous: returns deny
```

## 设计原则 / Design Principles

1. 确定性检查放在 hook，不依赖模型记忆。 / Deterministic checks in hooks, not model memory.
2. 业务口径放在文件，不依赖临时对话。 / Business definitions in files, not ad-hoc conversation.
3. 大输出放到 subagent，不污染主 context。 / Large output in subagents, not main context.
4. 任务流程放进 skill，减少每次重复解释。 / Workflow in skills, less re-explaining.
5. 路径相关规范放进 rules，按需加载。 / Path-scoped rules, loaded on demand.
