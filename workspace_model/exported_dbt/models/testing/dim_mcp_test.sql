-- dbt Model: dim_mcp_test
-- Logical Entity: MCP Test Dimension | Subject Area: Testing
{{
  config(
    materialized='table',
    unique_key='TEST_ID',
    schema='core',
    tags=['testing', 'mart']
  )
}}

WITH base_dim_mcp_test AS (
    SELECT *
    FROM {{ source('core', 'dim_mcp_test') }}
),

final AS (
    SELECT
        CAST(TEST_ID AS NUMBER(38,0)) AS TEST_ID, -- Test Identifier
        CAST(TEST_NAME AS VARCHAR(255)) AS TEST_NAME -- Test Name
    FROM base_dim_mcp_test
)

SELECT * FROM final
