-- dbt Model: fct_insrnc_clm_fct
-- Logical Entity: Insurance Claim Fact | Subject Area: Claims
{{
  config(
    materialized='incremental',
    unique_key='CLM_ID',
    schema='claims',
    tags=['claims', 'mart', 'gold', 'claims_mart', 'actuarial']
  )
}}

WITH base_fct_insrnc_clm_fct AS (
    SELECT *
    FROM {{ source('claims', 'fct_insrnc_clm_fct') }}
),

ref_dim_insrnc_plcy AS (
    SELECT *
    FROM {{ ref('dim_insrnc_plcy') }}
),

ref_dim_cust AS (
    SELECT *
    FROM {{ ref('dim_cust') }}
),

ref_stg_raw_claims AS (
    SELECT *
    FROM {{ ref('stg_raw_claims') }}
),

final AS (
    SELECT
        CAST(CLM_ID AS NUMBER(38,0)) AS CLM_ID, -- Claim Identifier
        CAST(PLCY_ID AS NUMBER(38,0)) AS PLCY_ID, -- Policy Identifier
        CAST(CUST_ID AS NUMBER(38,0)) AS CUST_ID, -- Customer Identifier
        CAST(CLM_NBR AS VARCHAR(30)) AS CLM_NBR, -- Claim Number [INTERNAL]
        CAST(CLM_INCURRED_DT AS DATE) AS CLM_INCURRED_DT, -- Claim Incurred Date
        CAST(CLM_PAID_AMT AS NUMBER(18,2)) AS CLM_PAID_AMT, -- Claim Paid Amount [CONFIDENTIAL]
        CAST(CLM_RESERVE_AMT AS NUMBER(18,2)) AS CLM_RESERVE_AMT, -- Claim Reserve Amount [CONFIDENTIAL]
        CAST(CLM_STAT_CD AS VARCHAR(30)) AS CLM_STAT_CD, -- Claim Status Code [INTERNAL]
        CAST(REC_CRTD_TS AS TIMESTAMP_NTZ(9)) AS REC_CRTD_TS -- Record Created Timestamp
    FROM base_fct_insrnc_clm_fct
    {% if is_incremental() %}
    WHERE CLM_INCURRED_DT > (SELECT COALESCE(MAX(CLM_INCURRED_DT), '1900-01-01') FROM {{ this }})
    {% endif %}
)

SELECT * FROM final
