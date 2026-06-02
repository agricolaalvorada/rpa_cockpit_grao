from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List

from src.config.process_definitions import get_processos_ativos
from src.config.settings import log_config, postgres_config, sap_config
from src.connectors.hana_connector import HanaConnector
from src.connectors.postgres_connector import PostgresConnector
from src.services.process_runner import ProcessRunner
from src.services.resultado_service import ResultadoService
from src.utils.execution_summary import build_execution_summary, log_execution_summary
from src.utils.logger import setup_logger
from src.utils.paths import build_output_path, get_log_dir
from src.utils.teams_notifier import notify_teams_safe


SEPARADOR = "-" * 80
SEPARADOR_PRINCIPAL = "=" * 80
TARGET_SCHEMAS = ["dev", "prod"]
ENVIRONMENT = "dev"


def _join_cols(cols: List[str]) -> str:
    return ", ".join(cols) if cols else "(nenhum)"


def log_colunas_formatado(logger, df) -> None:
    cols = list(df.columns)

    principais = [
        c for c in cols
        if c in [
            "id",
            "tipo_processo",
            "status",
            "status_complemento_fixo",
            "tipo",
            "n_contrato",
            "doc_compra",
            "centro",
            "safra",
            "material",
            "cod_parceiro",
            "data_hora_ultima_atualizacao",
            "numero_cockpit",
            "msg_rpa",
            "parceiro",
            "local",
            "dt_criacao",
        ]
    ]

    controle = [
        c for c in cols
        if c in [
            "process_name",
            "data_execucao",
            "status_execucao",
            "tempo_execucao",
        ]
    ]

    zmmt = [c for c in cols if c.startswith("zmmt_")]
    ctr = [
        c
        for c in cols
        if c.startswith("ctr_")
        or c in ["bukrs", "ebeln", "konnr", "lifnr", "name", "cpf_cnpj", "ie", "name1_text"]
    ]
    vtin = [c for c in cols if c.startswith("vtin_")]
    nf = [
        c
        for c in cols
        if c in [
            "docnum",
            "peso_liquido",
            "vlr_nf",
            "item",
            "ncm",
            "cfop",
            "dig_ver",
            "num_aleatorio",
            "n_log",
        ]
    ]
    periodo = [c for c in cols if c in ["vtin_ano", "vtin_mes"]]
    quantitativos = [
        c
        for c in cols
        if c in ["zmmt_qtde", "zmmt_valor", "vtin_qtde", "vtin_vlr_nf", "a_vtin_vlr_nf"]
    ]
    resultado = [c for c in cols if c in ["resultado"]]

    colunas_mapeadas = set(
        principais + controle + zmmt + ctr + vtin + nf + periodo + quantitativos + resultado
    )
    outras = [c for c in cols if c not in colunas_mapeadas]

    logger.info(SEPARADOR)
    logger.info("🧱 Preparando carga PostgreSQL")
    logger.info("📊 Total de colunas: %s", len(cols))
    logger.info("🔹 Campos principais: %s", _join_cols(principais))
    logger.info("🔹 Campos de controle: %s", _join_cols(controle))
    logger.info("🔹 Campos SAP ZMMT: %s", _join_cols(zmmt))
    logger.info("🔹 Campos contrato / parceiro: %s", _join_cols(ctr))
    logger.info("🔹 Campos XML / VTIN: %s", _join_cols(vtin))
    logger.info("🔹 Campos NF / item: %s", _join_cols(nf))
    logger.info("🔹 Campos período: %s", _join_cols(periodo))
    logger.info("🔹 Campos quantitativos: %s", _join_cols(quantitativos))
    logger.info("🔹 Campos resultado: %s", _join_cols(resultado))
    logger.info("🔹 Outros campos: %s", _join_cols(outras))
    logger.info(SEPARADOR)


def _get_teams_url() -> str:
    """
    Lê a URL do Power Automate a partir do .env.
    """
    return os.getenv("POWER_AUTOMATE_TEAMS_URL", "").strip()


def _registrar_resultado_processo(
    processos_executados: List[Dict[str, Any]],
    process_name: str,
    status: str,
    rows: int,
    duration_seconds: float,
) -> None:
    processos_executados.append(
        {
            "process_name": process_name,
            "status": status,
            "rows": int(rows or 0),
            "duration_seconds": round(float(duration_seconds or 0), 4),
        }
    )


