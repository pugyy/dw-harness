# v1 → v2 迁移指南

## 一句话

```bash
git clone https://github.com/pugyy/dw-harness.git
bash dw-harness/init.sh /path/to/your-v1-project    # 或 pip install 后: dw init --target ...
```

合并式迁移：**不会** rm -rf、不会覆盖你改过的文件、重复执行不产生重复 hook。
推荐插件模式的，直接 `/plugin install`，然后跑 `/dw-harness:dw-bootstrap`。

## 命令对照（八步）

| v1 | v2 插件模式 | v2 模板模式 |
|---|---|---|
| `/dw-requirement-analysis` | `/dw-harness:dw-requirement-analysis` | 原名不变 |
| `/dw-technical-design` | `/dw-harness:dw-technical-design` | 原名不变 |
| `/dw-etl` | `/dw-harness:dw-etl` | 原名不变 |
| `/dw-self-test` | `/dw-harness:dw-self-test` | 原名不变 |
| `/dw-data-comparison` | `/dw-harness:dw-data-comparison` | 原名不变 |
| `/dw-sr` | `/dw-harness:dw-sr` | 原名不变 |
| `/dw-performance-optimization` | `/dw-harness:dw-performance-optimization` | 原名不变 |
| `/dw-dqc` | `/dw-harness:dw-dqc` | 原名不变 |

v2 新增：`dw-bootstrap`、`dw-contract`、`dw-check`、`dw-next`、`dw-review`、
`dw-backfill`、`dw-sql-reference`（自动加载，不手敲）。

## 迁移时具体发生了什么

| v1 项 | v2 处理 |
|---|---|
| `settings.json` 里三个 v1 hook 条目 | 自动移除（`python .claude/hooks/validate_sql.py` 等），换成 v2 接线；备份 `.bak-<ts>` |
| `statusLine` / `permissions` / 其他 hook | **原样保留** |
| `.claude/CLAUDE.md`（v1 模板） | 项目根 `CLAUDE.md` 追加 `@AGENTS.md` 引用，用户内容保留 |
| `.claude/rules/*.md` | 不动；新增 sql-style/etl/sr 三个规范文件（同名不覆盖） |
| 自定义 skills / agents | **绝不动**；与 v2 同名的 dw-* skill 按 v1 哈希识别后升级 |
| `.claude/context/` | 被 SessionStart 状态卡（读 state.json）替代；目录保留但不再被注入 |
| v1 hook 脚本（validate_sql.py 等） | 留在磁盘但不再接线（settings 已移除引用），可手动删 |

## 破坏性变更（心里有数）

1. 插件模式命令带 `dw-harness:` 前缀（模板模式无此问题）
2. subagent 不再声明 `permissionMode`（插件环境会忽略该字段），
   能力收窄改用 `tools` 白名单
3. `DW_HARNESS_DIALECT` 优先级降为第 3（显式参数 > 路径映射 > 环境变量 > 默认）
4. `init.sh/init.ps1` 不再提供 `rm -rf` 覆盖语义；强制刷新请手动清理

## 渐进纳管旧表

历史表没有契约时，`dw check` 对 `contract-validate` 给 UNVERIFIED（不是 FAIL）：
想要正式纳管，`cp contracts/contract.example.json contracts/<表>.json` 填好后
`dw contract validate` → `dw contract compile`，下次 `dw check` 即生效。

## 迁移后自检

```bash
dw doctor          # 期望: python-version/config/hook-scripts/settings-wiring 全 OK
                   # --statusline 可选开启 dw 状态栏（已有用户状态栏则不动）
                   # app-wiring-verified 显示未验证是正常的——首次真实 Claude Code
                   # 会话跑过之后，按 docs/e2e-demo.md 写入 wiring_verified.json
dw next            # 看看八步进度推断是否符合预期
```
