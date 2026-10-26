-- dbt Model: mart_product_category_performance
-- Logical Entity: Mart Product Category Performance | Subject Area: Consumption
{{
  config(
    materialized='view',
    schema='core',
    tags=['consumption', 'mart']
  )
}}

WITH base_mart_product_category_performance AS (
    SELECT *
    FROM {{ source('core', 'mart_product_category_performance') }}
),

ref_fct_order_items AS (
    SELECT *
    FROM {{ ref('fct_order_items') }}
),

ref_dim_product AS (
    SELECT *
    FROM {{ ref('dim_product') }}
),

final AS (
    SELECT
        CAST(PRODUCT_CATEGORY AS VARCHAR(255)) AS PRODUCT_CATEGORY, -- Product Category
        CAST(ITEMS_SOLD_COUNT AS NUMBER(38,0)) AS ITEMS_SOLD_COUNT, -- Items Sold Count
        CAST(CATEGORY_NET_SALES_AMT AS NUMBER(18,2)) AS CATEGORY_NET_SALES_AMT, -- Category Net Sales Amount
        CAST(CATEGORY_GROSS_PROFIT_AMT AS NUMBER(18,2)) AS CATEGORY_GROSS_PROFIT_AMT, -- Category Gross Profit Amount
        CAST(AVG_SELLING_PRICE_AMT AS NUMBER(18,2)) AS AVG_SELLING_PRICE_AMT -- Average Selling Price Amount
    FROM base_mart_product_category_performance
)

SELECT * FROM final
