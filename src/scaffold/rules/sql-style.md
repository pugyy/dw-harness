---
paths:
  - "**/*.sql"
---

# SQL 通用规范（按路径自动加载）

- 禁止 `SELECT *` / `t.*`；`COUNT(*)` 例外
- `INSERT (OVERWRITE)` 声明目标 `PARTITION`（StarRocks 项目可配置降级）
- `UPDATE` / `DELETE` 必须带 `WHERE`
- 金额 `DECIMAL(20,4)`；币种/单位见契约
- 注释三段式：业务含义 | 数据来源 | 计算逻辑
- 引擎语法与项目政策是两回事：报告里 `kind=engine` 是引擎限制，`kind=policy` 是团队约定
