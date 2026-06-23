# -*- coding: utf-8 -*-
"""Unitários do logger (sanitização de nome + idempotência do setup)."""
from __future__ import annotations

from src.utils.logger import _sanitize_file_name, setup_logger


def test_sanitize_file_name():
    assert _sanitize_file_name("a/b:c*") == "a_b_c_"
    assert _sanitize_file_name("  nome com espaco ") == "nome_com_espaco"
    assert _sanitize_file_name("") == "processo"


def test_setup_logger_idempotente(tmp_path):
    lg1 = setup_logger("teste_idem", tmp_path)
    n = len(lg1.handlers)
    lg2 = setup_logger("teste_idem", tmp_path)
    assert lg1 is lg2
    assert len(lg2.handlers) == n  # não duplica handlers a cada chamada
