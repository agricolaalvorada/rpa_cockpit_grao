WITH zmmt_base AS (
    SELECT
        zmmt.MANDT,
        zmmt.ID,
        zmmt.CONTRATO,
        zmmt."DATA",
        zmmt.QTDE,
        zmmt.VALOR,
        zmmt.MIRO_DATA,
        zmmt.MIRO_HORA,
        zmmt.MIRO_DOC,
        zmmt.MIRO_ANO,
        zmmt.TIPO
    FROM ZMMT0022 zmmt
    WHERE 1 = 1
      AND zmmt.CONTRATO = LPAD(?, 10, '0')
      AND LTRIM(zmmt.ID, '0') = LTRIM(?, '0')
      AND zmmt.MIRO_DATA != '00000000'
),

ctr AS (
    SELECT DISTINCT
        vbak.MANDT,
        vbak.VKORG       AS BUKRS,
        vbak.VBELN       AS EBELN,
        vbak.VBELN       AS KONNR,
        vbak.KUNNR       AS LIFNR,
        kna1.NAME1       AS NAME,
        COALESCE(NULLIF(kna1.STCD1, ''), kna1.STCD2) AS CPF_CNPJ,
        kna1.STCD2       AS IE,
        kna1.NAME1       AS NAME1_TEXT,
        vbak.AUART       AS TIPO_DOCUMENTO,
        vbak.VTWEG       AS CANAL_DISTRIBUICAO,
        vbak.SPART       AS DIVISAO,
        vbap.POSNR       AS ITEM_CONTRATO,
        vbap.MATNR       AS MATERIAL,
        vbap.ARKTX       AS DESCRICAO_ITEM,
        vbap.KWMENG      AS QTD_PREVISTA,
        vbap.VRKME       AS UM
    FROM VBAK vbak
    INNER JOIN VBAP vbap
        ON vbap.MANDT = vbak.MANDT
       AND vbap.VBELN = vbak.VBELN
    LEFT JOIN KNA1 kna1
        ON kna1.MANDT = vbak.MANDT
       AND kna1.KUNNR = vbak.KUNNR
    WHERE LPAD(vbak.VBELN, 10, '0') = LPAD(?, 10, '0')
),

vtin_fallback AS (
    SELECT
        act.PARID          AS PARCEIRO,
        act.BRANCH         AS LOCAL,
        act.CREDAT         AS DT_CRIACAO,
        act.DOCNUM,
        doc.NTGEW          AS PESO_LIQUIDO,
        doc.NFTOT          AS VLR_NF,
        vxr.MANSTA         AS VTIN_STATUS,
        vxr.CODESTA        AS VTIN_COD_STATUS_SEFAZ,
        vxr.ID             AS VTIN_XML,
        item.NFITEM        AS ITEM,
        item.NCM,
        item.CFOP,
        vxr.LIFNR          AS VTIN_COD_PARCEIRO,
        vxr.DATECR         AS VTIN_DT_CRIACAO,
        vxr.TIMECR         AS VTIN_HR_CRIACAO,
        vxr.D_EMI          AS VTIN_DT_EMISSAO,
        vxr.STCD1          AS VTIN_CPF_CNPJ,
        vxr.MODEL          AS VTIN_MODELO,
        vxr.BUKRS          AS VTIN_EMPRESA,
        vxr.BRANCH         AS VTIN_CENTRO,
        vxr.NFNUM9         AS VTIN_NF_NUM,
        vxr.SERIE          AS VTIN_SERIE,
        vxr.CDV            AS DIG_VER,
        vxr.DOCNUM9        AS NUM_ALEATORIO,
        vxr.AUTHCOD        AS N_LOG,
        vxr.NFYEAR         AS VTIN_ANO,
        vxr.NFMONTH        AS VTIN_MES,
        item.QCOM          AS VTIN_QTDE,
        vxr.V_NF           AS VTIN_VLR_NF,
        ROUND(vxr.V_NF, 0) AS A_VTIN_VLR_NF
    FROM "/VTIN/_XML_REC" vxr
    LEFT JOIN J_1BNFE_ACTIVE act
        ON act.NFYEAR  = vxr.NFYEAR
       AND act.NFMONTH = vxr.NFMONTH
       AND act.STCD1   = vxr.STCD1
       AND act.MODEL   = vxr.MODEL
       AND act.NFNUM9  = vxr.NFNUM9
       AND act.DOCNUM9 = vxr.DOCNUM9
       AND act.CDV     = vxr.CDV
       AND act.DIRECT  = '1'
       AND act.CANCEL  = ''
    LEFT JOIN J_1BNFDOC doc
        ON doc.DOCNUM = act.DOCNUM
    INNER JOIN "/VTIN/NFEIT" item
        ON item.NFEID = vxr.ID
    WHERE vxr.CODESTA IN ('100')
      AND vxr.MANSTA NOT IN ('03', '04')
)

