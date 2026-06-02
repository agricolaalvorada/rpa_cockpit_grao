from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class ProcessDefinition:
    process_name: str
    postgres_sql: Path
    hana_sql: Path
    parametros: List[str]
    tabela_destino: str
    ativo: bool = True
    truncate_before_insert: bool = False
    drop_and_create: bool = False


BASE_DIR = Path(__file__).resolve().parents[2]

SQL_POSTGRES_DIR = BASE_DIR / "sql" / "postgres" / "consultas"
SQL_SAP_HANA_DIR = BASE_DIR / "sql" / "sap_hana" / "consultas"


PROCESSOS: List[ProcessDefinition] = [
    ProcessDefinition(
        process_name="V2_Consulta_Comp_CTRFIXO",
        postgres_sql=SQL_POSTGRES_DIR / "Consulta_Comp_CTRFIXO.sql",
        hana_sql=SQL_SAP_HANA_DIR / "Consulta_Comp_CTRFIXO.sql",
        parametros=["doc_compra", "numero_cockpit"],
        tabela_destino="tb_resultado_final_hana",
        ativo=True,
        truncate_before_insert=False,
        drop_and_create=False,
    ),
    ProcessDefinition(
        process_name="V2_Consulta_Comp_CTR_S_FIXACAO",
        postgres_sql=SQL_POSTGRES_DIR / "Consulta_Comp_CTR_S_FIXACAO.sql",
        hana_sql=SQL_SAP_HANA_DIR / "Consulta_Comp_CTR_S_FIXACAO.sql",
        parametros=["doc_compra", "numero_cockpit"],
        tabela_destino="tb_resultado_final_hana",
        ativo=True,
        truncate_before_insert=False,
        drop_and_create=False,
    ),
    ProcessDefinition(
        process_name="V2_Consulta_Comp_ARMAZEN",
        postgres_sql=SQL_POSTGRES_DIR / "Consulta_Comp_ARMAZEN.sql",
        hana_sql=SQL_SAP_HANA_DIR / "Consulta_Comp_ARMAZEN.sql",
        parametros=["n_contrato", "numero_cockpit"],
        tabela_destino="tb_resultado_final_hana",
        ativo=True,
        truncate_before_insert=False,
        drop_and_create=False,
    ),
]


def get_processos_ativos() -> List[ProcessDefinition]:
    return [processo for processo in PROCESSOS if processo.ativo]


def get_processo_por_nome(process_name: str) -> ProcessDefinition:
    for processo in PROCESSOS:
        if processo.process_name == process_name:
            return processo
    raise ValueError(f"Processo não encontrado: {process_name}")