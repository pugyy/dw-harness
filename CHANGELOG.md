# Changelog

## 2.0.0 (2026-11-16, rev2) — 大版本重构：可安装、可配置、可验证

### rc.1 审计修正（rev2）

- 证据链生产/校验统一 canonical 角色（contract / sql:<name> / ddl:<name> / reconcile:spec），`dw reconcile --save-evidence` 的证据可被 `dw check` 直接过账（端到端测试覆盖）
- 证据信任边界：producer 字段（dw-reconcile/dw-check/ci/manual），strict 模式拒绝 manual 与 hand_edited；可选 HMAC（DW_HARNESS_EVIDENCE_KEY）
- 对账截断强制 UNVERIFIED，不再可能翻成 PASS
- marketplace `owner` 修正为对象结构
- 最低 Claude Code 版本改为 2.1.295（onFailure 所需）；doctor 实测 `claude --version`
- 迁移按 hook 脚本身份去重：用户同 matcher hook 不再静默抑制安全守卫
- `--python` 结构化替换：Windows 绝对路径 / `py -3`（拆 command+args）/ 中文路径均安全
- 不可读/缺失的 `-f` 脚本按 unknown 策略处理（dev ask / prod deny），不再放行；识别 `.exe/.cmd/.bat` 客户端包装；`ALTER TABLE ... DROP PARTITION` 计入破坏性
- 移除 FileChanged 死接线（glob matcher 按官方语义是字面文件名）；out-of-band 检查改由 `dw lint --changed` 承担
- doctor 区分 plugin/template 模式（repo checkout 自动按插件形态检查），CI 不再 `|| true`
- skills `allowed-tools` 逗号语法修正为独立规则；self-test/data-comparison 绑定专用 agent；dw-explorer Bash 命令级收窄；新增 statusline（`dw init --statusline`）
- `dw check --changed` / `dw lint --changed` 变更集批量模式；`dw contract diff --baseline git:<rev>:<path>` Git 基线
- DB 适配器 partition_exists 实测 COUNT（参数绑定），空分区与缺分区可区分
- 清理误提交的 .mimosa/（历史重写移除）

### rc.2 复审修正（rev3）

- R1 证据覆盖并集：校验集 = 本次 check 的 contract/sql/ddl ∪ 证据绑定角色，部分绑定无法隐藏
  SQL 漂移（负测锁定）；`dw reconcile` 新增 `--ddl` 绑定；spec 路径进 binding_paths（check 免传参反推）
- R2 信任边界补严：strict 模式且未配置 `DW_HARNESS_EVIDENCE_KEY` 时，拒绝一切「自称」
  producer 的证据（producer 为普通字段可伪造）；签名/篡改/伪造三测试 + demo d3
- R3 statusLine 修正为官方 schema（单条 shell `command` 字符串，无 args 字段），
  脚本输出纯文本行；settings schema 与输出测试锁定
- R4 文档数字对齐（105 测试 / 20 用例）；e2e 的 reconcile 命令补 `--contract/--sql/--ddl`
  与 strict/key 说明，文档路径可真跑通
- R5 plugin-validate workflow 安装 claude CLI + 强制 `CLAUDE_CODE_OAUTH_TOKEN` secret
  （缺失即红，不再空跑绿）
- R6 DB 分区存在性改查元数据（StarRocks information_schema/SHOW PARTITIONS；
  MaxCompute PyODPS 表 API，真机待验）
- R7 doctor：已安装但低于 2.1.295 的 claude 计为 critical
- R8 方言包真实加载：`dialects/*.json` 的 `rule_levels` 参与规则分级（不再是死资产）
- R9 marketplace owner 断言入测试；`dw init --statusline` schema 测试

单源重构 + 插件分发 + 表契约 + 键级对账 + 四态验收。v1 用户的八步流程、
OneData 背景、MaxCompute → StarRocks 主线全部保留；升级路径见
docs/upgrade-from-v1.md。

### 架构
- `src/` 成为唯一真源；`scripts/build.py` 确定性生成 `plugins/dw-harness/`、
  `template/`、`.claude-plugin/marketplace.json`，CI 以 `build --check` 拒绝漂移
- 抽出 Python 核心 `dw_core`，CLI / Claude Code hooks / CI / MCP 共用；
  核心与本地 hook 仅依赖标准库（Python ≥ 3.9），YAML/深解析/DB 客户端为可选能力
- 新增可安装 `dw` CLI（pyproject 入口）；插件 / Marketplace / 复制模板三种分发形态
- 本地 stdio MCP server（默认关闭）：lint_sql / get_contract / get_table_schema /
  get_lineage / get_check_report

### 修复（v1 遗留）
- `SessionStart(compact)` 钩子输出 `hookEventName: "PostCompact"` 导致规范重注入
  从未生效 → 现按事件名输出；PostCompact 事件仅做本地落盘（该事件无 additionalContext 契约）
