# fortress

<!-- Source: migrated from ~/.claude/skills/fortress/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: fortress -->

**Summary.** Angular 17+ dashboard engineering with Codename FORTRESS. Covers NgRx state management, Angular Material components, RxJS reactive patterns, standalone components, signals, and zone-less change detection for high-performance KPI dashboards. Trigger on: "Angular dashboard", "NgRx", "Angular Material chart", "standalone component", "Angular signals", "FORTRESS".

# Angular 17+ Dashboard Engineering (FORTRESS)

## Core Expertise
- Standalone components with bootstrapApplication (no NgModules)
- Angular Signals for reactive KPI state without RxJS boilerplate
- NgRx Store + Effects for complex async data flows
- Angular Material: MatTable, MatCard, MatProgressSpinner for dashboard UIs
- RxJS operators: switchMap, combineLatest, shareReplay for data streams
- Zone-less change detection with ChangeDetectionStrategy.OnPush

## When to Use
- Building Angular-based SPFx web parts or standalone Angular apps
- User references NgRx, Angular Material, or Angular-specific patterns
- Dashboard needs reactive state management with selectors and effects
- Migrating from AngularJS or Angular < 14 to modern standalone architecture

## Key Patterns

1. **Standalone KPI Dashboard Component**
```typescript
@Component({
  selector: 'app-kpi-dashboard',
  standalone: true,
  imports: [CommonModule, MatCardModule, NgApexchartsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-card *ngFor="let kpi of kpis()">
      <mat-card-title>{{ kpi.label }}</mat-card-title>
      <mat-card-content>{{ kpi.value }}</mat-card-content>
    </mat-card>
  `,
})
export class KpiDashboardComponent {
  kpis = this.store.selectSignal(selectAllKpis);
  constructor(private store: Store) {}
}
```

2. **NgRx KPI State Slice**
```typescript
// kpi.state.ts
export interface KpiState { data: KpiData | null; loading: boolean; error: string | null; }
export const kpiFeature = createFeature({
  name: 'kpi',
  reducer: createReducer(
    { data: null, loading: false, error: null } as KpiState,
    on(KpiActions.load,        state => ({ ...state, loading: true })),
    on(KpiActions.loadSuccess, (state, { data }) => ({ ...state, data, loading: false })),
    on(KpiActions.loadFailure, (state, { error }) => ({ ...state, error, loading: false })),
  ),
});
export const { selectData, selectLoading } = kpiFeature;
```

3. **NgRx Effect for Excel Data Fetch**
```typescript
loadKpis$ = createEffect(() => this.actions$.pipe(
  ofType(KpiActions.load),
  switchMap(() => this.kpiService.fetchLatest().pipe(
    map(data => KpiActions.loadSuccess({ data })),
    catchError(err => of(KpiActions.loadFailure({ error: err.message }))),
  )),
));
```

4. **Signal-Based Computed KPI Metrics**
```typescript
export class KpiMetricsService {
  private rawKpis = signal<KpiData | null>(null);
  totalPenalty = computed(() => {
    const k = this.rawKpis();
    if (!k) return 0;
    return calculateTotalPenalties(k); // from kpi-calculator
  });
  healthScore = computed(() => calculateOverallHealth(this.rawKpis()));
  setKpis(data: KpiData) { this.rawKpis.set(data); }
}
```

5. **RxJS Data Combination for Dashboard**
```typescript
vm$ = combineLatest([
  this.store.select(selectKpiData),
  this.store.select(selectAiInsights),
  this.store.select(selectAlerts),
]).pipe(
  map(([kpis, insights, alerts]) => ({ kpis, insights, alerts })),
  shareReplay(1),
);
```

6. **Angular Material Table with KPI Data**
```typescript
displayedColumns = ['metric', 'value', 'target', 'status', 'penalty'];
dataSource = new MatTableDataSource<KpiRow>();
ngOnInit() {
  this.store.select(selectKpiRows).subscribe(rows => {
    this.dataSource.data = rows;
  });
}
```

## Standards
- Use standalone components for all new Angular work; avoid NgModules
- Prefer Signals over BehaviorSubject for local component state
- Always use ChangeDetectionStrategy.OnPush on dashboard components
- NgRx effects must handle errors with catchError returning failure action
- Use trackBy in *ngFor loops over KPI arrays to prevent full re-renders
- Lazy-load heavy chart modules: loadChildren for route-based code splitting
