-- dbt Model: dim_date
-- Logical Entity: Calendar Date | Subject Area: Finance
{{
  config(
    materialized='table',
    unique_key='DT_KEY',
    schema='core',
    tags=['finance', 'mart']
  )
}}

WITH base_dim_date AS (
    SELECT *
    FROM {{ source('core', 'dim_date') }}
),

final AS (
    SELECT
        CAST(DT_KEY AS NUMBER(38,0)) AS DT_KEY, -- Date Identifier
        CAST(CALENDAR_DT AS DATE) AS CALENDAR_DT, -- Calendar Date
        CAST(FISCAL_YR_NBR AS NUMBER(4,0)) AS FISCAL_YR_NBR -- Fiscal Year Number
    FROM base_dim_date
)

SELECT * FROM final
