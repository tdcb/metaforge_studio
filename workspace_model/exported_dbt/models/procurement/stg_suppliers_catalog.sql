-- dbt Model: stg_suppliers_catalog
-- Logical Entity: Suppliers Catalog | Subject Area: Procurement
{{
  config(
    materialized='table',
    unique_key='SUPPLIER_ID',
    schema='core',
    tags=['procurement', 'mart', 'file_import', 'excel_csv']
  )
}}

WITH base_stg_suppliers_catalog AS (
    SELECT *
    FROM {{ source('core', 'stg_suppliers_catalog') }}
),

final AS (
    SELECT
        CAST(SUPPLIER_ID AS NUMBER(38,0)) AS SUPPLIER_ID, -- Supplier Identifier
        CAST(SUPPLIER_NAME AS VARCHAR(255)) AS SUPPLIER_NAME -- Supplier Name
    FROM base_stg_suppliers_catalog
)

SELECT * FROM final
