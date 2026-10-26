-- dbt Model: stg_customers
-- Logical Entity: Customers | Subject Area: Staging
{{
  config(
    materialized='view',
    unique_key='SRC_CUSTOMER_ID',
    schema='core',
    tags=['staging']
  )
}}

WITH source_data AS (
    SELECT *
    FROM {{ source('core', 'stg_customers') }}
),

final AS (
    SELECT
        CAST(SRC_CUSTOMER_ID AS NUMBER(38,0)) AS SRC_CUSTOMER_ID, -- Source Customer Identifier
        CAST(FIRST_NAME AS VARCHAR(50)) AS FIRST_NAME, -- First Name
        CAST(LAST_NAME AS VARCHAR(50)) AS LAST_NAME, -- Last Name
        CAST(EMAIL AS VARCHAR(120)) AS EMAIL, -- Email [RESTRICTED_PII]
        CAST(PHONE AS VARCHAR(30)) AS PHONE, -- Phone [RESTRICTED_PII]
        CAST(CITY AS VARCHAR(60)) AS CITY, -- City
        CAST(COUNTRY_CODE AS VARCHAR(3)) AS COUNTRY_CODE, -- Country Code
        CAST(REGISTRATION_DATE AS DATE) AS REGISTRATION_DATE, -- Registration Date
        CAST(STATUS AS VARCHAR(20)) AS STATUS, -- Status
        CAST(INGESTION_TIMESTAMP AS TIMESTAMP_NTZ(9)) AS INGESTION_TIMESTAMP -- Ingestion Timestamp
    FROM source_data
)

SELECT * FROM final
