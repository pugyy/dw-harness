---
name: dw-bootstrap
description: 初始化/迁移 dw-harness 到当前项目（写 AGENTS.md、rules、harness.json，合并 settings.json）。仅在用户明确要求安装或升级 harness 时使用。
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Glob, Bash(dw init:*), Bash(dw doctor:*)
---

# dw-bootstrap：安装 / 迁移

## 流程

1. 合并式安装（不覆盖用户修改，写备份）：

```bash
dw init --target . --python python
```

2. 首次安装检查：`dw doctor`
3. v1 项目升级：旧 hook 自动停用，八个旧命令对照见 `docs/upgrade-from-v1.md`
   （插件模式命令带 `dw-harness:` 前缀；模板模式保留原名）

## 要点

- 重复执行不产生重复 hook 配置（按 matcher 去重）
- 用户改过的文件报 conflict 并保留原样，绝不动手覆盖
- 需要 MCP 时：`dw init --mcp`（默认关闭，显式开启）

## 交付物

AGENTS.md、CLAUDE.md（引用 @AGENTS.md）、.claude/dw/*、.claude/rules/*、settings.json 合并报告
