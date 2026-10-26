import type { ProjectMetamodel } from '../types/metamodel';

const SYSTEM_INSTRUCTION = `You are the Lead Enterprise Data Architect for MetaForge Studio.
Your role is to inspect, reason over, and modify canonical data models (tables, views, columns, relationships, and subject areas).

When a user asks a question, provides refactoring instructions, or commands you to:
1. Add a model or subject area
2. Add or modify tables and columns (data types, primary keys, foreign keys, descriptions, PII classifications)
3. Add or modify relationships (identifying, non_identifying, upstream_lineage; one_to_one, one_to_many, many_to_many)
4. Add or modify a view (creating analytical view SQL, selecting columns, linking upstream lineage)

You MUST respond in valid JSON format with the following exact structure:
{
  "reply": "Markdown explanation of what you did or the answer to the user's question with formatted code blocks, bold names, and rationale.",
  "mutations": [
    // List of mutation actions to execute on the canonical model (empty if purely Q&A)
  ]
}

Supported mutation actions in the 'mutations' array:
- Add Subject Area:
  {"action": "add_subject_area", "name": "Logistics"}

- Add Table:
  {
    "action": "add_table",
    "physical_name": "DIM_SUPPLIER",
    "logical_name": "Supplier Dimension",
    "subject_area": "Core",
    "description": "Supplier enterprise dimension",
    "columns": [
      {"physical_name": "SUPPLIER_ID", "logical_name": "Supplier Identifier", "data_type": "NUMBER(38,0)", "is_pk": true},
      {"physical_name": "SUPPLIER_NM", "logical_name": "Supplier Name", "data_type": "VARCHAR(255)", "is_nullable": false},
      {"physical_name": "COUNTRY_CD", "logical_name": "Country Code", "data_type": "VARCHAR(10)"}
    ]
  }

- Modify Table:
  {
    "action": "modify_table",
    "physical_name": "DIM_CUSTOMER",
    "new_description": "Updated description",
    "columns_to_add": [{"physical_name": "PHONE_NBR", "data_type": "VARCHAR(50)", "pii_classification": "RESTRICTED_PII"}],
    "columns_to_drop": ["OBSOLETE_COL"]
  }

- Drop Table:
  {"action": "drop_table", "physical_name": "DIM_OLD_TABLE"}

- Add Column:
  {"action": "add_column", "table_name": "DIM_CUSTOMER", "physical_name": "LOYALTY_TIER", "data_type": "VARCHAR(50)"}

- Modify Column:
  {"action": "modify_column", "table_name": "DIM_CUSTOMER", "physical_name": "TAX_ID_NBR", "pii_classification": "RESTRICTED_PII"}

- Drop Column:
  {"action": "drop_column", "table_name": "DIM_CUSTOMER", "physical_name": "OLD_COLUMN"}

- Add Relationship:
  {
    "action": "add_relationship",
    "name": "FK_FCT_CLAIM_DIM_CUSTOMER",
    "parent_table": "DIM_CUSTOMER",
    "child_table": "FCT_CLAIM",
    "parent_column": "CUST_ID",
    "child_column": "CUST_ID",
    "rel_type": "non_identifying",
    "cardinality": "one_to_many"
  }

- Modify Relationship:
  {"action": "modify_relationship", "name": "FK_NAME", "cardinality": "one_to_one"}

- Drop Relationship:
  {"action": "drop_relationship", "name": "FK_NAME"}

- Add View:
  {
    "action": "add_view",
    "physical_name": "VW_HIGH_SEVERITY_CLAIMS",
    "logical_name": "High Severity Claims Summary",
    "subject_area": "Claims",
    "view_sql": "SELECT c.CLM_ID, c.LOSS_AMT, cust.CUST_FULL_NM FROM FCT_CLAIM c INNER JOIN DIM_CUSTOMER cust ON c.CUST_ID = cust.CUST_ID WHERE c.LOSS_AMT > 50000",
    "columns": [
      {"physical_name": "CLM_ID", "data_type": "NUMBER(38,0)"},
      {"physical_name": "LOSS_AMT", "data_type": "NUMBER(18,2)"},
      {"physical_name": "CUST_FULL_NM", "data_type": "VARCHAR(255)"}
    ],
    "materialization": "view"
  }

- Modify View:
  {
    "action": "modify_view",
    "physical_name": "VW_CUSTOMER_CLAIM_SUMMARY",
    "view_sql": "SELECT ... new query ..."
  }

- Drop View:
  {"action": "drop_view", "physical_name": "VW_OLD_VIEW"}

CRITICAL BUSINESS LANGUAGE & NAMING STANDARDS:
- ABSOLUTELY ZERO USE OF SHORTENED WORDS, ABBREVIATIONS, OR ACRONYMS in logical_name, description, or business explanations.
- Always expand shorthand to complete business terms: 'Policy' (not 'plcy'), 'Claim' (not 'clm'), 'Customer' (not 'cust'), 'Number' (not 'nbr'/'num'), 'Amount' (not 'amt'), 'Effective Date' (not 'eff_dt'), 'Transaction' (not 'txn'), 'Coverage' (not 'cvrg'), 'Premium' (not 'prem'), 'Indicator' (not 'ind'), etc.
- Logical names, descriptions, and view titles must make immediate, intuitive sense to non-technical business stakeholders.
Ensure all physical names adhere to standard uppercase SQL naming conventions.
Output strictly JSON without markdown backticks wrapping the whole output.`;

