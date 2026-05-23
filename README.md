<div align="center">

# dw-harness

**数仓 AI 编程，不靠记忆，靠代码**

Data Warehouse AI Coding Harness

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-green.svg)]()

</div>

---

## 这是什么 / What is this

> **中文**
>
> 用 Claude Code 做数仓开发，聊久了 AI 就开始犯糊涂——忘字段口径、SQL 不合规范、血缘查询把上下文撑爆。这些坑做数仓的人都踩过。
>
> `dw-harness` 把这些反复踩的坑变成了代码：hooks 自动拦截问题 SQL，subagents 把重活隔离出去，skills 把八步流程写死。复制到项目里，启动 `claude` 就能用。
>
> 不需要从零教 AI 你的规范，因为它根本不该靠"记住"。

> **English**
>
> If you use Claude Code for data warehouse work, you know the drill: long conversations make AI sloppy — forgetting field definitions, writing SQL that breaks your conventions, lineage queries eating up the entire context window.
>
> `dw-harness` turns these recurring headaches into code: hooks block bad SQL automatically, subagents isolate heavy lifting, skills lock in an 8-step workflow. Copy it into your project, run `claude`, done.
>
> Your conventions shouldn't rely on AI "remembering" them.

---

## 解决了什么 / Problems it solves

| 问题 / Problem | 你遇到的 / What happens | 怎么办 / Fix |
|---|---|---|
| AI 忘事 / Forgets things | compact 之后字段口径、本轮约束全丢了 / After compact, field definitions and iteration constraints are gone | `CLAUDE.md` + `context/` 写到文件里，compact 后自动重注入 / Persist to files, re-inject after compact |
| 规范写不住 / Can't enforce conventions | 还是会出现 `SELECT *`、缺 `PARTITION`、金额字段用 `DOUBLE` / Still getting `SELECT *`, missing `PARTITION`, `DOUBLE` on money fields | PostToolUse hook，写完 SQL 自动查，违规直接拦 / Auto-check on write, block on violation |
| 误操作 / Accidental damage | Bash 里不小心跑了 `DROP TABLE` / `TRUNCATE` / Accidentally running `DROP TABLE` / `TRUNCATE` in Bash | PreToolUse hook，危险命令执行前拦住 / Block dangerous commands before execution |
| Context 爆了 / Context overflow | 血缘、自测、比对结果塞满主对话 / Lineage, test results, comparison data flooding the conversation | subagents 接走重活，只把摘要交回来 / Subagents handle heavy work, only return summaries |
| 流程对不上 / No consistent process | 每次做需求都要从头给 AI 讲一遍流程 / Re-explaining the entire process every time | 8 个 skill 命令，流程写死 / 8 skill commands, workflow locked in |

---

## 快速上手 / Quick Start

### 1. 跑一下测试 / Run the smoke tests

确认模板没问题 / Make sure the template works:

```bash
python tests/run_hook_smoke_tests.py
```

### 2. 复制到你的项目 / Copy into your project

macOS / Linux:

```bash
git clone https://github.com/pugyy/dw-harness.git
cp -r dw-harness/template/.claude /your-dw-project/
cd /your-dw-project
claude
```

Windows PowerShell:

```powershell
git clone https://github.com/pugyy/dw-harness.git
Copy-Item -Recurse .\dw-harness\template\.claude C:\path\to\your-dw-project\
Set-Location C:\path\to\your-dw-project
claude
```

> Hook 脚本默认用 `python` 调用。如果你的系统只有 `python3`，改一下 `.claude/settings.json` 里的命令就行。
>
> Hook scripts use `python` by default. If your system only has `python3`, change the commands in `.claude/settings.json`.

### 3. 改一下 CLAUDE.md / Edit CLAUDE.md

填上你当前在开发的表名、版本、字段口径、不能动的表这些信息。
Fill in your current table name, version, field definitions, and tables that should not be modified.

---

## 五层防御 / Five Layers of Defense

| Layer | 中文 | English |
|:---:|---|---|
| 5 | SKILL 改造 -- 按需加载，不浪费 context | Skill refactor -- load on demand |
| 4 | Subagents -- 重活隔离出去，只回收结果 | Isolate heavy work, return summaries |
| 3 | Hooks -- 规范检查交给代码，不靠 AI 记 | Code-enforced checks, not model memory |
| 2 | Auto Memory -- 跨会话自动积累踩坑经验 | Cross-session knowledge accrual |
| 1 | CLAUDE.md -- 约束写死，compact 后重注入 | Persisted constraints, re-injected |

> 详细说明 / Full details: [docs/five-layers-defense.md](docs/five-layers-defense.md)

---

## 八步流程 / 8-Step Workflow

```
需求分析 ──→ 技术设计 ──→ ETL开发 ──→ 自测 ──→ 数据比对 ──→ SR导入 ──→ 性能优化 ──→ SLA/DQC
Analysis ──→ Design  ──→ ETL Dev  ──→ Test ──→ Compare  ──→ SR Import─→ Perf Tune ──→ SLA/DQC
```

