-- dbt Model: vw_policy_claim_summary
-- Logical Entity: Policy Claim Executive Summary View | Subject Area: Claims
{{
  config(
    materialized='view',
    unique_key='PLCY_ID',
    schema='claims',
    tags=['claims', 'mart', 'gold', 'executive_view']
  )
}}

WITH base_vw_policy_claim_summary AS (
    SELECT *
    FROM {{ source('claims', 'vw_policy_claim_summary') }}
),

ref_dim_policy AS (
    SELECT *
    FROM {{ ref('dim_policy') }}
),

ref_fct_claim AS (
    SELECT *
    FROM {{ ref('fct_claim') }}
),

final AS (
    SELECT
        CAST(PLCY_ID AS NUMBER(38,0)) AS PLCY_ID, -- Policy Identifier
        CAST(PLCY_NBR AS VARCHAR(30)) AS PLCY_NBR, -- Policy Number
        CAST(TOTAL_CLM_PAID_AMT AS NUMBER(18,2)) AS TOTAL_CLM_PAID_AMT, -- Total Claim Paid Amount [CONFIDENTIAL]
        CAST(TOTAL_CLM_RESERVE_AMT AS NUMBER(18,2)) AS TOTAL_CLM_RESERVE_AMT -- Total Claim Reserve Amount [CONFIDENTIAL]
    FROM base_vw_policy_claim_summary
)

SELECT * FROM final
