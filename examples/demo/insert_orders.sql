-- dialect: odps
INSERT OVERWRITE TABLE db_a.dws_trade_order_di PARTITION (partition_dt = '20261115')
SELECT
    order_no,
    CAST(net_amount AS DECIMAL(20,4)) AS net_amount,
    CAST(pay_amount AS DECIMAL(20,4)) AS pay_amount,
    order_status
FROM db_a.dwd_trade_order_detail
WHERE partition_dt = '20261115';
