# -*- coding: utf-8 -*-
"""Settings em Pydantic — preserva API (from_env, atributos, validate, defaults, globais)."""
from __future__ import annotations

import pytest


def test_globais_existem():
    from src.config.settings import log_config, postgres_config, sap_config

    assert hasattr(sap_config, "host")
    assert hasattr(sap_config, "validate")
    assert isinstance(postgres_config.port, int)
    assert log_config.level


def test_sapconfig_from_env(monkeypatch):
    monkeypatch.setenv("SAP_HOST", "h")
    monkeypatch.setenv("SAP_PORT", "30015")
    monkeypatch.setenv("SAP_DATABASE", "ECP")
    monkeypatch.setenv("SAP_SCHEMA", "SAPABAP1")
    monkeypatch.setenv("SAP_USER", "u")
    monkeypatch.setenv("SAP_PASSWORD", "p")

    from src.config.settings import SapConfig

    c = SapConfig.from_env()
    assert (c.host, c.port, c.database, c.schema, c.user, c.password) == (
        "h", 30015, "ECP", "SAPABAP1", "u", "p",
    )
    assert c.connection_delay == 1.0
    assert c.query_delay == 0.5
    c.validate()  # não levanta


def test_sapconfig_validate_lista_faltantes():
    from src.config.settings import SapConfig

    c = SapConfig(host="", port=0, database="", schema="", user="", password="")
    with pytest.raises(ValueError) as exc:
        c.validate()
    assert "SAP_HOST" in str(exc.value)
    assert "SAP_PASSWORD" in str(exc.value)


def test_postgres_defaults(monkeypatch):
    monkeypatch.delenv("POSTGRES_PORT", raising=False)
    monkeypatch.delenv("POSTGRES_SCHEMA", raising=False)
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")

    from src.config.settings import PostgresConfig

    c = PostgresConfig.from_env()
    assert c.port == 5432
    assert c.schema == "public"


def test_safra_ano_default_e_override(monkeypatch):
    from datetime import date

    from src.config.settings import SapConfig

    monkeypatch.delenv("SAFRA_ANO", raising=False)
    assert SapConfig.from_env().safra_ano == date.today().year

    monkeypatch.setenv("SAFRA_ANO", "2027")
    assert SapConfig.from_env().safra_ano == 2027


def test_config_imutavel():
    from src.config.settings import SapConfig

    c = SapConfig(host="h", port=1, database="d", schema="s", user="u", password="p")
    with pytest.raises(Exception):
        c.host = "outro"
