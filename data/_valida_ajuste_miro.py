# -*- coding: utf-8 -*-
"""
Valida se os cockpits pendentes no Postgres sao encontrados no HANA
com o novo SQL UNION ALL (VIA_MIRO + VIA_CPF_MATCH).
Usa os mesmos parametros que o processes.yaml define para cada processo.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config.settings import postgres_config, sap_config
from src.connectors.postgres_connector import PostgresConnector
from src.connectors.hana_connector import HanaConnector

SQL_DIR = ROOT / "sql" / "sap_hana" / "consultas"

# Mapeamento igual ao processes.yaml:
#   - parametros: lista de colunas do Postgres na ordem dos '?' do HANA
#   - CTR: (doc_compra, numero_cockpit, doc_compra)
#   - ARMAZEN: (n_contrato, numero_cockpit, n_contrato)
PROCESSOS = [
    {
        "nome": "CTR_FIXO",
        "sql_hana": SQL_DIR / "Consulta_Comp_CTRFIXO.sql",
        "parametros_pg": ["doc_compra", "numero_cockpit", "doc_compra"],
        "sql_pg": """
            SELECT cqff.id, cqff.n_contrato, cqff.doc_compra,
                   TRIM(s) AS numero_cockpit
            FROM prod.complemento_quantidade_fixo_fila cqff
            CROSS JOIN LATERAL (
                SELECT DISTINCT TRIM(s) AS s
                FROM regexp_split_to_table(COALESCE(cqff.numero_cockpit,''), '\\|') s
                WHERE TRIM(s) <> ''
            ) x
            WHERE cqff.status IN ('12','13')
            ORDER BY cqff.id
        """,
    },
    {
        "nome": "CTR_S_FIXACAO",
        "sql_hana": SQL_DIR / "Consulta_Comp_CTR_S_FIXACAO.sql",
        "parametros_pg": ["doc_compra", "numero_cockpit", "doc_compra"],
        "sql_pg": """
            SELECT cqff.id, cqff.n_contrato, cqff.doc_compra,
                   TRIM(s) AS numero_cockpit
            FROM prod.complemento_quantidade_sem_fixacao_fila cqff
            CROSS JOIN LATERAL (
                SELECT DISTINCT TRIM(s) AS s
                FROM regexp_split_to_table(COALESCE(cqff.numero_cockpit,''), '\\|') s
                WHERE TRIM(s) <> ''
            ) x
            WHERE cqff.status IN ('12','13','9')
            ORDER BY cqff.id
        """,
    },
    {
        "nome": "CTR_C_FIXACAO",
        "sql_hana": SQL_DIR / "Consulta_Comp_CTR_C_FIXACAO.sql",
        "parametros_pg": ["doc_compra", "numero_cockpit", "doc_compra"],
        "sql_pg": """
            SELECT cqff.id, cqff.n_contrato, cqff.doc_compra,
                   TRIM(s) AS numero_cockpit
            FROM prod.complemento_quantidade_com_fixacao_fila cqff
            CROSS JOIN LATERAL (
                SELECT DISTINCT TRIM(s) AS s
                FROM regexp_split_to_table(COALESCE(cqff.numero_cockpit,''), '\\|') s
                WHERE TRIM(s) <> ''
            ) x
            WHERE cqff.status IN ('12','13')
            ORDER BY cqff.id
        """,
    },
    {
        "nome": "DEPOSITO",
        "sql_hana": SQL_DIR / "Consulta_Comp_ARMAZEN.sql",
        "parametros_pg": ["n_contrato", "numero_cockpit", "n_contrato"],
        "sql_pg": """
            SELECT cqff.id, cqff.n_contrato, cqff.doc_compra,
                   TRIM(s) AS numero_cockpit
            FROM prod.complemento_quantidade_deposito_fila cqff
            CROSS JOIN LATERAL (
                SELECT DISTINCT TRIM(s) AS s
                FROM regexp_split_to_table(COALESCE(cqff.numero_cockpit,''), '\\|') s
                WHERE TRIM(s) <> ''
            ) x
            WHERE cqff.status IN ('12','13')
            ORDER BY cqff.id
        """,
    },
]

# Diagnostico ZMMT (sem filtro MIRO_DATA) para entender o status de cada item
SQL_ZMMT_DIAG = """
SELECT zmmt.ID, zmmt.CONTRATO, zmmt.MIRO_DATA, zmmt.MIRO_DOC, zmmt.MIRO_ANO, zmmt.TIPO
FROM ZMMT0022 zmmt
WHERE zmmt.CONTRATO = ?
  AND LTRIM(zmmt.ID, '0') = LTRIM(?, '0')
"""

SQL_ZMMT_DIAG_ARMAZEN = """
SELECT zmmt.ID, zmmt.CONTRATO, zmmt.MIRO_DATA, zmmt.MIRO_DOC, zmmt.MIRO_ANO, zmmt.TIPO
FROM ZMMT0022 zmmt
WHERE zmmt.CONTRATO = LPAD(?, 10, '0')
  AND LTRIM(zmmt.ID, '0') = LTRIM(?, '0')
