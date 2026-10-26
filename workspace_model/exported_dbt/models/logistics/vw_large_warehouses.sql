-- dbt Model: vw_large_warehouses
-- Logical Entity: Large Warehouses View | Subject Area: Logistics
{{
  config(
    materialized='view',
    schema='core',
    tags=['logistics', 'mart']
  )
}}

WITH base_vw_large_warehouses AS (
    SELECT *
    FROM {{ source('core', 'vw_large_warehouses') }}
),

ref_dim_warehouse AS (
    SELECT *
    FROM {{ ref('dim_warehouse') }}
),

final AS (
    SELECT
        CAST(WAREHOUSE_ID AS NUMBER(38,0)) AS WAREHOUSE_ID, -- Warehouse Identifier
        CAST(WAREHOUSE_NM AS VARCHAR(255)) AS WAREHOUSE_NM -- Warehouse Name
    FROM base_vw_large_warehouses
)

SELECT * FROM final
