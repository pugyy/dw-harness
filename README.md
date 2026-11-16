# dw-harness

[中文](README.md) | [English](README.en.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-green.svg)
[![Tests](https://github.com/pugyy/dw-harness/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/pugyy/dw-harness/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/pugyy/dw-harness)](https://github.com/pugyy/dw-harness/releases)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-blueviolet)](https://github.com/pugyy/dw-harness#install)

**数仓 AI 编程：装得上、管得住、说得清、跑得回。**

## 简介

dw-harness 是面向数仓团队的 Claude Code 插件与 CLI。它把表契约、SQL 规范、危险操作守卫、键级对账和四态验收报告做成可安装、可配置、可验证的工程层，主线是 MaxCompute → StarRocks，流程沿用 OneData 八步。

适合使用 Claude Code 的数仓/数据平台团队，尤其是已经在 MaxCompute、StarRocks、Hive 或 Spark 上做 ETL，并希望把 AI 产出纳入 review 和 CI 的团队。它不替代调度系统、元数据平台或 BI 工具，也不是一个只做 SQL 格式化的插件。

## 目录

- [版本历史](#版本历史)
- [让 AI Agent 帮你部署](#让-ai-agent-帮你部署)
- [为什么是 dw-harness](#为什么是-dw-harness)
- [功能](#功能)
- [30 秒演示](#30-秒演示)
- [安装](#安装)
- [架构](#架构)
- [六层防线](#六层防线)
- [CLI](#cli)
- [支持矩阵](#支持矩阵)
- [文档](#文档)
- [关键词](#关键词)
- [参与贡献](#参与贡献)
- [License](#license)

## 版本历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0.0 | 2026-05-23 | 初始版本：复制模板、五层防线、3 个 Hook、8 个 Skill、4 个 Subagent |
| v2.0.0 | 2026-11-16 | Evidence Gate：插件 + CLI、表契约、四态验收、键级对账、证据链 |

### v1.0.0 — 2026-05-23 — 初始版本

首个公开版本，以复制 `.claude` 模板的方式提供一套数仓 AI 开发规范：

- 五层防线：`CLAUDE.md`、Auto Memory、Hooks、Subagents、Skills
- 3 个 Hook：`validate_sql.py`（写后 SQL 规范检查）、`block_dangerous_ddl.py`（Bash 危险 DDL 拦截）、`inject_context.py`（compact 后重注入规范）
- 8 个 Skill：需求分析、技术设计、ETL 开发、自测、数据比对、SR 导入、性能优化、DQC
- 4 个 Subagent：`dw-explorer`、`sql-validator`、`data-quality-checker`、`data-comparator`
- 支持 ODPS/MaxCompute、Hive、Spark；内置 23 项自测和 9 类 DQC 模板
- Python 3.9+；用冒烟测试验证 Hook

### v2.0.0 — 2026-11-16 — Evidence Gate

**交付形态**

- 从复制模板升级为 Claude Code 插件 + Marketplace + `dw` CLI，保留复制模板作为离线/内网路径
- `src/` 单一源码，`plugins/`、`template/`、`.claude-plugin/marketplace.json` 由 `build.py` 生成，CI 用 `build --check` 阻止漂移
- 15 个 Skill、4 个平铺 Subagent、7 个 Hook 适配器；新增 bootstrap、contract、check、next、review、backfill 和按需加载的 SQL 参考

**新增能力**

- 表契约：`dw contract validate/compile/diff`，记录粒度、业务键、分区、列类型、币种/单位、质量阈值和 SLA；破坏性变更必须记录迁移决定
- 验收门禁：`dw check` 输出 PASS/FAIL/UNVERIFIED/N/A 四态，退出码 0/1/2；证据绑定 SQL、DDL、契约、基线和分区
- 键级对账：`dw reconcile` 支持文件、MaxCompute、StarRocks，使用 Decimal、单位换算、绝对/相对容差、零基线和 NULL 语义
- 计划与生成：`dw plan ddl/backfill`、`dw dqc gen/check`、`dw impact`
- 工程化守卫：`dw lint`、`Bash|PowerShell` 危险命令拦截、`-f`/`--file=` 检查、PII 扫描、带有效期的策略例外
- 会话体验：SessionStart 状态卡、PostCompact 本地落盘、statusLine、SessionEnd handoff、默认关闭的本地 stdio MCP
- 三平台 CI：ubuntu-24.04 / Windows / macOS × Python 3.9 / 3.13，包含干净 wheel 安装步骤

**变更**

- 插件模式命令带 `dw-harness:` 前缀；模板模式保留原名
- `init` 改为合并式迁移：备份、`managed.json`、冲突报告，不再 `rm -rf .claude`
- Hook 重命名：`validate_sql.py` → `validate_post.py`，`block_dangerous_ddl.py` → `guard_shell.py`，`inject_context.py` → `session_context.py` + `post_compact.py`
- Subagent 目录拍平；不再依赖插件环境会忽略的 `permissionMode`
- 移除无效的 `FileChanged` 接线，旁路修改改用 `dw lint --changed` / `dw check --changed`
- strict 证据需要 `DW_HARNESS_EVIDENCE_KEY`；不配 key 时用 `--mode local`
- 插件 Hook 使用 PATH 上的 `python`；只有 `python3` 的环境需要解释器别名或模板安装

**保留**

- OneData 八步流程、23 项自测、9 类 DQC
- MaxCompute → StarRocks 主线
- 四个 Subagent 的职责划分
- 路径级规则、SQL 规范、金额 `DECIMAL(20,4)`、`partition_dt` 约定
- 自定义 Skill、规则、权限和状态栏：迁移只合并，不主动删除

## 让 AI Agent 帮你部署

把下面这段直接发给有终端权限的 AI Agent（Claude Code、Codex、Cursor 或其他编码 Agent）。它覆盖环境检查、备份、插件/模板选择、项目文件生成和验收。Agent 遇到冲突时应停下，而不是自行删除你的配置。

```text
你是一名资深数据平台工程师。请在我的数据仓库项目中安装并验收 dw-harness v2.0.0：
https://github.com/pugyy/dw-harness

执行顺序：
1. 检查环境并记录：操作系统、shell、git、python --version（>=3.9）、claude --version（>=2.1.295，如果有 Claude Code）。
2. 备份：cp -r .claude .claude.v1.bak（PowerShell 用 Copy-Item -Recurse .claude .claude.v1.bak）；确认 git status。
3. 选择安装路径：
   A. 有 Claude Code：依次执行 /plugin marketplace add pugyy/dw-harness、/plugin install dw-harness@dw-harness、/dw-harness:dw-bootstrap。
   B. 没有 Claude Code 或需要离线：pip install "dw-harness[yaml,deep]"；先 dw init --target . --python python --dry-run，确认输出后再 dw init --target . --python python。
4. 不要覆盖已有的 settings.json、skills、rules、agents、statusLine。遇到冲突先停下，列出文件、冲突原因和建议，不要自行删除。
5. 检查生成结果：AGENTS.md、根 CLAUDE.md、.claude/rules/、.claude/dw/harness.json、contracts/contract.example.json。把 dialect 设为 odps 或 starrocks，把已上线只读表填进 protected_objects。
6. 验收并记录退出码：
   - dw doctor --mode plugin 或 --mode template
   - dw lint 一个包含 SELECT t.* 的样例（必须失败）
   - dw lint 一个包含 COUNT(*) 的样例（必须通过）
   - dw check --table <表> --env dev --partition <yyyyMMdd>
7. 输出报告：改动文件、执行过的命令、验收结果、未验证项、回滚命令。

约束：
- 不要执行 DROP/TRUNCATE/ALTER TABLE ... DROP/INSERT OVERWRITE。
- 不要提交或推送 git。
- 不要修改我没有明确同意的生产配置。
- 无法验证的项（真实 MaxCompute/StarRocks、Claude Code 真机加载）写入“未验证”，不要标成通过。
```

English version of the same prompt is in [README.en.md](README.en.md#let-an-ai-agent-install-it).

## 为什么是 dw-harness

| 常见问题 | dw-harness 的做法 |
|---|---|
| 字段口径散落在文档、聊天和人的记忆里 | 表契约记录粒度、业务键、分区、类型、币种/单位和阈值；`dw check` 按契约验收 |
| SQL 规范靠 review 提醒，执行不稳定 | PreToolUse/PostToolUse Hook + `dw lint` 使用同一套规则；错误退出码可直接接 CI |
| 改完 SQL 说不清有没有验证过 | 证据绑定 SQL、DDL、契约、基线和分区；输入变化自动变 UNVERIFIED |
| 对账只看总行数、总金额，金额对调查不出来 | 键级对账逐键比较，支持单位换算、容差、零基线和 NULL 语义 |
| 升级模板会覆盖团队自定义内容 | `init` 合并式迁移：备份、`managed.json`、冲突报告，不删除用户配置 |
| 血缘、自测、比对结果撑爆主对话 | 4 个 Subagent + `context: fork`；主对话只收摘要 |

## 功能

| 能力 | 入口 | 说明 |
|---|---|---|
| 表契约 | `dw contract validate/compile/diff` | 记录表标识、粒度、业务键、分区、列类型、币种/单位、质量阈值、SLA |
| SQL 校验 | `dw lint`、PostToolUse | 覆盖 ODPS/Hive/Spark/StarRocks；区分引擎语法与团队政策；`t.*`、字符串伪关键字、子查询都处理 |
| 执行前守卫 | PreToolUse、`guard_shell.py` | Bash/PowerShell 危险 DDL、无 WHERE DML、`-f`/`--file=`、分区安全阀、PII、带期限的例外 |
| 键级对账 | `dw reconcile` | 文件、MaxCompute、StarRocks；预检分区/空键/重复键/缺失键，再做总量和逐键比较 |
| 验收与证据 | `dw check` | 四态报告、0/1/2 退出码、JSON + PR Markdown、输入绑定的 evidence |
| 计划与生成 | `dw plan`、`dw dqc`、`dw impact` | DDL 迁移/回填预演、DQC 稳定 ID、仓库 SQL 血缘 |
| 会话与协作 | Hooks、Skills、Agents、MCP | 状态卡、handoff、statusLine、15 个 Skill、4 个 Subagent、可选本地 MCP |
| 分发与 CI | 插件、CLI、模板 | Marketplace 安装、`pip install`、`build --check`、三平台矩阵 + wheel 安装 |

## 30 秒演示（订单表演示，离线可复现）

```bash
git clone https://github.com/pugyy/dw-harness.git && cd dw-harness
python scripts/run_demo.py        # 无凭据、无数据库、无 Claude Code 依赖
```

输出 20 个验收用例，包括反例：

- `SELECT t.*` 在 hook 和 CLI 命中同一规则；`COUNT(*)`、字符串里的 `'drop table'` 不误报
- `net_amount` 从「分」改「元」：SQL 全绿，**契约验收 FAIL 并指出缺少迁移决定**
- 两笔订单金额对调：总行数总金额都不变，**键级对账照样 FAIL**
- SQL/契约一变，旧证据自动变 UNVERIFIED，严格 CI 拒绝放行
- 生产覆盖、无 WHERE 删除、`-f` 间接 DROP、过期例外、普通命令，策略各得其所
- v1 项目重复迁移：自定义 skills/rules/状态栏原样保留，hook 不重复追加

## 安装（三条可复现路径）

### 1. Claude Code 插件（主路径，命令带 `dw-harness:` 前缀）

```text
/plugin marketplace add pugyy/dw-harness
/plugin install dw-harness@dw-harness
```

装完在项目里跑 `/dw-harness:dw-bootstrap` 生成项目侧文件（AGENTS.md / rules / harness.json / contracts）。需要 Claude Code ≥ 2.1.295（Hook 启动失败时可阻断）。插件使用 PATH 上的 Python 3.9+ `python`；复制模板可用 `dw init --python` 指定解释器。

### 2. 本地加载插件（开发/试用）

```bash
git clone https://github.com/pugyy/dw-harness.git
claude --plugin-dir ./dw-harness/plugins/dw-harness
```

`plugin-validate` workflow 需要 `CLAUDE_CODE_OAUTH_TOKEN` secret（缺了会红，不再静默跳过）；或改用预装 claude 的 self-hosted runner。

### 3. CI 里单独安装 CLI（无需 Claude Code）

```bash
pip install -e ".[test]"          # 或 pip install dw-harness
python -m unittest discover -s tests -t .
python scripts/build.py --check   # 生成物漂移门禁
python scripts/run_demo.py        # 离线端到端验收
```

复制模板模式（v1 风格，命令保留原名）仍然支持：`bash init.sh /your/project`（合并式，不再 rm -rf）。v1 升级详见 [中文](docs/upgrade-from-v1.md) / [English](docs/upgrade-from-v1.en.md)。

## 架构

```text
src/                          # 唯一真源（手写只动这里）
├── dw_core/                  # 核心包：CLI / hooks / CI / MCP 共用，纯标准库
├── hooks/                    # 7 个 Claude Code hook 适配器（薄壳，fail-closed）
├── skills/                   # 15 个 skill（八步 + bootstrap/contract/check/next/review/backfill/sql-reference）
├── agents/                   # 4 个 subagent（平铺，model: inherit，无 permissionMode 依赖）
├── dialects/                 # odps / hive / spark / starrocks 方言包
└── scaffold/                 # dw init 写入项目的模板（AGENTS.md/rules/harness.json）
scripts/build.py              # 确定性构建 → plugins/dw-harness + template/ + marketplace.json
mcp/server.py                 # 本地 stdio MCP（默认关闭，dw init --mcp 显式开启）
plugins/dw-harness/           # 生成物：插件安装单元
template/                     # 生成物：复制式安装
contracts/schema/             # 表契约 JSON Schema（ODCS 精简）
examples/demo/                # 订单表端到端 fixtures + 反例 a-f
tests/                        # 123 个测试：规则/守卫/契约/对账/证据/接线/迁移/manifest/CLI 端到端
```

## 六层防线（v1 五层升级）

| 层 | 机制 | 失败行为 |
|---|---|---|
| 1 AGENTS.md + rules/ | 跨工具共享规范，路径级按需加载 | — |
| 2 表契约 contract | 口径/币种/单位/阈值唯一真源 | 破坏性变更无迁移决定 → 验收 FAIL |
| 3 PreToolUse 守卫 | Bash+PowerShell 危险 DDL / 分区安全阀 / PII | fail-closed（`onFailure: block` + 脚本内兜底 deny） |
| 4 PostToolUse 反馈 | SQL 写后检查（ERROR exit 2 回喂修正） | 非阻塞 + doctor 报警 |
| 5 确定性命令 | dw lint / reconcile / check（模型只解释不放行） | 退出码 0/1/2 |
| 6 证据链 | 输入摘要绑定 + producer/HMAC 信任边界，变化即 UNVERIFIED | 严格 CI 退出码 2 |

> strict 模式的证据门禁需要 `DW_HARNESS_EVIDENCE_KEY`（`dw evidence keygen` 生成，
> 生产与校验同 key；不配 key 时 strict 会把证据判 untrusted，临时用 `--mode local`）。

## CLI

```bash
dw init --target . --python python [--mode plugin] [--dialect odps] [--dry-run] [--mcp]
dw doctor [--json]                                  # 配置存在/脚本可跑/真机接线 三级自检
dw lint <files> [--dialect X] [--json] [--strict]   # 规则：engine vs policy 分开标注
dw contract validate|compile|diff|decide ...        # 契约四件套（diff 需 --baseline）
dw plan ddl --from a.sql --to b.sql [--allow-narrowing]
dw plan backfill --table t --start 20260101 --end 20261115 [--env prod]
dw dqc gen --contract c.json | dw dqc check ...     # 稳定 ID 规则生成/防漂移
dw impact --table db.t [--dataworks]                # 仓库 SQL 血缘 + 可选 DataWorks
dw reconcile --spec spec.json [--save-evidence]     # 键级对账（文件/MaxCompute/StarRocks）
dw evidence keygen                                  # 生成 DW_HARNESS_EVIDENCE_KEY（strict 信任边界）
dw check --table t --env offline --partition 20261115
dw next                                             # 从交付物推断八步进度
dw lint --changed / dw check --changed              # git 变更集批量模式
dw demo                                             # 离线端到端验收
```

## 支持矩阵

详见 [docs/support-matrix.md](docs/support-matrix.md)。要点：SQL 校验 odps/hive/spark/starrocks（SR 的 INSERT 省分区是引擎合法，政策降级为 warn）；核心与 hooks 只用标准库（Python ≥3.9）；YAML 契约 / sqlglot 深检 / 数据库适配器为可选能力。

真实 MaxCompute / StarRocks / DataWorks 适配器尚未连生产实例；`plugin-validate` 需要 secret 手动触发。这两项在 [docs/e2e-demo.md](docs/e2e-demo.md) 有复现步骤，发布说明里也标为“未验证”。

## 文档

- [docs/configuration.md](docs/configuration.md) — harness.json / 契约 / 例外 / 证据配置
- [docs/upgrade-from-v1.md](docs/upgrade-from-v1.md) — v1 → v2 迁移指南（中文）
- [docs/upgrade-from-v1.en.md](docs/upgrade-from-v1.en.md) — v1 → v2 migration guide (English)
- [docs/e2e-demo.md](docs/e2e-demo.md) — 端到端验收与真实环境复现步骤
- [docs/mcp.md](docs/mcp.md) — 本地 MCP server 注册与工具清单
- [CHANGELOG.md](CHANGELOG.md) — v2.0.0 变更全录
- [docs/architecture.md](docs/architecture.md) / [five-layers-defense.md](docs/five-layers-defense.md) / [eight-steps-workflow.md](docs/eight-steps-workflow.md)

## 关键词

Claude Code 插件、Claude Code plugin、Claude Code skills、Claude Code hooks、data warehouse、数据仓库、MaxCompute、ODPS、StarRocks、Hive、Spark SQL、SQL lint、SQL 规范、table contract、数据契约、data quality、数据质量、key-level reconciliation、键级对账、ETL、OneData、数据开发、AI coding、AI Agent、MCP、Python。

## 参与贡献

- 代码改动：先读 [CONTRIBUTING.md](CONTRIBUTING.md)。`src/` 是唯一真源，生成物由 `build.py` 产出。
- 文档：`README.md` / `README.en.md`、`docs/upgrade-from-v1.md` / `.en.md` 必须同步修改。
- 安全问题：见 [SECURITY.md](SECURITY.md)。
- 问题与建议：开 GitHub Issue；真实环境验证结果也欢迎提交。

如果 dw-harness 对你的团队有用，欢迎点一个 Star，让更多数仓团队看到。

## License

MIT
