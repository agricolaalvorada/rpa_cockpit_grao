# -*- coding: utf-8 -*-
"""
Mesma analise do armazem (status 15 -> escriturado?), agora para CONTRATO FIXO e SEM FIXACAO.
Criterio de escrituracao = DOCNUM (J_1BNFE_ACTIVE) preenchido na NF que casa.
Em lote (IN), sem agressividade no SAP. Dumpa detalhe em data/_analise15_data.json.
"""
import json
from src.config.settings import postgres_config, sap_config
from src.connectors.postgres_connector import PostgresConnector
from src.connectors.hana_connector import HanaConnector

pg = PostgresConnector(postgres_config); pg.connect()
hana = HanaConnector(sap_config); hana.connect()

PROCS = {
    "FIXO": "prod.complemento_quantidade_fixo_fila",
    "SEM_FIXACAO": "prod.complemento_quantidade_sem_fixacao_fila",
}

def in_clause(vals):
    return ",".join("'" + str(v).replace("'", "''") + "'" for v in vals)

def l0(s):
    return str(s or "").lstrip("0")

# ---------- 1) FILA (Postgres) ----------
rows = []  # cada cockpit explodido vira um item de trabalho
for proc, tab in PROCS.items():
    r = pg.execute_query(
        "SELECT doc_compra, numero_cockpit, status, valor, qtd_contratado, "
        "qtde_liquidada, num_nota_fiscal, chave_acesso "
        "FROM %s WHERE status='15' ORDER BY doc_compra" % tab)
    for x in r:
        dc = str(x["doc_compra"]).strip()
        cockpits = [c.strip() for c in str(x.get("numero_cockpit") or "").split("|") if c.strip()]
        if not cockpits:
            cockpits = [""]
        for ck in cockpits:
            rows.append({"proc": proc, "doc_compra": dc, "cockpit": ck,
                         "valor_fila": x.get("valor"), "qtd_fila": x.get("qtd_contratado"),
                         "num_nf_fila": x.get("num_nota_fiscal"), "chave_fila": x.get("chave_acesso")})

doc_compras = sorted({r["doc_compra"] for r in rows})
print("FILA  itens(cockpit explodido)=%d | doc_compras distintos=%d" % (len(rows), len(doc_compras)))
for proc in PROCS:
    n = sum(1 for r in rows if r["proc"] == proc)
    d = len({r["doc_compra"] for r in rows if r["proc"] == proc})
    print("   %-12s itens=%d doc_compras=%d" % (proc, n, d))

dc_in = in_clause(doc_compras)
dc_lpad = in_clause([d.zfill(10) for d in doc_compras])

# ---------- 2) ZMMT0022 (esperado: QTDE + VALOR por cockpit) ----------
zmm = hana.execute_query(
    "SELECT ID, CONTRATO, QTDE, VALOR FROM ZMMT0022 "
    "WHERE CONTRATO IN (%s) OR CONTRATO IN (%s)" % (dc_in, dc_lpad))
# index: lstrip(CONTRATO) -> list de {id, qtde, valor}
zmm_by_ctr = {}
for z in zmm:
    zmm_by_ctr.setdefault(l0(z["CONTRATO"]), []).append({
        "ID": str(z["ID"]), "QTDE": float(z["QTDE"]) if z["QTDE"] is not None else None,
        "VALOR": float(z["VALOR"]) if z["VALOR"] is not None else None})
print("ZMMT  linhas=%d | contratos com ZMMT=%d" % (len(zmm), len(zmm_by_ctr)))

# ---------- 3) CPF do fornecedor (EKKO + ZVS_BP_ID_FISCAL) ----------
bp = hana.execute_query(
    "SELECT DISTINCT ko.EBELN, bp.CPF_CNPJ, bp.NAME FROM EKKO ko "
    "INNER JOIN ZVS_BP_ID_FISCAL bp ON ko.LIFNR = bp.PARTNER "
    "WHERE ko.EBELN IN (%s) OR ko.EBELN IN (%s)" % (dc_in, dc_lpad))
cpf_by_dc = {}
name_by_dc = {}
for b in bp:
    k = l0(b["EBELN"])
    if b.get("CPF_CNPJ"):
        cpf_by_dc.setdefault(k, set()).add(str(b["CPF_CNPJ"]).strip())
        name_by_dc[k] = str(b.get("NAME") or "")
print("CPF   pedidos com CPF=%d" % len(cpf_by_dc))

# lista de CPFs (LTRIM 0) para a busca VTIN
all_cpfs = sorted({l0(c) for s in cpf_by_dc.values() for c in s if l0(c)})
cpf_in = in_clause(all_cpfs) if all_cpfs else "''"

