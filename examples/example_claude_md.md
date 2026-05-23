# 当前迭代状态（每次迭代手动更新）

## 正在开发
- 表：db_a.dws_trade_order_di
- 版本：V1.0
- node_id：1000000001
- 状态：ETL 开发阶段（Step 3/8）

## 本次迭代约束
- 禁止修改：dwd_trade_order_detail（已上线，只读）
- 分区字段：partition_dt（格式 yyyyMMdd，不是 dt）
- amount 字段单位：千元（不是元）
- 本版本不处理退款逻辑，退款金额字段设为 0

## 数仓全局规范
- 建表：分区字段必须是 partition_dt string
- 禁止：SELECT *，UPDATE/DELETE 无 WHERE
- 金额字段用 DECIMAL(20,4)，不用 DOUBLE
- INSERT 必须带 PARTITION 子句
- 注释三段式：业务含义 + 数据来源 + 计算逻辑

## 跨会话经验（建议沉淀到 Memory 或长期 CLAUDE.md）
- amount 字段在上游 dwd 层已经是千元单位，不需要再做转换
- partition_dt 在 20260101 之前的数据有缺失，需要特殊处理
- is_perform 字段为 Y 时，perform_flag 必须为 1，否则为 0