| 步骤 / Step | 命令 / Command | 产出 / Output |
|---|---|---|
| 1 需求分析 / Requirement Analysis | `/dw-requirement-analysis` | 需求摘要、字段口径草稿、待确认问题清单 / Requirement summary, field caliper draft, open questions |
| 2 技术设计 / Technical Design | `/dw-technical-design` | OneData 建模说明、主键/分区/粒度设计 / OneData modeling, PK/partition/granularity design |
| 3 ETL 开发 / ETL Development | `/dw-etl` | ODPS DDL + Insert SQL + SR 建表 / ODPS DDL + Insert SQL + SR table |
| 4 自测 / Self Test | `/dw-self-test` | 23 项标准自测摘要 / 23-item standard test summary |
| 5 数据比对 / Data Comparison | `/dw-data-comparison` | 差异字段、差异率、结论 / Diff fields, diff rates, conclusion |
| 6 SR 导入 / SR Import | `/dw-sr` | SR 建表语句、同步配置、风险分析 / SR DDL, sync config, risk analysis |
| 7 性能优化 / Performance Tuning | `/dw-performance-optimization` | SQL 和资源优化建议 / SQL and resource tuning suggestions |
| 8 SLA/DQC | `/dw-dqc` | DQC 规则 JSON、SLA 配置 / DQC rules JSON, SLA config |

> 详细说明 / Full details: [docs/eight-steps-workflow.md](docs/eight-steps-workflow.md)

---

## Hook 规则 / Hook Rules

### `validate_sql.py` — 写完 SQL 自动查 / Auto-check on write

- `SELECT *` -- 不行，必须写清楚字段 / Not allowed, list fields explicitly
- `INSERT` 不带 `PARTITION` -- 不行，必须指定分区 / Not allowed, specify partition
- `UPDATE` / `DELETE` 不带 `WHERE` -- 不行，必须加条件 / Not allowed, add WHERE clause
- 金额字段用 `DOUBLE` -- 不行，换成 `DECIMAL(20,4)` / Money field uses DOUBLE -- not allowed, use `DECIMAL(20,4)`
- 分区字段叫 `dt` -- 不行，统一叫 `partition_dt` / Partition field named `dt` -- not allowed, use `partition_dt`

支持 ODPS/MaxCompute、Hive、Spark SQL。默认按环境变量 `DW_HARNESS_DIALECT`、文件名/近邻目录、SQL 文件头部注释和语法特征自动判断；不确定时按 ODPS 处理。

Supports ODPS/MaxCompute, Hive, and Spark SQL. Detection checks `DW_HARNESS_DIALECT`, file names/nearby directories, header comments, and dialect syntax; ODPS is the fallback.

### `block_dangerous_ddl.py` — 执行前拦住 / Block before execution

- `DROP TABLE` / `DROP DATABASE`
- `TRUNCATE TABLE`
- `ALTER TABLE ... DROP COLUMN`
- `DELETE FROM` 不带 `WHERE` / `DELETE FROM` without `WHERE`

---

## 项目结构 / Project Structure

```text
dw-harness/
├── README.md
├── docs/                            # 设计文档 / Design docs
├── examples/
│   ├── example_claude_md.md         # CLAUDE.md 填写示例 / CLAUDE.md example
│   └── sample-sql/                  # 好/坏 SQL 示例 / Good/bad SQL samples
├── template/.claude/                # <-- 复制这个目录到你的项目 / Copy this to your project
│   ├── CLAUDE.md                    # 上下文持久化 / Context persistence
│   ├── settings.json                # Hooks 配置 / Hook config
│   ├── context/                     # compact 后重注入的规范 / Re-injected after compact
│   ├── hooks/                       # 自动化脚本 / Automation scripts (Python)
│   ├── agents/                      # 4 个 subagent
│   ├── rules/                       # 路径级规范，按需加载 / Path-scoped rules, load on demand
│   └── skills/                      # 8 个 SKILL 文件 / 8 SKILL files
└── tests/                           # Hook 冒烟测试 / Hook smoke tests
```

所有 subagent 默认用 `opus`，图个稳。复制过去之后想省钱可以改成 `sonnet` 或 `haiku`。

All subagents default to `opus` for reliability. Downgrade to `sonnet` or `haiku` if cost is a concern.

---

## 为什么这么做 / Why this approach

**中文**：数仓 AI 开发的瓶颈从来不是 AI 不会写 SQL，而是两件事老出问题：语义理解对不上、规范执行不稳定。所以思路很简单——**人擅长的事（判断口径、理清语义）写死到文件里，AI 擅长的事（检查规范、干重复活）交给代码去强制执行。** 别让 AI 靠"记住"来做事，让它靠代码来做事。

**English**: The bottleneck in DW AI development is never about whether AI can write SQL. It's about two things that keep breaking: getting the semantics right, and enforcing conventions consistently. The idea is straightforward -- **persist human judgment (field definitions, semantics) into files, and let code enforce what AI is good at (checking rules, doing repetitive work).** Don't make AI rely on "remembering". Make it rely on code.

---

## 参考 / References

- [Claude Code Hooks](https://docs.anthropic.com/en/docs/claude-code/hooks)
- [Claude Code Skills](https://docs.anthropic.com/en/docs/claude-code/skills)
- [Claude Code Memory & Rules](https://docs.anthropic.com/en/docs/claude-code/memory)

---

## License

[MIT](LICENSE)
