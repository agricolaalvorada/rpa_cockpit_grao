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
      AND zmmt.CONTRATO = ?
      AND LTRIM(zmmt.ID, '0') = LTRIM(?, '0')
      AND zmmt.MIRO_DATA != '00000000'
),

ctr AS (
    SELECT DISTINCT
        ko.MANDT,
        ko.BUKRS,
        ko.EBELN,
        ko.KONNR,
        ko.LIFNR,
        bp.NAME,
        bp.CPF_CNPJ,
        bp.IE,
        bp.NAME1_TEXT
    FROM EKKO ko
    INNER JOIN ZVS_BP_ID_FISCAL bp
        ON ko.LIFNR = bp.PARTNER
    INNER JOIN (
        SELECT
            MANDT,
            EBELN,
            MATNR
        FROM EKPO
    ) po
        ON ko.EBELN = po.EBELN
       AND po.MANDT = ko.MANDT
    INNER JOIN (
        SELECT
            MATNR,
            SPART
        FROM MARA
        WHERE SPART = '01'
    ) ma
        ON po.MATNR = ma.MATNR
    WHERE ko.EBELN = ?
),

vtin_fallback AS (
    SELECT
        act.PARID          AS PARCEIRO,
        act.BRANCH         AS LOCAL,
        act.CREDAT         AS DT_CRIACAO,
        act.DOCNUM,
        doc.NTGEW          AS PESO_LIQUIDO,
        doc.NFTOT          AS VLR_NF,
        doc.CRENAM,
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
        ON vxr.ID = item.NFEID
    WHERE vxr.CODESTA IN ('100')
      AND vxr.MANSTA NOT IN ('03', '04')
)

-- Caminho primario: MIRO_DOC → ETAPA_PROC (GJAHR real) → J_1BNFDOC → DOCNUM
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

    act.PARID               AS PARCEIRO,
    act.BRANCH              AS LOCAL,
    act.CREDAT              AS DT_CRIACAO,
    doc.DOCNUM,
    doc.CRENAM,
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
    ON ctr.EBELN = zmmt_base.CONTRATO
INNER JOIN "/VTIN/ETAPA_PROC" etp
    ON etp.NUM_DOC = zmmt_base.MIRO_DOC
   AND etp.TCODE  = 'MIRO'
LEFT JOIN J_1BNFDOC doc
    ON doc.BELNR  = etp.NUM_DOC
   AND doc.GJAHR  = etp.GJAHR
   AND doc.DIRECT = '1'
LEFT JOIN J_1BNFE_ACTIVE act
    ON act.DOCNUM = doc.DOCNUM
   AND act.DIRECT = '1'
   AND act.CANCEL = ''
LEFT JOIN "/VTIN/_XML_REC" vxr
    ON vxr.ID     = etp.ID
   AND vxr.CODESTA IN ('100')
LEFT JOIN "/VTIN/NFEIT" item
    ON item.NFEID = vxr.ID
WHERE zmmt_base.MIRO_DOC IS NOT NULL
  AND zmmt_base.MIRO_DOC != ''
  AND doc.NTGEW IS NOT NULL
  AND ROUND(doc.NTGEW, 3) = ROUND(zmmt_base.QTDE, 3)
  AND (
      ROUND(doc.NFTOT, 2) = ROUND(zmmt_base.VALOR, 2)
      OR ROUND(doc.NFTOT, 0) = ROUND(zmmt_base.VALOR, 0)
  )
  AND (doc.DOCNUM IS NULL OR doc.DOCNUM = '')

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

    vtin_fallback.PARCEIRO,
    vtin_fallback.LOCAL,
    vtin_fallback.DT_CRIACAO,
    vtin_fallback.DOCNUM,
    vtin_fallback.CRENAM,
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
    ON ctr.EBELN = zmmt_base.CONTRATO
INNER JOIN vtin_fallback
    ON LTRIM(ctr.CPF_CNPJ, '0') = LTRIM(vtin_fallback.VTIN_CPF_CNPJ, '0')
   AND zmmt_base.QTDE IS NOT NULL
   AND ROUND(zmmt_base.QTDE, 3) = ROUND(vtin_fallback.VTIN_QTDE, 3)
   AND (
        ROUND(zmmt_base.VALOR, 2) = ROUND(vtin_fallback.VTIN_VLR_NF, 2)
        OR ROUND(zmmt_base.VALOR, 2) = ROUND(vtin_fallback.A_VTIN_VLR_NF, 2)
   )
WHERE (zmmt_base.MIRO_DOC IS NULL OR zmmt_base.MIRO_DOC = '')
  AND YEAR(vtin_fallback.VTIN_DT_EMISSAO) IN ({anos})
  AND (vtin_fallback.DOCNUM IS NULL OR vtin_fallback.DOCNUM = '');
