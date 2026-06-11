# -*- coding: utf-8 -*-
"""Golden do ResultadoService: trava a sequência de chamadas ao Postgres (com UPSERT)."""
from __future__ import annotations

import pandas as pd

from src.services.resultado_service import ResultadoService
from tests.fakes import FakePostgresConnector
from tests.golden_utils import assert_golden

TABELA = "tb_resultado_final_hana"
# colunas da chave única já presentes (cenário realista de resultado consolidado)
COLS_BASE = ["process_name", "doc_compra", "n_contrato", "numero_cockpit", "docnum",
             "status_execucao", "valor"]


def _df():
    return pd.DataFrame([
        {"process_name": "V2_X", "doc_compra": "4500451189", "n_contrato": "",
         "numero_cockpit": "123490", "docnum": "3038001", "status_execucao": "SUCESSO", "valor": 19205},
        {"process_name": "V2_X", "doc_compra": "4500725349", "n_contrato": "",
         "numero_cockpit": "122253", "docnum": None, "status_execucao": "SEM_RETORNO", "valor": None},
    ])


def test_salvar_tabela_inexistente_cria_indexa_e_upserta():
    pg = FakePostgresConnector()  # nenhuma tabela existe
    ResultadoService(pg, default_schema="dev").salvar_no_postgres(_df(), TABELA, schema="dev")
    assert_golden("resultado__cria_indexa_upsert", pg.calls)


def test_salvar_tabela_existente_upsert():
    pg = FakePostgresConnector(
        existing_tables={("dev", TABELA)},
        table_columns={("dev", TABELA): COLS_BASE},
    )
    ResultadoService(pg, default_schema="dev").salvar_no_postgres(_df(), TABELA, schema="dev")
    assert_golden("resultado__existente_upsert", pg.calls)


def test_salvar_com_truncate():
    pg = FakePostgresConnector(
        existing_tables={("dev", TABELA)},
        table_columns={("dev", TABELA): COLS_BASE},
    )
    ResultadoService(pg, default_schema="dev").salvar_no_postgres(
        _df(), TABELA, schema="dev", truncate_before_insert=True
    )
    assert_golden("resultado__truncate_upsert", pg.calls)


def test_salvar_com_drop_and_create():
    pg = FakePostgresConnector(existing_tables={("dev", TABELA)})
    ResultadoService(pg, default_schema="dev").salvar_no_postgres(
        _df(), TABELA, schema="dev", drop_and_create=True
    )
    assert_golden("resultado__drop_create_upsert", pg.calls)


def test_salvar_df_vazio_nao_faz_nada():
    pg = FakePostgresConnector()
    ResultadoService(pg, default_schema="dev").salvar_no_postgres(pd.DataFrame(), TABELA, schema="dev")
    assert pg.calls == []


def test_garantir_chave_unica_adiciona_colunas_faltantes():
    # tabela existe mas só com doc_compra -> as demais colunas-chave devem ser criadas
    pg = FakePostgresConnector(
        existing_tables={("dev", TABELA)},
        table_columns={("dev", TABELA): ["doc_compra"]},
    )
    ResultadoService(pg, default_schema="dev").salvar_no_postgres(_df(), TABELA, schema="dev")
    add_cols = [c[3] for c in pg.calls if c[0] == "add_column"]
    # process_name, n_contrato, numero_cockpit, docnum, status_execucao (faltavam)
    assert "status_execucao" in add_cols and "docnum" in add_cols
    assert "doc_compra" not in add_cols  # já existia
    assert any(c[0] == "ensure_unique_index" for c in pg.calls)
    assert any(c[0] == "upsert_dataframe" for c in pg.calls)
