-- dbt Model: dim_product
-- Logical Entity: Product | Subject Area: Finance
{{
  config(
    materialized='table',
    unique_key='PROD_ID',
    schema='core',
    tags=['finance', 'mart']
  )
}}

WITH base_dim_product AS (
    SELECT *
    FROM {{ source('core', 'dim_product') }}
),

final AS (
    SELECT
        CAST(PROD_ID AS NUMBER(38,0)) AS PROD_ID, -- Product Identifier
        CAST(PROD_SKU_CD AS VARCHAR(30)) AS PROD_SKU_CD, -- Product SKU Code
        CAST(PROD_DESC AS VARCHAR(255)) AS PROD_DESC, -- Product Description
        CAST(UNIT_LIST_PRICE_AMT AS NUMBER(18,2)) AS UNIT_LIST_PRICE_AMT -- Unit List Price Amount
    FROM base_dim_product
)

SELECT * FROM final