# ---------- 4a) VTIN por PONUMBER (vinculo direto NF<->pedido) ----------
vtin_po = hana.execute_query(
    'SELECT it.PONUMBER, vxr.STCD1, it.QCOM, vxr.V_NF, vxr.NFNUM9, vxr.DATECR, act.DOCNUM '
    'FROM "/VTIN/_XML_REC" vxr '
    'INNER JOIN "/VTIN/NFEIT" it ON it.NFEID = vxr.ID '
    'LEFT JOIN J_1BNFE_ACTIVE act ON act.NFYEAR=vxr.NFYEAR AND act.NFMONTH=vxr.NFMONTH '
    '  AND act.STCD1=vxr.STCD1 AND act.MODEL=vxr.MODEL AND act.NFNUM9=vxr.NFNUM9 '
    '  AND act.DOCNUM9=vxr.DOCNUM9 AND act.CDV=vxr.CDV AND act.DIRECT=\'1\' AND act.CANCEL=\'\' '
    'WHERE it.PONUMBER IN (%s) OR it.PONUMBER IN (%s)' % (dc_in, dc_lpad))
po_by_dc = {}
for v in vtin_po:
    po_by_dc.setdefault(l0(v["PONUMBER"]), []).append({
        "QCOM": float(v["QCOM"]) if v["QCOM"] is not None else None,
        "V_NF": float(v["V_NF"]) if v["V_NF"] is not None else None,
        "NF": str(v.get("NFNUM9") or ""), "STCD1": str(v.get("STCD1") or ""),
        "DOCNUM": (str(v["DOCNUM"]).strip() if v.get("DOCNUM") is not None else None)})
print("VTIN-PO linhas=%d | pedidos com NF ligada=%d" % (len(vtin_po), len(po_by_dc)))

# ---------- 4b) VTIN por CPF (match estilo query oficial: qtde+valor) ----------
vtin_cpf = hana.execute_query(
    'SELECT vxr.STCD1, it.QCOM, vxr.V_NF, vxr.NFNUM9, act.DOCNUM '
    'FROM "/VTIN/_XML_REC" vxr '
    'INNER JOIN "/VTIN/NFEIT" it ON it.NFEID = vxr.ID '
    'LEFT JOIN J_1BNFE_ACTIVE act ON act.NFYEAR=vxr.NFYEAR AND act.NFMONTH=vxr.NFMONTH '
    '  AND act.STCD1=vxr.STCD1 AND act.MODEL=vxr.MODEL AND act.NFNUM9=vxr.NFNUM9 '
    '  AND act.DOCNUM9=vxr.DOCNUM9 AND act.CDV=vxr.CDV AND act.DIRECT=\'1\' AND act.CANCEL=\'\' '
    'WHERE LTRIM(vxr.STCD1,\'0\') IN (%s) AND vxr.DATECR LIKE \'2026%%\'' % cpf_in)
vtin_by_cpf = {}
for v in vtin_cpf:
    vtin_by_cpf.setdefault(l0(v["STCD1"]), []).append({
        "QCOM": float(v["QCOM"]) if v["QCOM"] is not None else None,
        "V_NF": float(v["V_NF"]) if v["V_NF"] is not None else None,
        "NF": str(v.get("NFNUM9") or ""),
        "DOCNUM": (str(v["DOCNUM"]).strip() if v.get("DOCNUM") is not None else None)})
print("VTIN-CPF linhas=%d | cpfs com NF 2026=%d" % (len(vtin_cpf), len(vtin_by_cpf)))

def docnum_ok(d):
    return bool(d and str(d).strip("0").strip())

def val_bate(a, b):
    if a is None or b is None:
        return False
    return abs(a - b) <= 0.10 or round(a, 0) == round(b, 0)

