---
name: dw-sql-reference
description: 数仓 SQL 规范参考（引擎差异、政策规则、正反例）。Claude 在读写 SQL 文件时按需加载，不给用户手动调用。
user-invocable: false
paths:
  - "**/*.sql"
---

# SQL 规范参考（自动加载）

## 引擎 vs 政策

- `kind=engine`：引擎语法限制（如 Hive 缺 STORED AS、UPDATE 无 WHERE）
- `kind=policy`：团队约定（如禁 SELECT *、SR 也建议声明分区）

## 规则速查

| 规则 | 默认级别 | 说明 |
|---|---|---|
| no-select-star | error | `SELECT *`/`t.*` 全禁；`COUNT(*)` 例外 |
| insert-requires-partition | error（SR: warn） | 声明目标分区 |
| dml-requires-where | error | UPDATE/DELETE 带 WHERE |
| partition-name | error | `partition_dt`，禁 `dt` |
| money-decimal | error | `DECIMAL(20,4)` 禁 DOUBLE |
| money-precision | warn | 低于 (20,4) 提醒 |
| sr-table-key / sr-distributed-by | warn | SR 建表要素 |
| spark/hive-create-format | warn | 建表格式声明 |

## 正反例

```sql
-- 坏：SELECT t.*（照样被抓）
SELECT t.* FROM db_a.dwd_trade_order_detail t;

-- 好：显式列 + 分区 + 注释三段式
INSERT OVERWRITE TABLE db_a.dws_trade_order_di PARTITION (partition_dt = '20261115')
SELECT
    order_no,      -- 订单号|dwd.order_no|直接继承
    CAST(pay_amount AS DECIMAL(20,4)) AS pay_amount
FROM db_a.dwd_trade_order_detail
WHERE partition_dt = '20261115';
```

完整配置：`.claude/dw/harness.json`；方言解析优先级：显式参数 > 路径映射 > DW_HARNESS_DIALECT > 默认。
