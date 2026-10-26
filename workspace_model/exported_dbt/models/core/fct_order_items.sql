-- dbt Model: fct_order_items
-- Logical Entity: Order Items | Subject Area: Core
{{
  config(
    materialized='table',
    unique_key='ORDER_ITEM_KEY',
    schema='core',
    tags=['core', 'mart']
  )
}}

WITH base_fct_order_items AS (
    SELECT *
    FROM {{ source('core', 'fct_order_items') }}
),

ref_fct_orders AS (
    SELECT *
    FROM {{ ref('fct_orders') }}
),

ref_dim_product AS (
    SELECT *
    FROM {{ ref('dim_product') }}
),

ref_dim_customer AS (
    SELECT *
    FROM {{ ref('dim_customer') }}
),

final AS (
    SELECT
        CAST(ORDER_ITEM_KEY AS NUMBER(38,0)) AS ORDER_ITEM_KEY, -- Order Item Key
        CAST(ORDER_KEY AS NUMBER(38,0)) AS ORDER_KEY, -- Order Key
        CAST(PRODUCT_KEY AS NUMBER(38,0)) AS PRODUCT_KEY, -- Product Key
        CAST(CUSTOMER_KEY AS NUMBER(38,0)) AS CUSTOMER_KEY, -- Customer Key
        CAST(ITEM_QUANTITY AS NUMBER(38,0)) AS ITEM_QUANTITY, -- Item Quantity
        CAST(UNIT_SELLING_PRICE_AMT AS NUMBER(12,2)) AS UNIT_SELLING_PRICE_AMT, -- Unit Selling Price Amount [CONFIDENTIAL]
        CAST(DISCOUNT_AMT AS NUMBER(10,2)) AS DISCOUNT_AMT, -- Discount Amount [CONFIDENTIAL]
        CAST(NET_SALES_AMT AS NUMBER(12,2)) AS NET_SALES_AMT, -- Net Sales Amount [CONFIDENTIAL]
        CAST(GROSS_PROFIT_AMT AS NUMBER(12,2)) AS GROSS_PROFIT_AMT -- Gross Profit Amount [CONFIDENTIAL]
    FROM base_fct_order_items
)

SELECT * FROM final
