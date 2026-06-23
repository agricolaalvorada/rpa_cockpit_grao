# -*- coding: utf-8 -*-
"""Carrega os processos a partir de config/processes.yaml -> List[ProcessDefinition].

Substitui a lista Python hardcoded; a ordem do arquivo é preservada.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import yaml

from src.domain.models import ProcessDefinition
from src.utils.paths import get_project_root


def default_yaml_path() -> Path:
    return get_project_root() / "config" / "processes.yaml"


def default_sql_root() -> Path:
    return get_project_root() / "sql"


def load_processos(
    yaml_path: Optional[Path] = None,
    sql_root: Optional[Path] = None,
) -> List[ProcessDefinition]:
    yaml_path = Path(yaml_path) if yaml_path else default_yaml_path()
    sql_root = Path(sql_root) if sql_root else default_sql_root()

    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}

    processos: List[ProcessDefinition] = []
    for item in data.get("processos", []):
        processos.append(
            ProcessDefinition(
                process_name=item["process_name"],
                postgres_sql=(sql_root / item["postgres_sql"]).resolve(),
                hana_sql=(sql_root / item["hana_sql"]).resolve(),
                parametros=list(item["parametros"]),
                tabela_destino=item["tabela_destino"],
                ativo=item.get("ativo", True),
                truncate_before_insert=item.get("truncate_before_insert", False),
                drop_and_create=item.get("drop_and_create", False),
                aa_file_id=item.get("aa_file_id"),
            )
        )
    return processos
