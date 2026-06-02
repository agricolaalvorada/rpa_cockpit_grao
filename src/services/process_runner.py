from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from src.config.process_definitions import ProcessDefinition
from src.connectors.hana_connector import HanaConnector
from src.connectors.postgres_connector import PostgresConnector
from src.utils.logger import setup_logger
from src.utils.paths import get_log_dir

SEPARADOR = "-" * 149


class ProcessRunner:
    def __init__(
        self,
        postgres: PostgresConnector,
        hana: HanaConnector,
    ):
        self.postgres = postgres
        self.hana = hana

    def _read_sql_file(self, path: Path) -> str:
        if not path.exists():
            raise FileNotFoundError(
                f"Arquivo SQL não encontrado:\n{path}\n\n"
                f"Verifique o caminho configurado no process_definitions.py"
            )

        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def run(self, process: ProcessDefinition) -> pd.DataFrame:
        logger = setup_logger(process.process_name, get_log_dir())

        logger.info(SEPARADOR)
        logger.info("🚀 Iniciando processo: %s", process.process_name)
        logger.info("📄 SQL PostgreSQL: %s", process.postgres_sql)
        logger.info("📄 SQL SAP HANA: %s", process.hana_sql)
        logger.info("🎯 Tabela destino: %s", process.tabela_destino)
        logger.info(SEPARADOR)

        logger.info("🔎 Validando existência dos arquivos SQL...")
        logger.info(
            "📁 PostgreSQL exists=%s | %s",
            process.postgres_sql.exists(),
            process.postgres_sql,
        )
        logger.info(
            "📁 SAP exists=%s | %s",
            process.hana_sql.exists(),
            process.hana_sql,
        )

        logger.info("🔎 Lendo dados do PostgreSQL...")
        sql_postgres = self._read_sql_file(process.postgres_sql)
        rows = self.postgres.execute_query(sql_postgres)

        if not rows:
            logger.warning("⚠️ Nenhum registro encontrado na fila.")
            logger.info(SEPARADOR)
            return pd.DataFrame()

        logger.info("📦 Registros encontrados: %s", len(rows))

        resultado_final: List[Dict[str, Any]] = []

        sql_hana = self._read_sql_file(process.hana_sql)
        sql_hana = self.hana.qualify_sql_with_schema(sql_hana)

        for idx, row in enumerate(rows, start=1):
            try:
                params = tuple(row[p] for p in process.parametros)

                logger.info(SEPARADOR)
                logger.info(
                    "🔎 Executando SAP [%s/%s] | %s",
                    idx,
                    len(rows),
                    " | ".join([f"{p}={row[p]}" for p in process.parametros]),
                )

                inicio = datetime.now()
                hana_result = self.hana.execute_query(sql_hana, params)
                duracao = (datetime.now() - inicio).total_seconds()

                if hana_result:
                    for h in hana_result:
                        merged = {
                            **row,
                            **h,
                            "process_name": process.process_name,
                            "data_execucao": datetime.now(),
                            "status_execucao": "SUCESSO",
                            "tempo_execucao": duracao,
                        }
                        resultado_final.append(merged)

                    logger.info(
                        "✅ Retorno encontrado | linhas=%s | tempo=%.4fs",
                        len(hana_result),
                        duracao,
                    )
                else:
                    merged = {
                        **row,
                        "process_name": process.process_name,
                        "data_execucao": datetime.now(),
                        "status_execucao": "SEM_RETORNO",
                        "tempo_execucao": duracao,
                    }
                    resultado_final.append(merged)

                    logger.info(
                        "ℹ️ Sem retorno | linhas=0 | tempo=%.4fs",
                        duracao,
                    )

                logger.info(SEPARADOR)
                self.hana.wait_between_queries()

            except Exception as e:
                logger.error("❌ Erro ao executar SAP: %s", e)

                merged = {
                    **row,
                    "process_name": process.process_name,
                    "data_execucao": datetime.now(),
                    "status_execucao": "ERRO",
                    "mensagem_erro": str(e),
                }
                resultado_final.append(merged)

                logger.info(SEPARADOR)

        df = pd.DataFrame(resultado_final)

        logger.info(SEPARADOR)
        logger.info("🏁 Processo finalizado: %s", process.process_name)
        logger.info("📊 Total de linhas consolidadas: %s", len(df))
        logger.info(SEPARADOR)

        return df