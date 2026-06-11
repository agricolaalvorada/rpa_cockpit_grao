# -*- coding: utf-8 -*-
"""YEAR parametrizado: qualify_sql_with_schema substitui {ano} nos SQL HANA reais."""
from __future__ import annotations

from src.config.settings import sap_config
from src.connectors.hana_connector import HanaConnector
from src.utils.paths import get_project_root

SQLS = [
    "Consulta_Comp_CTRFIXO.sql",
    "Consulta_Comp_CTR_S_FIXACAO.sql",
    "Consulta_Comp_ARMAZEN.sql",
]


def test_qualify_substitui_ano_nos_sql_reais():
    hana = HanaConnector(sap_config)  # não conecta
    root = get_project_root() / "sql" / "sap_hana" / "consultas"

    for nome in SQLS:
        sql = (root / nome).read_text(encoding="utf-8")
        assert "= {ano}" in sql, f"{nome} deveria conter o placeholder {{ano}}"
        out = hana.qualify_sql_with_schema(sql)
        assert "{ano}" not in out
        assert "{" not in out and "}" not in out  # nenhuma chave solta
        assert f"YEAR(vtin2.VTIN_DT_CRIACAO) = {sap_config.safra_ano}" in out


def test_qualify_usa_ano_configurado():
    hana = HanaConnector(sap_config)
    hana.config = sap_config.model_copy(update={"safra_ano": 2099})
    out = hana.qualify_sql_with_schema("WHERE YEAR(x) = {ano}")
    assert out == "WHERE YEAR(x) = 2099"
