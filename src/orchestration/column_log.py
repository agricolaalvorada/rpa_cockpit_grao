# -*- coding: utf-8 -*-
"""Log formatado das colunas da carga (extraído do main.py, comportamento preservado)."""
from __future__ import annotations

from typing import List

SEPARADOR = "-" * 80


def join_cols(cols: List[str]) -> str:
    return ", ".join(cols) if cols else "(nenhum)"


def log_colunas_formatado(logger, df) -> None:
    cols = list(df.columns)

    principais = [
        c for c in cols
        if c in [
            "id",
            "tipo_processo",
            "status",
            "status_complemento_fixo",
            "tipo",
            "n_contrato",
            "doc_compra",
            "centro",
            "safra",
            "material",
            "cod_parceiro",
            "data_hora_ultima_atualizacao",
            "numero_cockpit",
            "msg_rpa",
            "parceiro",
            "local",
            "dt_criacao",
        ]
    ]

    controle = [
        c for c in cols
        if c in [
            "process_name",
            "data_execucao",
            "status_execucao",
            "tempo_execucao",
        ]
    ]

    zmmt = [c for c in cols if c.startswith("zmmt_")]
    ctr = [
        c
        for c in cols
        if c.startswith("ctr_")
        or c in ["bukrs", "ebeln", "konnr", "lifnr", "name", "cpf_cnpj", "ie", "name1_text"]
    ]
    vtin = [c for c in cols if c.startswith("vtin_")]
    nf = [
        c
        for c in cols
        if c in [
            "docnum",
            "peso_liquido",
            "vlr_nf",
            "item",
            "ncm",
            "cfop",
            "dig_ver",
            "num_aleatorio",
            "n_log",
        ]
    ]
    periodo = [c for c in cols if c in ["vtin_ano", "vtin_mes"]]
    quantitativos = [
        c
        for c in cols
        if c in ["zmmt_qtde", "zmmt_valor", "vtin_qtde", "vtin_vlr_nf", "a_vtin_vlr_nf"]
    ]
    resultado = [c for c in cols if c in ["resultado"]]

    colunas_mapeadas = set(
        principais + controle + zmmt + ctr + vtin + nf + periodo + quantitativos + resultado
    )
    outras = [c for c in cols if c not in colunas_mapeadas]

    logger.info(SEPARADOR)
    logger.info("🧱 Preparando carga PostgreSQL")
    logger.info("📊 Total de colunas: %s", len(cols))
    logger.info("🔹 Campos principais: %s", join_cols(principais))
    logger.info("🔹 Campos de controle: %s", join_cols(controle))
    logger.info("🔹 Campos SAP ZMMT: %s", join_cols(zmmt))
    logger.info("🔹 Campos contrato / parceiro: %s", join_cols(ctr))
    logger.info("🔹 Campos XML / VTIN: %s", join_cols(vtin))
    logger.info("🔹 Campos NF / item: %s", join_cols(nf))
    logger.info("🔹 Campos período: %s", join_cols(periodo))
    logger.info("🔹 Campos quantitativos: %s", join_cols(quantitativos))
    logger.info("🔹 Campos resultado: %s", join_cols(resultado))
    logger.info("🔹 Outros campos: %s", join_cols(outras))
    logger.info(SEPARADOR)