- 危险命令守卫只匹配 `Bash` → 现在 `Bash|PowerShell`（Windows 无 Git Bash 时走 PowerShell 工具）
- hook 命令相对路径 → `${CLAUDE_PROJECT_DIR}`（插件形态用 `${CLAUDE_PLUGIN_ROOT}` + exec args）
- matcher 中已废弃的 `MultiEdit` 移除
- `init.sh/init.ps1` 的整目录 `rm -rf` 行为废除 → 合并式迁移（备份 + managed.json
  哈希跟踪 + 冲突报告 + `--dry-run`）

### SQL 校验与守卫
- 规则引擎重写：语句/字符串/注释/标识符级扫描；`SELECT t.*`、`DISTINCT t.*`、
  子查询内 `SELECT *` 全覆盖；`COUNT(*)`、字符串字面量关键字、`price * 2` 算术零误报
- 规则分级 error/warn/off 可配置；每条规则标注 engine（引擎限制）与 policy（团队政策）
- StarRocks 方言：键模型/分桶检查；INSERT 省分区按引擎合法降级为 warn
- PreToolUse 内容级守卫：内联 SQL 与 `-f` 脚本都检查；破坏性 DDL / 无 WHERE DML /
  分区安全阀（非 yyyyMMdd、未来日期、表达式、生产环境升级为 deny）
- 有期限策略例外（审批人/原因/环境/对象/操作/有效期），过期不生效；
  决策日志（输入哈希关联）落 `.claude/dw/guard_log.jsonl`
- PII 扫描（手机号/身份证/银行卡，命中默认告警并给脱敏建议）
- 可选 sqlglot 深检：解析失败显式标记 unresolved，Hive 近似解析不冒充 MaxCompute 结论

### 表契约 / DDL / 计划 / DQC / 影响面
- 版本化 contract（YAML 需可选 PyYAML，JSON 始终可用），运行态规范化 JSON；
  金额列币种与单位分开声明（CNY 的分/元/千元是不同契约事实）
- `dw contract diff`：删列/类型收窄/单位/键/粒度/分区/阈值变化分级，
  破坏性变更必须记录迁移决定（from_hash→to_hash 绑定）
- DDL 交叉验证（仅 DDL 可证明属性）；`dw plan ddl` 生成 ALTER 候选，
  类型收窄需显式 `--allow-narrowing`，键/分区变化输出重建/切换/验证/恢复步骤
- `dw plan backfill`：环境/范围/幂等/检查点/扫描估算（COST SQL 预演不执行，未知标未知）
- `dw dqc gen/check`：9 类规则稳定 ID（同表同类同列同阈值同 ID），配置漂移 FAIL
- `dw impact`：仓库 SQL 表级血缘 + 可确认列级路径，来源与未知项显式标注；
  DataWorks 适配器可选（仅 https、拒绝内网/环回/保留地址）

### 对账与验收
- `dw reconcile`：文件 / MaxCompute / StarRocks 三类适配器；预检（分区缺失/空键/
  重复键/缺失键）→ 总量 → 键级；Decimal 计价、单位换算、绝对+相对容差组合、
  零基线与 NULL 语义显式化；结果 pass/fail/unverified 可区分
- `dw check` 四态验收（PASS/FAIL/UNVERIFIED/N-A），退出码 0/1/2；
  JSON + 可贴 PR 的 Markdown；本地模式允许未验证项但保留状态与理由
- 证据链：schema/工具版本/输入摘要/commit/环境分区/时间戳；输入变化 → UNVERIFIED；
  手改 PASS 仅可作展示，严格 CI 只认本次重跑或可信验证任务

### Claude Code 体验
- 15 个 skill：原八步升级（fork 隔离、allowed-tools、argument-hint、交付物可验证），
  新增 bootstrap/contract/check/next/review/backfill + 按路径自动加载的 sql-reference
- 4 个 subagent 平铺：model: inherit、tools 收窄、memory: project、maxTurns；
  不再依赖 plugin 环境下会被忽略的 permissionMode
- SessionStart 注入 ≤2000 字会话状态卡；PostCompact 只落盘；SessionEnd 写 handoff.md
- AGENTS.md 承载跨工具共享规范，CLAUDE.md 显式 `@AGENTS.md` 引用

### 测试 / CI / 文档
- 105 个测试：规则误报矩阵、守卫决策、契约与证据、对账语义、真实 hook 脚本接线、
  manifest、构建漂移、迁移幂等、MCP 握手、离线端到端
- CI：ubuntu/windows/macos × Python 3.9/3.13 + CLI 安装 + build --check + demo；
  插件真机验证独立 workflow（需受信环境，缺 claude CLI 时优雅跳过）
- 新增 docs：configuration / upgrade-from-v1 / support-matrix / e2e-demo / mcp；
  README 重写为安装 + 演示首屏

### 已知边界
- MaxCompute/StarRocks 适配器代码就绪但未连真实实例验证（无凭据环境），
  复现步骤见 docs/e2e-demo.md
- Claude Code 真机加载/写后反馈/会话注入待受信环境按 docs/e2e-demo.md 验证
  （本仓库 doctor 的 app-wiring-verified 检查项即为该验证的落点）

## 1.x
见 git history（2026-05-23 初始发布：hooks + 8 skills + 4 subagents 模板）。
