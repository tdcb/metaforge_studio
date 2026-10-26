-- dbt Model: stg_web_clicks
-- Logical Entity: Web Clicks | Subject Area: Staging
{{
  config(
    materialized='view',
    unique_key='EVENT_ID',
    schema='core',
    tags=['staging']
  )
}}

WITH source_data AS (
    SELECT *
    FROM {{ source('core', 'stg_web_clicks') }}
),

final AS (
    SELECT
        CAST(EVENT_ID AS NUMBER(38,0)) AS EVENT_ID, -- Event Identifier
        CAST(SESSION_ID AS VARCHAR(64)) AS SESSION_ID, -- Session Identifier
        CAST(SRC_CUSTOMER_ID AS NUMBER(38,0)) AS SRC_CUSTOMER_ID, -- Source Customer Identifier
        CAST(PAGE_PATH AS VARCHAR(200)) AS PAGE_PATH, -- Page Path
        CAST(EVENT_NAME AS VARCHAR(50)) AS EVENT_NAME, -- Event Name
        CAST(DEVICE_TYPE AS VARCHAR(25)) AS DEVICE_TYPE, -- Device Type
        CAST(EVENT_TIMESTAMP AS TIMESTAMP_NTZ(9)) AS EVENT_TIMESTAMP -- Event Timestamp
    FROM source_data
)

SELECT * FROM final
