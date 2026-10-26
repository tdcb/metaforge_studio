"""Enterprise Naming Standards & Glossary (NSM) Auto-Translation Engine."""
import re
from typing import Dict
from .schema import NamingStandardGlossary, ProjectMetamodel


DEFAULT_GLOSSARY_ABBREVIATIONS: Dict[str, str] = {
    "CUSTOMER": "CUST",
    "IDENTIFIER": "ID",
    "AMOUNT": "AMT",
    "TIMESTAMP": "TS",
    "TRANSACTION": "TXN",
    "POLICY": "PLCY",
    "EFFECTIVE": "EFF",
    "EXPIRATION": "EXP",
    "DATE": "DT",
    "NUMBER": "NBR",
    "CODE": "CD",
    "DESCRIPTION": "DESC",
    "DIMENSION": "DIM",
    "FACT": "FCT",
    "STAGING": "STG",
    "ACCOUNT": "ACCT",
    "BALANCE": "BAL",
    "STATUS": "STAT",
    "ADDRESS": "ADDR",
    "ORGANIZATION": "ORG",
    "INSURANCE": "INSRNC",
    "RECORD": "REC",
    "CREATED": "CRTD",
    "UPDATED": "UPDT",
    "SOURCE": "SRC",
    "SYSTEM": "SYS",
    "PAYMENT": "PYMT",
    "CLAIM": "CLM",
    "COVERAGE": "CVRG",
    "PREMIUM": "PREM",
    "QUANTITY": "QTY",
    "PRODUCT": "PROD",
    "ORDER": "ORD",
    "PERCENTAGE": "PCT",
    "COUNT": "CNT",
    "RATE": "RT",
    "CATEGORY": "CAT",
    "GROUP": "GRP",
    "DETAIL": "DTL",
    "REFERENCE": "REF",
    "LOCATION": "LOC",
    "COUNTRY": "CTRY",
    "TELEPHONE": "TEL",
    "EMPLOYEE": "EMP",
    "SUPPLIER": "SUPP",
    "VENDOR": "VEND",
    "INVOICE": "INV",
    "WAREHOUSE": "WH",
    "SCHEDULE": "SCHED",
    "MONTH": "MTH",
    "YEAR": "YR",
    "AVERAGE": "AVG",
    "TOTAL": "TOT",
}

EXPANDED_ABBREVIATIONS_MAP: Dict[str, str] = {
    "PLCY": "Policy",
    "POL": "Policy",
    "CLM": "Claim",
    "CUST": "Customer",
    "NBR": "Number",
    "NUM": "Number",
    "NO": "Number",
    "ID": "Identifier",
    "NM": "Name",
    "AMT": "Amount",
    "BAL": "Balance",
    "DT": "Date",
    "TS": "Timestamp",
    "TM": "Time",
    "CD": "Code",
    "STAT": "Status",
    "STS": "Status",
    "IND": "Indicator",
    "FLG": "Flag",
    "FLAG": "Flag",
    "CNT": "Count",
    "QTY": "Quantity",
    "PCT": "Percentage",
    "PERC": "Percentage",
    "VAL": "Value",
    "RT": "Rate",
    "TXN": "Transaction",
    "TRANS": "Transaction",
    "EFF": "Effective",
    "EXP": "Expiration",
    "CRTD": "Created",
    "UPDT": "Updated",
    "SRC": "Source",
    "SYS": "System",
    "REC": "Record",
    "ADDR": "Address",
    "ORG": "Organization",
    "ACCT": "Account",
    "PYMT": "Payment",
    "CVRG": "Coverage",
    "COV": "Coverage",
    "PREM": "Premium",
    "PROD": "Product",
    "ORD": "Order",
    "DESC": "Description",
    "DSCR": "Description",
    "CAT": "Category",
    "CTG": "Category",
    "GRP": "Group",
    "TYP": "Type",
    "DTL": "Detail",
    "DET": "Detail",
    "HDR": "Header",
    "REF": "Reference",
    "AUTH": "Authorization",
    "CHG": "Charge",
    "ADJ": "Adjustment",
    "EST": "Estimate",
    "REV": "Revenue",
    "STD": "Standard",
    "INFO": "Information",
    "PROP": "Property",
    "AUTO": "Automobile",
    "VEH": "Vehicle",
    "DED": "Deductible",
    "BEN": "Benefit",
    "REL": "Relationship",
    "INSRD": "Insured",
    "AGNT": "Agent",
    "AGT": "Agent",
    "BRKR": "Broker",
    "BKR": "Broker",
    "LOC": "Location",
    "CTRY": "Country",
    "TEL": "Telephone",
    "PHN": "Phone",
    "MOB": "Mobile",
    "DIV": "Division",
    "DEPT": "Department",
    "MGR": "Manager",
    "EMP": "Employee",
    "SUPP": "Supplier",
    "VEND": "Vendor",
    "INV": "Invoice",
    "ITEM": "Item",
    "WH": "Warehouse",
    "WHS": "Warehouse",
    "FAC": "Facility",
    "SCHED": "Schedule",
    "MTH": "Month",
    "YR": "Year",
    "QTR": "Quarter",
    "WK": "Week",
    "SEC": "Second",
    "MIN": "Minute",
    "MAX": "Maximum",
    "AVG": "Average",
    "TOT": "Total",
    "DIM": "Dimension",
    "FCT": "Fact",
    "STG": "Staging",
    "VW": "View",
    "INSRNC": "Insurance",
    "RPTD": "Reported",
    "RPT": "Report",
    "PAID": "Paid",
    "LOSS": "Loss",
    "SUBTOT": "Subtotal",
    "SPND": "Spend",
    "PRC": "Price",
    "CST": "Cost",
    "DISC": "Discount",
    "PROF": "Profit",
    "GROSS": "Gross",
    "NET": "Net",
    "LTV": "Lifetime Value",
    "KPI": "Key Performance Indicator",
    "KPIS": "Key Performance Indicators",
}


