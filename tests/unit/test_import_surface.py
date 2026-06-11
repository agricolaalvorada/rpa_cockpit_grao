# -*- coding: utf-8 -*-
"""Superfície de import pública — guarda os caminhos usados pelos scripts _*.py e pela memória.

Se a reestruturação quebrar qualquer um destes imports/atributos, este teste falha.
"""
from __future__ import annotations


def test_settings_globais_e_atributos():
    from src.config.settings import postgres_config, sap_config, log_config

    for attr in ("host", "port", "database", "schema", "user", "password",
                 "connection_delay", "query_delay"):
        assert hasattr(sap_config, attr), f"sap_config faltando {attr}"
    assert hasattr(sap_config, "validate")

    for attr in ("host", "port", "database", "user", "password", "schema"):
        assert hasattr(postgres_config, attr), f"postgres_config faltando {attr}"
    assert hasattr(postgres_config, "validate")

    assert hasattr(log_config, "level")


def test_connectors_construtor_e_metodos():
    from src.config.settings import postgres_config, sap_config
    from src.connectors.postgres_connector import PostgresConnector
    from src.connectors.hana_connector import HanaConnector

    pg = PostgresConnector(postgres_config)  # 1 arg posicional (como nos scripts)
    hana = HanaConnector(sap_config)
    for obj in (pg, hana):
        assert hasattr(obj, "connect")
        assert hasattr(obj, "execute_query")
        assert hasattr(obj, "close")


def test_process_definitions_api():
    from src.config.process_definitions import (
        ProcessDefinition,
        get_processos_ativos,
        get_processo_por_nome,
    )

    ativos = get_processos_ativos()
    assert len(ativos) >= 1
    assert all(isinstance(p.process_name, str) for p in ativos)
    nome = ativos[0].process_name
    assert get_processo_por_nome(nome).process_name == nome
