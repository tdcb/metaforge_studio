-- dbt Model: fct_orders
-- Logical Entity: Orders Fact Table | Subject Area: Live
{{
  config(
    materialized='table',
    unique_key='ORDER_KEY',
    schema='core',
    tags=['live', 'mart']
  )
}}

WITH base_fct_orders AS (
    SELECT *
    FROM {{ source('core', 'fct_orders') }}
),

ref_dim_customer AS (
    SELECT *
    FROM {{ ref('dim_customer') }}
),

ref_dim_date AS (
    SELECT *
    FROM {{ ref('dim_date') }}
),

final AS (
    SELECT
        CAST(ORDER_KEY AS NUMBER(38,0)) AS ORDER_KEY, -- Order Key
        CAST(ORDER_ID_NK AS NUMBER(38,0)) AS ORDER_ID_NK, -- Order Identifier Nk
        CAST(CUSTOMER_KEY AS NUMBER(38,0)) AS CUSTOMER_KEY, -- Customer Key
        CAST(ORDER_DATE_KEY AS NUMBER(38,0)) AS ORDER_DATE_KEY, -- Order Date Key
        CAST(ORDER_STATUS_CD AS VARCHAR(20)) AS ORDER_STATUS_CD, -- Order Status Code [INTERNAL]
        CAST(PAYMENT_METHOD_CD AS VARCHAR(20)) AS PAYMENT_METHOD_CD, -- Payment Method Code [INTERNAL]
        CAST(SUBTOTAL_AMT AS NUMBER(12,2)) AS SUBTOTAL_AMT, -- Subtotal Amount [CONFIDENTIAL]
        CAST(TAX_AMT AS NUMBER(10,2)) AS TAX_AMT, -- Tax Amount [CONFIDENTIAL]
        CAST(SHIPPING_AMT AS NUMBER(10,2)) AS SHIPPING_AMT, -- Shipping Amount [CONFIDENTIAL]
        CAST(TOTAL_ORDER_AMT AS NUMBER(12,2)) AS TOTAL_ORDER_AMT, -- Total Order Amount [CONFIDENTIAL]
        CAST(ORDER_ITEM_COUNT AS NUMBER(38,0)) AS ORDER_ITEM_COUNT -- Order Item Count
    FROM base_fct_orders
)

SELECT * FROM final
