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
    split_cockpit.numero_cockpit,
    cqff.msg_rpa,
    cqff.chave_acesso,
    cqff.data_processamento,
    cqff.hora_processamento
FROM prod.complemento_quantidade_fixo_fila AS cqff
CROSS JOIN LATERAL (
    SELECT DISTINCT TRIM(s) AS numero_cockpit
    FROM regexp_split_to_table(COALESCE(cqff.numero_cockpit, ''), '\|') AS s
    WHERE TRIM(s) <> ''
) AS split_cockpit
WHERE 1 = 1
  AND cqff.status IN ('12', '13')
ORDER BY cqff.id;