-- dbt Model: dim_customer
-- Logical Entity: Customer Dimension | Subject Area: Live
{{
  config(
    materialized='table',
    unique_key='CUST_ID',
    schema='core',
    tags=['live', 'mart']
  )
}}

WITH base_dim_customer AS (
    SELECT *
    FROM {{ source('core', 'dim_customer') }}
),

final AS (
    SELECT
        CAST(CUST_ID AS NUMBER(38,0)) AS CUST_ID, -- Customer Identifier
        CAST(CUST_FULL_NM AS VARCHAR(150)) AS CUST_FULL_NM, -- Customer Full Name [RESTRICTED_PII]
        CAST(CUST_EMAIL_ADDR AS VARCHAR(255)) AS CUST_EMAIL_ADDR, -- Customer Email Address [RESTRICTED_PII]
        CAST(TAX_ID_NBR AS VARCHAR(20)) AS TAX_ID_NBR, -- Tax Identifier Number [RESTRICTED_PII]
        CAST(CUST_STAT_CD AS VARCHAR(20)) AS CUST_STAT_CD, -- Customer Status Code
        CAST(REC_CRTD_TS AS TIMESTAMP_NTZ(9)) AS REC_CRTD_TS -- Record Created Timestamp
    FROM base_dim_customer
)

SELECT * FROM final
