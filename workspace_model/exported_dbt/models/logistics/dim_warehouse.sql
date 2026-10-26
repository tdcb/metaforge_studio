-- dbt Model: dim_warehouse
-- Logical Entity: Warehouse | Subject Area: Logistics
{{
  config(
    materialized='table',
    unique_key='WAREHOUSE_ID',
    schema='core',
    tags=['logistics', 'mart']
  )
}}

WITH base_dim_warehouse AS (
    SELECT *
    FROM {{ source('core', 'dim_warehouse') }}
),

final AS (
    SELECT
        CAST(WAREHOUSE_ID AS NUMBER(38,0)) AS WAREHOUSE_ID, -- Warehouse Identifier
        CAST(WAREHOUSE_NM AS VARCHAR(255)) AS WAREHOUSE_NM, -- Warehouse Name
        CAST(CAPACITY_SQFT AS NUMBER(38,0)) AS CAPACITY_SQFT -- Capacity Sqft
    FROM base_dim_warehouse
)

SELECT * FROM final
