from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Dict, Optional, Set

import pandas as pd

from src.connectors.postgres_connector import PostgresConnector

# Chave natural do resultado.
# Deve casar com o índice único criado pela migração (_migra_dedup.py).
UPSERT_KEY_COLS = [
    "PROCESS_NAME", "DOC_COMPRA", "N_CONTRATO", "NUMERO_COCKPIT", "DOCNUM", "STATUS_EXECUCAO",
]
UPSERT_INDEX_NAME = "ix_uq_complemento_notas_escrituracao"
_UPSERT_KEY_SQL = (
    '"PROCESS_NAME", COALESCE("DOC_COMPRA",\'\'), COALESCE("N_CONTRATO",\'\'), '
    'COALESCE("NUMERO_COCKPIT",\'\'), COALESCE("DOCNUM",\'\'), "STATUS_EXECUCAO"'
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
        nome = str(nome_coluna).strip().upper()
        nome = unicodedata.normalize("NFD", nome).encode("ascii", "ignore").decode("ascii")
        nome = nome.replace(" ", "_")
        nome = nome.replace("-", "_")
        nome = nome.replace("/", "_")
        nome = nome.replace("\\", "_")
        nome = nome.replace(".", "_")
        nome = nome.replace("(", "")
        nome = nome.replace(")", "")
        nome = nome.replace("%", "PERC")
        return nome

    def preparar_dataframe_para_banco(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df.copy()

        novo_df = df.copy()
        novo_df.columns = [self._normalizar_nome_coluna(col) for col in novo_df.columns]
        novo_df = novo_df.where(pd.notnull(novo_df), None)

        return novo_df

    def garantir_tabela(
        self,
        df: pd.DataFrame,
        table_name: str,
        schema: str | None = None,
        predefined_columns: Optional[Dict[str, str]] = None,
    ) -> Set[str]:
        schema_name = schema or self.default_schema

        if predefined_columns is not None:
            if not self.postgres.table_exists(schema_name, table_name):
                self.postgres.create_table(schema_name, table_name, predefined_columns)
                return set(predefined_columns.keys())

            existing_columns = set(self.postgres.get_table_columns(schema_name, table_name))
            for col_name, col_type in predefined_columns.items():
                if col_name not in existing_columns:
                    self.postgres.add_column(schema_name, table_name, col_name, col_type)
                    existing_columns.add(col_name)
            return existing_columns

        # Schema dinâmico (comportamento original)
        prepared_df = self.preparar_dataframe_para_banco(df)

        if prepared_df.empty:
            return set()

        columns_def: Dict[str, str] = {
            col: self._mapear_tipo_sql(prepared_df[col])
            for col in prepared_df.columns
        }

        if not self.postgres.table_exists(schema_name, table_name):
            self.postgres.create_table(schema_name, table_name, columns_def)
            return set(columns_def.keys())

        existing_columns = set(self.postgres.get_table_columns(schema_name, table_name))

        for col_name, col_type in columns_def.items():
            if col_name not in existing_columns:
                self.postgres.add_column(schema_name, table_name, col_name, col_type)
                existing_columns.add(col_name)

        return existing_columns

    def salvar_no_postgres(
        self,
        df: pd.DataFrame,
        table_name: str,
        schema: str | None = None,
        truncate_before_insert: bool = False,
        drop_and_create: bool = False,
        predefined_columns: Optional[Dict[str, str]] = None,
    ) -> None:
        schema_name = schema or self.default_schema
        prepared_df = self.preparar_dataframe_para_banco(df)

        if drop_and_create:
            self.postgres.drop_table_if_exists(schema_name, table_name)

        if predefined_columns is not None:
            # DDL fixo: garante schema mesmo com df vazio
            existing_cols = self.garantir_tabela(df, table_name, schema_name, predefined_columns)
        elif prepared_df.empty:
            return
        else:
            existing_cols = self.garantir_tabela(df, table_name, schema_name)

        if prepared_df.empty:
            return

        if truncate_before_insert and self.postgres.table_exists(schema_name, table_name):
            self.postgres.truncate_table(schema_name, table_name)

        self._garantir_chave_unica(table_name, schema_name, existing_cols)
        self.postgres.upsert_dataframe(
            schema_name, table_name, prepared_df, _UPSERT_CONFLICT_SQL
        )

    def _garantir_chave_unica(self, table_name: str, schema_name: str, existing_cols: Optional[Set[str]] = None) -> None:
        existing = existing_cols if existing_cols is not None else set(self.postgres.get_table_columns(schema_name, table_name))
        for col in UPSERT_KEY_COLS:
            if col not in existing:
                self.postgres.add_column(schema_name, table_name, col, "TEXT")
        self.postgres.ensure_unique_index(
            schema_name, table_name, _UPSERT_KEY_SQL, UPSERT_INDEX_NAME
        )
