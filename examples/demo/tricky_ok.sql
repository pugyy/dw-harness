-- dialect: odps
-- all of these must PASS the linter (no false positives)
SELECT COUNT(*) FROM db_a.dwd_trade_order_detail WHERE partition_dt = '20261115';

SELECT 'drop table db_a.dws_trade_order_di' AS remark FROM db_a.dwd_trade_order_detail LIMIT 1;

SELECT price * 2 AS double_price, qty * price AS amount FROM db_a.dwd_trade_order_detail LIMIT 1;

DELETE FROM db_a.dws_trade_order_di WHERE partition_dt = '20200101' AND order_no IN (SELECT order_no FROM db_a.tmp_bad_orders);
