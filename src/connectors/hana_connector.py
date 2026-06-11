from __future__ import annotations

import logging
import time
from typing import Any, Iterable, Optional

from hdbcli import dbapi

from src.config.settings import SapConfig


class HanaConnector:
    def __init__(self, config: SapConfig, logger: Optional[logging.Logger] = None) -> None:
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.connection: Optional[dbapi.Connection] = None

    def connect(self) -> dbapi.Connection:
        if self.connection is not None:
            return self.connection

        self.config.validate()

        self.logger.info(
            "🔌 Conectando no SAP HANA | host=%s | port=%s | db=%s | schema=%s",
            self.config.host,
            self.config.port,
            self.config.database,
            self.config.schema,
        )

        try:
            self.connection = dbapi.connect(
                address=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                databaseName=self.config.database,
            )
            self.logger.info("✅ Conexão SAP estabelecida com databaseName")
        except Exception as exc:
            self.logger.warning(
                "⚠️ Falha ao conectar com databaseName=%s | detalhe=%s",
                self.config.database,
                exc,
            )
            self.logger.info("🔁 Tentando conexão SAP sem databaseName...")

            self.connection = dbapi.connect(
                address=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
            )
            self.logger.info("✅ Conexão SAP estabelecida sem databaseName")

        self._apply_schema()

        self.logger.info(
            "⏳ Aguardando %ss para estabilização da sessão SAP...",
            self.config.connection_delay,
        )
        time.sleep(self.config.connection_delay)

        self.logger.info("🚀 Sessão SAP pronta para execução")
        return self.connection

    def _apply_schema(self) -> None:
        conn = self.connection
        if conn is None:
            raise RuntimeError("Conexão SAP não inicializada para aplicar schema.")

        cursor = conn.cursor()
        try:
            cursor.execute(f'SET SCHEMA "{self.config.schema}"')
            self.logger.info("✅ Schema SAP aplicado: %s", self.config.schema)
        finally:
            cursor.close()

    def get_connection(self) -> dbapi.Connection:
        if self.connection is None:
            return self.connect()
        return self.connection

    def test_connection(self) -> dict[str, Any]:
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            started_at = time.perf_counter()

            cursor.execute(
                """
                SELECT
                    CURRENT_USER,
                    CURRENT_SCHEMA,
                    CURRENT_UTCTIMESTAMP
                FROM DUMMY
                """
            )
            row = cursor.fetchone()
            elapsed = time.perf_counter() - started_at

            result = {
                "current_user": row[0] if row else None,
                "current_schema": row[1] if row else None,
                "current_utctimestamp": str(row[2]) if row else None,
                "elapsed_seconds": round(elapsed, 4),
            }

            self.logger.info(
                "🔎 Validação SAP | user=%s | schema_atual=%s | utc=%s | tempo=%.4fs",
                result["current_user"],
                result["current_schema"],
                result["current_utctimestamp"],
                result["elapsed_seconds"],
            )

            return result

        finally:
            cursor.close()

    def execute_query(
        self,
        sql: str,
        params: Optional[Iterable[Any]] = None,
    ) -> list[dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            started_at = time.perf_counter()

            if params is not None:
                cursor.execute(sql, list(params))
            else:
                cursor.execute(sql)

            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            elapsed = time.perf_counter() - started_at

            result = [dict(zip(columns, row)) for row in rows]

            self.logger.info(
                "✅ Consulta SAP executada | linhas=%s | tempo=%.4fs",
                len(result),
                elapsed,
            )

            return result

        except Exception as exc:
            self.logger.error("❌ Erro ao executar SAP: %s", exc)
            raise

        finally:
            cursor.close()

    def wait_between_queries(self) -> None:
        if self.config.query_delay > 0:
            time.sleep(self.config.query_delay)

    def qualify_sql_with_schema(self, sql: str) -> str:
        return sql.format(schema=self.config.schema, ano=self.config.safra_ano)

    def close(self) -> None:
        if self.connection is not None:
            try:
                self.connection.close()
                self.logger.info("🔌 Conexão SAP encerrada")
            finally:
                self.connection = None