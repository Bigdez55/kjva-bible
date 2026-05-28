# perf-profiler

<!-- Source: migrated from ~/.claude/skills/perf-profiler/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: perf-profiler -->

**Summary.** Dashboard performance profiling and optimization: Core Web Vitals targets (LCP < 2.5s, CLS < 0.1, INP < 200ms), Lighthouse CI with performance budgets, bundle analysis (webpack-bundle-analyzer, source-map-explorer), code splitting, lazy loading, Web Worker offloading, virtual scrolling, image optimization, caching strategies, render optimization, memory profiling, and React DevTools Profiler. Trigger on: 'performance', 'profiling', 'slow', 'Lighthouse', 'bundle size', 'Web Worker', 'lazy loading', 'virtual scroll', 'Core Web Vitals', 're-render', 'memory leak'.

# Dashboard Performance Profiling & Optimization

## Purpose & Scope

Profiles and optimizes dashboard performance across all layers: network, rendering, computation, and memory. Produces Lighthouse CI configs, Web Worker scripts, code splitting strategies, and performance budgets.

## When to Trigger

- Dashboard is sluggish when scrolling, filtering, or switching views
- User asks about Lighthouse scores, bundle size, or Core Web Vitals
- Charts flicker or re-render when unrelated state changes
- Memory usage grows over time without stabilizing (memory leak)
- SharePoint List queries are slow or returning too much data
- User reports "the dashboard feels slow"
- Need Web Worker for heavy computation

## When NOT to Trigger

- Chart configuration → **chart-builder** skill
- Data processing logic → **data-pipeline** skill
- Testing → **test-harness** skill
- Full performance architecture → **TURBO** agent

## Core Web Vitals Targets

| Metric | Target | What It Measures |
|--------|--------|-----------------|
| **LCP** | < 2.5s | Largest Contentful Paint — main content visible |
| **CLS** | < 0.1 | Cumulative Layout Shift — visual stability |
| **INP** | < 200ms | Interaction to Next Paint — input responsiveness |
| **FCP** | < 1.8s | First Contentful Paint — first visual feedback |
| **TTFB** | < 800ms | Time to First Byte — server response time |

## Lighthouse CI Configuration

```json
{
  "ci": {
    "collect": {
      "numberOfRuns": 3,
      "startServerCommand": "npm run preview",
      "url": ["http://localhost:4173/"]
    },
    "assert": {
      "assertions": {
        "categories:performance": ["error", { "minScore": 0.9 }],
        "categories:accessibility": ["error", { "minScore": 0.9 }],
        "categories:best-practices": ["warn", { "minScore": 0.9 }],
        "first-contentful-paint": ["error", { "maxNumericValue": 1800 }],
        "largest-contentful-paint": ["error", { "maxNumericValue": 2500 }],
        "cumulative-layout-shift": ["error", { "maxNumericValue": 0.1 }],
        "total-blocking-time": ["error", { "maxNumericValue": 300 }]
      }
    },
    "upload": {
      "target": "temporary-public-storage"
    }
  }
}
```

## Performance Budget

```json
{
  "budgets": [
    {
      "resourceSizes": [
        { "resourceType": "script", "budget": 300 },
        { "resourceType": "stylesheet", "budget": 50 },
        { "resourceType": "image", "budget": 200 },
        { "resourceType": "total", "budget": 600 }
      ],
      "resourceCounts": [
        { "resourceType": "script", "budget": 15 },
        { "resourceType": "third-party", "budget": 5 }
      ]
    }
  ]
}
```

## Performance Audit Protocol

### Phase 1: Measure
```javascript
// web-vitals library
import { onLCP, onCLS, onINP, onFCP, onTTFB } from 'web-vitals';

function reportVitals(metric) {
  console.log(`${metric.name}: ${metric.value.toFixed(1)} (${metric.rating})`);
  // Send to analytics endpoint
  fetch('/api/vitals', {
    method: 'POST',
    body: JSON.stringify({ name: metric.name, value: metric.value, id: metric.id }),
  });
}

onLCP(reportVitals);
onCLS(reportVitals);
onINP(reportVitals);
onFCP(reportVitals);
onTTFB(reportVitals);
```

