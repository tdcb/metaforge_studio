-- dbt Model: fct_retail_order
-- Logical Entity: Retail Order Fact | Subject Area: Finance
{{
  config(
    materialized='incremental',
    unique_key='ORD_ID',
    schema='core',
    tags=['finance', 'mart']
  )
}}

WITH base_fct_retail_order AS (
    SELECT *
    FROM {{ source('core', 'fct_retail_order') }}
),

ref_dim_customer AS (
    SELECT *
    FROM {{ ref('dim_customer') }}
),

ref_dim_product AS (
    SELECT *
    FROM {{ ref('dim_product') }}
),

ref_dim_date AS (
    SELECT *
    FROM {{ ref('dim_date') }}
),

final AS (
    SELECT
        CAST(ORD_ID AS NUMBER(38,0)) AS ORD_ID, -- Order Identifier
        CAST(CUST_ID AS NUMBER(38,0)) AS CUST_ID, -- Customer Identifier
        CAST(PROD_ID AS NUMBER(38,0)) AS PROD_ID, -- Product Identifier
        CAST(ORD_DT_KEY AS NUMBER(38,0)) AS ORD_DT_KEY, -- Order Date Identifier
        CAST(ORD_QTY AS NUMBER(10,0)) AS ORD_QTY, -- Order Quantity
        CAST(ORD_TOTAL_AMT AS NUMBER(18,2)) AS ORD_TOTAL_AMT, -- Order Total Amount [CONFIDENTIAL]
        CAST(REC_CRTD_TS AS TIMESTAMP_NTZ(9)) AS REC_CRTD_TS -- Record Created Timestamp
    FROM base_fct_retail_order
    {% if is_incremental() %}
    WHERE ORD_DT_KEY > (SELECT COALESCE(MAX(ORD_DT_KEY), '1900-01-01') FROM {{ this }})
    {% endif %}
)

SELECT * FROM final
