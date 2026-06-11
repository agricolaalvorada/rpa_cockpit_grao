# -*- coding: utf-8 -*-
"""Unitários da camada de domínio (enums + models)."""
from __future__ import annotations

import json

from src.domain.enums import SaveStrategy, StatusExecucaoGlobal, StatusProcesso


def test_status_serializa_como_string():
    assert StatusProcesso.SUCESSO == "SUCESSO"
    assert StatusProcesso.SEM_RETORNO.value == "SEM_RETORNO"
    assert json.dumps(StatusProcesso.ERRO) == '"ERRO"'
    assert StatusExecucaoGlobal.PARCIAL.value == "PARCIAL"


def test_save_strategy_from_flags_precedencia():
    assert SaveStrategy.from_flags(False, False) is SaveStrategy.APPEND
    assert SaveStrategy.from_flags(False, True) is SaveStrategy.TRUNCATE
    assert SaveStrategy.from_flags(True, False) is SaveStrategy.DROP_CREATE
    # drop tem prioridade sobre truncate
    assert SaveStrategy.from_flags(True, True) is SaveStrategy.DROP_CREATE


def test_process_definition_pydantic(tmp_path):
    from src.domain.models import ProcessDefinition

    p = ProcessDefinition(
        process_name="X",
        postgres_sql=tmp_path / "a.sql",
        hana_sql=tmp_path / "b.sql",
        parametros=["doc_compra", "numero_cockpit"],
        tabela_destino="tb",
    )
    assert p.ativo is True
    assert p.truncate_before_insert is False
    assert p.save_strategy is SaveStrategy.APPEND
    assert p.parametros == ["doc_compra", "numero_cockpit"]
