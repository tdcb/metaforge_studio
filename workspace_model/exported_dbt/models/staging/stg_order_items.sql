-- dbt Model: stg_order_items
-- Logical Entity: Order Items | Subject Area: Staging
{{
  config(
    materialized='view',
    unique_key='SRC_ITEM_ID',
    schema='core',
    tags=['staging']
  )
}}

WITH source_data AS (
    SELECT *
    FROM {{ source('core', 'stg_order_items') }}
),

final AS (
    SELECT
        CAST(SRC_ITEM_ID AS NUMBER(38,0)) AS SRC_ITEM_ID, -- Source Item Identifier
        CAST(SRC_ORDER_ID AS NUMBER(38,0)) AS SRC_ORDER_ID, -- Source Order Identifier
        CAST(SRC_PRODUCT_SKU AS VARCHAR(40)) AS SRC_PRODUCT_SKU, -- Source Product Sku
        CAST(QUANTITY AS NUMBER(38,0)) AS QUANTITY, -- Quantity
        CAST(UNIT_PRICE AS NUMBER(10,2)) AS UNIT_PRICE, -- Unit Price
        CAST(DISCOUNT_PERCENT AS NUMBER(5,2)) AS DISCOUNT_PERCENT, -- Discount Percent
        CAST(LINE_TOTAL AS NUMBER(12,2)) AS LINE_TOTAL, -- Line Total
        CAST(INGESTION_TIMESTAMP AS TIMESTAMP_NTZ(9)) AS INGESTION_TIMESTAMP -- Ingestion Timestamp
    FROM source_data
)

SELECT * FROM final
