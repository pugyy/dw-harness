# 端到端验收

## 离线部分（无凭据可复现，CI 已覆盖）

```bash
python scripts/run_demo.py       # 等价 dw demo
```

日分区订单表 `db_a.dws_trade_order_di` 走完整链路：MaxCompute DDL/INSERT →
SR DDL → 契约 → DDL/回填预演 → DQC → 键级对账 → 影响面 → 报告。
18 个用例含反例 a–f（见 README）。报告落 `examples/demo/report/report.{json,md}`。

## 真实环境部分（本仓库无凭据，未执行 —— 精确复现步骤如下）

### 1. MaxCompute 只读对账

```bash
pip install dw-harness[odps]
export DW_HARNESS_ODPS_ACCESS_ID=...        # 只读身份
export DW_HARNESS_ODPS_ACCESS_KEY=...
export DW_HARNESS_ODPS_PROJECT=...
export DW_HARNESS_ODPS_ENDPOINT=https://odps.xxx.api.aliyun.com
cat > recon.json <<'EOF'
{"table": "db_a.dws_trade_order_di",
 "left":  {"adapter": "maxcompute", "table": "db_a.dws_trade_order_di", "partition": "20261115"},
 "right": {"adapter": "file", "path": "examples/demo/csv/old.csv", "partition": "20261115"},
 "keys": ["order_no"],
 "metrics": [{"column": "net_amount", "abs_tol": "0", "rel_tol": "0",
              "unit_left": "fen", "unit_right": "fen"}]}
EOF
dw reconcile --spec recon.json --save-evidence
```

预期：连接成功时预检+键级比较输出；无权限/超时 → UNVERIFIED + 原因。
查询为参数绑定（分区值），表名走标识符白名单。

### 2. StarRocks 只读对账

```bash
pip install dw-harness[sr]
export DW_HARNESS_SR_HOST=... DW_HARNESS_SR_PORT=9030
export DW_HARNESS_SR_USER=readonly DW_HARNESS_SR_PASSWORD=... DW_HARNESS_SR_DATABASE=db_a
# spec 里 "adapter": "starrocks"，其余同上
```

### 3. Claude Code 真机验证（受信环境）

```bash
npm install -g @anthropic-ai/claude-code && claude   # 登录
cd /tmp/probe && dw init --target . --python python  # 或直接用插件：
claude --plugin-dir /path/to/dw-harness/plugins/dw-harness
```

逐项验证并记录版本与输出：

1. `claude --version`；插件列表出现 dw-harness（userConfig 弹窗填 python）
2. **写后反馈**：让 Claude 写 `bad_star.sql`（内容 `SELECT t.* FROM db.t`）→
   预期 PostToolUse 反馈 no-select-star 并自动修正
3. **拒绝**：让 Claude 跑 `odpscmd -e 'DROP TABLE db.t'` → 预期 PreToolUse deny
4. **会话注入**：新会话首条消息前看到 `[dw-harness] 会话状态卡`；
   `/compact` 后 PostCompact 只落盘（`.claude/dw/last_compact.json`）不注入
5. **权限故障**：把 settings 里 python 改成不存在的解释器 → 预期守卫 fail-closed
   deny 而非放行；`dw doctor` 报 hook-scripts problem
6. 验证通过后写标记：

```bash
echo '{"verified_at": "<ts>", "claude_version": "<version>",
       "checked": ["plugin-load", "post-feedback", "deny", "session-inject"]}' \
  > .claude/dw/wiring_verified.json
```

`dw doctor` 的 app-wiring-verified 检查随即转绿。

### 4. 插件评测（可选）

受信环境：`claude plugin eval dw-harness`（workflow: plugin-validate.yml）。
