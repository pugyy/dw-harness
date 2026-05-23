<div align="center">

# dw-harness

**数仓 AI 编程，不再靠记忆**

Data Warehouse AI Coding Harness

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-green.svg)]()

</div>

---

## 这是什么 / What is this

> **中文** 👇
>
> 用 Claude Code 做数仓开发时，你大概率遇到过这些问题：对话一长 AI 就忘了字段口径、写出来的 SQL 不合规范、血缘查询把上下文撑爆……
>
> `dw-harness` 是一套开箱即用的 Claude Code 项目模板。它把数仓开发中那些"每次都要讲一遍但 AI 还是会忘"的东西，变成了代码级的基础设施——hooks 强制拦截坏 SQL、subagents 隔离高 token 操作、skills 把八步流程固化下来。
>
> 复制到你的项目里，`claude` 一启动就能用。

> **English** 👇
>
> When using Claude Code for data warehouse development, you've probably hit these walls: AI forgets field definitions mid-conversation, SQL it produces breaks your conventions, and lineage queries blow up the context window.
>
> `dw-harness` is a ready-to-use Claude Code project template. It turns the "things you have to repeat every time but AI still forgets" into code-level infrastructure — hooks that block bad SQL, subagents that isolate high-token work, and skills that codify an 8-step workflow.
>
> Copy it into your project, start `claude`, and you're good to go.

---

## 解决了什么 / Problems it solves

| | 问题 / Problem | 表现 / Symptom | 解法 / Solution |
|---|---|---|---|
| 🧠 | AI "失忆" / Context amnesia | compact 后字段口径、本轮约束全丢 | `CLAUDE.md` + `context/` 持久化，compact 后自动重注入 |
| 📏 | 规范靠记忆 / Conventions live in prompts | `SELECT *`、缺 `PARTITION`、金额字段用 `DOUBLE` | PostToolUse hook 写完 SQL 自动检查，违规即拦截 |
| ⚠️ | 危险操作 / Dangerous DDL | Bash 里误跑 `DROP TABLE` / `TRUNCATE` | PreToolUse hook 在执行前阻断 |
| 🎈 | Context 膨胀 / Context bloat | 血缘、自测、比对结果撑满主对话 | subagents 只返回摘要，主 context 保持干净 |
| 🔄 | 流程不稳定 / Inconsistent workflow | 每个需求都从头讲一遍流程 | 8 个标准化 skill 命令 |

---

## 快速上手 / Quick Start

### 1️⃣ 验证模板 / Verify the template

```bash
python tests/run_hook_smoke_tests.py
```

### 2️⃣ 复制到你的项目 / Copy to your project

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

> 💡 Hook 默认用 `python`。如果你的机器只有 `python3`，把 `.claude/settings.json` 里的命令改成 `python3 .claude/hooks/*.py`。

### 3️⃣ 填写项目信息 / Fill in your project context

编辑 `.claude/CLAUDE.md`，写上当前表名、版本、字段口径、本轮禁止修改的表等。

---

## 五层防御 / Five Layers of Defense

```
┌──────────────────────────────────────────────────┐
│  Layer 5  SKILL 改造 — 按需加载，减少 context 消耗  │
├──────────────────────────────────────────────────┤
│  Layer 4  Subagents — 隔离高 token 操作，只回收摘要  │
├──────────────────────────────────────────────────┤
│  Layer 3  Hooks — SQL 规范强制检查，不靠 AI 记忆    │
├──────────────────────────────────────────────────┤
│  Layer 2  Auto Memory — 跨会话自动沉淀经验和口径    │
├──────────────────────────────────────────────────┤
│  Layer 1  CLAUDE.md — 写死约束，compact 后重注入    │
└──────────────────────────────────────────────────┘
```

> 详见 / See also: [docs/five-layers-defense.md](docs/five-layers-defense.md)

---

## 八步流程 / 8-Step Workflow

```
需求分析 ──→ 技术设计 ──→ ETL开发 ──→ 自测 ──→ 数据比对 ──→ SR导入 ──→ 性能优化 ──→ SLA/DQC
```

