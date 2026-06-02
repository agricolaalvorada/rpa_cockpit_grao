SELECT
    cqff.id,
    'COM_CTR_FIXO' AS tipo_processo,
    cqff.status,
    cqff.status_complemento_fixo,
    cqff.tipo,
    cqff.n_contrato,
    cqff.doc_compra,
    cqff.numero_cockpit AS numero_cockpit_original,
    cqff.centro,
    cqff.safra,
    cqff.material,
    cqff.cod_parceiro,
    cqff.data_hora_ultima_atualizacao,
    TRIM(split_cockpit) AS numero_cockpit,
    cqff.msg_rpa
FROM prod.complemento_quantidade_fixo_fila AS cqff
CROSS JOIN LATERAL regexp_split_to_table(
    COALESCE(cqff.numero_cockpit, ''),
    '\|'
) AS split_cockpit
WHERE 1 = 1
  AND cqff.status IN ('12', '13')
  AND TRIM(split_cockpit) <> ''
ORDER BY cqff.id;