### Phase 2: Identify Bottlenecks

```bash
# Bundle analysis
npx webpack-bundle-analyzer dist/stats.json
npx source-map-explorer dist/assets/*.js

# Lighthouse audit
npx lighthouse http://localhost:3000 --output html --output-path ./lighthouse-report.html

# Long task detection
```

```javascript
const observer = new PerformanceObserver(list => {
  for (const entry of list.getEntries()) {
    if (entry.duration > 50) {
      console.warn(`Long task: ${entry.duration.toFixed(0)}ms`, entry);
    }
  }
});
observer.observe({ entryTypes: ['longtask'] });
```

### Phase 3: Optimize

#### Code Splitting

```javascript
// Route-based splitting (React)
const PenaltyReport = lazy(() => import('./pages/PenaltyReport'));
const HistoricalData = lazy(() => import('./pages/HistoricalData'));

// Vendor splitting (Vite)
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          charts: ['recharts'],
          export: ['jspdf', 'xlsx'],
        },
      },
    },
  },
});
```

#### Lazy Loading

```tsx
// React.lazy + Suspense
const TrendChart = lazy(() => import('./components/TrendChart'));

function Dashboard() {
  return (
    <Suspense fallback={<ChartSkeleton />}>
      <TrendChart data={data} />
    </Suspense>
  );
}

// IntersectionObserver for below-fold content
function useLazyLoad(ref) {
  const [isVisible, setVisible] = useState(false);
  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setVisible(true); observer.disconnect(); } },
      { rootMargin: '200px' }
    );
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, [ref]);
  return isVisible;
}
```

#### Web Worker for KPI Calculations

```javascript
// kpi-worker.js
self.addEventListener('message', (e) => {
  const { dailyRows } = e.data;

  // Heavy computation moved off main thread
  const totals = dailyRows.reduce((acc, row) => ({
    passengers: acc.passengers + (row.totalPassengers || 0),
    hours: acc.hours + (row.totalHours || 0),
    trips: acc.trips + (row.totalTrips || 0),
    onTime: acc.onTime + (row.onTimeTrips || 0),
    late: acc.late + (row.lateTrips || 0),
    excessiveLate: acc.excessiveLate + (row.excessivelyLateTrips || 0),
    missed: acc.missed + (row.missedTrips || 0),
  }), { passengers: 0, hours: 0, trips: 0, onTime: 0, late: 0, excessiveLate: 0, missed: 0 });

  const kpis = {
    pph: totals.hours > 0 ? totals.passengers / totals.hours : 0,
    otp: totals.trips > 0 ? (totals.onTime / totals.trips) * 100 : 0,
    lateTripsPercent: totals.trips > 0 ? (totals.late / totals.trips) * 100 : 0,
    excessivelyLatePercent: totals.trips > 0 ? (totals.excessiveLate / totals.trips) * 100 : 0,
    missedTripsPercent: totals.trips > 0 ? (totals.missed / totals.trips) * 100 : 0,
  };

  self.postMessage({ kpis, totals, rowCount: dailyRows.length });
});

// Usage in React
function useKpiWorker() {
  const workerRef = useRef(null);
  const [result, setResult] = useState(null);

  useEffect(() => {
    workerRef.current = new Worker(new URL('./kpi-worker.js', import.meta.url));
    workerRef.current.onmessage = (e) => setResult(e.data);
    return () => workerRef.current?.terminate();
  }, []);

  const calculate = useCallback((dailyRows) => {
    workerRef.current?.postMessage({ dailyRows });
  }, []);

  return { calculate, result };
}
```

#### Virtual Scrolling

```tsx
import { useVirtualizer } from '@tanstack/react-virtual';

function VirtualTable({ data }) {
  const parentRef = useRef(null);
  const rowVirtualizer = useVirtualizer({
    count: data.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 40,
    overscan: 20,
  });

  return (
    <div ref={parentRef} style={{ height: '600px', overflow: 'auto' }}>
      <div style={{ height: `${rowVirtualizer.getTotalSize()}px`, position: 'relative' }}>
        {rowVirtualizer.getVirtualItems().map(virtualRow => (
          <div key={virtualRow.index}
            style={{ position: 'absolute', top: virtualRow.start, height: virtualRow.size, width: '100%' }}>
            <TableRow data={data[virtualRow.index]} />
          </div>
        ))}
      </div>
    </div>
  );
}
```

