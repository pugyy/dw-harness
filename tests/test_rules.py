"""Rule engine coverage per spec item 6: identifiers, strings, comments,
statement layers, SELECT * variants, COUNT(*), partition and DECIMAL rules."""
from __future__ import annotations

import unittest

from dw_core.config import DEFAULT_CONFIG, HarnessConfig
from dw_core.rules import lint_sql
from dw_core.sqlsplit import scan_sql

_CONFIG = HarnessConfig(data=dict(DEFAULT_CONFIG), root=None, path=None)


def lint(sql, dialect="odps"):
    return lint_sql(sql, dialect, _CONFIG)


def rules_of(result):
    return {i.rule for i in result.issues}


class ScannerTests(unittest.TestCase):
    def test_multiline_statement_line_numbers(self):
        sql = "-- header\nINSERT OVERWRITE TABLE t PARTITION (dt='x')\nSELECT a\nFROM b;\nSELECT c FROM d;"
        stmts, problems = scan_sql(sql)
        self.assertFalse(problems)
        self.assertEqual(len(stmts), 2)
        self.assertEqual(stmts[0].start_line, 2)
        self.assertEqual(stmts[1].start_line, 5)

    def test_semicolon_inside_string_does_not_split(self):
        sql = "SELECT 'a;b' FROM t; SELECT 'drop table x' FROM t"
        stmts, problems = scan_sql(sql)
        self.assertEqual(len(stmts), 2)
        self.assertFalse(problems)
        self.assertNotIn("drop", stmts[1].code.replace("'", ""))


class SelectStarTests(unittest.TestCase):
    def test_select_star_variants(self):
        for sql in ("SELECT * FROM t",
                    "select   *\nfrom t",
                    "SELECT DISTINCT * FROM t",
                    "SELECT t.* FROM t AS t",
                    "SELECT DISTINCT t.* FROM db.t t",
                    "SELECT a, *, b FROM t",
                    "SELECT x, t.*, y FROM db.t t",
                    "SELECT (SELECT * FROM sub) FROM t"):
            with self.subTest(sql=sql):
                result = lint(sql)
                self.assertIn("no-select-star", rules_of(result), sql)

    def test_count_star_and_arithmetic_pass(self):
        for sql in ("SELECT COUNT(*) FROM t",
                    "SELECT count( * ) FROM t",
                    "SELECT price * 2 FROM t",
                    "SELECT a * b, c / 2 FROM t",
                    "SELECT SUM(x * y) FROM t",
                    "SELECT (a + b) * 2 FROM t"):
            with self.subTest(sql=sql):
                result = lint(sql)
                self.assertNotIn("no-select-star", rules_of(result), sql)

    def test_string_literal_keywords_pass(self):
        result = lint("SELECT 'drop table x' AS s, \"TRUNCATE TABLE y\" AS t2 FROM t")
        self.assertFalse(result.errors)


class DmlAndPartitionTests(unittest.TestCase):
    def test_insert_requires_partition(self):
        result = lint("INSERT INTO db.t SELECT a FROM s")
        self.assertIn("insert-requires-partition", rules_of(result))

    def test_insert_with_partition_passes(self):
        result = lint("INSERT OVERWRITE TABLE db.t PARTITION (partition_dt='20260101') SELECT a FROM s")
        self.assertNotIn("insert-requires-partition", rules_of(result))

    def test_starrocks_insert_partition_downgraded_to_warn(self):
        result = lint("INSERT INTO sr_db.t VALUES (1)", dialect="starrocks")
        severities = [i.severity for i in result.issues if i.rule == "insert-requires-partition"]
        self.assertTrue(all(s == "warn" for s in severities))

    def test_delete_update_require_where(self):
        self.assertIn("dml-requires-where", rules_of(lint("DELETE FROM db.t")))
        self.assertIn("dml-requires-where", rules_of(lint("UPDATE db.t SET a=1")))
        self.assertNotIn("dml-requires-where",
                         rules_of(lint("DELETE FROM db.t WHERE dt='20260101'")))
        self.assertNotIn("dml-requires-where",
                         rules_of(lint("UPDATE db.t SET a=1 WHERE id=2")))

    def test_where_inside_subquery_counts(self):
        result = lint("DELETE FROM db.t WHERE id IN (SELECT id FROM s WHERE flag=1)")
        self.assertNotIn("dml-requires-where", rules_of(result))

    def test_partition_named_dt_flagged(self):
        result = lint("CREATE TABLE t (a string) PARTITIONED BY (dt string)")
        self.assertIn("partition-name", rules_of(result))

    def test_partition_named_partition_dt_ok(self):
        result = lint("CREATE TABLE t (a string) PARTITIONED BY (partition_dt string)")
        self.assertNotIn("partition-name", rules_of(result))


class MoneyTests(unittest.TestCase):
    def test_double_money_rejected(self):
        result = lint("CREATE TABLE t (pay_amount DOUBLE, id BIGINT)")
        self.assertIn("money-decimal", rules_of(result))

    def test_low_precision_warns(self):
        result = lint("CREATE TABLE t (pay_amount DECIMAL(10,2))")
        self.assertIn("money-precision", rules_of(result))
        self.assertNotIn("money-decimal", rules_of(result))

    def test_standard_decimal_passes(self):
        result = lint("CREATE TABLE t (pay_amount DECIMAL(20,4))")
        self.assertFalse(result.errors)


class DialectFormatTests(unittest.TestCase):
    def test_spark_using_hint(self):
        result = lint("CREATE TABLE t (a int)", dialect="spark")
        self.assertIn("spark-create-format", rules_of(result))
        result = lint("CREATE TABLE t (a int) USING parquet", dialect="spark")
        self.assertNotIn("spark-create-format", rules_of(result))

    def test_starrocks_key_and_distribution(self):
        result = lint("CREATE TABLE sr_t (k int, v int) DISTRIBUTED BY HASH(k)", dialect="starrocks")
        self.assertIn("sr-table-key", rules_of(result))
        result = lint("CREATE TABLE sr_t (k int, v int) PRIMARY KEY(k) DISTRIBUTED BY HASH(k)", dialect="starrocks")
        self.assertNotIn("sr-table-key", rules_of(result))
        self.assertNotIn("sr-distributed-by", rules_of(result))


class ConfiguredLevelsTests(unittest.TestCase):
    def test_off_disables_rule(self):
        import copy
        data = copy.deepcopy(DEFAULT_CONFIG)
        data["rules"]["no-select-star"] = "off"
        config = HarnessConfig(data=data, root=None, path=None)
        result = lint_sql("SELECT * FROM t", "odps", config)
        self.assertNotIn("no-select-star", rules_of(result))

    def test_dialect_resolution_priority(self):
        from pathlib import Path
        config = HarnessConfig.load(root=Path("."))
        self.assertEqual(config.resolve_dialect("x/sr/a.sql"), "starrocks")
        self.assertEqual(config.resolve_dialect(file_path="a.sql", explicit="hive"), "hive")
        self.assertEqual(
            config.resolve_dialect("plain.sql", env={"DW_HARNESS_DIALECT": "spark"}), "spark")
        self.assertEqual(config.resolve_dialect("plain.sql"), "odps")


if __name__ == "__main__":
    unittest.main()
