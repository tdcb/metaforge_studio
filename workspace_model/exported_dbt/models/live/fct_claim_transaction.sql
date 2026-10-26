-- dbt Model: fct_claim_transaction
-- Logical Entity: Claim Transaction | Subject Area: Live
{{
  config(
    materialized='table',
    unique_key='CLM_TXN_ID',
    schema='core',
    tags=['live', 'mart']
  )
}}

WITH base_fct_claim_transaction AS (
    SELECT *
    FROM {{ source('core', 'fct_claim_transaction') }}
),

ref_dim_insurance_policy AS (
    SELECT *
    FROM {{ ref('dim_insurance_policy') }}
),

ref_dim_customer AS (
    SELECT *
    FROM {{ ref('dim_customer') }}
),

final AS (
    SELECT
        CAST(CLM_TXN_ID AS NUMBER(38,0)) AS CLM_TXN_ID, -- Claim Transaction Identifier
        CAST(PLCY_ID AS NUMBER(38,0)) AS PLCY_ID, -- Policy Identifier
        CAST(CUST_ID AS NUMBER(38,0)) AS CUST_ID, -- Customer Identifier
        CAST(CLM_RPTD_DT AS DATE) AS CLM_RPTD_DT, -- Claim Reported Date
        CAST(CLM_LOSS_AMT AS NUMBER(18,2)) AS CLM_LOSS_AMT, -- Claim Loss Amount [CONFIDENTIAL]
        CAST(CLM_PAID_AMT AS NUMBER(18,2)) AS CLM_PAID_AMT, -- Claim Paid Amount [CONFIDENTIAL]
        CAST(CLM_STAT_CD AS VARCHAR(20)) AS CLM_STAT_CD -- Claim Status Code
    FROM base_fct_claim_transaction
)

SELECT * FROM final
