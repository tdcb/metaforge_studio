-- dbt Model: mart_customer_lifetime_value
-- Logical Entity: Mart Customer Lifetime Value | Subject Area: Consumption
{{
  config(
    materialized='view',
    schema='core',
    tags=['consumption', 'mart']
  )
}}

WITH base_mart_customer_lifetime_value AS (
    SELECT *
    FROM {{ source('core', 'mart_customer_lifetime_value') }}
),

ref_dim_customer AS (
    SELECT *
    FROM {{ ref('dim_customer') }}
),

ref_fct_orders AS (
    SELECT *
    FROM {{ ref('fct_orders') }}
),

ref_dim_date AS (
    SELECT *
    FROM {{ ref('dim_date') }}
),

final AS (
    SELECT
        CAST(CUSTOMER_KEY AS NUMBER(38,0)) AS CUSTOMER_KEY, -- Customer Key
        CAST(CUSTOMER_NAME AS VARCHAR(255)) AS CUSTOMER_NAME, -- Customer Name
        CAST(CUSTOMER_STATUS AS VARCHAR(255)) AS CUSTOMER_STATUS, -- Customer Status
        CAST(LIFETIME_ORDERS_COUNT AS NUMBER(38,0)) AS LIFETIME_ORDERS_COUNT, -- Lifetime Orders Count
        CAST(FIRST_PURCHASE_DATE AS VARCHAR(255)) AS FIRST_PURCHASE_DATE, -- First Purchase Date
        CAST(LATEST_PURCHASE_DATE AS VARCHAR(255)) AS LATEST_PURCHASE_DATE, -- Latest Purchase Date
        CAST(LIFETIME_NET_SPEND_AMT AS NUMBER(18,2)) AS LIFETIME_NET_SPEND_AMT, -- Lifetime Net Spend Amount
        CAST(AVG_ORDER_BASKET_AMT AS NUMBER(18,2)) AS AVG_ORDER_BASKET_AMT -- Average Order Basket Amount
    FROM base_mart_customer_lifetime_value
)

SELECT * FROM final
