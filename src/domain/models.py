# -*- coding: utf-8 -*-
"""Modelos do domínio (Pydantic)."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from src.domain.enums import SaveStrategy


class ProcessDefinition(BaseModel):
    """Definição de um processo de escrituração.

    Campos idênticos à dataclass original (compatibilidade de construção por
    keyword args). `frozen=True` reproduz a imutabilidade do `@dataclass(frozen=True)`.
    """

    model_config = ConfigDict(frozen=True)

    process_name: str
    postgres_sql: Path
    hana_sql: Path
    parametros: List[str]
    tabela_destino: str
    ativo: bool = True
    truncate_before_insert: bool = False
    drop_and_create: bool = False
    aa_file_id: Optional[int] = None

    @property
    def save_strategy(self) -> SaveStrategy:
        return SaveStrategy.from_flags(self.drop_and_create, self.truncate_before_insert)
