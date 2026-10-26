-- dbt Model: vw_active_customers
-- Logical Entity: Active Customers | Subject Area: Core
{{
  config(
    materialized='view',
    schema='core',
    tags=['core', 'mart']
  )
}}

WITH base_vw_active_customers AS (
    SELECT *
    FROM {{ source('core', 'vw_active_customers') }}
),

ref_dim_customer AS (
    SELECT *
    FROM {{ ref('dim_customer') }}
),

final AS (
    SELECT
        CAST(ID AS NUMBER(38,0)) AS ID -- View ID
    FROM base_vw_active_customers
)

SELECT * FROM final
