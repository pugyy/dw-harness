---
paths:
  - "**/*_sr_*.sql"
  - "**/sr/**"
---

# StarRocks 规范

- 建表声明 `PRIMARY/DUPLICATE/UNIQUE KEY` 与 `DISTRIBUTED BY`（或确认使用默认分桶）
- SR `INSERT` 可省略分区（自动路由）——引擎合法；项目政策默认降级为告警
- 金额同步自 MaxCompute 时单位以契约为准，转换在契约 `unit` 中声明
- 同步任务上线前跑 `/dw-sr` 风险矩阵
