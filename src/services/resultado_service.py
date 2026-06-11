from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd

from src.connectors.postgres_connector import PostgresConnector

# Chave natural do resultado (mantém histórico de tentativas: status no fim).
# Deve casar com o índice único criado pela migração (_migra_dedup.py).
UPSERT_KEY_COLS = [
    "process_name", "doc_compra", "n_contrato", "numero_cockpit", "docnum", "status_execucao",
]
UPSERT_INDEX_NAME = "ix_uq_tb_resultado_final_hana"
_UPSERT_KEY_SQL = (
    "process_name, COALESCE(doc_compra,''), COALESCE(n_contrato,''), "
    "COALESCE(numero_cockpit,''), COALESCE(docnum,''), status_execucao"
)
_UPSERT_CONFLICT_SQL = "(%s)" % _UPSERT_KEY_SQL


class ResultadoService:
    def __init__(self, postgres: PostgresConnector, default_schema: str):
        self.postgres = postgres
        self.default_schema = default_schema

    def exportar_excel(self, df: pd.DataFrame, output_file: Path) -> None:
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="RESULTADO")

    def _mapear_tipo_sql(self, serie: pd.Series) -> str:
        if pd.api.types.is_integer_dtype(serie):
            return "BIGINT"

        if pd.api.types.is_float_dtype(serie):
            return "NUMERIC(18,6)"

        if pd.api.types.is_bool_dtype(serie):
            return "BOOLEAN"

        if pd.api.types.is_datetime64_any_dtype(serie):
            return "TIMESTAMP"

        return "TEXT"

    def _normalizar_nome_coluna(self, nome_coluna: str) -> str:
        nome = str(nome_coluna).strip().lower()
        nome = nome.replace(" ", "_")
        nome = nome.replace("-", "_")
        nome = nome.replace("/", "_")
        nome = nome.replace("\\", "_")
        nome = nome.replace(".", "_")
        nome = nome.replace("(", "")
        nome = nome.replace(")", "")
        nome = nome.replace("%", "perc")
        nome = nome.replace("ç", "c")
        nome = nome.replace("ã", "a")
        nome = nome.replace("á", "a")
        nome = nome.replace("à", "a")
        nome = nome.replace("â", "a")
        nome = nome.replace("é", "e")
        nome = nome.replace("ê", "e")
        nome = nome.replace("í", "i")
        nome = nome.replace("ó", "o")
        nome = nome.replace("ô", "o")
        nome = nome.replace("õ", "o")
        nome = nome.replace("ú", "u")
        nome = nome.replace("ü", "u")
        return nome

    def preparar_dataframe_para_banco(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df.copy()

        novo_df = df.copy()
        novo_df.columns = [self._normalizar_nome_coluna(col) for col in novo_df.columns]
        novo_df = novo_df.where(pd.notnull(novo_df), None)

        return novo_df

    def garantir_tabela(self, df: pd.DataFrame, table_name: str, schema: str | None = None) -> None:
        schema_name = schema or self.default_schema
        prepared_df = self.preparar_dataframe_para_banco(df)

        if prepared_df.empty:
            return

        columns_def: Dict[str, str] = {
            col: self._mapear_tipo_sql(prepared_df[col])
            for col in prepared_df.columns
        }

        if not self.postgres.table_exists(schema_name, table_name):
            self.postgres.create_table(schema_name, table_name, columns_def)
            return

        existing_columns = set(self.postgres.get_table_columns(schema_name, table_name))

        for col_name, col_type in columns_def.items():
            if col_name not in existing_columns:
                self.postgres.add_column(schema_name, table_name, col_name, col_type)

    def salvar_no_postgres(
        self,
        df: pd.DataFrame,
        table_name: str,
        schema: str | None = None,
        truncate_before_insert: bool = False,
        drop_and_create: bool = False,
    ) -> None:
        schema_name = schema or self.default_schema
        prepared_df = self.preparar_dataframe_para_banco(df)

        if prepared_df.empty:
            return

        if drop_and_create:
            self.postgres.drop_table_if_exists(schema_name, table_name)

        self.garantir_tabela(prepared_df, table_name, schema_name)

        if truncate_before_insert and self.postgres.table_exists(schema_name, table_name):
            self.postgres.truncate_table(schema_name, table_name)

        # garante a chave única e faz UPSERT (em vez de INSERT append-only) para
        # não duplicar a tabela a cada ciclo, preservando o histórico de tentativas.
        self._garantir_chave_unica(table_name, schema_name)
        self.postgres.upsert_dataframe(
            schema_name, table_name, prepared_df, _UPSERT_CONFLICT_SQL
        )

    def _garantir_chave_unica(self, table_name: str, schema_name: str) -> None:
        existing = set(self.postgres.get_table_columns(schema_name, table_name))
        for col in UPSERT_KEY_COLS:
            if col not in existing:
                self.postgres.add_column(schema_name, table_name, col, "TEXT")
        self.postgres.ensure_unique_index(
            schema_name, table_name, _UPSERT_KEY_SQL, UPSERT_INDEX_NAME
        )