from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Union

import psycopg
from psycopg import sql as pgsql
from psycopg.rows import dict_row

from src.config.settings import PostgresConfig


class PostgresConnector:
    def __init__(
        self,
        config: PostgresConfig,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.conn: Optional[psycopg.Connection] = None

    def connect(self) -> None:
        if self.conn:
            return

        self.config.validate()

        self.logger.info(
            "🔌 Conectando no PostgreSQL | host=%s | port=%s | db=%s | schema=%s | user=%s",
            self.config.host,
            self.config.port,
            self.config.database,
            self.config.schema,
            self.config.user,
        )

        self.conn = psycopg.connect(
            host=self.config.host,
            port=self.config.port,
            dbname=self.config.database,
            user=self.config.user,
            password=self.config.password,
            row_factory=dict_row,
        )

        self.logger.info("✅ Conexão PostgreSQL estabelecida com sucesso")

    def test_connection(self) -> dict[str, Any]:
        self.connect()

        if self.conn is None:
            raise RuntimeError("Conexão PostgreSQL não inicializada.")

        with self.conn.cursor() as cursor:
            started_at = time.perf_counter()

            cursor.execute(
                """
                SELECT
                    current_user AS current_user,
                    current_database() AS current_database,
                    current_schema() AS current_schema,
                    current_timestamp AS current_timestamp
                """
            )
            row = cursor.fetchone()
            elapsed = time.perf_counter() - started_at

            result = {
                "current_user": row["current_user"] if row else None,
                "current_database": row["current_database"] if row else None,
                "current_schema": row["current_schema"] if row else None,
                "current_timestamp": str(row["current_timestamp"]) if row else None,
                "elapsed_seconds": round(elapsed, 4),
            }

            self.logger.info(
                "🔎 Validação PostgreSQL | user=%s | db=%s | schema_atual=%s | ts=%s | tempo=%.4fs",
                result["current_user"],
                result["current_database"],
                result["current_schema"],
                result["current_timestamp"],
                result["elapsed_seconds"],
            )

            return result

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None
            self.logger.info("🔌 Conexão PostgreSQL encerrada")

    def execute_query(
        self,
        sql: str,
        params: Optional[tuple] = None,
    ) -> List[Dict[str, Any]]:
        self.connect()

        if self.conn is None:
            raise RuntimeError("Conexão PostgreSQL não inicializada.")

        with self.conn.cursor() as cursor:
            cursor.execute(sql, params or ())
            result = cursor.fetchall()
            return list(result)

    def execute_non_query(
        self,
        sql: Union[str, pgsql.Composable],
        params: Optional[tuple] = None,
    ) -> None:
        self.connect()

        if self.conn is None:
            raise RuntimeError("Conexão PostgreSQL não inicializada.")

        try:
            with self.conn.cursor() as cursor:
                cursor.execute(sql, params or ())
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def execute_many(self, sql: Union[str, pgsql.Composable], data: List[tuple]) -> None:
        if not data:
            return

        self.connect()

        if self.conn is None:
            raise RuntimeError("Conexão PostgreSQL não inicializada.")

        try:
            with self.conn.cursor() as cursor:
                cursor.executemany(sql, data)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def table_exists(self, schema: str, table: str) -> bool:
        sql = """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = %s
        ) AS exists
        """
        result = self.execute_query(sql, (schema, table))
        return bool(result[0]["exists"])

    def get_table_columns(self, schema: str, table: str) -> List[str]:
        sql = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position
        """
        result = self.execute_query(sql, (schema, table))
        return [row["column_name"] for row in result]

    def create_schema_if_not_exists(self, schema: str) -> None:
        stmt = pgsql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(pgsql.Identifier(schema))
        self.execute_non_query(stmt)

    def drop_table_if_exists(self, schema: str, table: str) -> None:
        stmt = pgsql.SQL("DROP TABLE IF EXISTS {}").format(pgsql.Identifier(schema, table))
        self.execute_non_query(stmt)

    def truncate_table(self, schema: str, table: str) -> None:
        stmt = pgsql.SQL("TRUNCATE TABLE {}").format(pgsql.Identifier(schema, table))
        self.execute_non_query(stmt)

    def create_table(self, schema: str, table: str, columns: Dict[str, str]) -> None:
        self.create_schema_if_not_exists(schema)

        cols = pgsql.SQL(",\n            ").join(
            pgsql.SQL("{} {}").format(pgsql.Identifier(col), pgsql.SQL(dtype))
            for col, dtype in columns.items()
        )

        stmt = pgsql.SQL(
            "CREATE TABLE IF NOT EXISTS {} (\n            {}\n        )"
        ).format(pgsql.Identifier(schema, table), cols)
        self.execute_non_query(stmt)

    def add_column(self, schema: str, table: str, column: str, dtype: str) -> None:
        stmt = pgsql.SQL(
            "ALTER TABLE {} ADD COLUMN IF NOT EXISTS {} {}"
        ).format(pgsql.Identifier(schema, table), pgsql.Identifier(column), pgsql.SQL(dtype))
        self.execute_non_query(stmt)

    def insert_dataframe(self, schema: str, table: str, df) -> None:
        if df.empty:
            return

        columns = list(df.columns)
        col_ids = pgsql.SQL(", ").join(pgsql.Identifier(c) for c in columns)
        placeholders = pgsql.SQL(", ").join(pgsql.Placeholder() for _ in columns)

        stmt = pgsql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            pgsql.Identifier(schema, table), col_ids, placeholders
        )

        data = [tuple(row) for row in df.itertuples(index=False, name=None)]
        self.execute_many(stmt, data)

    def ensure_unique_index(self, schema: str, table: str, columns_sql: str, index_name: str) -> None:
        """Cria índice único (IF NOT EXISTS). `columns_sql` é SQL controlado (constante)."""
        stmt = pgsql.SQL("CREATE UNIQUE INDEX IF NOT EXISTS {} ON {} ({})").format(
            pgsql.Identifier(index_name),
            pgsql.Identifier(schema, table),
            pgsql.SQL(columns_sql),
        )
        self.execute_non_query(stmt)

    def upsert_dataframe(self, schema: str, table: str, df, conflict_sql: str) -> None:
        """INSERT ... ON CONFLICT <conflict_sql> DO UPDATE. `conflict_sql` é SQL controlado."""
        if df.empty:
            return

        columns = list(df.columns)
        col_ids = pgsql.SQL(", ").join(pgsql.Identifier(c) for c in columns)
        placeholders = pgsql.SQL(", ").join(pgsql.Placeholder() for _ in columns)
        set_clause = pgsql.SQL(", ").join(
            pgsql.SQL("{} = EXCLUDED.{}").format(pgsql.Identifier(c), pgsql.Identifier(c))
            for c in columns
        )

        stmt = pgsql.SQL(
            "INSERT INTO {} ({}) VALUES ({}) ON CONFLICT {} DO UPDATE SET {}"
        ).format(
            pgsql.Identifier(schema, table),
            col_ids,
            placeholders,
            pgsql.SQL(conflict_sql),
            set_clause,
        )

        data = [tuple(row) for row in df.itertuples(index=False, name=None)]
        self.execute_many(stmt, data)