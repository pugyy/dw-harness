# 本地 MCP Server（默认关闭）

stdio 传输、newline-delimited JSON-RPC 2.0、只读工具、有限结果。
默认**不**注册——需要显式开启：

## 注册（两种独立方式）

```bash
dw init --mcp                     # 写 .mcp.json 条目指向 .claude/dw/mcp/server.py
dw mcp --selftest                 # 可验证：子进程握手 initialize + tools/list + tools/call
```

手动注册（等价）：

```json
// .mcp.json
{"mcpServers": {"dw-harness": {"command": "python",
  "args": [".claude/dw/mcp/server.py"], "env": {}}}}
```

插件形态下 server 位于 `${CLAUDE_PLUGIN_ROOT}/mcp/server.py`。

## 工具清单

| 工具 | 入参 | 出参要点 |
|---|---|---|
| `lint_sql` | `{sql, dialect?}` | 结构化 issues（≤50 条，超出标 truncated） |
| `get_contract` | `{path?}` | 契约规范化 JSON + 来源文件 + 新鲜度（mtime） |
| `get_table_schema` | `{table}` | 从仓库 DDL 解析；标注 `repo-ddl:` 来源与未解析项 |
| `get_lineage` | `{table}` | 表级上下游 + 列级（可确认时）；来源 repo-sql/dataworks、未知显式标注 |
| `get_check_report` | `{path?}` | 最近一次 `dw check` 四态报告 |

## 纪律

- 全部只读；批量检查走 `dw check` 的变更集模式（CLI/CI），不经 MCP
- 结构化参数、清晰错误（`{"error": ...}` + `isError`）
- 表结构/血缘都带来源与新鲜度，不冒充实时 catalog
