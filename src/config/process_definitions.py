# -*- coding: utf-8 -*-
"""Shim de compatibilidade.

A definição dos processos migrou para `config/processes.yaml` (carregado por
`process_loader`) e `ProcessDefinition` migrou para `src.domain.models`. Este
módulo re-exporta os mesmos símbolos públicos para não quebrar imports
existentes (`from src.config.process_definitions import ...`).
"""
from __future__ import annotations

from typing import List

from src.config.process_loader import load_processos
from src.domain.models import ProcessDefinition

__all__ = [
    "ProcessDefinition",
    "PROCESSOS",
    "get_processos_ativos",
    "get_processo_por_nome",
]

PROCESSOS: List[ProcessDefinition] = load_processos()


def get_processos_ativos() -> List[ProcessDefinition]:
    return [processo for processo in PROCESSOS if processo.ativo]


def get_processo_por_nome(process_name: str) -> ProcessDefinition:
    for processo in PROCESSOS:
        if processo.process_name == process_name:
            return processo
    raise ValueError(f"Processo não encontrado: {process_name}")
