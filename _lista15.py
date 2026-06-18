# -*- coding: utf-8 -*-
"""Regrava a lista (colunas pedidas) a partir do JSON, com DOCNUM/CPF como texto limpo."""
import json
import pandas as pd

det = json.load(open("data/_analise15_data.json", encoding="utf-8"))
SIT = {
    "ESCRITURADO": "ESCRITURADO",
    "LIGADO_SEM_DOCNUM": "NAO ESCRITURADO - NF do pedido sem DOCNUM",
    "NF_DIVERGE": "NAO ESCRITURADO - NF do CPF nao casa qtde/valor",
    "SEM_NF_DO_CPF": "NAO ESCRITURADO - sem NF do CPF no VTIN",
    "SEM_CPF": "NAO ESCRITURADO - sem CPF do fornecedor",
    "SEM_ZMMT_COCKPIT": "NAO ESCRITURADO - cockpit sem ZMMT",
}

def cpf_list(d):
    v = d.get("cpf")
    if isinstance(v, list):
        return ", ".join(v)
    return str(v or "")

lista = [{
    "PROCESSO": d["proc"],
    "PEDIDO": str(d["doc_compra"]),
    "COCKPIT": str(d["cockpit"]),
    "CPF": cpf_list(d),
    "FORNECEDOR": d.get("nome", ""),
    "QTDE": d.get("qexp"),
    "VALOR": d.get("vexp"),
    "DOCNUM": str(d.get("docnum") or "").split(".")[0],
    "ESCRITURADO": "SIM" if d["classe"] == "ESCRITURADO" else "NAO",
    "SITUACAO": SIT.get(d["classe"], d["classe"]),
} for d in det]

df = pd.DataFrame(lista, columns=["PROCESSO", "PEDIDO", "COCKPIT", "CPF", "FORNECEDOR",
                                  "QTDE", "VALOR", "DOCNUM", "ESCRITURADO", "SITUACAO"])
df = df.sort_values(["ESCRITURADO", "PROCESSO", "PEDIDO", "COCKPIT"]).reset_index(drop=True)
df["DOCNUM"] = df["DOCNUM"].astype("string")
df["CPF"] = df["CPF"].astype("string")

df.to_csv("data/output/lista_status15_fixo_semfix.csv", index=False, sep=";", encoding="utf-8-sig")
with pd.ExcelWriter("data/output/lista_status15_fixo_semfix.xlsx", engine="openpyxl") as w:
    df.to_excel(w, index=False, sheet_name="status15")
    ws = w.sheets["status15"]
    for col in ("D", "H"):  # CPF, DOCNUM como texto
        for cell in ws[col]:
            cell.number_format = "@"
    widths = {"A": 13, "B": 12, "C": 9, "D": 17, "E": 30, "F": 10, "G": 12, "H": 10, "I": 12, "J": 48}
    for c, wdt in widths.items():
        ws.column_dimensions[c].width = wdt

print("Linhas: %d | SIM=%d NAO=%d" % (len(df), (df.ESCRITURADO == "SIM").sum(), (df.ESCRITURADO == "NAO").sum()))
print("Arquivo -> data/output/lista_status15_fixo_semfix.xlsx (e .csv)")
