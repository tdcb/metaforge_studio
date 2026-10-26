-- dbt Model: to
-- Logical Entity: To | Subject Area: Core
{{
  config(
    materialized='view',
    schema='core',
    tags=['core', 'mart']
  )
}}

WITH base_to AS (
    SELECT *
    FROM {{ source('core', 'to') }}
),

ref_dim_customer AS (
    SELECT *
    FROM {{ ref('dim_customer') }}
),

ref_dim_insurance_policy AS (
    SELECT *
    FROM {{ ref('dim_insurance_policy') }}
),

ref_fct_claim_transaction AS (
    SELECT *
    FROM {{ ref('fct_claim_transaction') }}
),

final AS (
    SELECT
        CAST(ID AS NUMBER(38,0)) AS ID -- View Identifier
    FROM base_to
)

SELECT * FROM final