def expand_business_text(text: str) -> str:
    """
    Scans natural language business definitions, logical names, and grain statements
    and replaces any shorthand or technical database abbreviations (e.g. 'plcy', 'clm', 'cust', 'nbr', 'amt')
    with full, professional business words ('policy', 'claim', 'customer', 'number', 'amount').
    Ensures zero usage of shortened words.
    """
    if not text or not text.strip():
        return ""

    result = text

    # First clean up physical naming patterns with underscores like PLCY_ID, CLM_LOSS_AMT, DIM_CUSTOMER
    snake_map = dict(EXPANDED_ABBREVIATIONS_MAP)
    snake_map["NO"] = "Number"

    def replace_snake_token(match: re.Match) -> str:
        token = match.group(0)
        parts = token.split("_")
        expanded_parts = [
            snake_map.get(p.upper(), p.title())
            for p in parts
            if p.upper() not in ("DIM", "FCT", "STG", "VW", "MV", "HUB", "SAT", "LNK", "CORE", "DBO")
        ]
        return " ".join(expanded_parts) or token

    result = re.sub(r"\b[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+\b", replace_snake_token, result)

    # Next clean up individual standalone abbreviation tokens case-insensitively.
    # Exclude English words like 'no' to prevent corrupting negation ("no records found").
    for abbr, full_word in EXPANDED_ABBREVIATIONS_MAP.items():
        if len(abbr) <= 1 or abbr.upper() in ("NO", "IN", "IS", "OR", "TO", "AT", "ON", "BY"):
            continue
        pattern = re.compile(rf"\b{re.escape(abbr)}\b", re.IGNORECASE)

        def make_repl(target_full: str):
            def repl(m: re.Match) -> str:
                matched = m.group(0)
                if matched.isupper():
                    return target_full.title()
                elif matched.islower():
                    return target_full.lower()
                elif matched[0].isupper():
                    return target_full.title()
                return target_full
            return repl

        result = pattern.sub(make_repl(full_word), result)

    # Clean up double spaces or awkward punctuation
    result = re.sub(r"\s+", " ", result).strip()
    result = re.sub(r"\s+([,.:;])", r"\1", result)
    result = re.sub(r"\(\s+", "(", result)
    result = re.sub(r"\s+\)", ")", result)
    return result


