-- dbt Model: dim_insurance_policy
-- Logical Entity: Insurance Policy | Subject Area: Core
{{
  config(
    materialized='table',
    unique_key='PLCY_ID',
    schema='core',
    tags=['core', 'mart']
  )
}}

WITH base_dim_insurance_policy AS (
    SELECT *
    FROM {{ source('core', 'dim_insurance_policy') }}
),

ref_dim_customer AS (
    SELECT *
    FROM {{ ref('dim_customer') }}
),

ref_dim_agent_broker AS (
    SELECT *
    FROM {{ ref('dim_agent_broker') }}
),

final AS (
    SELECT
        CAST(PLCY_ID AS NUMBER(38,0)) AS PLCY_ID, -- Policy Identifier
        CAST(PLCY_NBR AS VARCHAR(50)) AS PLCY_NBR, -- Policy Number
        CAST(CUST_ID AS NUMBER(38,0)) AS CUST_ID, -- Customer Identifier
        CAST(BRKR_ID AS NUMBER(38,0)) AS BRKR_ID, -- Broker Identifier
        CAST(CVRG_TYP_CD AS VARCHAR(30)) AS CVRG_TYP_CD, -- Coverage Type Code
        CAST(ANNUAL_PREM_AMT AS NUMBER(18,2)) AS ANNUAL_PREM_AMT, -- Annual Premium Amount [CONFIDENTIAL]
        CAST(PLCY_EFF_DT AS DATE) AS PLCY_EFF_DT, -- Policy Effective Date
        CAST(PLCY_EXP_DT AS DATE) AS PLCY_EXP_DT -- Policy Expiration Date
    FROM base_dim_insurance_policy
)

SELECT * FROM final
