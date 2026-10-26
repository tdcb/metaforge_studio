-- dbt Model: dim_underwriter
-- Logical Entity: Underwriter | Subject Area: Finance
{{
  config(
    materialized='table',
    unique_key='UW_ID',
    schema='finance',
    tags=['finance', 'mart']
  )
}}

WITH base_dim_underwriter AS (
    SELECT *
    FROM {{ source('finance', 'dim_underwriter') }}
),

final AS (
    SELECT
        CAST(UW_ID AS NUMBER(38,0)) AS UW_ID, -- Uw Identifier
        CAST(UW_FULL_NM AS VARCHAR(100)) AS UW_FULL_NM -- Uw Full Name [RESTRICTED_PII]
    FROM base_dim_underwriter
)

SELECT * FROM final
