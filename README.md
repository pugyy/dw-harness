# dw-harness v2

__数仓 AI 编程：装得上（plugin）、管得住（fail-closed 守卫）、说得清（契约 + 验收报告）、跑得回（键级对账）__

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-green.svg)

> 用 AI 做数仓开发，痛点从来不是"不会写 SQL"，而是：字段口径靠记忆、规范执行靠自觉、
> 改没改对靠感觉。dw-harness v2 把这三件事全部交给确定性代码：**契约记录口径，
> hooks 强制规范，`dw check` 出四态验收报告，`dw reconcile` 做键级对账。**
> MaxCompute → StarRocks 主线 + OneData 八步工作流，v1 的所有能力全部保留并升级。

## 30 秒看懂（订单表演示，离线可复现）

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

```
/plugin marketplace add pugyy/dw-harness
/plugin install dw-harness@dw-harness
```

装完在项目里跑 `/dw-harness:dw-bootstrap` 生成项目侧文件（AGENTS.md / rules /
harness.json / contracts）。需要 Claude Code ≥ 2.1.295
（Hook 启动失败时可阻断）。插件使用 PATH 上的 Python 3.9+ `python`，复制模板可用 `dw init --python` 指定解释器。

### 2. 本地加载插件（开发/试用）

```bash
git clone https://github.com/pugyy/dw-harness.git
claude --plugin-dir ./dw-harness/plugins/dw-harness
```

> `plugin-validate` workflow 需要 `CLAUDE_CODE_OAUTH_TOKEN` secret（缺了会红，不再静默跳过）；
> 或改用预装 claude 的 self-hosted runner。

### 3. CI 里单独安装 CLI（无需 Claude Code）

```bash
pip install -e ".[test]"          # 或 pip install dw-harness
python -m unittest discover -s tests -t .
python scripts/build.py --check   # 生成物漂移门禁
python scripts/run_demo.py        # 离线端到端验收
```

复制模板模式（v1 风格，命令保留原名）仍然支持：`bash init.sh /your/project`
（合并式，不再 rm -rf）。v1 升级详见 [docs/upgrade-from-v1.md](docs/upgrade-from-v1.md)。

## 架构一览

```
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

## CLI 速查

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
dw evidence keygen                             # 生成 DW_HARNESS_EVIDENCE_KEY（strict 信任边界）
dw check --table t --env offline --partition 20261115 # 四态验收报告（JSON + PR Markdown）
dw next                                              # 从交付物推断八步进度
dw lint --changed / dw check --changed                # git 变更集批量模式
dw demo                                              # 离线端到端验收
```

## 支持矩阵

详见 [docs/support-matrix.md](docs/support-matrix.md)。要点：SQL 校验
odps/hive/spark/starrocks（SR 的 INSERT 省分区是引擎合法，政策降级为 warn）；
核心与 hooks 只用标准库（Python ≥3.9）；YAML 契约 / sqlglot 深检 / 数据库适配器为可选能力。

## 文档

- [docs/configuration.md](docs/configuration.md) — harness.json / 契约 / 例外 / 证据配置
- [docs/upgrade-from-v1.md](docs/upgrade-from-v1.md) — v1 → v2 逐项迁移指南 + 命令对照
- [docs/e2e-demo.md](docs/e2e-demo.md) — 端到端验收与真实环境复现步骤
- [docs/mcp.md](docs/mcp.md) — 本地 MCP server 注册与工具清单
- [CHANGELOG.md](CHANGELOG.md) — v2.0.0 变更全录
- [docs/architecture.md](docs/architecture.md) / [five-layers-defense.md](docs/five-layers-defense.md) / [eight-steps-workflow.md](docs/eight-steps-workflow.md)

## License

MIT
