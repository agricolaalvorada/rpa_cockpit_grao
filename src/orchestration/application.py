# -*- coding: utf-8 -*-
"""Orquestração da execução (extraída do main.py).

`Application.run()` reproduz EXATAMENTE a sequência e os efeitos do antigo
`main()`: testa conexões, itera os processos ativos, exporta Excel, grava nos
schemas dev+prod (DataFrame CRU), monta o payload, loga, notifica Teams e
imprime/retorna o payload. As dependências são injetáveis (para testes); sem
injeção, o comportamento é idêntico ao de produção.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence

import pandas as pd

from src.config.ddl_complemento import COMPLEMENTO_NOTAS_DDL
from src.config.process_definitions import get_processos_ativos
from src.config.settings import aa_config, log_config, postgres_config, sap_config
from src.connectors.automation_anywhere_connector import AutomationAnywhereConnector
from src.domain.enums import StatusProcesso
from src.connectors.hana_connector import HanaConnector
from src.connectors.postgres_connector import PostgresConnector
from src.orchestration.column_log import log_colunas_formatado
from src.services.process_runner import ProcessRunner
from src.services.resultado_service import ResultadoService
from src.utils.execution_summary import build_execution_summary, log_execution_summary
from src.utils.logger import setup_logger
from src.utils.paths import build_output_path, get_log_dir
from src.utils.teams_notifier import notify_teams_safe

SEPARADOR = "-" * 80
SEPARADOR_PRINCIPAL = "=" * 80


def _aa_guard_check(logger: Any, file_ids: List[int]) -> bool:
    """Verifica se algum bot de escrituração está ativo no Control Room.

    Retorna True se algum está rodando (ciclo deve ser abortado).
    Retorna False se todos estão livres (pode prosseguir).
    Erros de conexão ao AA são logados mas NÃO abortam o ciclo.
    """
    if not file_ids or not aa_config.run_as_user_ids:
        return False
    aa = None
    try:
        aa = AutomationAnywhereConnector(aa_config, logger=logger)
        aa.connect()
        bot_ocupado = aa.any_bot_running(file_ids)
        if bot_ocupado:
            logger.warning(
                "⏸️ AA: bot de escrituração em andamento (fileId=%s) — ciclo adiado para próxima execução",
                bot_ocupado,
            )
            return True
        logger.info("✅ AA: nenhum bot de escrituração em andamento — prosseguindo")
        return False
    except Exception as exc:
        logger.warning("⚠️ AA: falha ao verificar status dos bots (%s) — prosseguindo normalmente", exc)
        return False
    finally:
        if aa is not None:
            try:
                aa.close()
            except Exception:
                pass


def _schedule_aa_safe(
    logger: Any,
    file_id: int,
    runner_ids: List[int],
    delay_minutes: int = 3,
) -> Optional[int]:
    """Agenda o bot AA daqui `delay_minutes` minutos no primeiro runner livre.
    Retorna o runner_id usado, ou None se não agendou. Nunca levanta exceção."""
    aa = None
    try:
        aa = AutomationAnywhereConnector(aa_config, logger=logger)
        aa.connect()

        runner_id = aa.pick_runner(runner_ids)
        if runner_id is None:
            logger.warning("⚠️ AA: todos os runners estão ocupados — agendamento ignorado | fileId=%s", file_id)
            return None

        schedule_id = aa.schedule_bot(
            file_id=file_id,
            run_as_user_id=runner_id,
            delay_minutes=delay_minutes,
        )
        logger.info(
            "📅 AA: agendamento criado | fileId=%s | runner=%s | scheduleId=%s | em +%smin",
            file_id, runner_id, schedule_id, delay_minutes,
        )
        return runner_id
    except Exception as exc:
        logger.warning("⚠️ AA: falha ao agendar bot fileId=%s: %s", file_id, exc)
        return None
    finally:
        if aa is not None:
            try:
                aa.close()
            except Exception:
                pass


def _registrar_resultado_processo(
    processos_executados: List[Dict[str, Any]],
    process_name: str,
    status: str,
    rows: int,
    duration_seconds: float,
    rows_aptas: int = 0,
    rows_pendentes: int = 0,
    aa_runner_id: Optional[int] = None,
) -> None:
    processos_executados.append(
        {
            "process_name": process_name,
            "status": status,
            "rows": int(rows or 0),
            "rows_aptas": int(rows_aptas or 0),
            "rows_pendentes": int(rows_pendentes or 0),
            "duration_seconds": round(float(duration_seconds or 0), 4),
            "aa_runner_id": aa_runner_id,
        }
    )


class Application:
    def __init__(
        self,
        *,
        process_name: str = "SAP_ESCRITURAR_V2",
        environment: str = "dev",
        target_schemas: Optional[Sequence[str]] = None,
        postgres: Any = None,
        hana: Any = None,
        processos: Any = None,
        runner: Any = None,
        resultado_service: Any = None,
        teams_url: Optional[str] = None,
        clock: Callable[[], datetime] = datetime.now,
        logger: Any = None,
    ) -> None:
        self.process_name = process_name
        self.environment = environment
        self.target_schemas: List[str] = (
            list(target_schemas) if target_schemas is not None else ["dev", "prod"]
        )
        self._postgres = postgres
        self._hana = hana
        self._processos = processos
        self._runner = runner
        self._resultado_service = resultado_service
        self._teams_url = teams_url
        self._clock = clock
        self._logger = logger

    def _now(self) -> datetime:
        return self._clock()

    def _resolve_teams_url(self) -> str:
        if self._teams_url is not None:
            return self._teams_url
        if not _get_env_bool("TEAMS_NOTIFY", True):
            return ""
        return os.getenv("POWER_AUTOMATE_TEAMS_URL", "").strip()

    def run(self) -> Dict[str, Any]:
        process_name = self.process_name
        logger = self._logger or setup_logger(process_name, get_log_dir(), level=log_config.level, save_file=log_config.save_file)

        started_at = self._now()

        postgres = self._postgres or PostgresConnector(postgres_config, logger=logger)
        hana = self._hana or HanaConnector(sap_config, logger=logger)

        processos_executados: List[Dict[str, Any]] = []
        processos_com_erro: List[Dict[str, Any]] = []

        teams_url = self._resolve_teams_url()
        target_schemas = self.target_schemas
        environment = self.environment

        try:
            logger.info(SEPARADOR_PRINCIPAL)
            logger.info("🚀 Iniciando execução principal do projeto")
            logger.info("🌍 Ambiente: %s", environment)
            logger.info("🕒 Início: %s", started_at.isoformat())
            logger.info("🎯 Schemas de destino: %s", ", ".join(target_schemas))
            logger.info("📣 Envio Teams habilitado: %s", "SIM" if teams_url else "NÃO")
            logger.info(SEPARADOR_PRINCIPAL)

            teste_sap = hana.test_connection()
            logger.info(
                "✅ Teste inicial SAP OK | user=%s | schema=%s | utc=%s | tempo=%.4fs",
                teste_sap.get("current_user"),
                teste_sap.get("current_schema"),
                teste_sap.get("current_utctimestamp"),
                teste_sap.get("elapsed_seconds", 0),
            )

            teste_postgres = postgres.test_connection()
            logger.info(
                "✅ Teste inicial PostgreSQL OK | user=%s | db=%s | schema=%s | ts=%s | tempo=%.4fs",
                teste_postgres.get("current_user"),
                teste_postgres.get("current_database"),
                teste_postgres.get("current_schema"),
                teste_postgres.get("current_timestamp"),
                teste_postgres.get("elapsed_seconds", 0),
            )

            runner = self._runner or ProcessRunner(postgres=postgres, hana=hana)
            resultado_service = self._resultado_service or ResultadoService(
                postgres=postgres,
                default_schema=postgres_config.schema,
            )

            processos = (
                self._processos if self._processos is not None else get_processos_ativos()
            )

            if not processos:
                logger.warning("⚠️ Nenhum processo ativo encontrado.")

                finished_at = self._now()
                payload = build_execution_summary(
                    process_name=process_name,
                    environment=environment,
                    target_schemas=target_schemas,
                    started_at=started_at,
                    finished_at=finished_at,
                    processos_executados=[],
                    processos_com_erro=[],
                )

                log_execution_summary(logger, payload)

                print(json.dumps(payload, ensure_ascii=False, indent=4))
                return payload

            logger.info("📦 Total de processos ativos: %s", len(processos))

            # Guard AA: se algum bot de escrituração estiver rodando, abortar o ciclo inteiro.
            # Não truncar, não consultar — aguardar a próxima execução agendada pelo Windows.
            # Ignorado quando AA_CALL_RPA=false.
            aa_file_ids = [p.aa_file_id for p in processos if p.aa_file_id]
            if aa_config.call_rpa and _aa_guard_check(logger=logger, file_ids=aa_file_ids):
                finished_at = self._now()
                payload = build_execution_summary(
                    process_name=process_name,
                    environment=environment,
                    target_schemas=target_schemas,
                    started_at=started_at,
                    finished_at=finished_at,
                    processos_executados=[],
                    processos_com_erro=[],
                )
                log_execution_summary(logger, payload)
                print(json.dumps(payload, ensure_ascii=False, indent=4))
                return payload

            tabelas_destino = {p.tabela_destino for p in processos}
            for schema in target_schemas:
                for tabela in tabelas_destino:
                    if postgres.table_exists(schema, tabela):
                        logger.info("🗑️ Limpando tabela antes da execução | schema=%s | tabela=%s", schema, tabela)
                        postgres.truncate_table(schema, tabela)

            logger.info(SEPARADOR)

            for idx, processo in enumerate(processos, start=1):
                processo_inicio = self._now()

                try:
                    logger.info(SEPARADOR)
                    logger.info(
                        "▶️ Executando processo [%s/%s]: %s",
                        idx,
                        len(processos),
                        processo.process_name,
                    )
                    logger.info("📄 SQL PostgreSQL: %s", processo.postgres_sql)
                    logger.info("📄 SQL SAP: %s", processo.hana_sql)
                    logger.info("🎯 Tabela destino: %s", processo.tabela_destino)
                    logger.info(SEPARADOR)

                    df = runner.run(processo)

                    if df.empty:
                        logger.warning(
                            "⚠️ Processo sem dados para exportar/salvar: %s",
                            processo.process_name,
                        )

                        _registrar_resultado_processo(
                            processos_executados=processos_executados,
                            process_name=processo.process_name,
                            status=StatusProcesso.SEM_DADOS.value,
                            rows=0,
                            duration_seconds=(self._now() - processo_inicio).total_seconds(),
                        )
                        continue

                    arquivo_excel = build_output_path(
                        processo.process_name,
                        f"{processo.process_name}_{self._now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    )

                    resultado_service.exportar_excel(df, arquivo_excel)
                    logger.info("📁 Excel gerado com sucesso: %s", arquivo_excel)

                    df_prepared = resultado_service.preparar_dataframe_para_banco(df)
                    log_colunas_formatado(logger, df_prepared)

                    _docnum_col = next(
                        (c for c in df.columns if c.upper() == "DOCNUM"), None
                    )
                    df_aptas = (
                        df[df[_docnum_col].isna() | (df[_docnum_col].astype(str).str.strip() == "")]
                        if _docnum_col is not None
                        else pd.DataFrame()
                    )

                    aa_runner_id: Optional[int] = None

                    if df_aptas.empty:
                        logger.info(
                            "ℹ️ Nenhuma nota apta para escrituração | processo=%s",
                            processo.process_name,
                        )

                    # Sempre garante o schema da tabela (mesmo sem aptas) e insere se houver.
                    for schema_idx, target_schema in enumerate(target_schemas, start=1):
                        logger.info(SEPARADOR)
                        logger.info(
                            "🗄️ Garantindo schema PostgreSQL [%s/%s] | schema=%s | tabela=%s | aptas=%s",
                            schema_idx,
                            len(target_schemas),
                            target_schema,
                            processo.tabela_destino,
                            len(df_aptas),
                        )

                        resultado_service.salvar_no_postgres(
                            df=df_aptas,
                            table_name=processo.tabela_destino,
                            schema=target_schema,
                            truncate_before_insert=processo.truncate_before_insert,
                            drop_and_create=processo.drop_and_create,
                            predefined_columns=COMPLEMENTO_NOTAS_DDL,
                        )

                        if not df_aptas.empty:
                            logger.info(
                                "✅ Dados salvos no PostgreSQL | schema=%s | tabela=%s | linhas=%s",
                                target_schema,
                                processo.tabela_destino,
                                len(df_aptas),
                            )
                        logger.info(SEPARADOR)

                    # Agendamento AA — uma vez por processo, após salvar em todos os schemas.
                    # Ignorado quando AA_CALL_RPA=false.
                    if aa_config.call_rpa and not df_aptas.empty and processo.aa_file_id and aa_config.run_as_user_ids:
                        aa_runner_id = _schedule_aa_safe(
                            logger=logger,
                            file_id=processo.aa_file_id,
                            runner_ids=list(aa_config.run_as_user_ids),
                            delay_minutes=3,
                        )
                    elif not aa_config.call_rpa and not df_aptas.empty and processo.aa_file_id:
                        logger.info(
                            "⏭️ AA: agendamento desabilitado (AA_CALL_RPA=false) | processo=%s | aptas=%s",
                            processo.process_name, len(df_aptas),
                        )

                    rows_aptas = len(df_aptas)
                    _status_col_name = next(
                        (c for c in df.columns if c.upper() == "STATUS_EXECUCAO"), None
                    )
                    rows_pendentes = (
                        int((df[_status_col_name] == StatusProcesso.SEM_RETORNO.value).sum())
                        if _status_col_name is not None else 0
                    )

                    _registrar_resultado_processo(
                        processos_executados=processos_executados,
                        process_name=processo.process_name,
                        status=StatusProcesso.SUCESSO.value,
                        rows=len(df_prepared),
                        duration_seconds=(self._now() - processo_inicio).total_seconds(),
                        rows_aptas=rows_aptas,
                        rows_pendentes=rows_pendentes,
                        aa_runner_id=aa_runner_id,
                    )

                except Exception as exc_processo:
                    duracao_processo = round(
                        (self._now() - processo_inicio).total_seconds(),
                        4,
                    )

                    logger.exception(
                        "❌ Falha no processo %s: %s",
                        processo.process_name,
                        exc_processo,
                    )
                    logger.info(SEPARADOR)

                    _registrar_resultado_processo(
                        processos_executados=processos_executados,
                        process_name=processo.process_name,
                        status=StatusProcesso.ERRO.value,
                        rows=0,
                        duration_seconds=duracao_processo,
                    )

                    processos_com_erro.append(
                        {
                            "process_name": processo.process_name,
                            "error": str(exc_processo),
                            "duration_seconds": duracao_processo,
                        }
                    )

                    continue

            finished_at = self._now()

            payload = build_execution_summary(
                process_name=process_name,
                environment=environment,
                target_schemas=target_schemas,
                started_at=started_at,
                finished_at=finished_at,
                processos_executados=processos_executados,
                processos_com_erro=processos_com_erro,
            )

            log_execution_summary(logger, payload)

            total_aptas = payload.get("summary", {}).get("total_notas_aptas", 0)
            if teams_url and total_aptas > 0:
                notify_teams_safe(logger=logger, url=teams_url, execution_summary=payload)
            elif teams_url and total_aptas == 0:
                logger.info("⏭️ Teams: sem notas aptas neste ciclo — notificação suprimida")

            print(json.dumps(payload, ensure_ascii=False, indent=4))
            return payload

        except Exception as exc:
            finished_at = self._now()

            processos_com_erro.append(
                {
                    "process_name": process_name,
                    "error": str(exc),
                    "duration_seconds": round((finished_at - started_at).total_seconds(), 4),
                }
            )

            payload = build_execution_summary(
                process_name=process_name,
                environment=environment,
                target_schemas=target_schemas,
                started_at=started_at,
                finished_at=finished_at,
                processos_executados=processos_executados,
                processos_com_erro=processos_com_erro,
            )

            logger.exception("❌ Falha na execução principal: %s", exc)
            log_execution_summary(logger, payload)

            total_aptas = payload.get("summary", {}).get("total_notas_aptas", 0)
            if teams_url and total_aptas > 0:
                notify_teams_safe(logger=logger, url=teams_url, execution_summary=payload)

            print(json.dumps(payload, ensure_ascii=False, indent=4))
            return payload

        finally:
            hana.close()
            postgres.close()
