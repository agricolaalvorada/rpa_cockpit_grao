# -*- coding: utf-8 -*-
"""Enums do domínio. Todos `str, Enum` para serializarem como as MESMAS strings
usadas hoje (DataFrame / JSON / Excel / payload Teams). Use sempre `.value` na
fronteira de serialização.
"""
from __future__ import annotations

from enum import Enum


class StatusProcesso(str, Enum):
    """Status por linha gravado em `status_execucao` pelo ProcessRunner."""

    SUCESSO = "SUCESSO"
    SEM_RETORNO = "SEM_RETORNO"
    ERRO = "ERRO"
    SEM_DADOS = "SEM_DADOS"  # usado pela orquestração quando a fila vem vazia


class StatusExecucaoGlobal(str, Enum):
    """Status final consolidado da execução (execution_summary)."""

    SUCESSO = "SUCESSO"
    PARCIAL = "PARCIAL"
    ERRO = "ERRO"


class SaveStrategy(str, Enum):
    """Rótulo da estratégia de gravação.

    OBS: a precedência reproduz `ResultadoService.salvar_no_postgres` (drop tem
    prioridade sobre truncate). O serviço continua recebendo os dois booleans
    para preservar 100% o comportamento (inclusive o caso ambos=True); este
    enum é um rótulo legível derivado deles.
    """

    APPEND = "APPEND"
    TRUNCATE = "TRUNCATE"
    DROP_CREATE = "DROP_CREATE"

    @classmethod
    def from_flags(cls, drop_and_create: bool, truncate_before_insert: bool) -> "SaveStrategy":
        if drop_and_create:
            return cls.DROP_CREATE
        if truncate_before_insert:
            return cls.TRUNCATE
        return cls.APPEND
