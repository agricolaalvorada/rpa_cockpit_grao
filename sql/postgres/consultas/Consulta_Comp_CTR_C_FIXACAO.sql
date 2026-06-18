SELECT
    cqcff.id,
    'COM_CTR_C_FIXACAO' AS tipo_processo,
    cqcff.status,
    cqcff.status_complemento_fixo,
    cqcff.tipo,
    cqcff.n_contrato,
    cqcff.doc_compra,
    cqcff.numero_cockpit AS numero_cockpit_original,
    cqcff.centro,
    cqcff.safra,
    cqcff.material,
    cqcff.cod_parceiro,
    cqcff.data_hora_ultima_atualizacao,
    split_cockpit.numero_cockpit,
    cqcff.msg_rpa
FROM prod.complemento_quantidade_com_fixacao_fila cqcff
CROSS JOIN LATERAL (
    SELECT DISTINCT TRIM(s) AS numero_cockpit
    FROM regexp_split_to_table(COALESCE(cqcff.numero_cockpit, ''), '\|') AS s
    WHERE TRIM(s) <> ''
) AS split_cockpit
WHERE 1 = 1
  AND cqcff.status IN ('12', '13')
ORDER BY cqcff.id;
