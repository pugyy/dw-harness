# dw-harness

[中文](#中文) | [English](#english)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-green.svg)
[![Tests](https://github.com/pugyy/dw-harness/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/pugyy/dw-harness/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/pugyy/dw-harness)](https://github.com/pugyy/dw-harness/releases)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-blueviolet)](https://github.com/pugyy/dw-harness#install)

<a id="中文"></a>

## 中文

**数仓 AI 编程：装得上、管得住、说得清、跑得回。**

**面向 MaxCompute / StarRocks 数仓的 Claude Code 插件 + CLI：SQL 校验、表契约、键级对账、验收证据。**

### 简介

dw-harness 是面向数仓团队的 Claude Code 插件与 CLI。它把表契约、SQL 规范、危险操作守卫、键级对账和四态验收报告做成可安装、可配置、可验证的工程层，主线是 MaxCompute → StarRocks，流程沿用 OneData 八步。

适合使用 Claude Code 的数仓/数据平台团队，尤其是已经在 MaxCompute、StarRocks、Hive 或 Spark 上做 ETL，并希望把 AI 产出纳入 review 和 CI 的团队。它不替代调度系统、元数据平台或 BI 工具，也不是一个只做 SQL 格式化的插件。

> **当前状态**：v2.0.0 已发布；123 个测试和 6/6 CI 矩阵通过；真实 MaxCompute/StarRocks/DataWorks 适配器未连生产实例，`plugin-validate` 需要 secret 手动触发。未验证项和复现步骤见 [docs/e2e-demo.md](docs/e2e-demo.md)。

### 目录

- [版本历史](#版本历史)
- [让 AI Agent 帮你部署](#让-ai-agent-帮你部署)
- [为什么是 dw-harness](#为什么是-dw-harness)
- [功能](#功能)
- [30 秒演示](#30-秒演示)
- [环境要求](#环境要求)
- [安装](#安装)
- [安全与数据边界](#安全与数据边界)
- [架构](#架构)
- [六层防线](#六层防线)
- [CLI](#cli)
- [支持矩阵](#支持矩阵)
- [FAQ](#faq)
- [文档](#文档)
- [参与贡献](#参与贡献)
- [License](#license)

### 版本历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0.0 | 2026-05-23 | 初始版本：复制模板、五层防线、3 个 Hook、8 个 Skill、4 个 Subagent |
| v2.0.0 | 2026-11-16 | Evidence Gate：插件 + CLI、表契约、四态验收、键级对账、证据链 |

#### v1.0.0 — 2026-05-23 — 初始版本

首个公开版本，以复制 `.claude` 模板的方式提供一套数仓 AI 开发规范：

- 概念上的五层：`CLAUDE.md`、Auto Memory（由 Claude Code 提供）、Hooks、Subagents、Skills
- 3 个 Hook：`validate_sql.py`（写后 SQL 规范检查）、`block_dangerous_ddl.py`（Bash 危险 DDL 拦截）、`inject_context.py`（设计为 compact 后重注入；v1 因事件名写错实际未生效，v2 修复）
- 8 个 Skill：需求分析、技术设计、ETL 开发、自测、数据比对、SR 导入、性能优化、DQC
- 4 个 Subagent：`dw-explorer`、`sql-validator`、`data-quality-checker`、`data-comparator`
- 支持 ODPS/MaxCompute、Hive、Spark；内置 23 项自测和 9 类 DQC 模板
- Python 3.9+；用冒烟测试验证 Hook

#### v2.0.0 — 2026-11-16 — Evidence Gate

**交付形态**

- 从复制模板升级为 Claude Code 插件 + Marketplace + `dw` CLI，保留复制模板作为离线/内网路径
- `src/` 单一源码，`plugins/`、`template/`、`.claude-plugin/marketplace.json` 由 `build.py` 生成，CI 用 `build --check` 阻止漂移
- 15 个 Skill、4 个平铺 Subagent、6 个 Hook 适配器 + statusLine；新增 bootstrap、contract、check、next、review、backfill 和按需加载的 SQL 参考

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

### 让 AI Agent 帮你部署

把下面这段直接发给有终端权限的 AI Agent（Claude Code、Codex、Cursor 或其他编码 Agent）。它覆盖环境检查、备份、插件/模板选择、项目文件生成和验收。Agent 遇到冲突时应停下，而不是自行删除你的配置。

```text
你是一名资深数据平台工程师。请在我的数据仓库项目中安装并验收 dw-harness v2.0.0：
https://github.com/pugyy/dw-harness

执行顺序：
1. 检查环境并记录：操作系统、shell、git、python --version（>=3.9）、claude --version（>=2.1.295，如果有 Claude Code）。
2. 备份：cp -r .claude .claude.v1.bak（PowerShell 用 Copy-Item -Recurse .claude .claude.v1.bak）；确认 git status。
3. 选择安装路径：
   A. 有 Claude Code：依次执行 /plugin marketplace add pugyy/dw-harness、/plugin install dw-harness@dw-harness、/dw-harness:dw-bootstrap。
   B. 没有 Claude Code 或需要离线：
      python -m pip install "dw-harness[yaml,deep] @ git+https://github.com/pugyy/dw-harness.git"
      （离线：git clone https://github.com/pugyy/dw-harness.git /tmp/dw-harness && (cd /tmp/dw-harness && python -m pip install -e ".[yaml,deep]")）
      然后先 dw init --target . --python python --dry-run，确认输出后再 dw init --target . --python python。
4. 不要覆盖已有的 settings.json、skills、rules、agents、statusLine。遇到冲突先停下，列出文件、冲突原因和建议，不要自行删除。
5. 检查生成结果：AGENTS.md、根 CLAUDE.md、.claude/rules/、.claude/dw/harness.json、contracts/contract.example.json。把 dialect 设为 odps/hive/spark/starrocks，把已上线只读表填进 protected_objects。
6. 验收并记录退出码：
   - dw doctor --mode plugin 或 --mode template
   - dw lint 一个包含 SELECT t.* 的样例（必须失败）
   - dw lint 一个包含 COUNT(*) 的样例（必须通过）
   - dw check --table <表> --env dev --partition <yyyyMMdd> \
       --contract contracts/<表>.json --sql insert_<表>.sql \
       --ddl ddl_<表>.sql --reconcile-spec reconcile_<表>.json
     strict 模式需要 DW_HARNESS_EVIDENCE_KEY；没有 key 时加 --mode local。
7. 输出报告：改动文件、执行过的命令、验收结果、未验证项、回滚命令。

约束：
- 不要执行 DROP/TRUNCATE/ALTER TABLE ... DROP/INSERT OVERWRITE。
- 不要提交或推送 git。
- 不要修改我没有明确同意的生产配置。
- 无法验证的项（真实 MaxCompute/StarRocks、Claude Code 真机加载）写入“未验证”，不要标成通过。
```

English version of the same prompt is in [English section](#english).

### 为什么是 dw-harness

| 常见问题 | dw-harness 的做法 |
|---|---|
| 字段口径散落在文档、聊天和人的记忆里 | 表契约记录粒度、业务键、分区、类型、币种/单位和阈值；`dw check` 按契约验收 |
| SQL 规范靠 review 提醒，执行不稳定 | PreToolUse/PostToolUse Hook + `dw lint` 使用同一套规则；错误退出码可直接接 CI |
| 改完 SQL 说不清有没有验证过 | 证据绑定 SQL、DDL、契约、基线和分区；输入变化自动变 UNVERIFIED |
| 对账只看总行数、总金额，金额对调查不出来 | 键级对账逐键比较，支持单位换算、容差、零基线和 NULL 语义 |
| 升级模板会覆盖团队自定义内容 | `init` 合并式迁移：备份、`managed.json`、冲突报告，不删除用户配置 |
| 血缘、自测、比对结果撑爆主对话 | 4 个 Subagent + `context: fork`；主对话只收摘要 |

**与现有工具的关系**：dw-harness 不替代 dbt tests、Great Expectations 或 sqlfluff。它把这些检查接到 Claude Code 的 hooks、表契约和验收报告里；调度、元数据、BI 仍由现有平台负责。

### 功能

| 能力 | 入口 | 说明 |
|---|---|---|
| 表契约 | `dw contract validate/compile/diff` | 记录表标识、粒度、业务键、分区、列类型、币种/单位、质量阈值、SLA |
| SQL 校验 | `dw lint`、PostToolUse | 覆盖 ODPS/Hive/Spark/StarRocks；区分引擎语法与团队政策；`t.*`、字符串伪关键字、子查询都处理 |
| 执行前守卫 | PreToolUse、`guard_shell.py` | Bash/PowerShell 危险 DDL、无 WHERE DML、`-f`/`--file=`、分区安全阀、PII、带期限的例外 |
| 键级对账 | `dw reconcile` | 文件、MaxCompute、StarRocks；预检分区/空键/重复键/缺失键，再做总量和逐键比较 |
| 验收与证据 | `dw check` | 四态报告、0/1/2 退出码、JSON + PR Markdown、输入绑定的 evidence |
| 计划与生成 | `dw plan`、`dw dqc`、`dw impact` | DDL 迁移/回填预演、DQC 稳定 ID、仓库 SQL 血缘 |
| 会话与协作 | Hooks、Skills、Agents、MCP | 状态卡、handoff、statusLine、15 个 Skill、4 个 Subagent、可选本地 MCP |
| 分发与 CI | 插件、CLI、模板 | Marketplace 安装、源码安装、`build --check`、三平台矩阵 + wheel 安装 |

### 30 秒演示（订单表演示，离线可复现）

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

### 环境要求

| 项 | 要求 |
|---|---|
| Python | 3.9–3.13（CI 覆盖 3.9 与 3.13） |
| Claude Code | ≥ 2.1.295（插件模式；CLI 模式不需要） |
| 操作系统 | macOS / Linux / Windows（PowerShell 已覆盖） |
| Git | 克隆、迁移、`--changed`、Git 基线需要 |
| 数据库客户端 | 可选：odpscmd、beeline/hive、spark-sql、mysql/StarRocks；也可用文件适配器 |
| 可选依赖 | `yaml`、`deep`、`odps`、`sr`（按需安装） |

### 安装

PyPI 尚未发布；CLI 从源码安装。

#### 1. Claude Code 插件（主路径，命令带 `dw-harness:` 前缀）

```text
/plugin marketplace add pugyy/dw-harness
/plugin install dw-harness@dw-harness
```

装完在项目里跑 `/dw-harness:dw-bootstrap` 生成项目侧文件（AGENTS.md / rules / harness.json / contracts）。需要 Claude Code ≥ 2.1.295（Hook 启动失败时可阻断）。插件使用 PATH 上的 Python 3.9+ `python`；只有 `python3` 时先建别名，或改用模板模式。

#### 2. 本地加载插件（开发/试用）

```bash
git clone https://github.com/pugyy/dw-harness.git
claude --plugin-dir ./dw-harness/plugins/dw-harness
```

`plugin-validate` workflow 需要 `CLAUDE_CODE_OAUTH_TOKEN` secret（缺了会红，不再静默跳过）；或改用预装 claude 的 self-hosted runner。

#### 3. CLI（CI 或无 Claude Code）

```bash
# 直接从 Git 安装（PyPI 尚未发布）
pip install "dw-harness[test] @ git+https://github.com/pugyy/dw-harness.git"

# 或使用 v2.0.0 Release 中的 wheel
pip install https://github.com/pugyy/dw-harness/releases/download/v2.0.0/dw_harness-2.0.0-py3-none-any.whl

# 或 clone 后 editable 安装
git clone https://github.com/pugyy/dw-harness.git
cd dw-harness
pip install -e ".[test]"

# 验证
python -m unittest discover -s tests -t .
python scripts/build.py --check
python scripts/run_demo.py
```

复制模板模式（v1 风格，命令保留原名）仍然支持：`bash init.sh /your/project`（合并式，不再 rm -rf）。Windows 也可用 `.\init.ps1`。v1 升级详见 [中文](docs/upgrade-from-v1.md) / [English](docs/upgrade-from-v1.en.md)。

### 安全与数据边界

- Hook 以当前用户权限执行本地 Python 脚本；安装前应审阅 `.claude/hooks/` 或插件 `hooks/`。
- 数据库适配器使用 `DW_HARNESS_*` 环境变量配置的只读身份；不执行写入；查询有超时和行数上限。
- `dw reconcile` 读取 CSV 或数据库结果；evidence 只保存摘要、路径和结果状态，不保存数据行。
- `DW_HARNESS_EVIDENCE_KEY` 只放环境变量或 CI secret，不写进仓库。
- 本地 stdio MCP 默认关闭，需要 `dw init --mcp` 显式注册。
- `dw init` 不会删除 `.claude`；迁移会生成 `.bak-<时间戳>` 和 `managed.json`。

### 架构

```text
src/                          # 唯一真源（手写只动这里）
├── dw_core/                  # 核心包：CLI / hooks / CI / MCP 共用，纯标准库
│   └── data/dialects/        # odps / hive / spark / starrocks 方言包（随包分发）
├── hooks/                    # 6 个 Claude Code hook 适配器 + statusline.py（薄壳，fail-closed）
├── skills/                   # 15 个 skill（八步 + bootstrap/contract/check/next/review/backfill/sql-reference）
├── agents/                   # 4 个 subagent（平铺，model: inherit，无 permissionMode 依赖）
└── scaffold/                 # dw init 写入项目的模板（AGENTS.md/rules/harness.json）
scripts/build.py              # 确定性构建 → plugins/dw-harness + template/ + marketplace.json
mcp/server.py                 # 本地 stdio MCP（默认关闭，dw init --mcp 显式开启）
plugins/dw-harness/           # 生成物：插件安装单元
template/                     # 生成物：复制式安装
contracts/schema/             # 表契约 JSON Schema（ODCS 精简）
examples/demo/                # 订单表端到端 fixtures + 反例 a-f
tests/                        # 123 个测试：规则/守卫/契约/对账/证据/接线/迁移/manifest/CLI 端到端
```

### 六层防线（v1 五层升级）

| 层 | 机制 | 失败行为 |
|---|---|---|
| 1 AGENTS.md + rules/ | 跨工具共享规范，路径级按需加载 | — |
| 2 表契约 contract | 口径/币种/单位/阈值唯一真源 | 破坏性变更无迁移决定 → 验收 FAIL |
| 3 PreToolUse 守卫 | Bash+PowerShell 危险 DDL / 分区安全阀 / PII | fail-closed（`onFailure: block` + 脚本内兜底 deny） |
| 4 PostToolUse 反馈 | SQL 写后检查（ERROR exit 2 回喂修正） | 非阻塞；`doctor` 检查脚本可运行 |
| 5 确定性命令 | dw lint / reconcile / check（模型只解释不放行） | 退出码 0/1/2 |
| 6 证据链 | 输入摘要绑定 + producer/HMAC 信任边界，变化即 UNVERIFIED | 严格 CI 退出码 2 |

> strict 模式的证据门禁需要 `DW_HARNESS_EVIDENCE_KEY`（`dw evidence keygen` 生成，
> 生产与校验同 key；不配 key 时 strict 会把证据判 untrusted，临时用 `--mode local`）。

### CLI

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

### 支持矩阵

详见 [docs/support-matrix.md](docs/support-matrix.md)。要点：SQL 校验 odps/hive/spark/starrocks（SR 的 INSERT 省分区是引擎合法，政策降级为 warn）；核心与 hooks 只用标准库（Python ≥3.9）；YAML 契约 / sqlglot 深检 / 数据库适配器为可选能力。

真实 MaxCompute / StarRocks / DataWorks 适配器尚未连生产实例；`plugin-validate` 需要 secret 手动触发。这两项在 [docs/e2e-demo.md](docs/e2e-demo.md) 有复现步骤，发布说明里也标为“未验证”。

### FAQ

**只有 `python3`，没有 `python`？**
插件 Hook 使用 PATH 上的 `python`；建一个别名（例如 `ln -s $(which python3) ~/.local/bin/python`），或改用模板模式 `dw init --python python3`。在 macOS 上不要依赖系统自带的 `python`。

**插件模式和模板模式怎么选？**
想自动更新、少维护项目内副本，用插件；内网、离线、需要把 Hook 写进项目 `settings.json`，用模板。两者不要同时安装：Hook 路径不同，去重逻辑不会合并两套接线。

**没有 Claude Code 能用吗？**
可以。`dw` CLI、`dw lint`、`dw contract`、`dw reconcile`、`dw check` 都不依赖 Claude Code；`dw demo` 也不需要数据库。

**`dw check` 一直是 UNVERIFIED？**
先看 `reconcile` 项：strict 模式需要 `DW_HARNESS_EVIDENCE_KEY`，没有 key 用 `--mode local`；再确认传了 `--contract`、`--sql`、`--ddl`、`--reconcile-spec`。如果分区或文件变化，旧证据会失效，需要重新 `dw reconcile --save-evidence`。

**怎么生成 evidence key？**
```bash
dw evidence keygen
```
生产与校验两端 export 同一个 `DW_HARNESS_EVIDENCE_KEY`；CI 用 secret，不要提交到仓库。

**怎么回滚？**
迁移会保留 `.claude`，`settings.json` 和 `CLAUDE.md` 有 `.bak-<时间戳>`。先 `git checkout -- .claude CLAUDE.md`，再用 `git clean -nd .claude AGENTS.md` 预览未跟踪文件，确认后再清理。卸载插件用 `/plugin uninstall dw-harness@dw-harness`。详见 [升级指南](docs/upgrade-from-v1.md)。

### 文档

- [docs/configuration.md](docs/configuration.md) — harness.json / 契约 / 例外 / 证据配置
- [docs/upgrade-from-v1.md](docs/upgrade-from-v1.md) — v1 → v2 迁移指南（中文）
- [docs/upgrade-from-v1.en.md](docs/upgrade-from-v1.en.md) — v1 → v2 migration guide (English)
- [docs/e2e-demo.md](docs/e2e-demo.md) — 端到端验收与真实环境复现步骤
- [docs/mcp.md](docs/mcp.md) — 本地 MCP server 注册与工具清单
- [docs/publishing.md](docs/publishing.md) — PyPI Trusted Publishing 与发布流程
- [CHANGELOG.md](CHANGELOG.md) — v2.0.0 变更全录
- [docs/architecture.md](docs/architecture.md) / [five-layers-defense.md](docs/five-layers-defense.md) / [eight-steps-workflow.md](docs/eight-steps-workflow.md)

### 参与贡献

- 代码改动：先读 [CONTRIBUTING.md](CONTRIBUTING.md)。`src/` 是唯一真源，生成物由 `build.py` 产出。
- 文档：`README.md` 的中文 / English 两段、`docs/upgrade-from-v1.md` / `.en.md` 必须同步修改。
- 安全问题：见 [SECURITY.md](SECURITY.md)。
- 问题与建议：开 GitHub Issue；真实环境验证结果也欢迎提交。

如果 dw-harness 对你的团队有用，欢迎点一个 Star，让更多数仓团队看到。

### License

MIT
---

<a id="english"></a>

## English

**Data warehouse AI development that installs, enforces checks, and leaves evidence.**

**A Claude Code plugin + CLI for MaxCompute / StarRocks warehouses: SQL lint, table contracts, key-level reconciliation and acceptance evidence.**

### What it is

dw-harness is a Claude Code plugin and CLI for data warehouse teams. It packages table contracts, SQL conventions, dangerous-operation guards, key-level reconciliation and a four-state acceptance report into an installable, configurable and verifiable engineering layer. The mainline is MaxCompute → StarRocks; the workflow follows the OneData eight steps.

It is built for warehouse and data-platform teams already using Claude Code, especially those running ETL on MaxCompute, StarRocks, Hive or Spark and wanting AI output to pass review and CI. It does not replace a scheduler, metadata platform or BI tool, and it is not a SQL formatter.

> **Status**: v2.0.0 is released; 123 tests and the 6/6 CI matrix pass. The live MaxCompute/StarRocks/DataWorks adapters have not been tested against production, and `plugin-validate` needs a secret and a manual dispatch. Unverified items and reproduction steps are in [docs/e2e-demo.md](docs/e2e-demo.md).

### Contents

- [Release history](#release-history)
- [Let an AI agent install it](#let-an-ai-agent-install-it)
- [Why dw-harness](#why-dw-harness)
- [Features](#features)
- [30-second demo](#30-second-demo)
- [Requirements](#requirements)
- [Install](#install)
- [Security and data boundaries](#security-and-data-boundaries)
- [Architecture](#architecture)
- [Six layers](#six-layers)
- [CLI](#cli)
- [Support](#support)
- [FAQ](#faq)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

### Release history

| Version | Date | Summary |
|---|---|---|
| v1.0.0 | 2026-05-23 | Initial release: copy template, five layers, three hooks, eight skills, four subagents |
| v2.0.0 | 2026-11-16 | Evidence Gate: plugin + CLI, table contracts, four-state acceptance, key-level reconciliation, evidence chain |

#### v1.0.0 — 2026-05-23 — Initial release

The first public version, delivered as a copyable `.claude` template for data warehouse teams:

- Five layers in concept: `CLAUDE.md`, Auto Memory (provided by Claude Code), Hooks, Subagents, Skills
- Three hooks: `validate_sql.py` (post-write SQL checks), `block_dangerous_ddl.py` (Bash DDL guard), `inject_context.py` (intended to re-inject conventions after compaction; v1 used the wrong event name and did not take effect, fixed in v2)
- Eight skills: requirement analysis, technical design, ETL development, self-test, data comparison, SR import, performance tuning, DQC
- Four subagents: `dw-explorer`, `sql-validator`, `data-quality-checker`, `data-comparator`
- ODPS/MaxCompute, Hive and Spark support; 23 self-test items and nine DQC categories
- Python 3.9+; hooks verified by a smoke test

#### v2.0.0 — 2026-11-16 — Evidence Gate

**Delivery**

- From a copy template to a Claude Code plugin, Marketplace listing and `dw` CLI, with the copy template retained for offline or restricted networks
- `src/` is the single source; `plugins/`, `template/` and `.claude-plugin/marketplace.json` are generated by `build.py`, with `build --check` in CI
- 15 skills, four flat subagents, six hook adapters plus statusLine; new bootstrap, contract, check, next, review and backfill skills plus an on-demand SQL reference

**Added**

- Table contracts: `dw contract validate/compile/diff`, covering grain, business key, partition, column types, currency and unit, quality thresholds and SLA; breaking changes require a recorded migration decision
- Acceptance gate: `dw check` returns PASS/FAIL/UNVERIFIED/N-A with exit codes 0/1/2; evidence binds SQL, DDL, contract, baseline and partition
- Key-level reconciliation: `dw reconcile` supports files, MaxCompute and StarRocks, using Decimal, unit conversion, absolute/relative tolerances, zero-baseline and NULL semantics
- Planning and generation: `dw plan ddl/backfill`, `dw dqc gen/check`, `dw impact`
- Guardrails: `dw lint`, destructive command blocking on `Bash|PowerShell`, `-f`/`--file=` inspection, PII scanning and time-bounded policy exceptions
- Session features: SessionStart state card, local-only PostCompact record, statusLine, SessionEnd handoff and an opt-in local stdio MCP server
- Three-platform CI: ubuntu-24.04, Windows and macOS on Python 3.9 and 3.13, including a clean wheel install

**Changed**

- Plugin commands are namespaced with `dw-harness:`; template mode keeps the original names
- `init` is now a merge-style migration with backups, `managed.json` and conflict reporting; it no longer removes `.claude`
- Hooks were renamed: `validate_sql.py` → `validate_post.py`, `block_dangerous_ddl.py` → `guard_shell.py`, `inject_context.py` → `session_context.py` + `post_compact.py`
- Subagent files are flat; the harness no longer relies on `permissionMode`, which plugin environments ignore
- The ineffective `FileChanged` wiring was removed; out-of-band edits use `dw lint --changed` / `dw check --changed`
- Strict evidence requires `DW_HARNESS_EVIDENCE_KEY`; use `--mode local` when no key is configured
- Plugin hooks use `python` from PATH; environments with only `python3` need an alias or a template install

**Preserved**

- The OneData eight-step workflow, the 23 self-test items and the nine DQC categories
- The MaxCompute → StarRocks mainline
- The four subagent responsibilities
- Path-scoped rules, SQL conventions, `DECIMAL(20,4)` for money and the `partition_dt` convention
- Custom skills, rules, permissions and status line entries: migration merges them and does not remove them

### Let an AI agent install it

Paste the block below into an AI coding agent with terminal access (Claude Code, Codex, Cursor or similar). It covers environment checks, backup, plugin-or-template selection, project scaffolding and acceptance. The agent is told to stop on conflicts instead of deleting your configuration.

```text
You are a senior data platform engineer. Install and validate dw-harness v2.0.0 in my data warehouse project:
https://github.com/pugyy/dw-harness

Do this in order:
1. Check and record: OS, shell, git, python --version (>=3.9), claude --version (>=2.1.295, if Claude Code is installed).
2. Back up: cp -r .claude .claude.v1.bak (PowerShell: Copy-Item -Recurse .claude .claude.v1.bak). Confirm git status.
3. Choose an install path:
   A. Claude Code: run /plugin marketplace add pugyy/dw-harness, /plugin install dw-harness@dw-harness, then /dw-harness:dw-bootstrap.
   B. No Claude Code or offline:
      python -m pip install "dw-harness[yaml,deep] @ git+https://github.com/pugyy/dw-harness.git"
      (offline: git clone https://github.com/pugyy/dw-harness.git /tmp/dw-harness && (cd /tmp/dw-harness && python -m pip install -e ".[yaml,deep]"))
      Then run dw init --target . --python python --dry-run, review it, then run dw init --target . --python python.
4. Do not overwrite existing settings.json, skills, rules, agents or statusLine. On conflict, stop and list the files, the reason and a recommendation. Do not delete anything.
5. Inspect the result: AGENTS.md, root CLAUDE.md, .claude/rules/, .claude/dw/harness.json, contracts/contract.example.json. Set dialect to odps/hive/spark/starrocks. Put read-only production tables into protected_objects.
6. Validate and record exit codes:
   - dw doctor --mode plugin or --mode template
   - dw lint on a sample containing SELECT t.* (must fail)
   - dw lint on a sample containing COUNT(*) (must pass)
   - dw check --table <table> --env dev --partition <yyyyMMdd> \
       --contract contracts/<table>.json --sql insert_<table>.sql \
       --ddl ddl_<table>.sql --reconcile-spec reconcile_<table>.json
     Strict mode needs DW_HARNESS_EVIDENCE_KEY; add --mode local when no key is configured.
7. Report: changed files, commands run, validation results, unverified items and rollback commands.

Constraints:
- Do not run DROP/TRUNCATE/ALTER TABLE ... DROP/INSERT OVERWRITE.
- Do not commit or push to git.
- Do not change production settings I have not approved.
- Anything you cannot verify (live MaxCompute/StarRocks, real Claude Code plugin load) must be listed as "unverified", not "passed".
```

The Chinese version of the same prompt is in [中文](#中文).

### Why dw-harness

| Common problem | What dw-harness does |
|---|---|
| Field definitions live in docs, chat and people's memory | A table contract records grain, business key, partition, types, currency/unit and thresholds; `dw check` enforces it |
| SQL conventions depend on review reminders | PreToolUse/PostToolUse hooks and `dw lint` share one rule set; exit codes plug into CI |
| Nobody can prove a change was validated | Evidence binds SQL, DDL, contract, baseline and partition; any input change becomes UNVERIFIED |
| Reconciliation only compares totals, missing swapped amounts | Key-level comparison with unit conversion, tolerances, zero-baseline and NULL semantics |
| Upgrading the template overwrites team customisations | Merge-style `init`: backups, `managed.json`, conflict reports; user files are not deleted |
| Lineage, self-test and comparison output drown the main conversation | Four subagents plus `context: fork`; the main thread gets summaries |

**Relationship to existing tools**: dw-harness does not replace dbt tests, Great Expectations or sqlfluff. It connects those checks to Claude Code hooks, table contracts and an acceptance report; scheduling, metadata and BI stay with existing platforms.

### Features

| Capability | Entry point | Notes |
|---|---|---|
| Table contracts | `dw contract validate/compile/diff` | Table identity, grain, business key, partition, column types, currency/unit, thresholds, SLA |
| SQL lint | `dw lint`, PostToolUse | ODPS/Hive/Spark/StarRocks; engine vs policy rules; `t.*`, string literals, subqueries |
| Pre-execution guards | PreToolUse, `guard_shell.py` | Dangerous DDL on Bash/PowerShell, DML without WHERE, `-f`/`--file=`, partition safety, PII, time-bounded exceptions |
| Key-level reconciliation | `dw reconcile` | File, MaxCompute and StarRocks adapters; prechecks for partition/empty/duplicate/missing keys, then totals and per-key comparison |
| Acceptance and evidence | `dw check` | Four-state report, exit codes 0/1/2, JSON and PR Markdown, input-bound evidence |
| Planning and generation | `dw plan`, `dw dqc`, `dw impact` | DDL migration/backfill rehearsal, stable DQC IDs, repository SQL lineage |
| Session workflow | Hooks, skills, agents, MCP | State card, handoff, statusLine, 15 skills, four subagents, opt-in local MCP |
| Distribution and CI | Plugin, CLI, template | Marketplace install, source install, `build --check`, three-platform matrix with wheel install |

### 30-second demo (orders table, offline)

```bash
git clone https://github.com/pugyy/dw-harness.git && cd dw-harness
python scripts/run_demo.py        # no credentials, database or Claude Code required
```

The demo runs 20 acceptance cases, including counter-examples:

- `SELECT t.*` is caught by both the hook and the CLI; `COUNT(*)` and `'drop table'` inside a string literal are not
- Changing `net_amount` from fen to yuan leaves the SQL valid; contract acceptance fails and points to the missing migration decision
- Swapping two order amounts keeps totals unchanged; key-level reconciliation still fails
- Editing a bound SQL or contract file turns old evidence UNVERIFIED and blocks strict CI
- Production overwrite, DELETE without WHERE, an indirect DROP through `-f`, an expired exception and a benign command each get the intended policy decision
- Re-running migration on a v1 project keeps custom skills, rules and status line, without duplicating hooks

### Requirements

| Item | Requirement |
|---|---|
| Python | 3.9–3.13 (CI covers 3.9 and 3.13) |
| Claude Code | ≥ 2.1.295 for plugin mode; not required for CLI mode |
| OS | macOS / Linux / Windows (PowerShell covered) |
| Git | Needed for clone, migration, `--changed` and Git baselines |
| Database clients | Optional: odpscmd, beeline/hive, spark-sql, mysql/StarRocks; the file adapter works without one |
| Optional extras | `yaml`, `deep`, `odps`, `sr` |

### Install

The package is not on PyPI. Install the CLI from source.

#### 1. Claude Code plugin (recommended)

```text
/plugin marketplace add pugyy/dw-harness
/plugin install dw-harness@dw-harness
```

Then run `/dw-harness:dw-bootstrap` in the project to generate the project-side files (`AGENTS.md`, rules, `harness.json`, contracts). Requires Claude Code 2.1.295 or later: a hook that fails to start blocks the tool call. The plugin uses `python` 3.9+ from PATH; if the machine only has `python3`, create an alias or use template mode.

#### 2. Load the plugin locally

```bash
git clone https://github.com/pugyy/dw-harness.git
claude --plugin-dir ./dw-harness/plugins/dw-harness
```

The `plugin-validate` workflow needs a `CLAUDE_CODE_OAUTH_TOKEN` secret; without it the job fails instead of silently skipping. A self-hosted runner with the CLI already installed also works.

#### 3. CLI (CI or no Claude Code)

```bash
# Install directly from Git (PyPI is not published yet)
pip install "dw-harness[test] @ git+https://github.com/pugyy/dw-harness.git"

# Or use the wheel attached to the v2.0.0 release
pip install https://github.com/pugyy/dw-harness/releases/download/v2.0.0/dw_harness-2.0.0-py3-none-any.whl

# Or clone and install editable
git clone https://github.com/pugyy/dw-harness.git
cd dw-harness
pip install -e ".[test]"

# Verify
python -m unittest discover -s tests -t .
python scripts/build.py --check
python scripts/run_demo.py
```

The copy-template mode remains available: `bash init.sh /your/project` (merge-style, no longer deletes `.claude`). On Windows, `.\init.ps1` also works. See the [Chinese](docs/upgrade-from-v1.md) or [English](docs/upgrade-from-v1.en.md) migration guide.

### Security and data boundaries

- Hooks run local Python scripts with your user privileges; review `.claude/hooks/` or the plugin `hooks/` before installing.
- Database adapters use read-only credentials from `DW_HARNESS_*` environment variables; they do not write, and queries have timeouts and row limits.
- `dw reconcile` reads CSV files or database results; evidence stores digests, paths and result state, not data rows.
- `DW_HARNESS_EVIDENCE_KEY` belongs in environment variables or a CI secret, never in the repository.
- The local stdio MCP server is off by default and requires `dw init --mcp`.
- `dw init` does not delete `.claude`; it writes `.bak-<timestamp>` and `managed.json`.

### Architecture

```text
src/                          # single source (edit here)
├── dw_core/                  # core used by CLI, hooks, CI and MCP; standard library only
│   └── data/dialects/        # odps / hive / spark / starrocks packs (shipped with the package)
├── hooks/                    # 6 Claude Code hook adapters + statusline.py (thin, fail-closed)
├── skills/                   # 15 skills (eight steps + bootstrap/contract/check/next/review/backfill/sql-reference)
├── agents/                   # 4 subagents (flat, model: inherit, no permissionMode dependency)
└── scaffold/                 # files written by dw init (AGENTS.md/rules/harness.json)
scripts/build.py              # deterministic build -> plugins/dw-harness + template/ + marketplace.json
mcp/server.py                 # local stdio MCP (off by default; dw init --mcp)
plugins/dw-harness/           # generated plugin install unit
template/                     # generated copy-template
contracts/schema/             # table-contract JSON Schema (ODCS subset)
examples/demo/                # orders-table fixtures and counter-cases a-f
tests/                        # 123 tests: rules, guards, contracts, reconciliation, evidence, wiring, migration, manifests, CLI
```

### Six layers

| Layer | Mechanism | Failure behaviour |
|---|---|---|
| 1 AGENTS.md + rules/ | Shared conventions, path-scoped and loaded on demand | — |
| 2 Table contract | Single source for grain, currency, unit and thresholds | Breaking change without a migration decision → acceptance FAIL |
| 3 PreToolUse guard | Dangerous DDL, partition safety, PII, Bash and PowerShell | fail-closed (`onFailure: block` plus in-script deny) |
| 4 PostToolUse feedback | SQL checks after a write (ERROR exit 2 feeds the model) | non-blocking; `doctor` checks the script is runnable |
| 5 Deterministic commands | `dw lint` / `reconcile` / `check`; the model explains but does not approve | exit codes 0/1/2 |
| 6 Evidence | Input digests plus producer/HMAC trust boundary; any change → UNVERIFIED | strict CI exits 2 |

Strict evidence requires `DW_HARNESS_EVIDENCE_KEY` (`dw evidence keygen`). The producing and checking shells must use the same key; without one, strict mode marks evidence untrusted. Use `--mode local` for a temporary local run.

### CLI

```bash
dw init --target . --python python [--mode plugin] [--dialect odps] [--dry-run] [--mcp]
dw doctor [--json]                                  # config / runnable scripts / live wiring
dw lint <files> [--dialect X] [--json] [--strict]   # engine vs policy rules
dw contract validate|compile|diff|decide ...        # contract operations (diff needs --baseline)
dw plan ddl --from a.sql --to b.sql [--allow-narrowing]
dw plan backfill --table t --start 20260101 --end 20261115 [--env prod]
dw dqc gen --contract c.json | dw dqc check ...     # stable IDs, drift check
dw impact --table db.t [--dataworks]                # repo SQL lineage, optional DataWorks
dw reconcile --spec spec.json [--save-evidence]     # file / MaxCompute / StarRocks
dw evidence keygen                                  # generate DW_HARNESS_EVIDENCE_KEY
dw check --table t --env offline --partition 20261115
dw next                                             # infer the eight-step progress from deliverables
dw lint --changed / dw check --changed              # git changeset mode
dw demo                                             # offline end-to-end demo
```

### Support

See [docs/support-matrix.md](docs/support-matrix.md). SQL lint covers odps/hive/spark/starrocks; StarRocks `INSERT` without a partition is engine-legal and downgraded to a warning by policy. Core and hooks use only the standard library (Python 3.9+); YAML contracts, sqlglot deep parsing and database adapters are optional capabilities.

The live MaxCompute, StarRocks and DataWorks adapters have not been tested against production instances. `plugin-validate` needs a secret and a manual dispatch. Both are marked unverified in the release notes; reproduction steps are in [docs/e2e-demo.md](docs/e2e-demo.md).

### FAQ

**Only `python3`, no `python`?**
Plugin hooks use `python` from PATH. Create an alias (for example `ln -s $(which python3) ~/.local/bin/python`) or use template mode with `dw init --python python3`. Do not rely on the system `python` on macOS.

**Plugin mode or template mode?**
Use the plugin for automatic updates and less per-project maintenance; use the template for offline/restricted networks or when hooks must live in the project `settings.json`. Do not install both: their hook paths differ, and migration de-duplication will not merge the two wirings.

**Can I use it without Claude Code?**
Yes. `dw`, `dw lint`, `dw contract`, `dw reconcile` and `dw check` do not require Claude Code. `dw demo` does not require a database.

**Why is `dw check` always UNVERIFIED?**
Check the `reconcile` item first: strict mode needs `DW_HARNESS_EVIDENCE_KEY`; use `--mode local` without a key. Then confirm `--contract`, `--sql`, `--ddl` and `--reconcile-spec` are present. If a partition or file changed, the old evidence is stale; rerun `dw reconcile --save-evidence`.

**How do I generate an evidence key?**
```bash
dw evidence keygen
```
Export the same `DW_HARNESS_EVIDENCE_KEY` on the producing and checking sides; use a CI secret and never commit it.

**How do I roll back?**
Migration preserves `.claude`; `settings.json` and `CLAUDE.md` get `.bak-<timestamp>`. Run `git checkout -- .claude CLAUDE.md`, then preview untracked files with `git clean -nd .claude AGENTS.md` before cleaning. Uninstall the plugin with `/plugin uninstall dw-harness@dw-harness`. See the [migration guide](docs/upgrade-from-v1.en.md).

### Documentation

- [docs/configuration.md](docs/configuration.md) — harness.json, contracts, exceptions, evidence
- [docs/upgrade-from-v1.md](docs/upgrade-from-v1.md) — v1 → v2 migration guide (Chinese)
- [docs/upgrade-from-v1.en.md](docs/upgrade-from-v1.en.md) — v1 → v2 migration guide (English)
- [docs/e2e-demo.md](docs/e2e-demo.md) — end-to-end acceptance and live-environment steps
- [docs/mcp.md](docs/mcp.md) — local MCP registration and tool list
- [docs/publishing.md](docs/publishing.md) — PyPI Trusted Publishing and release process
- [CHANGELOG.md](CHANGELOG.md) — v2.0.0 changes
- [docs/architecture.md](docs/architecture.md) / [five-layers-defense.md](docs/five-layers-defense.md) / [eight-steps-workflow.md](docs/eight-steps-workflow.md)

### Contributing

- Code: read [CONTRIBUTING.md](CONTRIBUTING.md). `src/` is the only source; generated artifacts come from `build.py`.
- Docs: both language sections in `README.md`, and `docs/upgrade-from-v1.md` / `.en.md`, must stay in sync.
- Security: see [SECURITY.md](SECURITY.md).
- Questions and reports: open a GitHub issue. Live-environment validation results are welcome.

If dw-harness helps your team, a star makes it easier for other warehouse teams to find it.

### License

MIT