| 步骤 / Step | Skill 命令 / Command | 核心产出 / Output |
|---|---|---|
| 1 需求分析 / Requirement Analysis | `/dw-requirement-analysis` | 需求摘要、字段口径草稿、待确认问题清单 |
| 2 技术设计 / Technical Design | `/dw-technical-design` | OneData 建模说明、主键/分区/粒度设计 |
| 3 ETL 开发 / ETL Development | `/dw-etl` | ODPS DDL + Insert SQL + SR 建表 |
| 4 自测 / Self Test | `/dw-self-test` | 23 项标准自测摘要 |
| 5 数据比对 / Data Comparison | `/dw-data-comparison` | 差异字段、差异率、结论 |
| 6 SR 导入 / SR Import | `/dw-sr` | SR 建表语句、同步配置、风险分析 |
| 7 性能优化 / Performance Tuning | `/dw-performance-optimization` | SQL 和资源优化建议 |
| 8 SLA/DQC | `/dw-dqc` | DQC 规则 JSON、SLA 配置 |

> 详见 / See also: [docs/eight-steps-workflow.md](docs/eight-steps-workflow.md)

---

## Hook 规则 / Hook Rules

### `validate_sql.py` — 写完 SQL 自动检查 / Auto-check on write

- 🚫 `SELECT *` — 必须明确字段
- 🚫 `INSERT` 不带 `PARTITION` — 必须指定分区
- 🚫 `UPDATE` / `DELETE` 不带 `WHERE` — 必须有条件
- 🚫 金额字段用 `DOUBLE` — 必须 `DECIMAL(20,4)`
- 🚫 分区字段叫 `dt` — 统一用 `partition_dt`

### `block_dangerous_ddl.py` — 执行前拦截 / Block before execution

- 🚫 `DROP TABLE` / `DROP DATABASE`
- 🚫 `TRUNCATE TABLE`
- 🚫 `ALTER TABLE ... DROP COLUMN`
- 🚫 `DELETE FROM` 不带 `WHERE`

---

## 项目结构 / Project Structure

```text
dw-harness/
├── README.md
├── docs/                            # 设计文档 / Design docs
├── examples/
│   ├── example_claude_md.md         # CLAUDE.md 填写示例
│   └── sample-sql/                  # 好/坏 SQL 示例
├── template/.claude/                # 📦 复制这个目录到你的项目
│   ├── CLAUDE.md                    # 上下文持久化
│   ├── settings.json                # Hooks 配置
│   ├── context/                     # compact 后重注入的规范
│   ├── hooks/                       # 自动化脚本 (Python)
│   ├── agents/                      # 4 个 subagent
│   ├── rules/                       # 路径级规范 (按需加载)
│   └── skills/                      # 8 个 SKILL 文件
└── tests/                           # Hook 冒烟测试
```

所有 subagent 默认使用 `model: opus`，优先保证分析质量。复制模板后可以按需降级到 `sonnet` 或 `haiku`。

> All subagents default to `model: opus` for reliability. You can downgrade to `sonnet` or `haiku` after copying the template.

---

## 设计理念 / Design Philosophy

**中文**：这个模板的出发点很简单——数仓 AI 开发的瓶颈不是 AI 不会写 SQL，而是语义理解和规范执行不稳定。所以核心思路是：**把人擅长的判断（语义、口径）写死到文件里，把 AI 擅长的执行（规范检查、重复劳动）交给代码强制执行。**

**English**: The core insight is simple — the bottleneck in DW AI development isn't SQL writing ability, but unstable semantic understanding and convention enforcement. So the approach is: **persist what humans are good at (semantics, field definitions) into files, and enforce what AI is good at (convention checks, repetitive work) with code.**

---

## 参考 / References

- [Claude Code Hooks](https://docs.anthropic.com/en/docs/claude-code/hooks)
- [Claude Code Skills](https://docs.anthropic.com/en/docs/claude-code/skills)
- [Claude Code Memory & Rules](https://docs.anthropic.com/en/docs/claude-code/memory)

---

## License

[MIT](LICENSE)

---

<div align="center">

**如果这个项目对你有帮助，给个 ⭐ 吧！**

**If this project helps you, a ⭐ would be appreciated!**

</div>
