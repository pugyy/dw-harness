# 支持矩阵

## Python / 平台

| 项 | 支持 | 备注 |
|---|---|---|
| Python | 3.9 – 3.13 | CI 矩阵跑 3.9（下限）与 3.13（较新受支持版） |
| 平台 | Linux / Windows / macOS | hook 同时匹配 Bash 与 PowerShell（Windows 无 Git Bash 时） |
| 核心依赖 | 无（纯标准库） | CLI、hooks、规则引擎、文件对账、验收全链路 |
| 可选能力 | `pip install dw-harness[yaml\|deep\|odps\|sr]` | YAML 契约 / sqlglot 深检 / MaxCompute / StarRocks |

## SQL 方言 × 规则

| 规则 | odps | hive | spark | starrocks | kind |
|---|---|---|---|---|---|
| no-select-star（含 t.*、DISTINCT t.*、子查询内） | error | error | error | error | policy |
| insert-requires-partition | error | error | error | **warn**（引擎允许省分区） | policy |
| dml-requires-where | error | error | error | error | engine |
| partition-name（禁 `dt`） | error | error | error | error | policy |
| money-decimal（禁 DOUBLE） | error | error | error | error | policy |
| money-precision（<20,4 提醒） | warn | warn | warn | warn | policy |
| spark-create-format | — | — | warn | — | engine |
| hive-create-format | — | warn | — | — | engine |
| sr-table-key / sr-distributed-by | — | — | — | warn | engine |
| sql-parse / sql-deep-parse（解析不了显式标记） | 全部 | 全部 | 全部 | 全部 | engine |

误报防护已测试：`COUNT(*)`、`count( * )`、字符串字面量里的伪关键字、
`price * 2` 算术、`(a+b)*2`、子查询带 WHERE 的 DELETE。

## Claude Code 版本

| 能力 | 最低版本 |
|---|---|
| 插件 userConfig `options` 枚举 | 2.1.271 |
| **整体声明最低版本（含 hook `onFailure` fail-closed）** | **2.1.295** |
| AGENTS.md 原生读取（CLAUDE.md 优先） | 2.1.277 |
| hook `onFailure: block` fail-closed | Agent SDK 0.3.3.317 同期 CLI 版本；低版本由脚本内 fail-closed 兜底 |

声明依据：v2 实际使用的特性 + 官方文档版本标注；`dw doctor` 会做版本相关自检。

## 数据库 / 元数据

| 适配器 | 状态 | 凭据 |
|---|---|---|
| 文件（CSV fixtures，离线演示全链路） | ✅ 已测试 | — |
| MaxCompute（pyodps） | 存在性走表 API；fetch 的 `execute_sql(params=)` 占位符语义**真机待验**，未连真实实例 | 环境变量，只读身份 |
| StarRocks（pymysql，参数绑定 + 标识符白名单） | 代码就绪，未连真实实例；分区存在性走 information_schema/SHOW PARTITIONS | 环境变量，只读身份 |
| MaxCompute 分区元数据（PyODPS 表 API） | 代码就绪，真机待验 | 同上 |
| DataWorks 血缘 | 可选，仅 https 公网（拒绝环回/内网/保留地址） | 环境变量 |
