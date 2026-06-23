# -*- coding: utf-8 -*-
"""Unitários de paths — guarda o risco do parents[2] (raiz do projeto)."""
from __future__ import annotations

from src.utils import paths


def test_project_root_aponta_para_raiz():
    root = paths.get_project_root()
    assert (root / "main.py").exists()
    assert (root / "src").is_dir()
    assert (root / "sql").is_dir()


def test_build_output_path():
    p = paths.build_output_path("V2_X", "arq.xlsx")
    assert p.name == "arq.xlsx"
    assert p.parent.name == "V2_X"
    assert "output" in p.parts
