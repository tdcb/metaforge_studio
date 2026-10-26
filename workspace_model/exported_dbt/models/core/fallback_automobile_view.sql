-- dbt Model: fallback_automobile_view
-- Logical Entity: Fallback Automobile View | Subject Area: Core
{{
  config(
    materialized='view',
    schema='core',
    tags=['core', 'mart']
  )
}}

WITH base_fallback_automobile_view AS (
    SELECT *
    FROM {{ source('core', 'fallback_automobile_view') }}
),

final AS (
    SELECT
        CAST(VIEW_ID AS NUMBER(38,0)) AS VIEW_ID -- View Identifier
    FROM base_fallback_automobile_view
)

SELECT * FROM final
