# -*- coding: utf-8 -*-
"""Unitários determinísticos do ResultadoService (normalização e mapeamento de tipos)."""
from __future__ import annotations

import pandas as pd
import pytest

from src.services.resultado_service import ResultadoService


@pytest.fixture
def svc():
    return ResultadoService(postgres=None, default_schema="dev")


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("DOC Compra", "DOC_COMPRA"),
        ("Situação Geral (%)", "SITUACAO_GERAL_PERC"),
        ("Qtde-Líquida/NF", "QTDE_LIQUIDA_NF"),
        ("VALOR", "VALOR"),
        ("Número.Cockpit", "NUMERO_COCKPIT"),
        ("CTR_DESCRIÇÃO_ITEM", "CTR_DESCRICAO_ITEM"),
        ("Endereço\\Caminho", "ENDERECO_CAMINHO"),
    ],
)
def test_normalizar_nome_coluna(svc, entrada, esperado):
    assert svc._normalizar_nome_coluna(entrada) == esperado


def test_mapear_tipo_sql(svc):
    assert svc._mapear_tipo_sql(pd.Series([1, 2, 3])) == "BIGINT"
    assert svc._mapear_tipo_sql(pd.Series([1.0, 2.5])) == "NUMERIC(18,6)"
    assert svc._mapear_tipo_sql(pd.Series([True, False])) == "BOOLEAN"
    assert svc._mapear_tipo_sql(pd.to_datetime(pd.Series(["2026-01-01"]))) == "TIMESTAMP"
    assert svc._mapear_tipo_sql(pd.Series(["a", "b"])) == "TEXT"


def test_preparar_dataframe_normaliza_colunas_e_nulos(svc):
    df = pd.DataFrame([{"DOC Compra": "45", "Situação": None}])
    out = svc.preparar_dataframe_para_banco(df)
    assert list(out.columns) == ["DOC_COMPRA", "SITUACAO"]
    assert out.iloc[0]["SITUACAO"] is None


def test_preparar_dataframe_vazio(svc):
    out = svc.preparar_dataframe_para_banco(pd.DataFrame())
    assert out.empty
