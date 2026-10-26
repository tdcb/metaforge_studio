-- dbt Model: dim_vehicle
-- Logical Entity: Vehicle | Subject Area: Core
{{
  config(
    materialized='table',
    unique_key='VEHICLE_ID',
    schema='core',
    tags=['core', 'mart']
  )
}}

WITH base_dim_vehicle AS (
    SELECT *
    FROM {{ source('core', 'dim_vehicle') }}
),

final AS (
    SELECT
        CAST(VEHICLE_ID AS NUMBER(38,0)) AS VEHICLE_ID, -- Vehicle Identifier
        CAST(VIN_NBR AS VARCHAR(255)) AS VIN_NBR, -- Vin Number
        CAST(MAKE AS VARCHAR(255)) AS MAKE, -- Make
        CAST(MODEL AS VARCHAR(255)) AS MODEL, -- Model
        CAST(YEAR AS NUMBER(38,0)) AS YEAR, -- Year
        CAST(ODOMETER_MILES AS NUMBER(38,0)) AS ODOMETER_MILES -- Odometer Miles
    FROM base_dim_vehicle
)

SELECT * FROM final