-- Caminho primario: MIRO_DOC → J_1BNFDOC → DOCNUM (determinístico, sem match fuzzy)
SELECT
    zmmt_base.MANDT         AS ZMMT_MANDT,
    zmmt_base.ID            AS ZMMT_ID,
    zmmt_base.CONTRATO      AS ZMMT_CONTRATO,
    zmmt_base."DATA"        AS ZMMT_DATA,
    zmmt_base.QTDE          AS ZMMT_QTDE,
    zmmt_base.VALOR         AS ZMMT_VALOR,
    zmmt_base.MIRO_DATA     AS ZMMT_MIRO_DATA,
    zmmt_base.MIRO_HORA     AS ZMMT_MIRO_HORA,
    zmmt_base.MIRO_DOC      AS ZMMT_MIRO_DOC,
    zmmt_base.MIRO_ANO      AS ZMMT_MIRO_ANO,
    zmmt_base.TIPO          AS ZMMT_TIPO,

    ctr.MANDT               AS CTR_MANDT,
    ctr.BUKRS,
    ctr.EBELN,
    ctr.KONNR,
    ctr.LIFNR,
    ctr.NAME,
    ctr.CPF_CNPJ,
    ctr.IE,
    ctr.NAME1_TEXT,
    ctr.TIPO_DOCUMENTO,
    ctr.CANAL_DISTRIBUICAO,
    ctr.DIVISAO,
    ctr.ITEM_CONTRATO,
    ctr.MATERIAL       AS CTR_MATERIAL,
    ctr.DESCRICAO_ITEM AS CTR_DESCRICAO_ITEM,
    ctr.QTD_PREVISTA   AS CTR_QTD_PREVISTA,
    ctr.UM             AS CTR_UM,

    act.PARID               AS PARCEIRO,
    act.BRANCH              AS LOCAL,
    act.CREDAT              AS DT_CRIACAO,
    doc.DOCNUM,
    doc.NTGEW               AS PESO_LIQUIDO,
    COALESCE(vxr.V_NF, doc.NFTOT) AS VLR_NF,
    vxr.MANSTA              AS VTIN_STATUS,
    vxr.CODESTA             AS VTIN_COD_STATUS_SEFAZ,
    vxr.ID                  AS VTIN_XML,
    item.NFITEM             AS ITEM,
    item.NCM,
    item.CFOP,
    vxr.LIFNR               AS VTIN_COD_PARCEIRO,
    vxr.DATECR              AS VTIN_DT_CRIACAO,
    vxr.TIMECR              AS VTIN_HR_CRIACAO,
    vxr.D_EMI               AS VTIN_DT_EMISSAO,
    vxr.STCD1               AS VTIN_CPF_CNPJ,
    vxr.MODEL               AS VTIN_MODELO,
    vxr.BUKRS               AS VTIN_EMPRESA,
    vxr.BRANCH              AS VTIN_CENTRO,
    vxr.NFNUM9              AS VTIN_NF_NUM,
    vxr.SERIE               AS VTIN_SERIE,
    vxr.CDV                 AS DIG_VER,
    vxr.DOCNUM9             AS NUM_ALEATORIO,
    vxr.AUTHCOD             AS N_LOG,
    vxr.NFYEAR              AS VTIN_ANO,
    vxr.NFMONTH             AS VTIN_MES,
    item.QCOM               AS VTIN_QTDE,
    vxr.V_NF                AS VTIN_VLR_NF,
    ROUND(vxr.V_NF, 0)      AS A_VTIN_VLR_NF,
    COALESCE(vxr.V_NF, doc.NFTOT, 0) AS RESULTADO,
    'VIA_MIRO'              AS ORIGEM_MATCH
FROM zmmt_base
INNER JOIN ctr
    ON ctr.EBELN = LPAD(zmmt_base.CONTRATO, 10, '0')
INNER JOIN J_1BNFDOC doc
    ON doc.BELNR  = zmmt_base.MIRO_DOC
   AND doc.GJAHR  = zmmt_base.MIRO_ANO
   AND doc.DIRECT = '1'
LEFT JOIN J_1BNFE_ACTIVE act
    ON act.DOCNUM = doc.DOCNUM
   AND act.DIRECT = '1'
   AND act.CANCEL = ''
LEFT JOIN "/VTIN/_XML_REC" vxr
    ON vxr.NFYEAR  = act.NFYEAR
   AND vxr.NFMONTH = act.NFMONTH
   AND vxr.NFNUM9  = act.NFNUM9
   AND vxr.STCD1   = act.STCD1
   AND vxr.CDV     = act.CDV
   AND vxr.CODESTA IN ('100')
