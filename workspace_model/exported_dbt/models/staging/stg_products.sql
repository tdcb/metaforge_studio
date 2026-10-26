-- dbt Model: stg_products
-- Logical Entity: Products | Subject Area: Staging
{{
  config(
    materialized='view',
    unique_key='SRC_PRODUCT_SKU',
    schema='core',
    tags=['staging']
  )
}}

WITH source_data AS (
    SELECT *
    FROM {{ source('core', 'stg_products') }}
),

final AS (
    SELECT
        CAST(SRC_PRODUCT_SKU AS VARCHAR(40)) AS SRC_PRODUCT_SKU, -- Source Product Sku
        CAST(PRODUCT_NAME AS VARCHAR(150)) AS PRODUCT_NAME, -- Product Name
        CAST(CATEGORY AS VARCHAR(50)) AS CATEGORY, -- Category
        CAST(BRAND AS VARCHAR(50)) AS BRAND, -- Brand
        CAST(UNIT_COST AS NUMBER(10,2)) AS UNIT_COST, -- Unit Cost
        CAST(LIST_PRICE AS NUMBER(10,2)) AS LIST_PRICE, -- List Price
        CAST(INVENTORY_COUNT AS NUMBER(38,0)) AS INVENTORY_COUNT, -- Inventory Count
        CAST(SUPPLIER_NAME AS VARCHAR(100)) AS SUPPLIER_NAME, -- Supplier Name
        CAST(INGESTION_TIMESTAMP AS TIMESTAMP_NTZ(9)) AS INGESTION_TIMESTAMP -- Ingestion Timestamp
    FROM source_data
)

SELECT * FROM final
