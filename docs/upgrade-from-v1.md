# dw-harness v1 到 v2 升级说明

[English version](upgrade-from-v1.en.md)

本文面向已经在项目里使用 v1 模板的团队。v2 保留 OneData 八步流程、MaxCompute → StarRocks 主线、4 个 subagent、23 项自测和 9 类 DQC。变化集中在安装方式、目录结构、命令命名、Hook 行为和验收方式。

## 先确认你属于哪种情况

- 项目里有 `.claude/hooks/validate_sql.py`、`block_dangerous_ddl.py`、`inject_context.py`，并且 `settings.json` 注册了这三个 Hook：这是标准 v1 项目。
- 团队改过 Hook、Skill、Agent 或 `settings.json`：迁移前先备份。`dw init` 会报告冲突，不会覆盖未识别的文件。
- 想继续用复制模板、不安装 Claude Code 插件：走模板迁移，命令名不变。
- 希望后续通过 Marketplace 更新、减少项目内副本：走插件迁移。

两种形态不要同时安装。插件和模板都会注册 Hook，同时存在会重复检查、重复拦截；由于两套 Hook 的脚本路径不同，迁移的去重逻辑也不会把它们合并。

## v2 的主要变化

| 领域 | v1 | v2 |
|---|---|---|
| 分发 | 复制 `template/.claude` | Claude Code 插件、`dw` CLI、复制模板，三种形态 |
| 源码 | 直接改 `template/.claude` | `src/` 单一源码，`plugins/`、`template/` 由 `build.py` 生成 |
| 命令 | `/dw-etl` 等 8 个裸命令 | 插件模式 `/dw-harness:dw-etl`；模板模式保留原名 |
| Hook | 3 个 Python 脚本，只匹配 Bash | 7 个适配器，匹配 `Bash\|PowerShell`，策略型 Hook fail-closed |
| Agent | `agents/<name>/<name>.md` 嵌套 | `agents/<name>.md` 平铺，`model: inherit` |
| Skill | 8 个 | 15 个：原八步 + bootstrap/contract/check/next/review/backfill/sql-reference |
| 规范载体 | `.claude/CLAUDE.md` + `context/` | 根 `CLAUDE.md` + `AGENTS.md` + `.claude/rules/` |
| 配置 | 环境变量、文件名推断方言 | `.claude/dw/harness.json` 统一配置，环境变量仍兼容 |
| 验收 | 自测和对账靠对话与文档 | `dw check` 四态报告 + 输入绑定的 evidence |
| Python | 3.9+，用 `python` 调用 | 3.9+；插件 Hook 用 PATH 上的 `python`，模板可用 `dw init --python` 指定 |

`CLAUDE.local.md` 是 Claude Code 自带的本地记忆文件，但 dw-harness 不生成它，也不依赖它。v2 的迭代状态放在根 `CLAUDE.md`、`.claude/dw/state.json` 和交付物里。

## 必须处理的破坏性变更

**1. 插件模式的命令带命名空间。**
`/dw-etl` 变成 `/dw-harness:dw-etl`。模板模式不变。Runbook、脚本和团队文档里写死的命令要同步修改；只写“执行 ETL skill”的描述不受影响。

**2. Hook 文件重命名，行为也变了。**
`validate_sql.py` → `validate_post.py`。仍然是写后检查，但文件已经落盘，`exit 2` 的作用是把错误喂回模型让它修正，不是阻止写入。

`block_dangerous_ddl.py` → `guard_shell.py`。同时覆盖 PowerShell；能识别 `-f` 脚本、`--file=`、复合命令和 `.cmd/.exe` 客户端。

`inject_context.py` → `session_context.py` + `post_compact.py`。SessionStart 注入状态卡；PostCompact 只落盘，不再向 PostCompact 注入上下文。

**3. `init` 不再删除 `.claude`。**
v1 的 `init.sh` 会 `rm -rf .claude` 后整目录覆盖。v2 改成合并式：读取现有 `settings.json`，只补缺失项，写 `.bak-<时间戳>`，用 `.claude/dw/managed.json` 记录托管文件哈希。用户改过的文件会进冲突列表，不会被覆盖。

