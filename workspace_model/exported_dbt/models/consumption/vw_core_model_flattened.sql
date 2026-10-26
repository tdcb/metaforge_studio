-- dbt Model: vw_core_model_flattened
-- Logical Entity: Core Model Flattened View | Subject Area: Consumption
{{
  config(
    materialized='view',
    schema='core',
    tags=['consumption', 'mart']
  )
}}

WITH base_vw_core_model_flattened AS (
    SELECT *
    FROM {{ source('core', 'vw_core_model_flattened') }}
),

ref_dim_agent_broker AS (
    SELECT *
    FROM {{ ref('dim_agent_broker') }}
),

ref_dim_customer AS (
    SELECT *
    FROM {{ ref('dim_customer') }}
),

ref_dim_date AS (
    SELECT *
    FROM {{ ref('dim_date') }}
),

ref_dim_insurance_policy AS (
    SELECT *
    FROM {{ ref('dim_insurance_policy') }}
),

ref_dim_product AS (
    SELECT *
    FROM {{ ref('dim_product') }}
),

ref_fct_claim_transaction AS (
    SELECT *
    FROM {{ ref('fct_claim_transaction') }}
),

ref_fct_orders AS (
    SELECT *
    FROM {{ ref('fct_orders') }}
),

ref_fct_order_items AS (
    SELECT *
    FROM {{ ref('fct_order_items') }}
),

ref_to AS (
    SELECT *
    FROM {{ ref('to') }}
),

