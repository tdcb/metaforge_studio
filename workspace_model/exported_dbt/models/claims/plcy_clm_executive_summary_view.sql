-- dbt Model: plcy_clm_executive_summary_view
-- Logical Entity: Policy Claim Executive Summary View | Subject Area: Claims
{{
  config(
    materialized='view',
    unique_key='PLCY_ID',
    schema='claims',
    tags=['claims', 'mart', 'gold', 'executive_view']
  )
}}

WITH base_plcy_clm_executive_summary_view AS (
    SELECT *
    FROM {{ source('claims', 'plcy_clm_executive_summary_view') }}
),

ref_dim_insrnc_plcy AS (
    SELECT *
    FROM {{ ref('dim_insrnc_plcy') }}
),

ref_fct_insrnc_clm_fct AS (
    SELECT *
    FROM {{ ref('fct_insrnc_clm_fct') }}
),

final AS (
    SELECT
        CAST(PLCY_ID AS NUMBER(38,0)) AS PLCY_ID, -- Policy Identifier
        CAST(PLCY_NBR AS VARCHAR(30)) AS PLCY_NBR, -- Policy Number
        CAST(TOT_CLM_PAID_AMT AS NUMBER(18,2)) AS TOT_CLM_PAID_AMT, -- Total Claim Paid Amount [CONFIDENTIAL]
        CAST(TOT_CLM_RESERVE_AMT AS NUMBER(18,2)) AS TOT_CLM_RESERVE_AMT -- Total Claim Reserve Amount [CONFIDENTIAL]
    FROM base_plcy_clm_executive_summary_view
)

SELECT * FROM final
