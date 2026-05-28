# spfx-dashboard-builder

<!-- Source: migrated from ~/.claude/skills/spfx-dashboard-builder/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: spfx-dashboard-builder -->

**Summary.** Use this skill when the user wants to design, scaffold, or code a SharePoint Framework (SPFx) dashboard. Triggers on requests for "SPFx web parts," "SharePoint dashboards," "PnPjs integration," "Fluent UI charts," "KPI_DailyData list," or "gulpfile build."

# SPFx Dashboard Specialist

Expert in building high-performance, contract-compliant KPI dashboards using SPFx 1.18.x with React 17, Fluent UI v8, ApexCharts, and PnPjs v3.

## Core Expertise

- SPFx 1.18.x project structure, manifest configuration, and gulp build pipeline
- PnPjs v3 (`@pnp/sp`) for SharePoint List queries with `$filter`, `$select`, `$orderby`, `$top`
- Fluent UI v8 components: Pivot (tabs), Shimmer, MessageBar, DetailsList, DatePicker, ContextualMenu
- ApexCharts via `react-apexcharts`: radial bar gauges, waterfall bars, multi-line trends, donut, sparklines
- ContractTerms.ts as single source of truth — never duplicate thresholds in component files
- KPICalculator.ts client-side verification against Power Automate pre-computed values

## When to Use

Activate for any request involving:
- Building or modifying the Transdev Paratransit KPI Dashboard SPFx web part
- Scaffolding new SPFx web parts or components
- PnPjs list queries or SharePoint data access patterns
- Fluent UI layout or theming within an SPFx context
- gulpfile, config.json, package-solution.json, or .yo-rc.json configuration
- CI/CD pipeline for `.sppkg` build and App Catalog deployment

## Key Patterns

1. **PnPjs initialization in onInit()**
```typescript
protected async onInit(): Promise<void> {
  await super.onInit();
  this._sp = spfi(this.properties.listSiteUrl || undefined).using(SPFx(this.context));
}
```

2. **Parallel data queries**
```typescript
const [latest, historical] = await Promise.all([
  sp.web.lists.getByTitle('KPI_DailyData')
    .items.filter(`ReportMonth eq '${month}'`).orderBy('ReportDate', false).top(1)(),
  sp.web.lists.getByTitle('KPI_DailyData')
    .items.filter(buildDateFilter(range)).orderBy('ReportDate', true).select(COLS)(),
]);
```

3. **Stale data detection**
```typescript
const stale = latest ? isStale(latest.ReportDate) : true; // 24-hour threshold
```

4. **Error boundary pattern per chart**
```tsx
<ErrorBoundary fallback={<div>Chart unavailable</div>}>
  <ReactApexChart type="radialBar" series={[score]} options={opts} />
</ErrorBoundary>
```

5. **Property pane for cross-site list URL**
```typescript
PropertyPaneTextField('listSiteUrl', {
  label: 'SharePoint Site URL (optional)',
  placeholder: 'https://tenant.sharepoint.com/sites/operations',
})
```

## Standards

- All contract values come exclusively from `ContractTerms.ts` — no magic numbers in components
- PPH penalty has `TODO: VERIFY CONTRACT` flag until clause is confirmed against the contract document
- `AIRecommendationsEngine.calculateCurrentPenalties()` must delegate to `KPICalculator` — never use ad-hoc formulas
- MTD PPH = `SUM(daily_passengers) / SUM(daily_hours)` — NOT average of daily PPH values
- Six tabs in order: Executive View → KPI Overview → Trends & Analysis → Contract Compliance → Live Calculations → AI Insights
- LoadingSkeleton (Shimmer) shown during fetch — no blank screens or plain spinners
- ErrorState shown on PnPjs failure with Retry button — no white-screen crashes
