# -*- coding: utf-8 -*-
"""YEAR parametrizado: render_sql_template substitui {ano} nos SQL HANA reais."""
from __future__ import annotations

from src.config.settings import sap_config
from src.connectors.hana_connector import HanaConnector
from src.utils.paths import get_project_root

SQLS = [
    "Consulta_Comp_CTRFIXO.sql",
    "Consulta_Comp_CTR_S_FIXACAO.sql",
    "Consulta_Comp_CTR_C_FIXACAO.sql",
    "Consulta_Comp_ARMAZEN.sql",
]


def test_qualify_substitui_ano_nos_sql_reais():
    hana = HanaConnector(sap_config)  # não conecta
    root = get_project_root() / "sql" / "sap_hana" / "consultas"

    for nome in SQLS:
        sql = (root / nome).read_text(encoding="utf-8")
        assert "IN ({anos})" in sql, f"{nome} deveria conter o placeholder {{anos}}"
        out = hana.render_sql_template(sql)
        assert "{anos}" not in out
        assert "{" not in out and "}" not in out  # nenhuma chave solta
        anos_str = ", ".join(str(a) for a in sap_config.safra_anos)
        assert f"YEAR(vtin_fallback.VTIN_DT_EMISSAO) IN ({anos_str})" in out


def test_qualify_usa_ano_configurado():
    hana = HanaConnector(sap_config)
    hana.config = sap_config.model_copy(update={"safra_anos": (2099,)})
    out = hana.render_sql_template("WHERE YEAR(x) IN ({anos})")
    assert out == "WHERE YEAR(x) IN (2099)"