# ---------- 5) CRUZAMENTO + CLASSIFICACAO ----------
detalhe = []
for r in rows:
    dc, ck = l0(r["doc_compra"]), r["cockpit"]
    # esperado da ZMMT (match cockpit == ID)
    zlist = zmm_by_ctr.get(dc, [])
    zrow = next((z for z in zlist if ck and l0(z["ID"]) == l0(ck)), None)
    qexp = zrow["QTDE"] if zrow else None
    vexp = zrow["VALOR"] if zrow else None
    cpfs = cpf_by_dc.get(dc, set())

    # --- A) VINCULO DIRETO (PONUMBER) ---
    po_nfs = po_by_dc.get(dc, [])
    escrit_po = any(docnum_ok(n["DOCNUM"]) for n in po_nfs)

    # --- B) MATCH OFICIAL (CPF + QTDE + VALOR) ---
    cand = []
    for c in cpfs:
        cand += vtin_by_cpf.get(l0(c), [])
    match_of = [n for n in cand if qexp is not None and n["QCOM"] is not None
                and round(n["QCOM"], 3) == round(qexp, 3) and val_bate(n["V_NF"], vexp)]
    escrit_of = any(docnum_ok(n["DOCNUM"]) for n in match_of)

    # DOCNUM da nota que casou (1a com DOCNUM preenchido)
    docnum_casado = ""
    nf_casada = ""
    for n in (po_nfs + match_of):
        if docnum_ok(n["DOCNUM"]):
            docnum_casado = str(n["DOCNUM"]); nf_casada = n.get("NF", ""); break

    # --- classificacao final (prioriza vinculo direto, mais robusto p/ fixo) ---
    if escrit_po or escrit_of:
        classe = "ESCRITURADO"
    elif po_nfs:
        classe = "LIGADO_SEM_DOCNUM"          # tem NF do pedido mas ainda sem DOCNUM
    elif not zrow:
        classe = "SEM_ZMMT_COCKPIT"           # cockpit nao achado na ZMMT
    elif not cpfs:
        classe = "SEM_CPF"                     # nao achou CPF do fornecedor
    elif not cand:
        classe = "SEM_NF_DO_CPF"               # CPF nao tem NF 2026 no VTIN
    else:
        classe = "NF_DIVERGE"                  # tem NF do CPF mas qtde/valor nao bate

    detalhe.append({**r, "qexp": qexp, "vexp": vexp,
                    "cpf": sorted(cpfs), "nome": name_by_dc.get(dc, ""),
                    "docnum": docnum_casado, "nf_casada": nf_casada,
                    "n_po_nfs": len(po_nfs), "escrit_po": escrit_po,
                    "n_match_oficial": len(match_of), "escrit_oficial": escrit_of,
                    "classe": classe})

# ---------- 6) RESUMO ----------
from collections import Counter
print("\n" + "=" * 70)
ordem = ["ESCRITURADO", "LIGADO_SEM_DOCNUM", "NF_DIVERGE", "SEM_NF_DO_CPF", "SEM_CPF", "SEM_ZMMT_COCKPIT"]
for proc in list(PROCS) + ["TOTAL"]:
    sub = detalhe if proc == "TOTAL" else [d for d in detalhe if d["proc"] == proc]
    c = Counter(d["classe"] for d in sub)
    esc = c.get("ESCRITURADO", 0)
    print("\n### %s  (itens=%d)" % (proc, len(sub)))
    print("   ESCRITURADO (DOCNUM):      %d  (%.0f%%)" % (esc, 100*esc/len(sub) if sub else 0))
    for k in ordem[1:]:
        if c.get(k):
            print("   %-26s %d" % (k + ":", c[k]))

with open("data/_analise15_data.json", "w", encoding="utf-8") as f:
    json.dump(detalhe, f, ensure_ascii=False, default=str)
print("\nDetalhe -> data/_analise15_data.json")

# ---------- 7) LISTA com as colunas pedidas (PEDIDO/CPF/COCKPIT/QTDE/VALOR/DOCNUM) ----------
import pandas as pd
SIT = {
    "ESCRITURADO": "ESCRITURADO",
    "LIGADO_SEM_DOCNUM": "NAO ESCRITURADO - NF do pedido sem DOCNUM",
    "NF_DIVERGE": "NAO ESCRITURADO - NF do CPF nao casa qtde/valor",
    "SEM_NF_DO_CPF": "NAO ESCRITURADO - sem NF do CPF no VTIN",
    "SEM_CPF": "NAO ESCRITURADO - sem CPF do fornecedor",
    "SEM_ZMMT_COCKPIT": "NAO ESCRITURADO - cockpit sem ZMMT",
}
lista = [{
    "PROCESSO": d["proc"],
    "PEDIDO": d["doc_compra"],
    "COCKPIT": d["cockpit"],
    "CPF": ", ".join(d["cpf"]),
    "FORNECEDOR": d["nome"],
    "QTDE": d["qexp"],
    "VALOR": d["vexp"],
    "DOCNUM": d["docnum"],
    "ESCRITURADO": "SIM" if d["classe"] == "ESCRITURADO" else "NAO",
    "SITUACAO": SIT.get(d["classe"], d["classe"]),
} for d in detalhe]
df = pd.DataFrame(lista, columns=["PROCESSO", "PEDIDO", "COCKPIT", "CPF", "FORNECEDOR",
                                  "QTDE", "VALOR", "DOCNUM", "ESCRITURADO", "SITUACAO"])
df = df.sort_values(["ESCRITURADO", "PROCESSO", "PEDIDO"]).reset_index(drop=True)
df.to_csv("data/output/lista_status15_fixo_semfix.csv", index=False, sep=";", encoding="utf-8-sig")
df.to_excel("data/output/lista_status15_fixo_semfix.xlsx", index=False)
print("Lista -> data/output/lista_status15_fixo_semfix.xlsx  (e .csv)  | %d linhas" % len(df))
pg.close(); hana.close()
