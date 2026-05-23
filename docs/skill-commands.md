# Skill 命令手册

`dw-harness` 的 skills 使用 Claude Code 标准结构：

```text
.claude/skills/<skill-name>/SKILL.md
```

目录名就是 slash command 名称，例如 `.claude/skills/dw-etl/SKILL.md` 对应 `/dw-etl`。

## 8 个命令

| 命令 | 对应步骤 | 核心产出 |
|------|---------|---------|
| `/dw-requirement-analysis` | Step 1 需求分析 | 需求摘要、字段口径草稿、待确认问题清单 |
| `/dw-technical-design` | Step 2 技术设计 | OneData 建模说明、主键/分区/粒度设计 |
| `/dw-etl` | Step 3 ETL 开发 | ODPS DDL、Insert SQL、SR 建表 |
| `/dw-self-test` | Step 4 自测 | 23 项标准自测摘要 |
| `/dw-data-comparison` | Step 5 数据比对 | 差异字段、差异率、结论 |
| `/dw-sr` | Step 6 SR 导入 | SR 建表语句、同步配置、风险分析 |
| `/dw-performance-optimization` | Step 7 性能优化 | SQL 和资源优化建议 |
| `/dw-dqc` | Step 8 SLA/DQC | DQC 规则 JSON、SLA 配置 |

## 以 `/dw-etl` 为例

`/dw-etl` 封装 ETL 开发最容易遗漏的要求：

1. 建表文件：`ddl_[表名].sql`
2. 插入文件：`insert_[表名].sql`
3. SR 建表：`ddl_sr_[表名].sql`
4. `INSERT OVERWRITE` 必须带 `PARTITION`
5. 金额字段使用 `DECIMAL(20,4)`
6. 写入 `.sql` 后由 hook 自动检查

## 旧命令映射

早期文章里使用过中文命令名。为了文件系统和跨团队使用更稳定，项目模板改为英文命令：

| 旧称 | 当前命令 |
|------|----------|
| `/dw-需求分析` | `/dw-requirement-analysis` |
| `/dw-技术设计` | `/dw-technical-design` |
| `/dw-自测` | `/dw-self-test` |
| `/dw-比对` | `/dw-data-comparison` |
| `/dw-优化` | `/dw-performance-optimization` |

`/dw-etl`、`/dw-sr`、`/dw-dqc` 保持不变。
