# pipeline

<!-- Source: migrated from ~/.claude/skills/pipeline/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: pipeline -->

**Summary.** Data pipeline design for paratransit dashboards: ETL patterns, SharePoint List schemas, Power Automate flows, Excel parsing with xlsx/exceljs, data validation, and MTD running totals. Covers Trapeze report ingestion, contract-aligned KPI calculations, IsComplete flags, and error handling in automated data flows. Trigger on: "data pipeline", "Power Automate", "Excel processing", "SharePoint list schema", "ETD calculations", "MTD", "Trapeze".

# Data Pipeline Design for Dashboards (DataOps)

## Core Expertise
- Excel/CSV ingestion: column mapping, header detection, data type coercion
- SharePoint List schema design for KPI storage with versioning
- Power Automate flow design: triggers, expressions, error branches
- MTD (Month-to-Date) aggregation: SUM-based running totals, not averages
- IsComplete flag pattern to distinguish partial vs final period data
- Contract-aligned validation rules baked into pipeline transforms

## When to Use
- Processing TD Report Excel files into structured KPI JSON
- Designing SharePoint List columns for KPI historical data
- Building Power Automate flows to automate data ingestion
- Calculating MTD totals that must use SUM not AVERAGE (e.g., PPH passengers)
- Adding validation to catch data quality issues before dashboard render

## Key Patterns

1. **Excel Column Mapper**
```javascript
const COLUMN_MAP = {
  'Total Passengers':       'totalPassengers',
  'Total Hours':            'totalHours',
  'On Time Trips':          'onTimeTrips',
  'Total Trips':            'totalTrips',
  'Late Trips':             'lateTrips',
  'Excessively Late Trips': 'excessivelyLateTrips',
  'Missed Trips':           'missedTrips',
};

function mapExcelRow(row, headers) {
  return Object.fromEntries(
    headers.map((h, i) => [COLUMN_MAP[h.trim()] || h, row[i]])
  );
}
```

2. **MTD Running Total (SUM-based PPH)**
```javascript
// PPH = total passengers / total hours for the period
// NEVER average individual daily PPH values
function calculateMTDPPH(dailyRows) {
  const totalPassengers = dailyRows.reduce((s, r) => s + (r.passengers || 0), 0);
  const totalHours      = dailyRows.reduce((s, r) => s + (r.hours || 0), 0);
  return totalHours > 0 ? totalPassengers / totalHours : 0;
}
```

3. **SharePoint List Schema for KPI History**
```javascript
const KPI_LIST_COLUMNS = [
  { name: 'ReportMonth',         type: 'DateTime',  required: true  },
  { name: 'PPH',                 type: 'Number',    required: true  },
  { name: 'OTP',                 type: 'Number',    required: true  },
  { name: 'LateTripsPercent',    type: 'Number',    required: true  },
  { name: 'ExcessiveLateCount',  type: 'Number',    required: false },
  { name: 'MissedTripsCount',    type: 'Number',    required: false },
  { name: 'TotalPenalty',        type: 'Currency',  required: false },
  { name: 'IsComplete',          type: 'Boolean',   default: false  },
  { name: 'DataSource',          type: 'Choice',    choices: ['Excel', 'Manual', 'API'] },
];
```

4. **IsComplete Flag Pattern**
```javascript
function markComplete(kpiRecord) {
  const requiredFields = ['pph', 'otp', 'lateTrips', 'missedTrips', 'complaints'];
  const isComplete = requiredFields.every(f => kpiRecord[f] != null && !isNaN(kpiRecord[f]));
  return { ...kpiRecord, isComplete, completedAt: isComplete ? new Date().toISOString() : null };
}
```

5. **Data Validation Pipeline**
```javascript
const VALIDATION_RULES = {
  pph:             { min: 0,    max: 5,   type: 'number' },
  otp:             { min: 0,    max: 100, type: 'number' },
  lateTrips:       { min: 0,    max: 100, type: 'number' },
  excessivelyLate: { min: 0,    max: 100, type: 'number' },
  missedTrips:     { min: 0,    max: 100, type: 'number' },
};

function validateKPI(key, value) {
  const rule = VALIDATION_RULES[key];
  if (!rule) return { valid: true };
  if (typeof value !== rule.type) return { valid: false, error: `${key}: expected ${rule.type}` };
  if (value < rule.min || value > rule.max) return { valid: false, error: `${key}: out of range [${rule.min}-${rule.max}]` };
  return { valid: true };
}
```

6. **Power Automate Expression: Get Month Label**
```
formatDateTime(triggerBody()?['ReportDate'], 'MMMM yyyy')
```

## Standards
- MTD PPH = SUM(passengers) / SUM(hours) — never average daily PPH values
- Always set IsComplete = false until all required KPIs are confirmed
- Store raw source data alongside calculated values for audit trail
- Validate all numeric KPI values are within plausible ranges before persisting
- Excel column names may vary; always use fuzzy header matching, not index-based
- Log transformation errors with original row data for debugging
