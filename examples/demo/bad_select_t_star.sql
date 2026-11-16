-- dialect: odps
INSERT OVERWRITE TABLE db_a.dws_trade_order_di PARTITION (partition_dt = '20261115')
SELECT t.* FROM db_a.dwd_trade_order_detail t
WHERE partition_dt = '20261115';
