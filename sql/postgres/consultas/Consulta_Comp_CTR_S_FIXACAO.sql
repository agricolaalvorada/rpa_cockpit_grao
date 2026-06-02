SELECT
    cqsff.id,
    'COM_CTR_S_FIXACAO' AS tipo_processo,
    cqsff.status,
    cqsff.status_complemento_fixo,
    cqsff.tipo,
    cqsff.n_contrato,
    cqsff.doc_compra,
    cqsff.centro,
    cqsff.safra,
    cqsff.material,
    cqsff.cod_parceiro,
    cqsff.data_hora_ultima_atualizacao,
    TRIM(split_cockpit) AS numero_cockpit,
    cqsff.msg_rpa
FROM prod.complemento_quantidade_sem_fixacao_fila cqsff
CROSS JOIN LATERAL regexp_split_to_table(
    COALESCE(cqsff.numero_cockpit, ''),
    '\|'
) AS split_cockpit
WHERE 1 = 1
  AND cqsff.status IN ('12', '13', '9')
  AND TRIM(split_cockpit) <> ''
ORDER BY cqsff.id;