final AS (
    SELECT
        CAST(CUST_ID AS NUMBER(38,0)) AS CUST_ID, -- Customer Identifier
        CAST(CUST_FULL_NM AS VARCHAR(255)) AS CUST_FULL_NM, -- Customer Full Name [RESTRICTED_PII]
        CAST(CUST_EMAIL_ADDR AS VARCHAR(255)) AS CUST_EMAIL_ADDR, -- Customer Email Address [RESTRICTED_PII]
        CAST(TAX_ID_NBR AS VARCHAR(255)) AS TAX_ID_NBR, -- Tax Identifier Number [RESTRICTED_PII]
        CAST(CUST_STAT_CD AS VARCHAR(255)) AS CUST_STAT_CD, -- Customer Status Code [INTERNAL]
        CAST(REC_CRTD_TS AS TIMESTAMP_NTZ) AS REC_CRTD_TS, -- Record Created Timestamp
        CAST(PLCY_ID AS NUMBER(38,0)) AS PLCY_ID, -- Policy Identifier
        CAST(PLCY_NBR AS VARCHAR(255)) AS PLCY_NBR, -- Policy Number
        CAST(CVRG_TYP_CD AS VARCHAR(255)) AS CVRG_TYP_CD, -- Coverage Type Code [INTERNAL]
        CAST(ANNUAL_PREM_AMT AS NUMBER(38,0)) AS ANNUAL_PREM_AMT, -- Annual Premium Amount [CONFIDENTIAL]
        CAST(PLCY_EFF_DT AS DATE) AS PLCY_EFF_DT, -- Policy Effective Date
        CAST(PLCY_EXP_DT AS DATE) AS PLCY_EXP_DT, -- Policy Expiration Date
        CAST(BRKR_ID AS NUMBER(38,0)) AS BRKR_ID, -- Brkr Identifier
        CAST(BRKR_FULL_NM AS VARCHAR(255)) AS BRKR_FULL_NM, -- Brkr Full Name [RESTRICTED_PII]
        CAST(BRKR_EMAIL_ADDR AS VARCHAR(255)) AS BRKR_EMAIL_ADDR, -- Brkr Email Address [RESTRICTED_PII]
        CAST(BRKR_REGION_CD AS VARCHAR(255)) AS BRKR_REGION_CD, -- Brkr Region Code [INTERNAL]
        CAST(COMMISSION_RATE_PCT AS NUMBER(38,0)) AS COMMISSION_RATE_PCT, -- Commission Rate Percentage
        CAST(BRKR_ACTIVE_IND AS VARCHAR(255)) AS BRKR_ACTIVE_IND, -- Brkr Active Indicator [INTERNAL]
        CAST(CLM_TXN_ID AS NUMBER(38,0)) AS CLM_TXN_ID, -- Claim Transaction Identifier
        CAST(CLM_RPTD_DT AS DATE) AS CLM_RPTD_DT, -- Claim Reported Date
        CAST(CLM_LOSS_AMT AS NUMBER(38,0)) AS CLM_LOSS_AMT, -- Claim Loss Amount [CONFIDENTIAL]
        CAST(CLM_PAID_AMT AS NUMBER(38,0)) AS CLM_PAID_AMT, -- Claim Paid Amount [CONFIDENTIAL]
        CAST(CLM_STAT_CD AS VARCHAR(255)) AS CLM_STAT_CD, -- Claim Status Code [INTERNAL]
        CAST(ORDER_KEY AS NUMBER(38,0)) AS ORDER_KEY, -- Order Key
        CAST(ORDER_ID_NK AS NUMBER(38,0)) AS ORDER_ID_NK, -- Order Identifier Nk
        CAST(ORDER_STATUS_CD AS VARCHAR(255)) AS ORDER_STATUS_CD, -- Order Status Code [INTERNAL]
        CAST(PAYMENT_METHOD_CD AS VARCHAR(255)) AS PAYMENT_METHOD_CD, -- Payment Method Code [INTERNAL]
        CAST(SUBTOTAL_AMT AS NUMBER(38,0)) AS SUBTOTAL_AMT, -- Subtotal Amount [CONFIDENTIAL]
        CAST(TAX_AMT AS NUMBER(38,0)) AS TAX_AMT, -- Tax Amount [CONFIDENTIAL]
        CAST(SHIPPING_AMT AS NUMBER(38,0)) AS SHIPPING_AMT, -- Shipping Amount [CONFIDENTIAL]
        CAST(TOTAL_ORDER_AMT AS NUMBER(38,0)) AS TOTAL_ORDER_AMT, -- Total Order Amount [CONFIDENTIAL]
        CAST(ORDER_ITEM_COUNT AS NUMBER(38,0)) AS ORDER_ITEM_COUNT, -- Order Item Count
        CAST(ORDER_CALENDAR_DATE AS DATE) AS ORDER_CALENDAR_DATE, -- Order Calendar Date
        CAST(ORDER_DAY_NAME AS VARCHAR(255)) AS ORDER_DAY_NAME, -- Order Day Name
        CAST(ORDER_MONTH_NUMBER AS NUMBER(38,0)) AS ORDER_MONTH_NUMBER, -- Order Month Number
        CAST(ORDER_MONTH_NAME AS VARCHAR(255)) AS ORDER_MONTH_NAME, -- Order Month Name
        CAST(ORDER_CALENDAR_QUARTER AS VARCHAR(255)) AS ORDER_CALENDAR_QUARTER, -- Order Calendar Quarter
        CAST(ORDER_CALENDAR_YEAR AS NUMBER(38,0)) AS ORDER_CALENDAR_YEAR, -- Order Calendar Year
        CAST(ORDER_IS_WEEKEND_IND AS VARCHAR(255)) AS ORDER_IS_WEEKEND_IND, -- Order Is Weekend Indicator [INTERNAL]
        CAST(ORDER_ITEM_KEY AS NUMBER(38,0)) AS ORDER_ITEM_KEY, -- Order Item Key
        CAST(ITEM_QUANTITY AS NUMBER(38,0)) AS ITEM_QUANTITY, -- Item Quantity
        CAST(UNIT_SELLING_PRICE_AMT AS NUMBER(38,0)) AS UNIT_SELLING_PRICE_AMT, -- Unit Selling Price Amount [CONFIDENTIAL]
        CAST(DISCOUNT_AMT AS NUMBER(38,0)) AS DISCOUNT_AMT, -- Discount Amount [CONFIDENTIAL]
        CAST(NET_SALES_AMT AS NUMBER(38,0)) AS NET_SALES_AMT, -- Net Sales Amount [CONFIDENTIAL]
        CAST(GROSS_PROFIT_AMT AS NUMBER(38,0)) AS GROSS_PROFIT_AMT, -- Gross Profit Amount [CONFIDENTIAL]
        CAST(PRODUCT_KEY AS NUMBER(38,0)) AS PRODUCT_KEY, -- Product Key
        CAST(PRODUCT_SKU_NK AS VARCHAR(255)) AS PRODUCT_SKU_NK, -- Product Sku Nk
        CAST(PRODUCT_NAME AS VARCHAR(255)) AS PRODUCT_NAME, -- Product Name
        CAST(CATEGORY_NAME AS VARCHAR(255)) AS CATEGORY_NAME, -- Category Name
        CAST(BRAND_NAME AS VARCHAR(255)) AS BRAND_NAME, -- Brand Name
        CAST(UNIT_COST_AMT AS NUMBER(38,0)) AS UNIT_COST_AMT, -- Unit Cost Amount [CONFIDENTIAL]
        CAST(LIST_PRICE_AMT AS NUMBER(38,0)) AS LIST_PRICE_AMT, -- List Price Amount [CONFIDENTIAL]
        CAST(MARGIN_PCT AS NUMBER(38,0)) AS MARGIN_PCT, -- Margin Percentage
        CAST(CURRENT_INVENTORY_QTY AS NUMBER(38,0)) AS CURRENT_INVENTORY_QTY -- Current Inventory Quantity
    FROM base_vw_core_model_flattened
)

SELECT * FROM final
