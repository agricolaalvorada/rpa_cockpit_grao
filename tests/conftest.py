# -*- coding: utf-8 -*-
"""Fixtures compartilhadas dos testes."""
from __future__ import annotations

import logging
from datetime import datetime

import pytest


@pytest.fixture(autouse=True)
def _quiet_runner_logger(monkeypatch):
    """Silencia o setup_logger do ProcessRunner (evita criar arquivos de log).

    Não afeta o DataFrame retornado — apenas o logging lateral.
    """
    import src.services.process_runner as pr

    lg = logging.getLogger("test_quiet_runner")
    if not lg.handlers:
        lg.addHandler(logging.NullHandler())
    lg.propagate = False
    monkeypatch.setattr(pr, "setup_logger", lambda *a, **k: lg)


@pytest.fixture
def frozen_now(monkeypatch):
    """Congela datetime.now() dentro do ProcessRunner para golden determinístico."""
    import src.services.process_runner as pr

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D401
            return datetime(2026, 1, 1, 12, 0, 0)

    monkeypatch.setattr(pr, "datetime", _Frozen)


@pytest.fixture
def ctrfixo_process(tmp_path):
    """ProcessDefinition de teste (CTRFIXO) com arquivos SQL temporários."""
    from src.config.process_definitions import ProcessDefinition

    pg_sql = tmp_path / "fila.sql"
    pg_sql.write_text("SELECT 1", encoding="utf-8")
    hana_sql = tmp_path / "hana.sql"
    hana_sql.write_text("SELECT 1 FROM DUMMY", encoding="utf-8")

    return ProcessDefinition(
        process_name="V2_Consulta_Comp_CTRFIXO",
        postgres_sql=pg_sql,
        hana_sql=hana_sql,
        parametros=["doc_compra", "numero_cockpit"],
        tabela_destino="tb_resultado_final_hana",
    )