def sanitize_model_business_text(model: ProjectMetamodel) -> None:
    """
    Ensures that all entities and columns in the model use clean, professional,
    natural enterprise business terms with zero usage of shortened words or abbreviations.
    """
    for ent in model.entities.values():
        if ent.logical_name:
            ent.logical_name = expand_business_text(ent.logical_name)
        if ent.description:
            ent.description = expand_business_text(ent.description)
        if ent.grain_statement:
            ent.grain_statement = expand_business_text(ent.grain_statement)
        for col in ent.columns:
            if col.logical_name:
                col.logical_name = expand_business_text(col.logical_name)
            if col.description:
                col.description = expand_business_text(col.description)


def translate_logical_to_physical(
    logical_name: str,
    glossary: NamingStandardGlossary,
    prefix: str = "",
) -> str:
    """
    Translate a business logical_name (e.g. 'Policy Effective Date') into an
    enterprise UPPER_SNAKE_CASE physical_name (e.g. 'PLCY_EFF_DT') using the
    active NamingStandardGlossary.
    """
    if not logical_name or not logical_name.strip():
        return "UNNAMED"

    # Split camelCase / PascalCase as well as spaces, hyphens, underscores, punctuation
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", logical_name)
    tokens = [t.upper() for t in re.split(r"[^A-Za-z0-9]+", spaced) if t]

    abbr_map = {k.upper(): v.upper() for k, v in glossary.abbreviations.items()}
    translated_tokens = [abbr_map.get(tok, tok) for tok in tokens]

    result = "_".join(translated_tokens)
    if prefix:
        clean_prefix = prefix.upper().rstrip("_")
        if not result.startswith(f"{clean_prefix}_") and result != clean_prefix:
            result = f"{clean_prefix}_{result}"
    return result


def apply_glossary_to_project(
    model: ProjectMetamodel,
    overwrite_existing: bool = True,
) -> Dict[str, int]:
    """
    Apply the Enterprise Naming Standards Glossary across all entities and columns in the project.
    Preserves standard layer prefixes (DIM_, FCT_, STG_) when translating entity names if
    the logical name doesn't already specify Dimension/Fact/Staging.
    Returns counts of translated entities and columns.
    """
    entities_updated = 0
    columns_updated = 0

    for entity in model.entities.values():
        existing_prefix = ""
        for pfx in ("DIM_", "FCT_", "STG_", "RAW_", "INT_", "BRG_"):
            if entity.physical_name.upper().startswith(pfx):
                existing_prefix = pfx.rstrip("_")
                break
        if not existing_prefix:
            if entity.dbt_layer == "staging":
                existing_prefix = "STG"
            elif entity.dbt_layer == "source":
                existing_prefix = "RAW"

        new_entity_phys = translate_logical_to_physical(
            entity.logical_name, model.glossary, prefix=existing_prefix
        )
        if overwrite_existing and new_entity_phys != entity.physical_name:
            entity.physical_name = new_entity_phys
            entities_updated += 1

        for col in entity.columns:
            new_col_phys = translate_logical_to_physical(col.logical_name, model.glossary)
            if overwrite_existing and new_col_phys != col.physical_name:
                col.physical_name = new_col_phys
                columns_updated += 1

    return {
        "entities_updated": entities_updated,
        "columns_updated": columns_updated,
    }


def physical_to_logical_guess(
    physical_name: str,
    glossary: NamingStandardGlossary | None = None,
) -> str:
    """Inverse NSM lookup: converts an UPPER_SNAKE_CASE physical name (e.g. PLCY_EFF_DT) into a Title Case business name (e.g. Policy Effective Date)."""
    if not physical_name or not physical_name.strip():
        return "Unnamed Attribute"
    abbr_src = glossary.abbreviations if glossary else DEFAULT_GLOSSARY_ABBREVIATIONS
    inv_map = {k.upper(): v for k, v in EXPANDED_ABBREVIATIONS_MAP.items()}
    inv_map.update({v.upper(): k.title() for k, v in abbr_src.items()})
    tokens = [t.upper() for t in re.split(r"[^A-Za-z0-9]+", physical_name) if t]
    # Strip leading technical table prefixes like DIM_, FCT_, STG_, VW_ when guessing entity logical name
    if len(tokens) > 1 and tokens[0] in ("DIM", "FCT", "STG", "VW", "MV", "HUB", "SAT", "LNK", "CORE", "DBO"):
        tokens = tokens[1:]
    words = [inv_map.get(tok, tok.title()) for tok in tokens]
    return expand_business_text(" ".join(words))

