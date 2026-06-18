# -*- coding: utf-8 -*-
"""Investiga por que CTR_FIXO nao acha registros no ZMMT0022.
Busca sem filtro de cockpit para ver quais IDs existem para o contrato."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config.settings import postgres_config, sap_config
from src.connectors.postgres_connector import PostgresConnector
from src.connectors.hana_connector import HanaConnector

pg = PostgresConnector(postgres_config)
hana = HanaConnector(sap_config)

# Pega os primeiros 3 CTR_FIXO pendentes
rows_pg = pg.execute_query("""
    SELECT cqff.id, cqff.n_contrato, cqff.doc_compra, cqff.numero_cockpit
    FROM prod.complemento_quantidade_fixo_fila cqff
    WHERE cqff.status IN ('12','13')
    ORDER BY cqff.id
    LIMIT 3
""")

print("=== CTR_FIXO: 3 primeiros da fila ===")
for r in rows_pg:
    print(f"  id={r['id']} | n_contrato={r['n_contrato']} | doc_compra={r['doc_compra']} | cockpit={r['numero_cockpit']}")

print()

# Para cada contrato, busca TUDO que existe no ZMMT0022 (sem filtro de cockpit)
SQL_FULL = """
SELECT zmmt.CONTRATO, zmmt.ID, zmmt.MIRO_DATA, zmmt.MIRO_DOC, zmmt.MIRO_ANO, zmmt.TIPO
FROM ZMMT0022 zmmt
WHERE zmmt.CONTRATO = ?
ORDER BY zmmt.ID
"""

# Tambem tenta com LPAD
SQL_LPAD = """
SELECT zmmt.CONTRATO, zmmt.ID, zmmt.MIRO_DATA, zmmt.MIRO_DOC, zmmt.MIRO_ANO, zmmt.TIPO
FROM ZMMT0022 zmmt
WHERE zmmt.CONTRATO = LPAD(?, 10, '0')
ORDER BY zmmt.ID
"""

for r in rows_pg:
    contrato = str(r['n_contrato'] or '').strip()
    doc_compra = str(r['doc_compra'] or '').strip()
    cockpit = str(r['numero_cockpit'] or '').strip()

    print(f"--- CONTRATO={contrato} (doc_compra={doc_compra}) cockpit_pg={cockpit} ---")

    # Tentativa 1: exato
    rows = hana.execute_query(SQL_FULL, (contrato,))
    print(f"  ZMMT exato '{contrato}': {len(rows)} linhas")
    for z in rows[:5]:
        print(f"    ID={z['ID']} | MIRO_DATA={z['MIRO_DATA']} | MIRO_DOC={z['MIRO_DOC']} | TIPO={z['TIPO']}")

    # Tentativa 2: com LPAD
    rows2 = hana.execute_query(SQL_LPAD, (contrato,))
    print(f"  ZMMT LPAD '{contrato}': {len(rows2)} linhas")
    for z in rows2[:5]:
        print(f"    ID={z['ID']} | MIRO_DATA={z['MIRO_DATA']} | MIRO_DOC={z['MIRO_DOC']} | TIPO={z['TIPO']}")

    # Tentativa 3: doc_compra em vez de n_contrato
    if doc_compra and doc_compra != contrato:
        rows3 = hana.execute_query(SQL_FULL, (doc_compra,))
        print(f"  ZMMT exato doc_compra='{doc_compra}': {len(rows3)} linhas")
        for z in rows3[:5]:
            print(f"    ID={z['ID']} | MIRO_DATA={z['MIRO_DATA']} | MIRO_DOC={z['MIRO_DOC']} | TIPO={z['TIPO']}")
    print()

# Tambem faz para S_FIXACAO - 2 itens
rows_sfx = pg.execute_query("""
    SELECT cqff.id, cqff.n_contrato, cqff.doc_compra, cqff.numero_cockpit
    FROM prod.complemento_quantidade_sem_fixacao_fila cqff
    WHERE cqff.status IN ('12','13','9')
    ORDER BY cqff.id
    LIMIT 2
""")

print("=== CTR_S_FIXACAO: 2 primeiros da fila ===")
for r in rows_sfx:
    contrato = str(r['n_contrato'] or '').strip()
    doc_compra = str(r['doc_compra'] or '').strip()
    cockpit = str(r['numero_cockpit'] or '').strip()

    print(f"--- CONTRATO={contrato} doc_compra={doc_compra} cockpit_pg={cockpit} ---")
    rows = hana.execute_query(SQL_FULL, (contrato,))
    print(f"  ZMMT exato '{contrato}': {len(rows)} linhas")
    for z in rows[:5]:
        print(f"    ID={z['ID']} | MIRO_DATA={z['MIRO_DATA']} | MIRO_DOC={z['MIRO_DOC']} | TIPO={z['TIPO']}")

    if doc_compra and doc_compra != contrato:
        rows3 = hana.execute_query(SQL_FULL, (doc_compra,))
        print(f"  ZMMT exato doc_compra='{doc_compra}': {len(rows3)} linhas")
        for z in rows3[:5]:
            print(f"    ID={z['ID']} | MIRO_DATA={z['MIRO_DATA']} | MIRO_DOC={z['MIRO_DOC']} | TIPO={z['TIPO']}")
    print()

pg.close()
hana.close()
