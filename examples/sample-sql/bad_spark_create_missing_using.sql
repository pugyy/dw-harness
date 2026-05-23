-- dialect: spark
CREATE TABLE db_a.dws_trade_order_di (
    order_no STRING,
    pay_amount DECIMAL(20,4)
)
PARTITIONED BY (partition_dt STRING);
