# -*- coding: utf-8 -*-
"""Golden do ProcessRunner: trava o DataFrame consolidado e a sequência de chamadas HANA."""
from __future__ import annotations

from src.services.process_runner import ProcessRunner
from tests.fakes import FakeHanaConnector, FakePostgresConnector
from tests.fixtures.sample_data import FILA_ROWS, HANA_RESPONSES
from tests.golden_utils import assert_golden, df_to_golden


def test_runner_consolidado_golden(ctrfixo_process, frozen_now):
    pg = FakePostgresConnector(fila_rows=FILA_ROWS)
    hana = FakeHanaConnector(HANA_RESPONSES)

    df = ProcessRunner(pg, hana).run(ctrfixo_process)

    assert_golden("process_runner__ctrfixo_consolidado", df_to_golden(df))


def test_runner_chama_hana_por_linha(ctrfixo_process, frozen_now):
    pg = FakePostgresConnector(fila_rows=FILA_ROWS)
    hana = FakeHanaConnector(HANA_RESPONSES)

    ProcessRunner(pg, hana).run(ctrfixo_process)

    params_chamados = [k for _, k in hana.queries]
    assert params_chamados == [
        ("4500451189", "123490"),
        ("4500725349", "122253"),
        ("4500756534", "123492"),
        ("9999999999", "000000"),
    ]


def test_runner_fila_vazia_retorna_df_vazio(ctrfixo_process, frozen_now):
    pg = FakePostgresConnector(fila_rows=[])
    hana = FakeHanaConnector(HANA_RESPONSES)

    df = ProcessRunner(pg, hana).run(ctrfixo_process)

    assert df.empty
    assert list(df.columns) == []
