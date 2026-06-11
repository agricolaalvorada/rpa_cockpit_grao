# -*- coding: utf-8 -*-
"""Dados sintéticos determinísticos para os golden tests.

Cobrem os 4 ramos do ProcessRunner: sucesso 1 linha, vazio (SEM_RETORNO),
sucesso N linhas, e exceção (ERRO).
"""
from __future__ import annotations

PARAMETROS = ["doc_compra", "numero_cockpit"]

FILA_ROWS = [
    {"id": 1, "tipo_processo": "COM_CTR_FIXO", "status": "12",
     "doc_compra": "4500451189", "numero_cockpit": "123490", "centro": "0001"},
    {"id": 2, "tipo_processo": "COM_CTR_FIXO", "status": "12",
     "doc_compra": "4500725349", "numero_cockpit": "122253", "centro": "0001"},
    {"id": 3, "tipo_processo": "COM_CTR_FIXO", "status": "13",
     "doc_compra": "4500756534", "numero_cockpit": "123492", "centro": "0002"},
    {"id": 4, "tipo_processo": "COM_CTR_FIXO", "status": "12",
     "doc_compra": "9999999999", "numero_cockpit": "000000", "centro": "0003"},
]

HANA_RESPONSES = {
    # sucesso, 1 linha
    ("4500451189", "123490"): [
        {"DOCNUM": "3038001", "PARCEIRO": "PROD A", "VTIN_QTDE": 7682.0, "VTIN_VLR_NF": 19205.0},
    ],
    # vazio -> SEM_RETORNO
    ("4500725349", "122253"): [],
    # sucesso, N linhas
    ("4500756534", "123492"): [
        {"DOCNUM": "3018855", "PARCEIRO": "PROD B", "VTIN_QTDE": 70000.0, "VTIN_VLR_NF": 126000.0},
        {"DOCNUM": "3018856", "PARCEIRO": "PROD B", "VTIN_QTDE": 73159.0, "VTIN_VLR_NF": 131724.68},
    ],
    # exceção -> ERRO
    ("9999999999", "000000"): RuntimeError("falha simulada SAP"),
}
