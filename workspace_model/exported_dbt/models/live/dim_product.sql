-- dbt Model: dim_product
-- Logical Entity: Product | Subject Area: Live
{{
  config(
    materialized='table',
    unique_key='PRODUCT_KEY',
    schema='core',
    tags=['live', 'mart']
  )
}}

WITH base_dim_product AS (
    SELECT *
    FROM {{ source('core', 'dim_product') }}
),

final AS (
    SELECT
        CAST(PRODUCT_KEY AS NUMBER(38,0)) AS PRODUCT_KEY, -- Product Key
        CAST(PRODUCT_SKU_NK AS VARCHAR(40)) AS PRODUCT_SKU_NK, -- Product Sku Nk
        CAST(PRODUCT_NAME AS VARCHAR(150)) AS PRODUCT_NAME, -- Product Name
        CAST(CATEGORY_NAME AS VARCHAR(50)) AS CATEGORY_NAME, -- Category Name
        CAST(BRAND_NAME AS VARCHAR(50)) AS BRAND_NAME, -- Brand Name
        CAST(UNIT_COST_AMT AS NUMBER(12,2)) AS UNIT_COST_AMT, -- Unit Cost Amount [CONFIDENTIAL]
        CAST(LIST_PRICE_AMT AS NUMBER(12,2)) AS LIST_PRICE_AMT, -- List Price Amount [CONFIDENTIAL]
        CAST(MARGIN_PCT AS NUMBER(6,2)) AS MARGIN_PCT, -- Margin Percentage
        CAST(CURRENT_INVENTORY_QTY AS NUMBER(38,0)) AS CURRENT_INVENTORY_QTY -- Current Inventory Quantity
    FROM base_dim_product
)

SELECT * FROM final
