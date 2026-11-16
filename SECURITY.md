# Security Notes

- **Hook 执行身份**：所有 hook/CLI 以当前用户身份运行；"plugin 所跑即你所跑"。
  安装第三方 marketplace 前请审代码——本仓库即全部源码。
- **Fail-closed**：策略型 PreToolUse 钩子（guard_shell / guard_write）任何内部
  异常都转为 `deny`（脚本内兜底）；`onFailure: "block"` 为第二道保险，
  旧版本 CLI 由脚本内兜底覆盖。
- **凭据**：数据库/适配器凭据只从环境变量读取；源码、示例、测试中零可用凭据字面量。
- **SQL 查询**：对账/血缘查询使用参数绑定；表名/列名不可绑定，走
  `^[A-Za-z_][A-Za-z0-9_.]{0,254}$` 标识符白名单后拼接。
- **出网**：DataWorks 适配器仅允许 https(s) 公网端点；localhost、环回、私有、
  保留、组播地址在发请求前被拒绝。
- **例外治理**：策略例外必须有 `not_after`；过期或畸形条目视为不存在。
  决策日志（含输入哈希）落 `.claude/dw/guard_log.jsonl` 供审计。
- **PII**：命中默认告警并给脱敏建议（样本打码）；`action: "deny"` 可升级为阻断。
- **证据**：手改的 PASS 文件只能用于展示/诊断；严格 CI 只认本次重跑或可信
  验证任务产出的证据。
- 报告漏洞：开 GitHub Issue 或私下联系仓库 owner。
