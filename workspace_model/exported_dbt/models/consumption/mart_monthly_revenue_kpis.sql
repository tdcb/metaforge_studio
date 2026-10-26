-- dbt Model: mart_monthly_revenue_kpis
-- Logical Entity: Mart Monthly Revenue Key Performance Indicators | Subject Area: Consumption
{{
  config(
    materialized='view',
    schema='core',
    tags=['consumption', 'mart']
  )
}}

WITH base_mart_monthly_revenue_kpis AS (
    SELECT *
    FROM {{ source('core', 'mart_monthly_revenue_kpis') }}
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
        CAST(REPORTING_YEAR AS VARCHAR(255)) AS REPORTING_YEAR, -- Reporting Year
        CAST(REPORTING_MONTH AS VARCHAR(255)) AS REPORTING_MONTH, -- Reporting Month
        CAST(TOTAL_ORDERS_COUNT AS NUMBER(38,0)) AS TOTAL_ORDERS_COUNT, -- Total Orders Count
        CAST(GROSS_REVENUE_AMT AS NUMBER(18,2)) AS GROSS_REVENUE_AMT, -- Gross Revenue Amount
        CAST(TOTAL_TAX_AMT AS NUMBER(18,2)) AS TOTAL_TAX_AMT, -- Total Tax Amount
        CAST(TOTAL_SHIPPING_AMT AS NUMBER(18,2)) AS TOTAL_SHIPPING_AMT, -- Total Shipping Amount
        CAST(ACTIVE_BUYING_CUSTOMERS AS NUMBER(38,0)) AS ACTIVE_BUYING_CUSTOMERS -- Active Buying Customers
    FROM base_mart_monthly_revenue_kpis
)

SELECT * FROM final
