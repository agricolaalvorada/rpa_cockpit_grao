# -*- coding: utf-8 -*-
"""Garante que o YAML reproduz exatamente as 3 definições originais (migração 1:1)."""
from __future__ import annotations

from src.config.process_definitions import PROCESSOS, get_processos_ativos
from src.config.process_loader import load_processos

ESPERADO = [
    ("V2_Consulta_Comp_CTRFIXO", ["doc_compra", "numero_cockpit"]),
    ("V2_Consulta_Comp_CTR_S_FIXACAO", ["doc_compra", "numero_cockpit"]),
    ("V2_Consulta_Comp_ARMAZEN", ["n_contrato", "numero_cockpit"]),
]


def test_ordem_nomes_e_parametros():
    procs = load_processos()
    assert [(p.process_name, p.parametros) for p in procs] == ESPERADO


def test_flags_e_tabela_destino():
    for p in load_processos():
        assert p.tabela_destino == "tb_resultado_final_hana"
        assert p.ativo is True
        assert p.truncate_before_insert is False
        assert p.drop_and_create is False


def test_paths_resolvem_para_arquivos_existentes():
    for p in load_processos():
        assert p.postgres_sql.exists(), p.postgres_sql
        assert p.hana_sql.exists(), p.hana_sql
        assert p.postgres_sql.name.startswith("Consulta_Comp_")
        assert "postgres" in p.postgres_sql.parts
        assert "sap_hana" in p.hana_sql.parts


def test_shim_reexporta_api():
    assert len(PROCESSOS) == 3
    assert len(get_processos_ativos()) == 3
