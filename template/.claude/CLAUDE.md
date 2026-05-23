# 当前迭代状态（每次迭代手动更新）

## 正在开发
- 表：[填写表名，如 db_a.dws_table_a]
- 版本：[如 V1.0]
- node_id：[如 1000000001]
- 状态：[如 ETL 开发阶段（Step 3/8）]

## 本次迭代约束
- 禁止修改：[如 dwd_table_b（已上线，只读）]
- 分区字段：partition_dt（格式 yyyyMMdd，不是 dt）
- 金额字段单位：[如 千元（不是元）]

## 数仓全局规范
- 建表：分区字段必须是 partition_dt string
- 禁止：SELECT *，UPDATE/DELETE 无 WHERE
- 金额字段用 DECIMAL(20,4)，不用 DOUBLE
- INSERT 必须带 PARTITION 子句
- 注释三段式：业务含义 + 数据来源 + 计算逻辑
