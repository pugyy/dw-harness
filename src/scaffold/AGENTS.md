# dw-harness 数仓工程规范（AGENTS.md）

本文件是跨工具共享的规范入口（Claude Code 通过 CLAUDE.md 的 `@AGENTS.md` 引用；
Codex / Cursor / ZCode 等可直接读取）。项目个性信息在 CLAUDE.md 与 contract 中。

## 硬规则（hook 强制，违反会被拦）

- 禁止 `SELECT *` / `t.*`，必须显式列字段（`COUNT(*)` 不受限）
- `INSERT (OVERWRITE)` 必须声明目标 `PARTITION`；StarRocks 按项目配置降级为告警
- `UPDATE` / `DELETE` 必须带 `WHERE`
- 分区字段统一 `partition_dt STRING`（yyyyMMdd），不叫 `dt`
- 金额字段 `DECIMAL(20,4)`，禁止 `DOUBLE`；币种与单位在契约中分开声明
- 受保护对象（`.claude/dw/harness.json` 的 `protected_objects`）禁止写入性操作
- 生产环境（`DW_HARNESS_PROD=1`）破坏性操作一律拒绝，走正式发布入口

## 八步工作流（MaxCompute → StarRocks 主线）

1. `/dw-requirement-analysis` 需求分析 → 需求摘要 + 字段口径草稿 + 待确认清单
2. `/dw-technical-design` 技术设计 → OneData 建模 + 契约 contract.yaml 定稿
3. `/dw-etl` ETL 开发 → `ddl_[表].sql` + `insert_[表].sql`（+ `ddl_sr_[表].sql`）
4. `/dw-self-test` 自测 → 23 项检查报告（fork 隔离运行）
5. `/dw-data-comparison` 数据比对 → `dw reconcile` 键级对账证据
6. `/dw-sr` SR 导入 → SR DDL + 风险分析
7. `/dw-performance-optimization` 性能优化 → 计划/静态判断说明
8. `/dw-dqc` SLA/DQC → `dw dqc gen` 稳定 ID 规则

进度由 `/dw-next` 从已验证交付物推断，不依赖会话记忆。

## 确定性命令（模型解释结果，不放行）

- 校验：`dw lint <files>`
- 验收：`dw check --table <t>`（四态：PASS/FAIL/UNVERIFIED/N-A）
- 对账：`dw reconcile --spec <spec.json>`
- 契约：`dw contract validate|diff|compile`
- 计划：`dw plan ddl|backfill`（预演只读）

## 上下文纪律

- 主对话只保留决策级信息；血缘、自测、比对交给 subagent / `context: fork`
- 长期规范进本文件与 `.claude/rules/`；迭代状态进 `.claude/dw/state.json`
- 契约是字段口径唯一真源；CLAUDE.md 只放“当前在做什么”
