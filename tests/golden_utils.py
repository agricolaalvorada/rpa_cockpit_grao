# -*- coding: utf-8 -*-
"""Utilitários para testes golden (snapshot) de caracterização.

assert_golden compara `actual` (serializável em JSON) contra um snapshot em
tests/fixtures/golden/snapshots/<name>.json. Na primeira execução o snapshot é
criado a partir do comportamento ATUAL (baseline); nas execuções seguintes a
igualdade é exigida — qualquer mudança de comportamento quebra o teste.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

SNAP_DIR = Path(__file__).resolve().parent / "fixtures" / "golden" / "snapshots"


def df_to_golden(df: pd.DataFrame) -> dict:
    """Representação determinística de um DataFrame: colunas (ordem), dtypes e registros."""
    return {
        "columns": [str(c) for c in df.columns],
        "dtypes": [str(t) for t in df.dtypes],
        "records": json.loads(df.to_json(orient="records", date_format="iso")),
    }


def _to_jsonable(obj: Any) -> Any:
    return json.loads(json.dumps(obj, ensure_ascii=False, default=str))


def assert_golden(name: str, actual: Any) -> None:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAP_DIR / f"{name}.json"
    normalized = _to_jsonable(actual)

    if not path.exists():
        path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return  # baseline criado nesta execução

    expected = json.loads(path.read_text(encoding="utf-8"))
    assert normalized == expected, (
        f"Golden divergente para '{name}'.\n"
        f"Esperado: {json.dumps(expected, ensure_ascii=False)[:800]}\n"
        f"Obtido:   {json.dumps(normalized, ensure_ascii=False)[:800]}"
    )