export const EXPANDED_ABBREVIATIONS: Record<string, string> = {
  PLCY: 'Policy',
  POL: 'Policy',
  CLM: 'Claim',
  CUST: 'Customer',
  NBR: 'Number',
  NUM: 'Number',
  ID: 'Identifier',
  NM: 'Name',
  AMT: 'Amount',
  BAL: 'Balance',
  DT: 'Date',
  TS: 'Timestamp',
  TM: 'Time',
  CD: 'Code',
  STAT: 'Status',
  STS: 'Status',
  IND: 'Indicator',
  FLG: 'Flag',
  FLAG: 'Flag',
  CNT: 'Count',
  QTY: 'Quantity',
  PCT: 'Percentage',
  PERC: 'Percentage',
  VAL: 'Value',
  RT: 'Rate',
  TXN: 'Transaction',
  TRANS: 'Transaction',
  EFF: 'Effective',
  EXP: 'Expiration',
  CRTD: 'Created',
  UPDT: 'Updated',
  SRC: 'Source',
  SYS: 'System',
  REC: 'Record',
  ADDR: 'Address',
  ORG: 'Organization',
  ACCT: 'Account',
  PYMT: 'Payment',
  CVRG: 'Coverage',
  COV: 'Coverage',
  PREM: 'Premium',
  PROD: 'Product',
  ORD: 'Order',
  DESC: 'Description',
  DSCR: 'Description',
  DIM: 'Dimension',
  FCT: 'Fact',
  STG: 'Staging',
  VW: 'View',
  INSRNC: 'Insurance',
  CAT: 'Category',
  CTG: 'Category',
  GRP: 'Group',
  TYP: 'Type',
  DTL: 'Detail',
  DET: 'Detail',
  HDR: 'Header',
  REF: 'Reference',
  AUTH: 'Authorization',
  CHG: 'Charge',
  ADJ: 'Adjustment',
  EST: 'Estimate',
  REV: 'Revenue',
  STD: 'Standard',
  INFO: 'Information',
  PROP: 'Property',
  AUTO: 'Automobile',
  VEH: 'Vehicle',
  DED: 'Deductible',
  BEN: 'Benefit',
  REL: 'Relationship',
  INSRD: 'Insured',
  AGNT: 'Agent',
  AGT: 'Agent',
  BRKR: 'Broker',
  BKR: 'Broker',
  LOC: 'Location',
  CTRY: 'Country',
  TEL: 'Telephone',
  PHN: 'Phone',
  MOB: 'Mobile',
  DIV: 'Division',
  DEPT: 'Department',
  MGR: 'Manager',
  EMP: 'Employee',
  SUPP: 'Supplier',
  VEND: 'Vendor',
  INV: 'Invoice',
  ITEM: 'Item',
  WH: 'Warehouse',
  WHS: 'Warehouse',
  FAC: 'Facility',
  SCHED: 'Schedule',
  MTH: 'Month',
  YR: 'Year',
  QTR: 'Quarter',
  WK: 'Week',
  SEC: 'Second',
  MIN: 'Minute',
  MAX: 'Maximum',
  AVG: 'Average',
  TOT: 'Total',
  RPTD: 'Reported',
  RPT: 'Report',
  PAID: 'Paid',
  LOSS: 'Loss',
  SUBTOT: 'Subtotal',
  SPND: 'Spend',
  PRC: 'Price',
  CST: 'Cost',
  DISC: 'Discount',
  PROF: 'Profit',
  GROSS: 'Gross',
  NET: 'Net',
  LTV: 'Lifetime Value',
  KPI: 'Key Performance Indicator',
  KPIS: 'Key Performance Indicators',
};

