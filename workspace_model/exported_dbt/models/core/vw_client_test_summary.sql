-- dbt Model: vw_client_test_summary
-- Logical Entity: Client Test Summary | Subject Area: Core
{{
  config(
    materialized='view',
    schema='core',
    tags=['core', 'mart']
  )
}}

WITH base_vw_client_test_summary AS (
    SELECT *
    FROM {{ source('core', 'vw_client_test_summary') }}
),

final AS (
    SELECT
        CAST(ID AS NUMBER(38,0)) AS ID -- View Identifier
    FROM base_vw_client_test_summary
)

SELECT * FROM final