**4. Agent 目录拍平。**
`agents/data-comparator/data-comparator.md` 改成 `agents/data-comparator.md`。自定义 Agent 如果还在嵌套目录，迁移时手动拍平，并检查 frontmatter 是否依赖 `permissionMode`；插件环境会忽略该字段，能力收窄应改用 `tools`。

**5. `FileChanged` 已移除。**
v1 想用文件监听覆盖“人改 SQL”的场景，但 `FileChanged` 的 matcher 按字面文件名注册，glob 不生效。v2 改成 `dw lint --changed` / `dw check --changed`，在 CLI 或 CI 里处理旁路修改。

**6. 严格证据链要求 key。**
`dw check` 的 strict 模式不再接受无签名的 producer 声明。生产与校验两端需要同一个 `DW_HARNESS_EVIDENCE_KEY`；本地体验可用 `--mode local`，或先运行 `dw evidence keygen` 生成 key。CI 把 key 放 secret。

**7. 插件 Hook 依赖 PATH 上的 `python`。**
插件安装后，PreToolUse 的 `onFailure: "block"` 会在解释器缺失时拦截 Bash/Write。macOS 或 Ubuntu 如果只有 `python3`，先激活包含 `python` 的环境，或改用模板模式并通过 `dw init --python python3` 指定解释器。

## 迁移路径 A：插件模式（推荐）

适合希望后续自动更新、减少项目内副本的团队。

1. 备份并确认工作区干净：
   ```bash
   git status
   cp -r .claude .claude.v1.bak
   ```
   PowerShell：
   ```powershell
   Copy-Item -Recurse .claude .claude.v1.bak
   ```

2. 安装插件：
   ```text
   /plugin marketplace add pugyy/dw-harness
   /plugin install dw-harness@dw-harness
   ```

3. 在项目里生成项目侧文件：
   ```text
   /dw-harness:dw-bootstrap
   ```
   已安装 `dw` CLI 时，也可以用：
   ```bash
   dw init --target . --mode plugin --dry-run
   dw init --target . --mode plugin
   ```
   插件模式不写 Hook 接线，Hook 由插件自带，因此 `--python` 不影响 Hook；它只用于 `--statusline` 生成的状态栏命令，以及 `--mcp` 注册的本地 server 命令。插件 Hook 始终使用 PATH 上的 `python`。

4. 检查 `settings.json`。迁移会移除可确认的 v1 Hook（`python .claude/hooks/validate_sql.py` 等），保留自定义权限、状态栏和其他 Hook。自定义过的 v1 Hook 会进冲突报告，按报告手工处理。

5. 检查项目文件：
   - 根 `CLAUDE.md` 是否引用了 `@AGENTS.md`；
   - `.claude/rules/` 下是否同时存在 v2 规则和团队自定义规则；
   - 迁移只给根 `CLAUDE.md` 追加 `@AGENTS.md`，**不会搬运** `.claude/CLAUDE.md` 的内容。请手动把旧文件里的迭代状态、当前表、版本和约束复制到根 `CLAUDE.md`；
   - 自定义 Skill、Agent 是否保留，嵌套 Agent 是否已拍平。

6. 跑一次自检：
   ```bash
   dw doctor --mode plugin
   ```

## 迁移路径 B：模板模式（内网、离线或不想装插件）

1. 备份 `.claude`，确认 `settings.json` 可解析。
2. 先预览：
   ```bash
   dw init --target . --python python --dry-run
   ```
3. 执行迁移：
   ```bash
   dw init --target . --python python
   ```
   或使用仓库里的包装脚本：
   ```bash
   bash init.sh /path/to/project
   ```
4. 检查 `.bak-*`、`.claude/dw/managed.json` 和冲突列表。
5. 运行：
   ```bash
   dw doctor --mode template
   ```

`dw init --python` 只影响模板 Hook 和可选状态栏；插件模式请按上文的 PATH 解释器规则处理。

## 迁移后需要验证的行为