## React Render Optimization

```tsx
// React Profiler wrapper
import { Profiler } from 'react';

function onRenderCallback(id, phase, actualDuration) {
  if (actualDuration > 16) {
    console.warn(`[Profiler] ${id} (${phase}) took ${actualDuration.toFixed(1)}ms`);
  }
}

<Profiler id="KpiGrid" onRender={onRenderCallback}>
  <KpiGrid kpis={kpis} />
</Profiler>

// Memoization
const MemoizedKpiCard = React.memo(KpiCard, (prev, next) =>
  prev.value === next.value && prev.status === next.status
);

// useMemo for expensive calculations
const penaltyTotal = useMemo(
  () => kpis.reduce((sum, kpi) => sum + (kpi.penalty || 0), 0),
  [kpis]
);

// Why-Did-You-Render (development only)
// src/wdyr.js
if (process.env.NODE_ENV === 'development') {
  const whyDidYouRender = require('@welldone-software/why-did-you-render');
  whyDidYouRender(React, { trackAllPureComponents: true });
}
KpiCard.whyDidYouRender = true;
```

## PnPjs Query Optimization

```typescript
// BAD: returns all columns, all rows
const items = await sp.web.lists.getByTitle('KPI Historical Data').items();

// GOOD: select only needed columns, limit rows
const items = await sp.web.lists.getByTitle('KPI Historical Data').items
  .select('ReportMonth', 'PPH', 'OTP', 'LateTripsPercent', 'TotalPenalty', 'IsComplete')
  .filter('IsComplete eq 1')
  .orderBy('ReportMonth', false)
  .top(12)(); // last 12 months only
```

## Memory Leak Prevention

```javascript
// Always destroy chart instances on unmount
useEffect(() => {
  const chart = new ApexCharts(chartRef.current, options);
  chart.render();
  return () => chart.destroy(); // REQUIRED
}, []);

// AbortController for fetch cleanup
useEffect(() => {
  const controller = new AbortController();
  fetch('/api/kpis', { signal: controller.signal })
    .then(r => r.json())
    .then(setData)
    .catch(err => { if (err.name !== 'AbortError') console.error(err); });
  return () => controller.abort();
}, []);

// Event listener cleanup
useEffect(() => {
  const handler = () => { /* ... */ };
  window.addEventListener('resize', handler);
  return () => window.removeEventListener('resize', handler);
}, []);
```

## Caching Strategies

```javascript
// HTTP cache headers (server)
res.setHeader('Cache-Control', 'public, max-age=300, stale-while-revalidate=60');

// React memoization
const expensiveResult = useMemo(() => computeHealthScore(kpis), [kpis]);

// SWR/React Query for data fetching with caching
const { data } = useSWR('/api/kpis', fetcher, {
  refreshInterval: 300000, // 5 minutes
  revalidateOnFocus: false,
});
```

## Integration

| Agent | Relationship |
|-------|-------------|
| **TURBO** (Performance) | Full performance architecture |
| **chart-builder** | Chart rendering optimization |
| **responsive-layout** | Responsive image and layout performance |
| **SENTINEL** | Lighthouse CI in test pipeline |

## Standards

- Any component render exceeding 16ms should be investigated
- Always destroy chart instances in cleanup functions
- PnPjs queries must use `$select` — never fetch all columns
- Use `$top` to limit SharePoint queries (default 100, max 5000)
- Memoize object/array/function references passed as props
- Run heap snapshots before and after navigation to detect leaks
- No memory leaks after 30 minutes of dashboard usage

## Anti-Patterns

1. **Premature optimization** — measure first, optimize what matters
2. **Missing cleanup** — always return cleanup functions in useEffect
3. **Fetching all columns** — use $select to name specific columns
4. **New references in render** — memoize objects, arrays, and callbacks
5. **No performance budget** — set Lighthouse CI thresholds in CI
6. **Ignoring memory** — profile memory after 30 minutes of use
