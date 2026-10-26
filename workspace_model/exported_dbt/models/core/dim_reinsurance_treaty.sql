-- dbt Model: dim_reinsurance_treaty
-- Logical Entity: Reinsurance Treaty Dimension | Subject Area: Core
{{
  config(
    materialized='table',
    unique_key='TREATY_SK',
    schema='core',
    tags=['core', 'mart']
  )
}}

WITH base_dim_reinsurance_treaty AS (
    SELECT *
    FROM {{ source('core', 'dim_reinsurance_treaty') }}
),

final AS (
    SELECT
        CAST(TREATY_SK AS NUMBER(38,0)) AS TREATY_SK -- Treaty Surrogate Key
    FROM base_dim_reinsurance_treaty
)

SELECT * FROM final
