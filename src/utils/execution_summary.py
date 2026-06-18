from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from src.domain.enums import StatusExecucaoGlobal, StatusProcesso


SEPARADOR = "-" * 5
SEPARADOR_PRINCIPAL = "=" * 5


def format_duration(seconds: float) -> str:
    """
    Converte segundos para HH:MM:SS.
    """
    total_seconds = int(round(float(seconds or 0)))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def build_execution_summary(
    *,
    process_name: str,
    environment: str,
    target_schemas: List[str],
    started_at: datetime,
    finished_at: datetime,
    processos_executados: List[Dict[str, Any]],
    processos_com_erro: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Monta o payload final consolidado da execução.
    """

    duration_seconds = round((finished_at - started_at).total_seconds(), 4)

    total_processos = len(processos_executados)

    processos_sucesso = sum(
        1
        for proc in processos_executados
        if str(proc.get("status", "")).upper() == StatusProcesso.SUCESSO.value
    )

    processos_sem_dados = sum(
        1
        for proc in processos_executados
        if str(proc.get("status", "")).upper() == StatusProcesso.SEM_DADOS.value
    )

    processos_erro = len(processos_com_erro)

    total_linhas_processadas = sum(
        int(proc.get("rows", 0) or 0)
        for proc in processos_executados
    )

    total_notas_aptas = sum(
        int(proc.get("rows_aptas", 0) or 0)
        for proc in processos_executados
    )

    total_notas_pendentes = sum(
        int(proc.get("rows_pendentes", 0) or 0)
        for proc in processos_executados
    )

    processos_formatados: List[Dict[str, Any]] = []
    for proc in processos_executados:
        proc_duration = round(float(proc.get("duration_seconds", 0) or 0), 4)

        processos_formatados.append(
            {
                "process_name": proc.get("process_name"),
                "status": proc.get("status"),
                "rows_processed": int(proc.get("rows", 0) or 0),
                "rows_aptas": int(proc.get("rows_aptas", 0) or 0),
                "rows_pendentes": int(proc.get("rows_pendentes", 0) or 0),
                "duration_seconds": proc_duration,
                "duration_formatted": format_duration(proc_duration),
            }
        )

    if total_processos == 0 and processos_erro == 0:
        status_final = StatusExecucaoGlobal.PARCIAL.value
        message = "Nenhum processo ativo encontrado para executar."
    elif processos_erro == 0:
        status_final = StatusExecucaoGlobal.SUCESSO.value
        message = "Execução finalizada com sucesso."
    elif processos_sucesso > 0 or processos_sem_dados > 0:
        status_final = StatusExecucaoGlobal.PARCIAL.value
        message = "Execução finalizada com falhas parciais."
    else:
        status_final = StatusExecucaoGlobal.ERRO.value
        message = "Execução finalizada com erro."

    return {
        "success": processos_erro == 0 and total_processos > 0,
        "status": status_final,
        "message": message,
        "process_name": process_name,
        "environment": environment,
        "target_schemas": target_schemas,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": duration_seconds,
        "duration_formatted": format_duration(duration_seconds),
        "summary": {
            "total_processos": total_processos,
            "processos_sucesso": processos_sucesso,
            "processos_sem_dados": processos_sem_dados,
            "processos_erro": processos_erro,
            "total_linhas_processadas": total_linhas_processadas,
            "total_notas_aptas": total_notas_aptas,
            "total_notas_pendentes": total_notas_pendentes,
        },
        "processos_executados": processos_formatados,
        "processos_com_erro": processos_com_erro,
    }


def log_execution_summary(logger: logging.Logger, execution_summary: Dict[str, Any]) -> None:
    """
    Escreve no logger um resumo final elegante da execução.
    """
    summary = execution_summary["summary"]
    processes = execution_summary["processos_executados"]
    errors = execution_summary["processos_com_erro"]

    logger.info(SEPARADOR_PRINCIPAL)
    logger.info(
        "🏁 EXECUÇÃO FINALIZADA | status=%s | aplicacao=%s",
        execution_summary["status"],
        execution_summary["process_name"],
    )
    logger.info(SEPARADOR_PRINCIPAL)

    logger.info("🌍 Ambiente...............: %s", execution_summary["environment"])
    logger.info(
        "🎯 Schemas destino........: %s",
        ", ".join(execution_summary["target_schemas"]),
    )
    logger.info("🕒 Início.................: %s", execution_summary["started_at"])
    logger.info("🕓 Fim....................: %s", execution_summary["finished_at"])
    logger.info(
        "⏱️ Duração total..........: %.4fs (%s)",
        execution_summary["duration_seconds"],
        execution_summary["duration_formatted"],
    )
    logger.info("📦 Total de processos.....: %s", summary["total_processos"])
    logger.info("✅ Processos com sucesso..: %s", summary["processos_sucesso"])
    logger.info("⚠️ Processos sem dados....: %s", summary["processos_sem_dados"])
    logger.info("❌ Processos com erro.....: %s", summary["processos_erro"])
    logger.info("📊 Total de linhas........: %s", summary["total_linhas_processadas"])

    if processes:
        logger.info(SEPARADOR)
        logger.info("📋 DETALHE DOS PROCESSOS")
        logger.info(SEPARADOR)

        for proc in processes:
            logger.info("🔹 Processo...............: %s", proc["process_name"])
            logger.info("🔹 Status.................: %s", proc["status"])
            logger.info("🔹 Linhas processadas.....: %s", proc["rows_processed"])
            logger.info(
                "🔹 Duração................: %.4fs (%s)",
                proc["duration_seconds"],
                proc["duration_formatted"],
            )
            logger.info(SEPARADOR)

    if errors:
        logger.info("🧨 DETALHE DOS ERROS")
        logger.info(SEPARADOR)

        for err in errors:
            logger.error("%s", json.dumps(err, ensure_ascii=False))

        logger.info(SEPARADOR)

    logger.info(SEPARADOR_PRINCIPAL)