export function expandBusinessText(text: string): string {
  if (!text || !text.trim()) return '';
  let result = text;

  // Replace snake_case tokens like PLCY_ID -> Policy Identifier
  const snakeMap: Record<string, string> = { ...EXPANDED_ABBREVIATIONS, NO: 'Number' };
  result = result.replace(/\b[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+\b/g, (match) => {
    const parts = match.split('_');
    const expandedParts = parts
      .filter((p) => !['DIM', 'FCT', 'STG', 'VW', 'MV', 'HUB', 'SAT', 'LNK', 'CORE', 'DBO'].includes(p.toUpperCase()))
      .map((p) => snakeMap[p.toUpperCase()] || p.charAt(0).toUpperCase() + p.slice(1).toLowerCase());
    return expandedParts.join(' ') || match;
  });

  // Replace standalone abbreviation tokens case-insensitively, excluding natural English words
  const excludeWords = new Set(['NO', 'IN', 'IS', 'OR', 'TO', 'AT', 'ON', 'BY']);
  for (const [abbr, fullWord] of Object.entries(EXPANDED_ABBREVIATIONS)) {
    if (abbr.length <= 1 || excludeWords.has(abbr.toUpperCase())) continue;
    const pattern = new RegExp(`\\b${abbr}\\b`, 'gi');
    result = result.replace(pattern, (matched) => {
      if (matched === matched.toUpperCase()) {
        return fullWord;
      } else if (matched === matched.toLowerCase()) {
        return fullWord.toLowerCase();
      } else {
        return fullWord;
      }
    });
  }

  return result.replace(/\s+/g, ' ').trim();
}

export function buildModelSummary(model: ProjectMetamodel): string {
  const lines: string[] = [
    `Project: ${model.name} (v${model.version})`,
    `Subject Areas: ${model.subject_areas.join(', ')}`,
    `Total Entities: ${Object.keys(model.entities).length}`,
    `Total Relationships: ${Object.keys(model.relationships).length}`,
    '',
    '### Entities in Canvas:',
  ];

  for (const ent of Object.values(model.entities)) {
    const colSummaries = ent.columns.map((c) => {
      const flags: string[] = [];
      if (c.is_pk) flags.push('PK');
      if (c.is_fk) flags.push('FK');
      const flagStr = flags.length > 0 ? ` [${flags.join(',')}]` : '';
      return `${c.physical_name} (${c.data_type_snowflake || 'VARCHAR'})${flagStr}`;
    });

    lines.push(
      `- **${ent.physical_name}** (${ent.logical_name}) [${ent.entity_type}, Area: ${ent.subject_area}]: ${colSummaries.join(', ')}`
    );
    if ((ent.entity_type === 'view' || ent.entity_type === 'materialized_view') && ent.view_sql) {
      lines.push(`  SQL: ${ent.view_sql}`);
    }
  }

  lines.push('');
  lines.push('### Relationships in Canvas:');
  for (const rel of Object.values(model.relationships)) {
    const pEnt = model.entities[rel.parent_entity_id];
    const cEnt = model.entities[rel.child_entity_id];
    const pName = pEnt ? pEnt.physical_name : rel.parent_entity_id;
    const cName = cEnt ? cEnt.physical_name : rel.child_entity_id;
    lines.push(`- ${rel.name}: ${pName} -> ${cName} [${rel.rel_type}, ${rel.cardinality}]`);
  }

  return lines.join('\n');
}

export async function callGeminiDirect(
  project: ProjectMetamodel,
  prompt: string,
  apiKey: string,
  geminiModel: string = 'gemini-2.5-flash'
): Promise<{ reply: string; mutations: any[] }> {
  const cleanKey = apiKey.trim();
  if (!cleanKey) {
    throw new Error('Google Gemini API Key is required. Please set it in the AI Agent config.');
  }

  const modelSummary = buildModelSummary(project);
  const userPayloadText = `### Current Data Model Context:\n${modelSummary}\n\n### User Instruction / Question:\n${prompt}`;

  const url = `https://generativelanguage.googleapis.com/v1beta/models/${geminiModel}:generateContent?key=${cleanKey}`;

  const requestBody = {
    system_instruction: {
      parts: [{ text: SYSTEM_INSTRUCTION }],
    },
    contents: [
      {
        role: 'user',
        parts: [{ text: userPayloadText }],
      },
    ],
    generationConfig: {
      response_mime_type: 'application/json',
      temperature: 0.2,
    },
  };

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errText = await response.text();
    let errMessage = `HTTP ${response.status}: ${errText}`;
    try {
      const errJson = JSON.parse(errText);
      if (errJson.error?.message) {
        errMessage = errJson.error.message;
      }
    } catch {
      // ignore json parse error
    }
    throw new Error(`Google Gemini Error (${response.status}): ${errMessage}`);
  }

  const data = await response.json();
  const candidates = data.candidates || [];
  if (!candidates.length) {
    throw new Error('No candidate response returned from Google Gemini.');
  }

  const contentParts = candidates[0].content?.parts || [];
  let rawText = contentParts.map((p: any) => p.text || '').join('').trim();

  // Strip code block wrappers if any
  if (rawText.startsWith('```')) {
    rawText = rawText.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/i, '').trim();
  }

  try {
    const parsed = JSON.parse(rawText);
    const cleanReply = expandBusinessText(String(parsed.reply || 'Action processed.'));
    const rawMutations = Array.isArray(parsed.mutations) ? parsed.mutations : [];
    const cleanMutations = rawMutations.map((m: any) => {
      const mut = { ...m };
      if (mut.logical_name) mut.logical_name = expandBusinessText(mut.logical_name);
      if (mut.new_logical_name) mut.new_logical_name = expandBusinessText(mut.new_logical_name);
      if (mut.description) mut.description = expandBusinessText(mut.description);
      if (mut.new_description) mut.new_description = expandBusinessText(mut.new_description);
      if (mut.grain_statement) mut.grain_statement = expandBusinessText(mut.grain_statement);
      if (mut.business_purpose) mut.business_purpose = expandBusinessText(mut.business_purpose);
      if (Array.isArray(mut.columns)) {
        mut.columns = mut.columns.map((c: any) => ({
          ...c,
          logical_name: c.logical_name ? expandBusinessText(c.logical_name) : c.logical_name,
          description: c.description ? expandBusinessText(c.description) : c.description,
        }));
      }
      if (Array.isArray(mut.columns_to_add)) {
        mut.columns_to_add = mut.columns_to_add.map((c: any) => ({
          ...c,
          logical_name: c.logical_name ? expandBusinessText(c.logical_name) : c.logical_name,
          description: c.description ? expandBusinessText(c.description) : c.description,
        }));
      }
      return mut;
    });
    return {
      reply: cleanReply,
      mutations: cleanMutations,
    };
  } catch (parseErr: any) {
    throw new Error(`Failed to parse Gemini JSON response: ${parseErr.message}\nRaw: ${rawText.slice(0, 300)}`);
  }
}
