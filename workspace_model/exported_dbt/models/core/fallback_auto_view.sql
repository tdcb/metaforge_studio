-- dbt Model: fallback_auto_view
-- Logical Entity: Fallback Auto View | Subject Area: Core
{{
  config(
    materialized='view',
    schema='core',
    tags=['core', 'mart']
  )
}}

WITH base_fallback_auto_view AS (
    SELECT *
    FROM {{ source('core', 'fallback_auto_view') }}
),

final AS (
    SELECT
        CAST(VIEW_ID AS NUMBER(38,0)) AS VIEW_ID -- View ID
    FROM base_fallback_auto_view
)

SELECT * FROM final
