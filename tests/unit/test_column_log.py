# -*- coding: utf-8 -*-
"""Unitários do column_log (particionamento de colunas + join_cols)."""
from __future__ import annotations

import logging

from src.orchestration.column_log import join_cols, log_colunas_formatado


def test_join_cols():
    assert join_cols([]) == "(nenhum)"
    assert join_cols(["a"]) == "a"
    assert join_cols(["a", "b"]) == "a, b"


def test_log_colunas_nao_quebra_com_colunas_variadas(caplog):
    import pandas as pd

    df = pd.DataFrame(columns=[
        "id", "doc_compra", "zmmt_qtde", "ctr_material", "vtin_vlr_nf",
        "docnum", "resultado", "process_name", "coluna_estranha",
    ])
    logger = logging.getLogger("test_collog")
    logger.propagate = True
    with caplog.at_level(logging.INFO, logger="test_collog"):
        log_colunas_formatado(logger, df)

    texto = "\n".join(r.getMessage() for r in caplog.records)
    assert "Total de colunas: 9" in texto
    assert "coluna_estranha" in texto  # cai em "Outros campos"
