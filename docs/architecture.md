# 架构设计

## 总览

```text
用户需求
  |
  v
Claude Code 主会话
  |
  +-- CLAUDE.md / context：保存项目约束和字段口径
  +-- rules：按路径加载 SQL/ETL 规范
  +-- skills：触发 8 步标准流程
  +-- hooks：自动检查 SQL、阻断危险 DDL
  +-- subagents：隔离血缘、自测、比对等高 token 工作
  |
  v
SQL 产出 + 质量报告 + DQC/SR 配置
```

## 组件职责

| 组件 | 路径 | 职责 |
|------|------|------|
| 项目记忆 | `.claude/CLAUDE.md` | 当前迭代状态、字段口径、全局规范 |
| 上下文摘要 | `.claude/context/` | 跨步骤复用规则、compact 摘要 |
| 自动化护栏 | `.claude/hooks/` | 确定性检查和危险操作阻断 |
| 专用 agent | `.claude/agents/` | 高 token 工作隔离 |
| 路径规则 | `.claude/rules/` | 文件路径匹配后的按需规范 |
| 流程技能 | `.claude/skills/` | 8 步数仓流程 |

## Hook 数据流

```text
Claude 写入 SQL
  |
  v
PostToolUse hook
  |
  v
validate_sql.py 读取 stdin JSON
  |
  +-- 通过：exit 0
  |
  +-- 失败：stderr 输出问题，exit 2 阻断
```

## Agent 目录

```text
.claude/agents/
├── sql-validator/sql-validator.md
├── dw-explorer/dw-explorer.md
├── data-quality-checker/data-quality-checker.md
└── data-comparator/data-comparator.md
```

四个 agent 默认均使用 `model: opus`。这是偏可靠性的默认配置，适合公开模板；落到团队内部后可以按成本和任务难度调整模型。

危险 DDL 使用 PreToolUse：

```text
Claude 准备执行 Bash
  |
  v
block_dangerous_ddl.py 读取 tool_input.command
  |
  +-- 安全：exit 0
  |
  +-- 危险：返回 permissionDecision=deny
```

## 设计原则

1. 确定性检查放在 hook，不依赖模型记忆。
2. 业务口径放在文件，不依赖临时对话。
3. 大输出放到 subagent，不污染主 context。
4. 任务流程放进 skill，减少每次重复解释。
5. 路径相关规范放进 rules，按需加载。