"""


def main():
    pg = PostgresConnector(postgres_config)
    hana = HanaConnector(sap_config)

    resumo_geral = []

    for proc in PROCESSOS:
        nome = proc["nome"]
        sql_hana_raw = proc["sql_hana"].read_text(encoding="utf-8")
        sql_hana = hana.render_sql_template(sql_hana_raw)
        params_cols = proc["parametros_pg"]
        is_armazen = nome == "DEPOSITO"

        print(f"\n{'='*70}")
        print(f"  Processo: {nome}")
        print(f"{'='*70}")

        rows_pg = pg.execute_query(proc["sql_pg"])
        print(f"  Cockpits pendentes no Postgres: {len(rows_pg)}")

        if not rows_pg:
            print("  (nenhum item pendente)")
            continue

        for row in rows_pg:
            # Monta params exatamente como o process_runner faz (via processes.yaml)
            try:
                params = tuple(str(row[c] or "").strip() for c in params_cols)
            except KeyError as e:
                print(f"  ERRO params: coluna {e} nao encontrada")
                continue

            contrato_zmmt = params[0]   # doc_compra (CTR) ou n_contrato (ARMAZEN)
            cockpit = params[1]

            # -- diagnostico ZMMT (sem MIRO_DATA) --------------------------------
            sql_zmmt = SQL_ZMMT_DIAG_ARMAZEN if is_armazen else SQL_ZMMT_DIAG
            try:
                zmmt_rows = hana.execute_query(sql_zmmt, (contrato_zmmt, cockpit))
                hana.wait_between_queries()
            except Exception as exc:
                zmmt_rows = []
                print(f"  ERRO ZMMT: {exc}")

            if not zmmt_rows:
                zmmt_status = "NAO_NO_ZMMT"
                miro_data = miro_doc = tipo = ""
            else:
                z = zmmt_rows[0]
                miro_data = str(z.get("MIRO_DATA") or "").strip()
                miro_doc  = str(z.get("MIRO_DOC")  or "").strip()
                tipo      = str(z.get("TIPO")       or "").strip()
                if miro_data == "00000000":
                    zmmt_status = "MIRO_NAO_EXEC"
                elif miro_doc:
                    zmmt_status = "MIRO_COM_DOC"
                else:
                    zmmt_status = "MIRO_SEM_DOC"

            # -- consulta HANA principal -----------------------------------------
            try:
                hana_rows = hana.execute_query(sql_hana, params)
                hana.wait_between_queries()
            except Exception as exc:
                hana_rows = []
                print(f"  ERRO HANA: {exc}")

            n_hana = len(hana_rows)
            if n_hana == 0:
                resultado = "SEM_RETORNO"
                docnum = origem = ""
            else:
                h = hana_rows[0]
                docnum  = str(h.get("DOCNUM")       or "").strip()
                origem  = str(h.get("ORIGEM_MATCH") or "").strip()
                resultado = "SUCESSO" if docnum else "SEM_DOCNUM"

            tag = "OK " if resultado == "SUCESSO" else "X  "
            n_contrato_pg = str(row.get("n_contrato") or "").strip()
            doc_compra_pg = str(row.get("doc_compra") or "").strip()

            print(
                f"  {tag} id={row['id']:6} | n_ctr={n_contrato_pg} doc={doc_compra_pg} "
                f"ckt={cockpit} | ZMMT={zmmt_status} MIRO={miro_data or '-'} "
                f"MIRO_DOC={miro_doc or '-'} TIPO={tipo or '-'} | "
                f"{resultado} {origem or '-'} DOCNUM={docnum or '-'}"
            )

            resumo_geral.append({
                "processo": nome,
                "zmmt_status": zmmt_status,
                "resultado": resultado,
                "origem": origem,
            })

    # ── Resumo final ─────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("  RESUMO FINAL")
    print(f"{'='*70}")

    from collections import Counter
    por_proc: dict[str, Counter] = {}
    for r in resumo_geral:
        p = r["processo"]
        if p not in por_proc:
            por_proc[p] = Counter()
        por_proc[p]["total"] += 1
        por_proc[p][r["resultado"]] += 1
        por_proc[p][r["zmmt_status"]] += 1
        if r["origem"]:
            por_proc[p][r["origem"]] += 1

    for p, cnt in por_proc.items():
        t = cnt["total"]
        s = cnt.get("SUCESSO", 0)
        sem = cnt.get("SEM_RETORNO", 0)
        sd  = cnt.get("SEM_DOCNUM", 0)
        miro_ok  = cnt.get("MIRO_COM_DOC", 0)
        miro_nao = cnt.get("MIRO_NAO_EXEC", 0)
        miro_sem = cnt.get("MIRO_SEM_DOC", 0)
        nao_zmmt = cnt.get("NAO_NO_ZMMT", 0)
        via_miro = cnt.get("VIA_MIRO", 0)
        via_cpf  = cnt.get("VIA_CPF_MATCH", 0)
        print(f"\n  {p} (total={t})")
        print(f"    Resultado : SUCESSO={s}  SEM_RETORNO={sem}  SEM_DOCNUM={sd}")
        print(f"    ZMMT      : MIRO_COM_DOC={miro_ok}  MIRO_NAO_EXEC={miro_nao}  MIRO_SEM_DOC={miro_sem}  NAO_NO_ZMMT={nao_zmmt}")
        print(f"    Origem    : VIA_MIRO={via_miro}  VIA_CPF_MATCH={via_cpf}")

    total = len(resumo_geral)
    total_s = sum(1 for r in resumo_geral if r["resultado"] == "SUCESSO")
    print(f"\n  TOTAL GERAL: {total_s}/{total} escriturados")

    pg.close()
    hana.close()


if __name__ == "__main__":
    main()
