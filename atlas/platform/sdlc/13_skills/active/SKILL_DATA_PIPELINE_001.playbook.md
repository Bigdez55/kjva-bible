# data-pipeline

<!-- Source: migrated from ~/.claude/skills/data-pipeline/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: data-pipeline -->

**Summary.** KPI data ingestion pipelines: Bronze/Silver/Gold medallion architecture, Trapeze CSV/Excel parsing, fuzzy column mapping, SUM-based MTD aggregation (never AVERAGE for PPH), SharePoint List writes via PnPjs, DuckDB-WASM in-browser SQL, data quality scoring, and audit trail logging. Trigger on: 'data pipeline', 'ETL', 'Trapeze', 'CSV parsing', 'MTD calculation', 'running total', 'data ingestion', 'medallion architecture'.

# KPI Data Ingestion Pipelines — Medallion Architecture

## Purpose & Scope

This skill designs ETL pipelines for dashboard data using the Bronze/Silver/Gold medallion architecture. Bronze = raw data with checksums. Silver = validated, fuzzy-mapped, range-checked data. Gold = SUM-based aggregated KPIs ready for dashboard consumption.

## When to Trigger

- Processing new TD Report Excel or Trapeze CSV exports
- Building ETL pipelines with Bronze/Silver/Gold stages
- Calculating MTD PPH, OTP, or late trip percentages from daily rows
- Writing KPI values to SharePoint Lists via PnPjs
- Setting up DuckDB-WASM for in-browser analytics
- Handling incomplete data with IsComplete flags

## When NOT to Trigger

- KPI analysis on processed data → **KPI Analyst Agent**
- Dashboard UI → framework APEX agent
- AI insights → **ORACLE** agent
- Deployment → **Dashboard Deployer Agent**

## Bronze Layer — Raw Ingestion

```javascript
const crypto = require('crypto');
const fs = require('fs');

function discoverSourceFiles(directory) {
  const extensions = ['.xlsx', '.xls', '.csv'];
  return fs.readdirSync(directory)
    .filter(f => extensions.some(ext => f.toLowerCase().endsWith(ext)))
    .map(f => ({
      filename: f, path: `${directory}/${f}`,
      size: fs.statSync(`${directory}/${f}`).size,
      modified: fs.statSync(`${directory}/${f}`).mtime,
    }));
}

function ingestToBronze(filePath) {
  const raw = fs.readFileSync(filePath);
  const checksum = crypto.createHash('sha256').update(raw).digest('hex');
  return {
    _layer: 'bronze', _source: filePath, _checksum: checksum,
    _ingestedAt: new Date().toISOString(), _sizeBytes: raw.length,
    data: null, headers: null, rowCount: 0,
  };
}
```

**Bronze Rules:** Never modify source files. Record SHA-256 checksums. Skip unchanged files. Preserve original column names.

## Silver Layer — Fuzzy Column Mapping & Validation

```javascript
const COLUMN_MAP = {
  'total passengers': 'totalPassengers', 'passengers': 'totalPassengers',
  'pax': 'totalPassengers', 'ridership': 'totalPassengers',
  'total hours': 'totalHours', 'revenue hours': 'totalHours',
  'service hours': 'totalHours', 'hours': 'totalHours',
  'total trips': 'totalTrips', 'trips': 'totalTrips',
  'trip count': 'totalTrips', 'completed trips': 'totalTrips',
  'on time trips': 'onTimeTrips', 'on-time trips': 'onTimeTrips',
  'otp': 'onTimeTrips', 'on time count': 'onTimeTrips',
  'late trips': 'lateTrips', 'late trip count': 'lateTrips',
  'late trips (6-20 min)': 'lateTrips',
  'excessively late': 'excessivelyLateTrips',
  'excessively late trips': 'excessivelyLateTrips',
  'late trips (>20 min)': 'excessivelyLateTrips',
  'missed trips': 'missedTrips', 'no shows': 'missedTrips',
};

function mapColumn(rawName) {
  const normalized = rawName.trim().toLowerCase().replace(/[^a-z0-9 ]/g, '');
  return COLUMN_MAP[normalized] || null;
}
```

