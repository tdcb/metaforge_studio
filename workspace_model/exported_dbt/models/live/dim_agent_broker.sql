-- dbt Model: dim_agent_broker
-- Logical Entity: Agent Broker | Subject Area: Live
{{
  config(
    materialized='table',
    unique_key='BRKR_ID',
    schema='core',
    tags=['live', 'mart']
  )
}}

WITH base_dim_agent_broker AS (
    SELECT *
    FROM {{ source('core', 'dim_agent_broker') }}
),

final AS (
    SELECT
        CAST(BRKR_ID AS NUMBER(38,0)) AS BRKR_ID, -- Broker Identifier
        CAST(BRKR_FULL_NM AS VARCHAR(150)) AS BRKR_FULL_NM, -- Broker Full Name [RESTRICTED_PII]
        CAST(BRKR_EMAIL_ADDR AS VARCHAR(255)) AS BRKR_EMAIL_ADDR, -- Broker Email Address [RESTRICTED_PII]
        CAST(BRKR_REGION_CD AS VARCHAR(30)) AS BRKR_REGION_CD, -- Broker Region Code
        CAST(COMMISSION_RATE_PCT AS NUMBER(5,2)) AS COMMISSION_RATE_PCT, -- Commission Rate Percentage
        CAST(ACTIVE_IND AS VARCHAR(1)) AS ACTIVE_IND -- Active Indicator
    FROM base_dim_agent_broker
)

SELECT * FROM final
