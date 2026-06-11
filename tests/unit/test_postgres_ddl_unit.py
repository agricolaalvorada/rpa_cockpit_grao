# -*- coding: utf-8 -*-
"""Unitários do SQL de DDL/DML gerado pelo PostgresConnector (sem tocar em banco).

Trava o formato atual (f-string com identificadores entre aspas) — referência
para a Fase 2 (migração para psycopg.sql.Identifier) não passar despercebida.
"""
from __future__ import annotations

import pandas as pd

from src.config.settings import postgres_config
from src.connectors.postgres_connector import PostgresConnector


def _render(obj):
    """Renderiza o SQL (psycopg.sql.Composed) para string para inspeção no teste."""
    return obj if isinstance(obj, str) else obj.as_string(None)


def _connector():
    pg = PostgresConnector(postgres_config)
    capturado = {"non_query": [], "many": []}
    pg.execute_non_query = lambda sql, params=None: capturado["non_query"].append(_render(sql))
    pg.execute_many = lambda sql, data: capturado["many"].append((_render(sql), data))
    return pg, capturado


def test_create_table_gera_schema_e_tabela():
    pg, cap = _connector()
    pg.create_table("dev", "tb_x", {"a": "BIGINT", "b": "TEXT"})
    assert 'CREATE SCHEMA IF NOT EXISTS "dev"' in cap["non_query"][0]
    create_sql = cap["non_query"][1]
    assert 'CREATE TABLE IF NOT EXISTS "dev"."tb_x"' in create_sql
    assert '"a" BIGINT' in create_sql
    assert '"b" TEXT' in create_sql


def test_add_column_idempotente():
    pg, cap = _connector()
    pg.add_column("dev", "tb_x", "nova", "TEXT")
    assert 'ALTER TABLE "dev"."tb_x"' in cap["non_query"][0]
    assert 'ADD COLUMN IF NOT EXISTS "nova" TEXT' in cap["non_query"][0]


def test_truncate_e_drop():
    pg, cap = _connector()
    pg.truncate_table("dev", "tb_x")
    pg.drop_table_if_exists("dev", "tb_x")
    assert cap["non_query"][0] == 'TRUNCATE TABLE "dev"."tb_x"'
    assert cap["non_query"][1] == 'DROP TABLE IF EXISTS "dev"."tb_x"'


def test_insert_dataframe_monta_insert_parametrizado():
    pg, cap = _connector()
    df = pd.DataFrame([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}])
    pg.insert_dataframe("dev", "tb_x", df)
    sql, data = cap["many"][0]
    assert 'INSERT INTO "dev"."tb_x" ("a", "b")' in sql
    assert "VALUES (%s, %s)" in sql
    assert data == [(1, "x"), (2, "y")]


def test_insert_dataframe_vazio_nao_executa():
    pg, cap = _connector()
    pg.insert_dataframe("dev", "tb_x", pd.DataFrame())
    assert cap["many"] == []


def test_ensure_unique_index_sql():
    pg, cap = _connector()
    pg.ensure_unique_index("dev", "tb_x", "process_name, COALESCE(docnum,'')", "ix_uq")
    sql = cap["non_query"][0]
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS "ix_uq" ON "dev"."tb_x"' in sql
    assert "(process_name, COALESCE(docnum,''))" in sql


def test_upsert_dataframe_monta_on_conflict():
    pg, cap = _connector()
    df = pd.DataFrame([{"process_name": "P", "docnum": "1", "valor": 10}])
    pg.upsert_dataframe("dev", "tb_x", df, "(process_name, COALESCE(docnum,''))")
    sql, data = cap["many"][0]
    assert 'INSERT INTO "dev"."tb_x" ("process_name", "docnum", "valor")' in sql
    assert "ON CONFLICT (process_name, COALESCE(docnum,'')) DO UPDATE SET" in sql
    assert '"valor" = EXCLUDED."valor"' in sql
    assert data == [("P", "1", 10)]
