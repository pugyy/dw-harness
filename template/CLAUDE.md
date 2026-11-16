# 当前迭代状态（dw init 生成，手动维护）

@AGENTS.md

## 正在开发
- 表：[填写，如 db_a.dws_trade_order_di]
- 版本：[如 V2.0]
- node_id：[如 1000000001]
- 状态：[如 ETL 开发（Step 3/8），可用 /dw-next 复核]

## 本次迭代约束
- 禁止修改：[如 dwd_trade_order_detail（已上线只读）]
- 分区字段：partition_dt（yyyyMMdd）
- 金额单位：以契约 contracts/ 为准（币种与单位分开）

> 长期规范在 AGENTS.md 与 .claude/rules/；本文件只保留“当前在做什么”。
