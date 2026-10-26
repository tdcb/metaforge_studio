-- dbt Model: dim_policy
-- Logical Entity: Insurance Policy | Subject Area: Core
{{
  config(
    materialized='table',
    unique_key='PLCY_ID',
    schema='core',
    tags=['core', 'mart', 'gold', 'underwriting']
  )
}}

WITH base_dim_policy AS (
    SELECT *
    FROM {{ source('core', 'dim_policy') }}
),

ref_dim_customer AS (
    SELECT *
    FROM {{ ref('dim_customer') }}
),

final AS (
    SELECT
        CAST(PLCY_ID AS NUMBER(38,0)) AS PLCY_ID, -- Policy Identifier
        CAST(CUST_ID AS NUMBER(38,0)) AS CUST_ID, -- Customer Identifier
        CAST(PLCY_NBR AS VARCHAR(30)) AS PLCY_NBR, -- Policy Number [INTERNAL]
        CAST(PLCY_EFF_DT AS DATE) AS PLCY_EFF_DT, -- Policy Effective Date
        CAST(PLCY_EXP_DT AS DATE) AS PLCY_EXP_DT, -- Policy Expiration Date
        CAST(ANNUAL_PREM_AMT AS NUMBER(18,2)) AS ANNUAL_PREM_AMT, -- Annual Premium Amount [CONFIDENTIAL]
        CAST(REC_CRTD_TS AS TIMESTAMP_NTZ(9)) AS REC_CRTD_TS -- Record Created Timestamp
    FROM base_dim_policy
)

SELECT * FROM final
