# -*- coding: utf-8 -*-
"""Golden da orquestração (Application): payload, ordem dev->prod e DataFrame CRU no save."""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from src.config.process_definitions import ProcessDefinition
from src.orchestration.application import Application
from tests.fakes import FakeHanaConnector, FakePostgresConnector
from tests.golden_utils import assert_golden


class _FakeRunner:
    """Devolve um DataFrame fixo (colunas UPPERCASE como o HANA), sem tocar em banco."""

    def __init__(self, df):
        self.df = df
        self.chamado_com = []

    def run(self, processo):
        self.chamado_com.append(processo.process_name)
        return self.df.copy()


class _RecordingResultado:
    def __init__(self):
        self.calls = []

    def exportar_excel(self, df, output_file):
        self.calls.append(["exportar_excel", list(df.columns)])

    def preparar_dataframe_para_banco(self, df):
        self.calls.append(["preparar", list(df.columns)])
        return df  # mantém colunas (o golden checa que o save recebe o df CRU)

    def salvar_no_postgres(self, df, table_name, schema, truncate_before_insert, drop_and_create, predefined_columns=None):
        self.calls.append([
            "salvar", schema, table_name, list(df.columns),
            truncate_before_insert, drop_and_create,
        ])


def _quiet_logger():
    lg = logging.getLogger("test_app")
    if not lg.handlers:
        lg.addHandler(logging.NullHandler())
    lg.propagate = False
    return lg


def _processo(tmp_path):
    pg = tmp_path / "f.sql"; pg.write_text("SELECT 1", encoding="utf-8")
    hn = tmp_path / "h.sql"; hn.write_text("SELECT 1", encoding="utf-8")
    return ProcessDefinition(
        process_name="V2_Consulta_Comp_CTRFIXO",
        postgres_sql=pg, hana_sql=hn,
        parametros=["doc_compra", "numero_cockpit"],
        tabela_destino="complemento_notas_escrituracao",
    )


def _app(tmp_path, runner, rec):
    fixed = datetime(2026, 1, 1, 12, 0, 0)
    return Application(
        postgres=FakePostgresConnector(),
        hana=FakeHanaConnector({}),
        processos=[_processo(tmp_path)],
        runner=runner,
        resultado_service=rec,
        teams_url="",          # vazio -> não dispara Teams
        clock=lambda: fixed,   # determinístico
        logger=_quiet_logger(),
    )


def test_application_sucesso_golden(tmp_path):
    df = pd.DataFrame([
        {"doc_compra": "4500451189", "DOCNUM": "", "VTIN_QTDE": 7682.0,
         "status_execucao": "SUCESSO"},
    ])
    runner = _FakeRunner(df)
    rec = _RecordingResultado()

    payload = _app(tmp_path, runner, rec).run()

    assert_golden("application__sucesso_payload", payload)
    assert_golden("application__sucesso_calls", rec.calls)


def test_application_ordem_dev_prod_e_df_cru(tmp_path):
    df = pd.DataFrame([{"doc_compra": "X", "DOCNUM": "1", "status_execucao": "SUCESSO"}])
    rec = _RecordingResultado()

    _app(tmp_path, _FakeRunner(df), rec).run()

    saves = [c for c in rec.calls if c[0] == "salvar"]
    assert [c[1] for c in saves] == ["dev", "prod"]
    # df CRU: colunas UPPERCASE preservadas (não normalizadas)
    assert saves[0][3] == ["doc_compra", "DOCNUM", "status_execucao"]


def test_application_sem_dados(tmp_path):
    rec = _RecordingResultado()
    app = _app(tmp_path, _FakeRunner(pd.DataFrame()), rec)

    payload = app.run()

    assert rec.calls == []  # nada salvo
    assert payload["summary"]["processos_sem_dados"] == 1
    assert payload["status"] == "SUCESSO"
