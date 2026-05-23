# Skill 命令手册 / Skill Command Reference

`dw-harness` 的 skills 使用 Claude Code 标准结构 / dw-harness skills use the standard Claude Code structure:

```text
.claude/skills/<skill-name>/SKILL.md
```

目录名就是 slash command 名称，例如 `.claude/skills/dw-etl/SKILL.md` 对应 `/dw-etl`。

The directory name is the slash command. For example, `.claude/skills/dw-etl/SKILL.md` corresponds to `/dw-etl`.

当前目录结构 / Current directory structure:

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

---

## 8 个命令 / 8 Commands

| 命令 / Command | 步骤 / Step | 核心产出 / Output |
|------|---------|---------|
| `/dw-requirement-analysis` | Step 1 需求分析 / Requirement Analysis | 需求摘要、字段口径草稿、待确认问题清单 / Summary, field draft, open questions |
| `/dw-technical-design` | Step 2 技术设计 / Technical Design | OneData 建模说明、主键/分区/粒度设计 / Modeling doc, PK/partition/granularity |
| `/dw-etl` | Step 3 ETL 开发 / ETL Development | ODPS DDL、Insert SQL、SR 建表 / ODPS DDL, Insert SQL, SR table |
| `/dw-self-test` | Step 4 自测 / Self Test | 23 项标准自测摘要 / 23-item test summary |
| `/dw-data-comparison` | Step 5 数据比对 / Data Comparison | 差异字段、差异率、结论 / Diff fields, rates, conclusion |
| `/dw-sr` | Step 6 SR 导入 / SR Import | SR 建表语句、同步配置、风险分析 / SR DDL, sync config, risk analysis |
| `/dw-performance-optimization` | Step 7 性能优化 / Performance Tuning | SQL 和资源优化建议 / SQL and resource tuning suggestions |
| `/dw-dqc` | Step 8 SLA/DQC | DQC 规则 JSON、SLA 配置 / DQC rules JSON, SLA config |

---

## 以 `/dw-etl` 为例 / Example: `/dw-etl`

`/dw-etl` 封装 ETL 开发最容易遗漏的要求 / Encapsulates the most commonly missed requirements in ETL development:

1. 建表文件 / DDL file: `ddl_[表名].sql`
2. 插入文件 / Insert file: `insert_[表名].sql`
3. SR 建表 / SR table: `ddl_sr_[表名].sql`
4. `INSERT OVERWRITE` 必须带 `PARTITION` / Must include `PARTITION`
5. 金额字段使用 `DECIMAL(20,4)` / Money fields use `DECIMAL(20,4)`
6. 写入 `.sql` 后由 hook 自动检查 / Hook auto-checks after writing `.sql`

---

## 文章术语对照 / Terminology Mapping

早期文章里使用过中文步骤叫法。项目模板实际只提供英文命令，下表用于把文章里的步骤名称对应到当前真实命令。

The original article used Chinese step names. The template only provides English commands. This table maps article names to actual commands.

| 文章步骤名 / Article name | 当前命令 / Current command |
|------------|----------|
| 需求分析 | `/dw-requirement-analysis` |
| 技术设计 | `/dw-technical-design` |
| 自测 | `/dw-self-test` |
| 数据比对 | `/dw-data-comparison` |
| 性能优化 | `/dw-performance-optimization` |

`/dw-etl`、`/dw-sr`、`/dw-dqc` 保持不变。 / These three remain unchanged.
