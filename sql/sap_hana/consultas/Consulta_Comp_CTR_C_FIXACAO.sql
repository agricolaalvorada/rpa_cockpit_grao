WITH zmmt_base AS (
    SELECT
        zmmt.MANDT,
        zmmt.ID,
        zmmt.CONTRATO,
        zmmt."DATA",
        zmmt.QTDE,
        zmmt.VALOR,
        zmmt.MIRO_DATA,
        zmmt.MIRO_HORA
    FROM ZMMT0022 zmmt
    WHERE 1 = 1
      AND zmmt.CONTRATO = ?
      AND LTRIM(zmmt.ID, '0') = LTRIM(?, '0')
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
    INNER JOIN (
        SELECT
            MATNR,
            SPART
        FROM MARA
        WHERE SPART = '01'
    ) ma
        ON po.MATNR = ma.MATNR
),

vtin2 AS (
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
        ON vxr.ID = item.NFEID
    WHERE (
        vxr.MANSTA NOT IN ('03', '04')
        OR vxr.CODESTA IN ('101')
    )
)

SELECT
    zmmt_base.MANDT         AS ZMMT_MANDT,
    zmmt_base.ID            AS ZMMT_ID,
    zmmt_base.CONTRATO      AS ZMMT_CONTRATO,
    zmmt_base."DATA"        AS ZMMT_DATA,
    zmmt_base.QTDE          AS ZMMT_QTDE,
    zmmt_base.VALOR         AS ZMMT_VALOR,
    zmmt_base.MIRO_DATA     AS ZMMT_MIRO_DATA,
    zmmt_base.MIRO_HORA     AS ZMMT_MIRO_HORA,

    ctr.MANDT               AS CTR_MANDT,
    ctr.BUKRS,
    ctr.EBELN,
    ctr.KONNR,
    ctr.LIFNR,
    ctr.NAME,
    ctr.CPF_CNPJ,
    ctr.IE,
    ctr.NAME1_TEXT,

    vtin2.PARCEIRO,
    vtin2.LOCAL,
    vtin2.DT_CRIACAO,
    vtin2.DOCNUM,
    vtin2.PESO_LIQUIDO,
    vtin2.VLR_NF,
    vtin2.VTIN_STATUS,
    vtin2.VTIN_COD_STATUS_SEFAZ,
    vtin2.VTIN_XML,
    vtin2.ITEM,
    vtin2.NCM,
    vtin2.CFOP,
    vtin2.VTIN_COD_PARCEIRO,
    vtin2.VTIN_DT_CRIACAO,
    vtin2.VTIN_HR_CRIACAO,
    vtin2.VTIN_DT_EMISSAO,
    vtin2.VTIN_CPF_CNPJ,
    vtin2.VTIN_MODELO,
    vtin2.VTIN_EMPRESA,
    vtin2.VTIN_CENTRO,
    vtin2.VTIN_NF_NUM,
    vtin2.VTIN_SERIE,
    vtin2.DIG_VER,
    vtin2.NUM_ALEATORIO,
    vtin2.N_LOG,
    vtin2.VTIN_ANO,
    vtin2.VTIN_MES,
    vtin2.VTIN_QTDE,
    vtin2.VTIN_VLR_NF,
    vtin2.A_VTIN_VLR_NF,

    GREATEST(COALESCE(vtin2.VTIN_VLR_NF, 0), COALESCE(vtin2.A_VTIN_VLR_NF, 0)) AS RESULTADO
FROM zmmt_base
INNER JOIN ctr
    ON ctr.EBELN = zmmt_base.CONTRATO
INNER JOIN vtin2
    ON LTRIM(ctr.CPF_CNPJ, '0') = LTRIM(vtin2.VTIN_CPF_CNPJ, '0')
   AND zmmt_base.QTDE IS NOT NULL
   AND ROUND(zmmt_base.QTDE, 3) = ROUND(vtin2.VTIN_QTDE, 3)
   AND (
        ROUND(zmmt_base.VALOR, 2) = ROUND(vtin2.VTIN_VLR_NF, 2)
        OR ROUND(zmmt_base.VALOR, 2) = ROUND(vtin2.A_VTIN_VLR_NF, 2)
   )
WHERE 1 = 1
  AND YEAR(vtin2.VTIN_DT_CRIACAO) = {ano};
