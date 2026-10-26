-- dbt Model: client_test_summary
-- Logical Entity: Client Test Summary | Subject Area: Core
{{
  config(
    materialized='view',
    schema='core',
    tags=['core', 'mart']
  )
}}

WITH base_client_test_summary AS (
    SELECT *
    FROM {{ source('core', 'client_test_summary') }}
),

final AS (
    SELECT
        CAST(VIEW_ID AS NUMBER(38,0)) AS VIEW_ID -- View Identifier
    FROM base_client_test_summary
)

SELECT * FROM final
