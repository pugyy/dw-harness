INSERT OVERWRITE TABLE db_a.ads_trade_summary_di
SELECT *
FROM db_a.dws_trade_order_di;
