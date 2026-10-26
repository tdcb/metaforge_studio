-- dbt Model: dim_date
-- Logical Entity: Date | Subject Area: Core
{{
  config(
    materialized='table',
    unique_key='DATE_KEY',
    schema='core',
    tags=['core', 'mart']
  )
}}

WITH base_dim_date AS (
    SELECT *
    FROM {{ source('core', 'dim_date') }}
),

final AS (
    SELECT
        CAST(DATE_KEY AS NUMBER(38,0)) AS DATE_KEY, -- Date Key
        CAST(CALENDAR_DATE AS DATE) AS CALENDAR_DATE, -- Calendar Date
        CAST(DAY_NAME AS VARCHAR(15)) AS DAY_NAME, -- Day Name
        CAST(MONTH_NUMBER AS NUMBER(38,0)) AS MONTH_NUMBER, -- Month Number
        CAST(MONTH_NAME AS VARCHAR(15)) AS MONTH_NAME, -- Month Name
        CAST(CALENDAR_QUARTER AS VARCHAR(5)) AS CALENDAR_QUARTER, -- Calendar Quarter
        CAST(CALENDAR_YEAR AS NUMBER(38,0)) AS CALENDAR_YEAR, -- Calendar Year
        CAST(IS_WEEKEND_IND AS VARCHAR(1)) AS IS_WEEKEND_IND -- Is Weekend Indicator
    FROM base_dim_date
)

SELECT * FROM final
