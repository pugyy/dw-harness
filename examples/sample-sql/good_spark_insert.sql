-- Spark SQL: valid INSERT with partition and explicit fields
INSERT INTO db_a.dws_trade_order_di PARTITION (partition_dt = '20260523')
SELECT
    order_no,
    user_id,
    CAST(pay_amount AS DECIMAL(20,4)) AS pay_amount,
    order_status
FROM db_a.dwd_trade_order_detail
WHERE partition_dt = '20260523';
