-- dbt Model: stg_raw_claims
-- Logical Entity: Staging Raw Claims | Subject Area: Claims
{{
  config(
    materialized='view',
    unique_key='RAW_CLM_PAYLOAD_ID',
    schema='staging',
    tags=['claims', 'staging', 'bronze', 'guidewire_raw']
  )
}}

WITH source_data AS (
    SELECT *
    FROM {{ source('staging', 'stg_raw_claims') }}
),

final AS (
    SELECT
        CAST(RAW_CLM_PAYLOAD_ID AS NUMBER(38,0)) AS RAW_CLM_PAYLOAD_ID, -- Raw Claim Payload Identifier
        CAST(CLM_ID AS NUMBER(38,0)) AS CLM_ID, -- Claim Identifier
        CAST(SRC_CLM_NBR AS VARCHAR(30)) AS SRC_CLM_NBR, -- Source Claim Number [INTERNAL]
        CAST(CLAIMANT_TAX_ID_NBR AS VARCHAR(50)) AS CLAIMANT_TAX_ID_NBR, -- Claimant Tax Identifier Number [RESTRICTED_PII]
        CAST(INGESTED_TS AS TIMESTAMP_NTZ(9)) AS INGESTED_TS -- Ingested Timestamp
    FROM source_data
)

SELECT * FROM final
