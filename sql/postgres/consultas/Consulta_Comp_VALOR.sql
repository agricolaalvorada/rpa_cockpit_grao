SELECT
    cvf.id,
    'COMP_VALOR'                              AS tipo_processo,
    cvf.ctr_status                            AS status,
    cvf.ctr_description                       AS status_complemento_fixo,
    cvf.tipo_complemento                      AS tipo,
    cvf.n_contrato,
    cvf.documento_compras                     AS doc_compra,
    cvf.id_cockpit                            AS numero_cockpit_original,
    cvf.centro,
    cvf.safra,
    cvf.material,
    cvf.codigo_parceiro                       AS cod_parceiro,
    cvf.ctr_last_updated                      AS data_hora_ultima_atualizacao,
    split_cockpit.numero_cockpit,
    cvf.msg_sap                               AS msg_rpa,
    NULL::varchar                             AS chave_acesso,
    NULL::varchar                             AS data_processamento,
    NULL::varchar                             AS hora_processamento
FROM prod.complem_valor_fila AS cvf
CROSS JOIN LATERAL (
    SELECT DISTINCT TRIM(s) AS numero_cockpit
    FROM regexp_split_to_table(COALESCE(cvf.id_cockpit, ''), '\|') AS s
    WHERE TRIM(s) <> ''
) AS split_cockpit
WHERE 1 = 1
  AND cvf.ctr_status IN ('01')
ORDER BY cvf.id;