LEFT JOIN "/VTIN/NFEIT" item
    ON item.NFEID = vxr.ID
WHERE zmmt_base.MIRO_DOC IS NOT NULL
  AND zmmt_base.MIRO_DOC != ''

UNION ALL

-- Caminho fallback: CPF + QTDE + VALOR no VTIN (quando MIRO_DOC vazio)
SELECT
    zmmt_base.MANDT         AS ZMMT_MANDT,
    zmmt_base.ID            AS ZMMT_ID,
    zmmt_base.CONTRATO      AS ZMMT_CONTRATO,
    zmmt_base."DATA"        AS ZMMT_DATA,
    zmmt_base.QTDE          AS ZMMT_QTDE,
    zmmt_base.VALOR         AS ZMMT_VALOR,
    zmmt_base.MIRO_DATA     AS ZMMT_MIRO_DATA,
    zmmt_base.MIRO_HORA     AS ZMMT_MIRO_HORA,
    zmmt_base.MIRO_DOC      AS ZMMT_MIRO_DOC,
    zmmt_base.MIRO_ANO      AS ZMMT_MIRO_ANO,
    zmmt_base.TIPO          AS ZMMT_TIPO,

    ctr.MANDT               AS CTR_MANDT,
    ctr.BUKRS,
    ctr.EBELN,
    ctr.KONNR,
    ctr.LIFNR,
    ctr.NAME,
    ctr.CPF_CNPJ,
    ctr.IE,
    ctr.NAME1_TEXT,
    ctr.TIPO_DOCUMENTO,
    ctr.CANAL_DISTRIBUICAO,
    ctr.DIVISAO,
    ctr.ITEM_CONTRATO,
    ctr.MATERIAL       AS CTR_MATERIAL,
    ctr.DESCRICAO_ITEM AS CTR_DESCRICAO_ITEM,
    ctr.QTD_PREVISTA   AS CTR_QTD_PREVISTA,
    ctr.UM             AS CTR_UM,

    vtin_fallback.PARCEIRO,
    vtin_fallback.LOCAL,
    vtin_fallback.DT_CRIACAO,
    vtin_fallback.DOCNUM,
    vtin_fallback.PESO_LIQUIDO,
    vtin_fallback.VLR_NF,
    vtin_fallback.VTIN_STATUS,
    vtin_fallback.VTIN_COD_STATUS_SEFAZ,
    vtin_fallback.VTIN_XML,
    vtin_fallback.ITEM,
    vtin_fallback.NCM,
    vtin_fallback.CFOP,
    vtin_fallback.VTIN_COD_PARCEIRO,
    vtin_fallback.VTIN_DT_CRIACAO,
    vtin_fallback.VTIN_HR_CRIACAO,
    vtin_fallback.VTIN_DT_EMISSAO,
    vtin_fallback.VTIN_CPF_CNPJ,
    vtin_fallback.VTIN_MODELO,
    vtin_fallback.VTIN_EMPRESA,
    vtin_fallback.VTIN_CENTRO,
    vtin_fallback.VTIN_NF_NUM,
    vtin_fallback.VTIN_SERIE,
    vtin_fallback.DIG_VER,
    vtin_fallback.NUM_ALEATORIO,
    vtin_fallback.N_LOG,
    vtin_fallback.VTIN_ANO,
    vtin_fallback.VTIN_MES,
    vtin_fallback.VTIN_QTDE,
    vtin_fallback.VTIN_VLR_NF,
    vtin_fallback.A_VTIN_VLR_NF,
    GREATEST(COALESCE(vtin_fallback.VTIN_VLR_NF, 0), COALESCE(vtin_fallback.A_VTIN_VLR_NF, 0)) AS RESULTADO,
    'VIA_CPF_MATCH'         AS ORIGEM_MATCH
FROM zmmt_base
INNER JOIN ctr
    ON ctr.EBELN = LPAD(zmmt_base.CONTRATO, 10, '0')
INNER JOIN vtin_fallback
    ON LTRIM(ctr.CPF_CNPJ, '0') = LTRIM(vtin_fallback.VTIN_CPF_CNPJ, '0')
   AND zmmt_base.QTDE IS NOT NULL
   AND ROUND(zmmt_base.QTDE, 3) = ROUND(vtin_fallback.VTIN_QTDE, 3)
   AND (
        ROUND(zmmt_base.VALOR, 2) = ROUND(vtin_fallback.VTIN_VLR_NF, 2)
        OR ROUND(zmmt_base.VALOR, 2) = ROUND(vtin_fallback.A_VTIN_VLR_NF, 2)
   )
WHERE (zmmt_base.MIRO_DOC IS NULL OR zmmt_base.MIRO_DOC = '')
  AND YEAR(vtin_fallback.VTIN_DT_EMISSAO) IN ({anos});