### Validation Rules

```javascript
const VALIDATION_RULES = {
  totalPassengers:      { type: 'number', min: 0, max: 100000, required: true },
  totalHours:           { type: 'number', min: 0, max: 50000,  required: true },
  totalTrips:           { type: 'number', min: 0, max: 100000, required: true },
  onTimeTrips:          { type: 'number', min: 0, max: 100000, required: true },
  lateTrips:            { type: 'number', min: 0, max: 100000, required: false },
  excessivelyLateTrips: { type: 'number', min: 0, max: 100000, required: false },
  missedTrips:          { type: 'number', min: 0, max: 100000, required: false },
};

function validateRecord(record) {
  const errors = [];
  const validated = {};
  for (const [field, rule] of Object.entries(VALIDATION_RULES)) {
    const value = record[field];
    if (value == null || value === '') {
      if (rule.required) errors.push({ field, error: 'MISSING_REQUIRED' });
      validated[field] = null; continue;
    }
    const num = Number(value);
    if (isNaN(num)) { errors.push({ field, error: 'TYPE_COERCION_FAILED', original: value }); validated[field] = null; continue; }
    if (num < rule.min || num > rule.max) { errors.push({ field, error: 'OUT_OF_RANGE', value: num }); }
    validated[field] = num;
  }
  if (validated.onTimeTrips > validated.totalTrips) {
    errors.push({ field: 'onTimeTrips', error: 'LOGICAL_INCONSISTENCY' });
  }
  return { ...validated, _errors: errors, _hasErrors: errors.length > 0 };
}
```

## Gold Layer — SUM-Based Aggregation

**CRITICAL: PPH = SUM(passengers) / SUM(hours), NEVER average of daily PPH.**

```javascript
function aggregateToGold(silverRecords) {
  const totals = silverRecords.reduce((acc, row) => ({
    passengers:    acc.passengers + (row.totalPassengers || 0),
    hours:         acc.hours + (row.totalHours || 0),
    trips:         acc.trips + (row.totalTrips || 0),
    onTime:        acc.onTime + (row.onTimeTrips || 0),
    late:          acc.late + (row.lateTrips || 0),
    excessiveLate: acc.excessiveLate + (row.excessivelyLateTrips || 0),
    missed:        acc.missed + (row.missedTrips || 0),
  }), { passengers: 0, hours: 0, trips: 0, onTime: 0, late: 0, excessiveLate: 0, missed: 0 });

  return {
    pph: totals.hours > 0 ? totals.passengers / totals.hours : 0,
    otp: totals.trips > 0 ? (totals.onTime / totals.trips) * 100 : 0,
    lateTripsPercent: totals.trips > 0 ? (totals.late / totals.trips) * 100 : 0,
    excessivelyLatePercent: totals.trips > 0 ? (totals.excessiveLate / totals.trips) * 100 : 0,
    missedTripsPercent: totals.trips > 0 ? (totals.missed / totals.trips) * 100 : 0,
    _rawTotals: totals, _recordCount: silverRecords.length,
  };
}
```

### Why SUM, Not Average

| Day | Passengers | Hours | Daily PPH |
|-----|-----------|-------|-----------|
| Mon | 10 | 5 | 2.00 |
| Tue | 100 | 80 | 1.25 |
| **Correct (SUM):** | 110 | 85 | **1.294** |
| **Wrong (AVG):** | — | — | **1.625** |

## Data Quality Scoring (0-100)

