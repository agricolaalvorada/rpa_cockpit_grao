# -*- coding: utf-8 -*-
"""Conectores fake com a MESMA API pública dos reais, para os testes golden.

- FakeHanaConnector: resolve execute_query(sql, params) por `params` a partir de
  um mapa de respostas (lista de dicts, lista vazia, ou Exception a levantar).
- FakePostgresConnector: devolve a fila e registra TODAS as chamadas (leitura e
  DDL/DML) em self.calls, sem tocar em banco.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def _df_snapshot(df) -> dict:
    return {
        "columns": [str(c) for c in df.columns],
        "records": json.loads(df.to_json(orient="records", date_format="iso")),
    }


class FakeHanaConnector:
    def __init__(self, responses: Dict[tuple, Any], schema: str = "SAPABAP1", safra_ano: int = 2026):
        self.responses = responses
        self.schema = schema
        self.safra_ano = safra_ano
        self.queries: List[tuple] = []  # (sql, params_key)

    def render_sql_template(self, sql: str) -> str:
        return sql.format(schema=self.schema, ano=self.safra_ano)

    def execute_query(self, sql: str, params: Optional[Any] = None) -> List[Dict[str, Any]]:
        key = tuple(params) if params is not None else None
        self.queries.append((sql, key))
        resp = self.responses.get(key)
        if isinstance(resp, BaseException):
            raise resp
        return list(resp) if resp is not None else []

    def wait_between_queries(self) -> None:
        pass

    def test_connection(self) -> dict:
        return {"current_user": "FAKE", "current_schema": self.schema}

    def connect(self):
        return None

    def close(self) -> None:
        pass


class FakePostgresConnector:
    def __init__(
        self,
        fila_rows: Optional[List[Dict[str, Any]]] = None,
        existing_tables: Optional[set] = None,
        table_columns: Optional[Dict[tuple, List[str]]] = None,
    ):
        self.fila_rows = fila_rows or []
        self.existing_tables = set(existing_tables or set())
        self.table_columns = dict(table_columns or {})
        self.calls: List[list] = []

    # --- leitura ---
    def test_connection(self) -> dict:
        return {
            "current_user": "FAKE",
            "current_database": "fake_db",
            "current_schema": "public",
            "current_timestamp": "2026-01-01T12:00:00",
            "elapsed_seconds": 0.0,
        }

    def execute_query(self, sql: str, params: Optional[Any] = None) -> List[Dict[str, Any]]:
        # O ProcessRunner chama uma vez (a fila). ResultadoService não usa este método.
        return list(self.fila_rows)

    def table_exists(self, schema: str, table: str) -> bool:
        exists = (schema, table) in self.existing_tables
        self.calls.append(["table_exists", schema, table, exists])
        return exists

    def get_table_columns(self, schema: str, table: str) -> List[str]:
        cols = list(self.table_columns.get((schema, table), []))
        self.calls.append(["get_table_columns", schema, table, cols])
        return cols

    # --- DDL/DML (capturadas, não executadas) ---
    def create_schema_if_not_exists(self, schema: str) -> None:
        self.calls.append(["create_schema_if_not_exists", schema])

    def drop_table_if_exists(self, schema: str, table: str) -> None:
        self.calls.append(["drop_table_if_exists", schema, table])
        self.existing_tables.discard((schema, table))

    def truncate_table(self, schema: str, table: str) -> None:
        self.calls.append(["truncate_table", schema, table])

    def create_table(self, schema: str, table: str, columns: Dict[str, str]) -> None:
        self.calls.append(["create_table", schema, table, dict(columns)])
        self.existing_tables.add((schema, table))
        self.table_columns[(schema, table)] = list(columns.keys())

    def add_column(self, schema: str, table: str, column: str, dtype: str) -> None:
        self.calls.append(["add_column", schema, table, column, dtype])
        self.table_columns.setdefault((schema, table), []).append(column)

    def insert_dataframe(self, schema: str, table: str, df) -> None:
        self.calls.append(["insert_dataframe", schema, table, _df_snapshot(df)])

    def ensure_unique_index(self, schema: str, table: str, columns_sql: str, index_name: str) -> None:
        self.calls.append(["ensure_unique_index", schema, table, index_name])

    def upsert_dataframe(self, schema: str, table: str, df, conflict_sql: str) -> None:
        self.calls.append(["upsert_dataframe", schema, table, _df_snapshot(df), conflict_sql])

    def connect(self):
        return None

    def close(self) -> None:
        pass
