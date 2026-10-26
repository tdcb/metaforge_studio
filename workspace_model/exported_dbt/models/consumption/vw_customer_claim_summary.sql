-- dbt Model: vw_customer_claim_summary
-- Logical Entity: Customer Claim Summary | Subject Area: Consumption
{{
  config(
    materialized='view',
    schema='core',
    tags=['consumption', 'mart']
  )
}}

WITH base_vw_customer_claim_summary AS (
    SELECT *
    FROM {{ source('core', 'vw_customer_claim_summary') }}
),

ref_dim_customer AS (
    SELECT *
    FROM {{ ref('dim_customer') }}
),

ref_dim_insurance_policy AS (
    SELECT *
    FROM {{ ref('dim_insurance_policy') }}
),

ref_fct_claim_transaction AS (
    SELECT *
    FROM {{ ref('fct_claim_transaction') }}
),

final AS (
    SELECT
        CAST(CUST_ID AS NUMBER(38,0)) AS CUST_ID, -- Customer Identifier
        CAST(CUST_FULL_NM AS VARCHAR(150)) AS CUST_FULL_NM, -- Customer Full Name [RESTRICTED_PII]
        CAST(PLCY_NBR AS VARCHAR(50)) AS PLCY_NBR, -- Policy Number
        CAST(TOTAL_CLM_CNT AS NUMBER(38,0)) AS TOTAL_CLM_CNT, -- Total Claim Count
        CAST(TOTAL_CLM_PAID_AMT AS NUMBER(18,2)) AS TOTAL_CLM_PAID_AMT -- Total Claim Paid Amount
    FROM base_vw_customer_claim_summary
)

SELECT * FROM final
