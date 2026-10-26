-- dbt Model: stg_orders
-- Logical Entity: Orders | Subject Area: Staging
{{
  config(
    materialized='view',
    unique_key='SRC_ORDER_ID',
    schema='core',
    tags=['staging']
  )
}}

WITH source_data AS (
    SELECT *
    FROM {{ source('core', 'stg_orders') }}
),

final AS (
    SELECT
        CAST(SRC_ORDER_ID AS NUMBER(38,0)) AS SRC_ORDER_ID, -- Source Order Identifier
        CAST(SRC_CUSTOMER_ID AS NUMBER(38,0)) AS SRC_CUSTOMER_ID, -- Source Customer Identifier
        CAST(ORDER_DATETIME AS TIMESTAMP_NTZ(9)) AS ORDER_DATETIME, -- Order Datetime
        CAST(ORDER_STATUS AS VARCHAR(25)) AS ORDER_STATUS, -- Order Status
        CAST(PAYMENT_METHOD AS VARCHAR(30)) AS PAYMENT_METHOD, -- Payment Method
        CAST(SUBTOTAL_AMOUNT AS NUMBER(12,2)) AS SUBTOTAL_AMOUNT, -- Subtotal Amount
        CAST(TAX_AMOUNT AS NUMBER(10,2)) AS TAX_AMOUNT, -- Tax Amount
        CAST(SHIPPING_AMOUNT AS NUMBER(10,2)) AS SHIPPING_AMOUNT, -- Shipping Amount
        CAST(TOTAL_AMOUNT AS NUMBER(12,2)) AS TOTAL_AMOUNT, -- Total Amount
        CAST(INGESTION_TIMESTAMP AS TIMESTAMP_NTZ(9)) AS INGESTION_TIMESTAMP -- Ingestion Timestamp
    FROM source_data
)

SELECT * FROM final