- `SELECT t.*`、`SELECT DISTINCT t.*` 在 Hook 和 `dw lint` 里命中同一条 `no-select-star`；`COUNT(*)`、字符串里的 `'drop table'` 不误报。
- 写一个带 `INSERT OVERWRITE` 但缺 `PARTITION` 的 SQL，确认 `dw lint` 和 PostToolUse 都会报错。
- 执行 `odpscmd -e 'DROP TABLE db.t'`，确认 PreToolUse 返回 deny；把解释器改成不存在的路径，确认 fail-closed 仍然拦截。
- 运行 `dw check`，确认输出 PASS/FAIL/UNVERIFIED/N/A 四态，退出码为 0/1/2。
- 修改 SQL 后重新 `dw check`，确认旧 evidence 变成 UNVERIFIED，而不是继续 PASS。
- 确认自定义状态栏仍在；如果要启用 dw 状态栏，运行 `dw init --statusline`，它不会覆盖已有 `statusLine`。
- CI 里用 `dw lint --changed` 和 `dw check --changed`，不再依赖 Claude Code 会话内的 Hook。

## 命令与文件对照

| v1 | v2 |
|---|---|
| `/dw-etl` | 插件 `/dw-harness:dw-etl`；模板 `/dw-etl` |
| `bash init.sh` | `dw init`（合并式，支持 `--dry-run`） |
| `python .claude/hooks/validate_sql.py` | `dw lint` / `validate_post.py` |
| `block_dangerous_ddl.py` | `guard_shell.py` |
| `inject_context.py` | `session_context.py` + `post_compact.py` |
| `agents/x/x.md` | `agents/x.md` |
| `.claude/context/0x_conventions.md` | `AGENTS.md` + `.claude/rules/` |
| `SELECT *` 检查 | `dw lint`，规则可在 `harness.json` 调级别 |

## 保留不变的部分

- OneData 八步流程和交付物顺序。
- MaxCompute → StarRocks 主线。
- 4 个 subagent 的职责：探索、校验、自测、对账。
- 23 项自测、9 类 DQC 的分类。
- 路径级规则、SQL 规范、金额字段 `DECIMAL(20,4)`、`partition_dt` 约定。
- 自定义 Skill、规则、权限、状态栏：迁移只合并，不主动删除。

## 渐进纳管旧表

历史表没有契约时，`dw check` 对 `contract-validate` 给 UNVERIFIED，而不是 FAIL。要正式纳管，复制 `contracts/contract.example.json` 为 `contracts/<表>.json`，补齐表标识、粒度、业务键、分区、列类型、币种/单位、质量阈值和 SLA，然后：

```bash
dw contract validate contracts/<表>.json
dw contract compile contracts/<表>.json
```

下一次 `dw check` 会按新契约执行。没有迁移决定的破坏性字段变更仍会被拦。

## 已知边界

- `plugin-validate` 需要 `CLAUDE_CODE_OAUTH_TOKEN` 并手动触发，发布时未跑。
- MaxCompute、StarRocks、DataWorks 适配器代码就绪，未连真实实例；`docs/e2e-demo.md` 有复现步骤。
- 插件 Hook 要求 PATH 上有 `python`；只有 `python3` 的环境需要先处理解释器。
- PyPI 尚未发布，CLI 从仓库安装。
- v1 没有证据链，因此没有 `dw-evidence/2` 历史数据需要迁移。

## 回滚

迁移不会删除 v1 文件；`settings.json` 和 `CLAUDE.md` 都有 `.bak-<时间戳>`。回滚时先备份当前状态：

```bash
git status
git checkout -- .claude CLAUDE.md
```

`git checkout` 只还原已跟踪文件。`dw init` 新增的 `AGENTS.md`、`.claude/dw/`、`.claude/rules/` 新规则通常未跟踪，不会被还原。先预览再清理：

```bash
git clean -nd .claude AGENTS.md
```

确认列表中没有团队自己的未跟踪文件后，再执行：

```bash
git clean -fd .claude AGENTS.md
```

`.claude.v1.bak` 也是未跟踪文件；建议把它加入 `.git/info/exclude` 或 `.gitignore`，避免长期出现在 `git status` 里。

如果安装了插件，卸载：

```text
/plugin uninstall dw-harness@dw-harness
```

如果 `dw init` 已写入 `managed.json`，先查看其中托管文件列表，再删除 `.claude`，避免误删团队自定义内容。