```javascript
function calculateQualityScore(silverOutput) {
  const weights = { completeness: 0.30, accuracy: 0.25, consistency: 0.20, freshness: 0.15, coverage: 0.10 };
  const scores = {
    completeness: silverOutput.summary.valid / silverOutput.summary.total * 100,
    accuracy: calculateAccuracyScore(silverOutput.records),
    consistency: calculateConsistencyScore(silverOutput.records),
    freshness: calculateFreshnessScore(silverOutput._processedAt),
    coverage: calculateCoverageScore(silverOutput.mappedColumns),
  };
  return Math.round(Object.entries(weights).reduce((sum, [k, w]) => sum + scores[k] * w, 0));
}
```

## PnPjs SharePoint List Upsert

```typescript
async function upsertKpiRecord(sp: SPFI, kpiData: IKpiData) {
  const list = sp.web.lists.getByTitle('KPI Historical Data');
  const existing = await list.items.filter(`ReportMonth eq '${kpiData.reportMonth}'`).select('Id')();
  const payload = {
    ReportMonth: kpiData.reportMonth, PPH: kpiData.pph, OTP: kpiData.otp,
    LateTripsPercent: kpiData.lateTripsPercent, ExcessiveLatePercent: kpiData.excessivelyLatePercent,
    MissedTripsPercent: kpiData.missedTripsPercent, TotalPenalty: kpiData.totalPenalty, IsComplete: kpiData.isComplete,
  };
  existing.length > 0 ? await list.items.getById(existing[0].Id).update(payload) : await list.items.add(payload);
}
```

## DuckDB-WASM In-Browser SQL

```javascript
async function queryKpiData(db, month) {
  return db.query(`
    SELECT SUM(total_passengers) / NULLIF(SUM(total_hours), 0) AS pph,
           SUM(on_time_trips) * 100.0 / NULLIF(SUM(total_trips), 0) AS otp,
           SUM(late_trips) * 100.0 / NULLIF(SUM(total_trips), 0) AS late_pct
    FROM daily_kpis WHERE report_month = '${month}'
  `);
}
```

## CSV/Excel Parsing

```javascript
import Papa from 'papaparse';
function parseCSV(file) {
  return new Promise((resolve, reject) => {
    Papa.parse(file, { header: true, dynamicTyping: true, skipEmptyLines: true,
      transformHeader: h => mapColumn(h.trim()) || h.trim(), complete: resolve, error: reject });
  });
}

import * as XLSX from 'xlsx';
function parseExcel(buffer) {
  const wb = XLSX.read(buffer, { type: 'buffer', cellDates: true });
  const rows = XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], { defval: null });
  return rows.map(row => {
    const mapped = {};
    for (const [key, value] of Object.entries(row)) { const std = mapColumn(key); if (std) mapped[std] = value; }
    return mapped;
  });
}
```

## Error Handling

| Error Type | Action |
|-----------|--------|
| Column mapping failure | Log column name, continue with available columns |
| Type coercion failure | Set field to null, mark record with error |
| Range validation failure | Include record but flag with warning |
| Logical inconsistency | Emit warning, include but flag |
| File read failure | Write processing-error.json with stack trace |
| Missing required column | Log warning, set IsComplete=false |
| Checksum unchanged | Skip file (already processed) |

## Integration with APEX Agents

| Agent | Relationship |
|-------|-------------|
| **PIPELINE** | Primary consumer for all ETL operations |
| **Excel Processor** | Project-specific Trapeze TD Report pipeline |
| **KPI Analyst** | Consumes Gold layer for penalty analysis |
| **SENTINEL** | Tests SUM-based aggregation accuracy |

## Anti-Patterns

1. **AVERAGE instead of SUM** — PPH must be SUM(passengers)/SUM(hours)
2. **Modifying source files** — Bronze is read-only
3. **Hardcoded column positions** — always fuzzy match by name
4. **Skipping validation** — every field gets type coercion + range check
5. **No checksum tracking** — reprocessing unchanged files wastes compute
6. **Missing audit trail** — every run logged with timestamps and counts
7. **No idempotency** — same file must produce identical output
