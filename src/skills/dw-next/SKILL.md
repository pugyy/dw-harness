---
name: dw-next
description: >
  从已验证的交付物推断八步流程进度并给出下一步。适用于会话开始、
  compact 之后、或不确定当前做到哪一步时。
allowed-tools: Read, Glob, Bash(dw next:*)
---

# dw-next：进度推断

```bash
dw next
```

进度不看会话记忆，只看文件证据：

| Step | 交付物判定 |
|---|---|
| 1 需求 | `01_requirement*.md` |
| 2 设计 | `02_design*.md` + 契约 |
| 3 ETL | `ddl_*.sql` + `insert_*.sql` |
| 4 自测 | `04_self_test*.md` |
| 5 比对 | `.claude/dw/evidence/reconcile-*.json` |
| 6 SR | `ddl_sr_*.sql` |
| 7 性能 | `07_perf*.md` |
| 8 DQC | `dqc_*.json` |

## 输出

- 已完成步骤 + 证据文件
- 下一步（第一个缺交付物的步骤）+ 该步命令
- `.claude/dw/state.json` 里的当前表/版本/约束（SessionStart 注入的同一来源）

规则：说"做完了"不算，文件在才算。
