# 配置参考

所有配置文件都住在项目侧（插件/模板只提供机器能力），`dw init` 负责生成与合并。

## .claude/dw/harness.json（项目策略）

| 键 | 默认 | 说明 |
|---|---|---|
| `dialect.default` | `odps` | 默认方言 |
| `dialect.by_path` | 见下 | glob → 方言映射 |
| `rules.<rule>` | 见规则表 | `error` / `warn` / `off` |
| `money_fields` | `amount\|amt\|price\|...` | 金额字段名正则 |
| `partition_column` | `partition_dt` | 分区字段命名约定 |
| `protected_objects` | `[]` | 禁改对象（写操作直接 deny） |
| `pii.enabled / scan_globs / patterns / action` | 开 / SQL+CSV / 三类 / `warn` | PII 扫描（`warn` 提醒脱敏，`deny` 拦截） |
| `guard.destructive` | `deny` | DROP/TRUNCATE/无 WHERE 删除 |
| `guard.overwrite_without_partition` | `ask` | 覆盖无显式分区 |
| `guard.future_partition` | `ask` | 非 yyyyMMdd / 未来日期 / 表达式分区 |
| `guard.unknown_write` | `ask` | 写入但目标/范围不可判定（生产升级为 deny） |
| `reconcile.sample_rows / max_rows / query_timeout_seconds` | 20 / 1e6 / 60 | 对账限制 |
| `evidence.freshness_hours` | 72 | 证据有效期 |

### 方言解析优先级（明确契约）

1. 显式参数（`--dialect` / MCP `dialect` 参数）
2. 项目路径映射 `dialect.by_path`
3. 兼容旧环境变量 `DW_HARNESS_DIALECT`
4. `dialect.default`（兜底 odps）

### 生产环境标记

`DW_HARNESS_PROD=1` 时：破坏性/未知写入的 `ask` 一律升级为 `deny`；
带确认范围的 INSERT OVERWRITE 也需要人工确认或走发布入口。

## .claude/dw/policy_exceptions.json（有期限例外）

```json
[{
  "id": "exc-2026-scratch",
  "approver": "trade-lead",
  "reason": "临时清理 scratch 表",
  "environment": "dev",
  "objects": ["db.tmp_scratch"],
  "operations": ["destructive"],
  "not_after": "2026-12-31"
}]
```

过期（`not_after` 早于今天）或字段畸形的例外**视为不存在**，绝不授予权限。
每次决策（含命中例外的）都追加记录到 `.claude/dw/guard_log.jsonl`，
以输入哈希前 12 位关联原始命令。

## contracts/contract.json（表契约）

schema 见 `contracts/schema/contract.schema.json`。要点：

- 金额列必须同时声明 `currency` 与 `unit`：`CNY` + `fen` / `yuan` / `qian_yuan`
  是三种**不同的契约事实**，对账换算由此驱动（1 yuan = 100 fen 基准）
- `quality` 阈值（波动/金额容差/新鲜度）与 `sla` 是 DQC 生成和对账判定的唯一来源
- YAML 格式需可选能力：`pip install "dw-harness[yaml]"`；JSON 永远可用

破坏性变更（删列/类型收窄/单位或币种/键/粒度/分区）必须记录迁移决定：

```bash
dw contract decide contracts/contract.json --baseline baselines/v1.json \
    --approver 张三 --reason "net_amount 分转元，下游同步换算"
```

## .claude/dw/state.json（迭代状态）

当前表/版本/Step/约束。SessionStart 注入的会话状态卡、statusline、handoff、
`dw next` 都读这里；`dw next` 另外用文件证据（交付物）推断进度，不信会话记忆。

## 证据与信任边界

- 证据带 `producer`（dw-reconcile / dw-check / ci / manual）与可选 HMAC 签名（`DW_HARNESS_EVIDENCE_KEY`，仅环境变量）
- `dw check --mode strict` 拒绝 manual/hand_edited 证据；且**未配置 HMAC key 时拒绝一切「自称」
  producer 的证据**（producer 是普通字段，无签名即可伪造）。本地闭环：export 同一个
  key 生成与校验；CI 配 secret；不想配 key 用 `--mode local`
- 证据记录 canonical 输入角色与绑定路径：contract / sql:<name> / ddl:<name> / reconcile:spec；任一重算不一致即 UNVERIFIED

## 环境变量（凭据只走环境，源码零字面量）

| 变量 | 用途 |
|---|---|
| `DW_HARNESS_PROD` | 生产标记（见上） |
| `DW_HARNESS_DIALECT` | 兼容 v1 的方言覆盖（优先级第 3） |
| `DW_HARNESS_ODPS_ACCESS_ID/_ACCESS_KEY/_PROJECT/_ENDPOINT` | MaxCompute 只读对账身份 |
| `DW_HARNESS_SR_HOST/_PORT/_USER/_PASSWORD/_DATABASE` | StarRocks 只读对账身份 |
| `DW_HARNESS_DW_ENDPOINT/_TOKEN/_PROJECT` | DataWorks 血缘适配器（仅 https 公网） |
| `DW_HARNESS_EVIDENCE_KEY` | 证据 HMAC 签名密钥（可选，仅环境变量） |

### 对账证据范围

`dw reconcile --save-evidence` 要求 spec 中的 `table` 和 `right.partition`。
CSV 作为右侧时，验收使用 `dw check --env offline --partition <分区>`。
数据库作为右侧时，`right.table` 必须与目标表一致，`right.environment` 对应
实际连接环境。CI 为各环境提供正确的只读连接与签名密钥。
StarRocks 在使用自定义物理分区名时，可在 spec 指定 `partition_name`。

CSV 相对路径以 spec 所在目录为准。使用 Git 基线时，在 `dw reconcile`
和 `dw check` 中均传入 `--baseline git:<rev>:<path>`。
`dw check --changed --base-ref <rev>` 对所有变化的表应用该 Git 基线。
旧版 dw-evidence/1 证据需要重新生成，签名绑定的结果不会跨环境、分区、文件内容和策略复用。
