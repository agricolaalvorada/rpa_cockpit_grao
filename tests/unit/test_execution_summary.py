# -*- coding: utf-8 -*-
"""Unitários de execution_summary (format_duration + build_execution_summary)."""
from __future__ import annotations

from datetime import datetime

from src.utils.execution_summary import build_execution_summary, format_duration


def test_format_duration():
    assert format_duration(0) == "00:00:00"
    assert format_duration(59) == "00:00:59"
    assert format_duration(61) == "00:01:01"
    assert format_duration(3661) == "01:01:01"
    assert format_duration(None) == "00:00:00"


def _args(executados, com_erro):
    return dict(
        process_name="SAP_ESCRITURAR_V2",
        environment="dev",
        target_schemas=["dev", "prod"],
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        finished_at=datetime(2026, 1, 1, 12, 0, 30),
        processos_executados=executados,
        processos_com_erro=com_erro,
    )


def test_summary_sucesso():
    s = build_execution_summary(**_args(
        [{"process_name": "P1", "status": "SUCESSO", "rows": 10, "duration_seconds": 5}],
        [],
    ))
    assert s["status"] == "SUCESSO"
    assert s["success"] is True
    assert s["summary"]["processos_sucesso"] == 1
    assert s["summary"]["total_linhas_processadas"] == 10
    assert s["duration_seconds"] == 30.0


def test_summary_parcial():
    s = build_execution_summary(**_args(
        [{"process_name": "P1", "status": "SUCESSO", "rows": 3, "duration_seconds": 1}],
        [{"process_name": "P2", "erro": "boom"}],
    ))
    assert s["status"] == "PARCIAL"
    assert s["success"] is False
    assert s["summary"]["processos_erro"] == 1


def test_summary_erro_total():
    s = build_execution_summary(**_args(
        [],
        [{"process_name": "P1", "erro": "boom"}],
    ))
    assert s["status"] == "ERRO"
    assert s["success"] is False


def test_summary_sem_dados_conta_como_parcial():
    s = build_execution_summary(**_args(
        [{"process_name": "P1", "status": "SEM_DADOS", "rows": 0, "duration_seconds": 0}],
        [{"process_name": "P2", "erro": "x"}],
    ))
    assert s["status"] == "PARCIAL"
    assert s["summary"]["processos_sem_dados"] == 1
