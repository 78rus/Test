"""Database client tests, run against a real SQLite engine."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cashdesk_control.core.db_client import DatabaseClient, DatabaseError, QueryResult
from cashdesk_control.core.models import DatabaseSettings


class DatabaseClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = Path(self._temp.name) / "cash.db"
        self.settings = DatabaseSettings(dialect="sqlite", database=str(self.db_path), via_tunnel=False)
        self.client = DatabaseClient(self.settings)
        self.addCleanup(self.client.dispose)
        self.client.connect()
        for statement in (
            "create table goods (id integer primary key, name text not null, price integer)",
            "insert into goods (name, price) values ('Молоко', 89), ('Хлеб', 45), ('Кофе', 599)",
            "create view cheap_goods as select * from goods where price < 100",
        ):
            self.client.execute(statement)

    def test_ping_measures_a_round_trip(self) -> None:
        self.assertGreaterEqual(self.client.ping(), 0.0)

    def test_select_returns_rows(self) -> None:
        result = self.client.execute("select name, price from goods order by price")
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.columns, ["name", "price"])
        self.assertEqual(len(result.rows), 3)
        self.assertEqual(result.rows[0][0], "Хлеб")
        self.assertTrue(result.is_select)

    def test_update_reports_rowcount_and_commits(self) -> None:
        result = self.client.execute("update goods set price = 50 where name = 'Хлеб'")
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.rowcount, 1)
        check = self.client.execute("select price from goods where name = 'Хлеб'")
        self.assertEqual(check.rows[0][0], 50)

    def test_broken_sql_is_returned_not_raised(self) -> None:
        result = self.client.execute("select * from no_such_table")
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.rows, [])

    def test_list_tables_finds_tables_and_views(self) -> None:
        tables = {item.name: item.kind for item in self.client.list_tables()}
        self.assertEqual(tables["goods"], "table")
        self.assertEqual(tables["cheap_goods"], "view")

    def test_list_columns(self) -> None:
        columns = [column["name"] for column in self.client.list_columns("goods")]
        self.assertEqual(columns, ["id", "name", "price"])

    def test_update_row_by_primary_key(self) -> None:
        result = self.client.update_row("goods", ["id"], [1], "price", 100)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.rowcount, 1)

    def test_csv_export(self) -> None:
        result = self.client.execute("select name, price from goods order by name")
        text = result.to_csv()
        self.assertEqual(text.splitlines()[0], "name;price")
        self.assertEqual(len(text.strip().splitlines()), 4)

        target = Path(self._temp.name) / "out.csv"
        result.save_csv(target)
        self.assertTrue(target.exists())
        self.assertIn("Кофе", target.read_text(encoding="utf-8-sig"))

    def test_preview_rendering(self) -> None:
        result = self.client.execute("select name, price from goods")
        text = result.preview(limit=2)
        self.assertIn("name", text)
        self.assertIn("ещё 1 строк", text)

    def test_display_url_hides_the_password(self) -> None:
        client = DatabaseClient(DatabaseSettings(username="postgres", database="cash"), "s3cret")
        self.assertNotIn("s3cret", client.display_url)

    def test_url_points_at_the_tunnel_endpoint(self) -> None:
        settings = DatabaseSettings(database="cash", username="postgres", local_port=15432)
        self.assertIn("@127.0.0.1:5432/cash", settings.url())
        self.assertIn("@127.0.0.1:15432/cash", settings.url(host="127.0.0.1", port=15432))

    def test_tunnel_spec_is_created_only_when_needed(self) -> None:
        self.assertIsNone(DatabaseSettings(local_port=None).tunnel_spec)
        self.assertIsNone(DatabaseSettings(via_tunnel=False, local_port=15432).tunnel_spec)
        spec = DatabaseSettings(local_port=15432, port=5432).tunnel_spec
        self.assertEqual(spec.local_port, 15432)
        self.assertEqual(spec.target_port, 5432)

    def test_execute_without_connection_raises(self) -> None:
        client = DatabaseClient(DatabaseSettings(dialect="sqlite", database=":memory:", via_tunnel=False))
        with self.assertRaises(DatabaseError):
            client.execute("select 1")

    def test_unsupported_dialect_is_rejected(self) -> None:
        client = DatabaseClient(DatabaseSettings(dialect="cobol", database="x", via_tunnel=False))
        with self.assertRaises(DatabaseError):
            client.connect()


class PreviewTableTests(unittest.IsolatedAsyncioTestCase):
    """``preview_table`` is async, so it gets its own async case."""

    async def asyncSetUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._temp.name) / "cash.db"
        self.client = DatabaseClient(DatabaseSettings(dialect="sqlite", database=str(self.db_path), via_tunnel=False))
        await self.client.connect_async()
        await self.client.execute_async("create table goods (id integer primary key, name text)")
        await self.client.execute_async("insert into goods (name) values ('a'), ('b'), ('c')")

    async def asyncTearDown(self) -> None:
        self.client.dispose()
        self._temp.cleanup()

    async def test_preview_table_respects_the_limit(self) -> None:
        result = await self.client.preview_table("goods", limit=2)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(result.rows), 2)
        self.assertIn("limit 2", result.sql)

    async def test_preview_missing_table_reports_an_error(self) -> None:
        result = await self.client.preview_table("absent")
        self.assertFalse(result.ok)
        self.assertIn("не найдена", result.error)

    async def test_schema_listing_over_async_api(self) -> None:
        tables = await self.client.list_tables_async()
        self.assertIn("goods", [item.name for item in tables])
        columns = await self.client.list_columns_async("goods")
        self.assertEqual([column["name"] for column in columns], ["id", "name"])


class QueryResultTests(unittest.TestCase):
    def test_empty_result_message(self) -> None:
        result = QueryResult(sql="create table t (a int)", rowcount=0)
        self.assertIn("Выполнено", result.preview())

    def test_error_preview(self) -> None:
        result = QueryResult(sql="select 1", error="boom")
        self.assertEqual(result.preview(), "boom")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
