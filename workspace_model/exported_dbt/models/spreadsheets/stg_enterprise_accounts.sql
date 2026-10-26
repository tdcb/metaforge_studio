-- dbt Model: stg_enterprise_accounts
-- Logical Entity: Enterprise Accounts | Subject Area: Spreadsheets
{{
  config(
    materialized='table',
    unique_key='CUSTOMER_ID',
    schema='core',
    tags=['spreadsheets', 'mart', 'file_import', 'excel_csv']
  )
}}

WITH base_stg_enterprise_accounts AS (
    SELECT *
    FROM {{ source('core', 'stg_enterprise_accounts') }}
),

final AS (
    SELECT
        CAST(CUSTOMER_ID AS NUMBER(38,0)) AS CUSTOMER_ID, -- Customer Identifier
        CAST(CUSTOMER_NAME AS VARCHAR(255)) AS CUSTOMER_NAME, -- Customer Name
        CAST(ANNUAL_SPEND AS DECIMAL(18,4)) AS ANNUAL_SPEND, -- Annual Spend [CONFIDENTIAL]
        CAST(IS_VIP AS BOOLEAN) AS IS_VIP, -- Is Vip
        CAST(SIGNUP_DATE AS DATE) AS SIGNUP_DATE -- Signup Date
    FROM base_stg_enterprise_accounts
)

SELECT * FROM final