def main() -> Dict[str, Any]:
    process_name = "SAP_ESCRITURAR_V2"
    logger = setup_logger(process_name, get_log_dir(), level=log_config.level)

    started_at = datetime.now()

    postgres = PostgresConnector(postgres_config, logger=logger)
    hana = HanaConnector(sap_config, logger=logger)

    processos_executados: List[Dict[str, Any]] = []
    processos_com_erro: List[Dict[str, Any]] = []

    teams_url = _get_teams_url()

    try:
        logger.info(SEPARADOR_PRINCIPAL)
        logger.info("🚀 Iniciando execução principal do projeto")
        logger.info("🌍 Ambiente: %s", ENVIRONMENT)
        logger.info("🕒 Início: %s", started_at.isoformat())
        logger.info("🎯 Schemas de destino: %s", ", ".join(TARGET_SCHEMAS))
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

        runner = ProcessRunner(postgres=postgres, hana=hana)
        resultado_service = ResultadoService(
            postgres=postgres,
            default_schema=postgres_config.schema,
        )

        processos = get_processos_ativos()

        if not processos:
            logger.warning("⚠️ Nenhum processo ativo encontrado.")

            finished_at = datetime.now()
            payload = build_execution_summary(
                process_name=process_name,
                environment=ENVIRONMENT,
                target_schemas=TARGET_SCHEMAS,
                started_at=started_at,
                finished_at=finished_at,
                processos_executados=[],
                processos_com_erro=[],
            )

            log_execution_summary(logger, payload)

            if teams_url:
                notify_teams_safe(
                    logger=logger,
                    url=teams_url,
                    execution_summary=payload,
                )

            print(json.dumps(payload, ensure_ascii=False, indent=4))
            return payload

        logger.info("📦 Total de processos ativos: %s", len(processos))
        logger.info(SEPARADOR)

        for idx, processo in enumerate(processos, start=1):
            processo_inicio = datetime.now()

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
                        status="SEM_DADOS",
                        rows=0,
                        duration_seconds=(datetime.now() - processo_inicio).total_seconds(),
                    )
                    continue

                arquivo_excel = build_output_path(
                    processo.process_name,
                    f"{processo.process_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                )

                resultado_service.exportar_excel(df, arquivo_excel)
                logger.info("📁 Excel gerado com sucesso: %s", arquivo_excel)

                df_prepared = resultado_service.preparar_dataframe_para_banco(df)
                log_colunas_formatado(logger, df_prepared)

                for schema_idx, target_schema in enumerate(TARGET_SCHEMAS, start=1):
                    logger.info(SEPARADOR)
                    logger.info(
                        "🗄️ Iniciando carga PostgreSQL [%s/%s] | schema=%s | tabela=%s",
                        schema_idx,
                        len(TARGET_SCHEMAS),
                        target_schema,
                        processo.tabela_destino,
                    )

                    resultado_service.salvar_no_postgres(
                        df=df,
                        table_name=processo.tabela_destino,
                        schema=target_schema,
                        truncate_before_insert=processo.truncate_before_insert,
                        drop_and_create=processo.drop_and_create,
                    )

                    logger.info(
                        "✅ Dados salvos no PostgreSQL | schema=%s | tabela=%s | linhas=%s",
                        target_schema,
                        processo.tabela_destino,
                        len(df_prepared),
                    )
                    logger.info(SEPARADOR)

                _registrar_resultado_processo(
                    processos_executados=processos_executados,
                    process_name=processo.process_name,
                    status="SUCESSO",
                    rows=len(df_prepared),
                    duration_seconds=(datetime.now() - processo_inicio).total_seconds(),
                )

            except Exception as exc_processo:
                duracao_processo = round(
                    (datetime.now() - processo_inicio).total_seconds(),
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
                    status="ERRO",
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

        finished_at = datetime.now()

        payload = build_execution_summary(
            process_name=process_name,
            environment=ENVIRONMENT,
            target_schemas=TARGET_SCHEMAS,
            started_at=started_at,
            finished_at=finished_at,
            processos_executados=processos_executados,
            processos_com_erro=processos_com_erro,
        )

        log_execution_summary(logger, payload)

        if teams_url:
            notify_teams_safe(
                logger=logger,
                url=teams_url,
                execution_summary=payload,
            )

        print(json.dumps(payload, ensure_ascii=False, indent=4))
        return payload

    except Exception as exc:
        finished_at = datetime.now()

        processos_com_erro.append(
            {
                "process_name": process_name,
                "error": str(exc),
                "duration_seconds": round((finished_at - started_at).total_seconds(), 4),
            }
        )

        payload = build_execution_summary(
            process_name=process_name,
            environment=ENVIRONMENT,
            target_schemas=TARGET_SCHEMAS,
            started_at=started_at,
            finished_at=finished_at,
            processos_executados=processos_executados,
            processos_com_erro=processos_com_erro,
        )

        logger.exception("❌ Falha na execução principal: %s", exc)
        log_execution_summary(logger, payload)

        if teams_url:
            notify_teams_safe(
                logger=logger,
                url=teams_url,
                execution_summary=payload,
            )

        print(json.dumps(payload, ensure_ascii=False, indent=4))
        return payload

    finally:
        hana.close()
        postgres.close()


if __name__ == "__main__":
    main()