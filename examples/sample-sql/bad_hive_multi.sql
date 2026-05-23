-- Hive: INSERT OVERWRITE without PARTITION, uses DOUBLE on money field, uses dt
INSERT OVERWRITE TABLE db_a.dws_trade_order_di
SELECT
    order_no,
    CAST(pay_amount AS DOUBLE) AS pay_amount
FROM db_a.dwd_trade_order_detail;

CREATE TABLE IF NOT EXISTS db_a.dws_trade_order_di (
    order_no STRING,
    pay_amount DOUBLE
)
PARTITIONED BY (dt STRING);
