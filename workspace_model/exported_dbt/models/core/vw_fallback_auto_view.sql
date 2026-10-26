-- dbt Model: vw_fallback_auto_view
-- Logical Entity: Fallback Automobile View | Subject Area: Core
{{
  config(
    materialized='view',
    schema='core',
    tags=['core', 'mart']
  )
}}

WITH base_vw_fallback_auto_view AS (
    SELECT *
    FROM {{ source('core', 'vw_fallback_auto_view') }}
),

final AS (
    SELECT
        CAST(ID AS NUMBER(38,0)) AS ID -- View Identifier
    FROM base_vw_fallback_auto_view
)

SELECT * FROM final
