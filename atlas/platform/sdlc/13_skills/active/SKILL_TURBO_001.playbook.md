# turbo

<!-- Source: migrated from ~/.claude/skills/turbo/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: turbo -->

**Summary.** Dashboard performance optimization: React.memo and useMemo for expensive KPI calculations, TanStack Virtual for large data tables, code splitting for chart libraries, bundle analysis, Lighthouse performance budgets, and lazy loading strategies. Trigger on: "performance", "optimization", "slow dashboard", "bundle size", "Lighthouse", "virtualization", "lazy load".

# Dashboard Performance Optimization

## Core Expertise
- React rendering optimization: memo, useMemo, useCallback, key stability
- TanStack Virtual for virtualizing large KPI history tables (1k+ rows)
- Code splitting: dynamic import for heavy chart libraries (ApexCharts, D3)
- Bundle analysis: webpack-bundle-analyzer, rollup-plugin-visualizer
- Lighthouse CI budgets: target LCP <2.5s, TBT <200ms, CLS <0.1
- Web Worker offloading for contract penalty calculations

## When to Use
- Dashboard feels slow to render or interact with
- Bundle size exceeds 500KB gzipped
- Table or list has more than 100 rows visible
- Lighthouse performance score below 70
- Chart re-renders on every parent state change

## Key Patterns

1. **Memoize KPI Calculation**
```jsx
import { useMemo } from 'react';
function KpiSummary({ rawData }) {
  const penalties = useMemo(() => calculateTotalPenalties(rawData), [rawData]);
  const healthScore = useMemo(() => calculateOverallHealth(rawData), [rawData]);
  return <div>Score: {healthScore} | Penalties: ${penalties.toLocaleString()}</div>;
}
// Wrap with React.memo to skip re-render when parent re-renders
export default React.memo(KpiSummary);
```

2. **Lazy Load Chart Library**
```jsx
import { lazy, Suspense } from 'react';
const ApexChart = lazy(() => import('react-apexcharts'));

function KpiChart({ series, options }) {
  return (
    <Suspense fallback={<div className="chart-skeleton" style={{ height: 300 }} />}>
      <ApexChart type="line" series={series} options={options} height={300} />
    </Suspense>
  );
}
```

3. **TanStack Virtual for KPI History Table**
```jsx
import { useVirtualizer } from '@tanstack/react-virtual';
function KpiHistoryTable({ rows }) {
  const parentRef = useRef(null);
  const virtualizer = useVirtualizer({
    count: rows.length, getScrollElement: () => parentRef.current,
    estimateSize: () => 48, overscan: 5,
  });
  return (
    <div ref={parentRef} style={{ height: 400, overflow: 'auto' }}>
      <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
        {virtualizer.getVirtualItems().map(item => (
          <div key={item.key} style={{ position: 'absolute', top: item.start, height: item.size, width: '100%' }}>
            <KpiRow row={rows[item.index]} />
          </div>
        ))}
      </div>
    </div>
  );
}
```

4. **Web Worker for Heavy Calculations**
```javascript
// penalty-worker.js
self.onmessage = ({ data: kpis }) => {
  const result = calculateAllPenalties(kpis); // expensive
  self.postMessage(result);
};

// In component:
const workerRef = useRef(null);
useEffect(() => {
  workerRef.current = new Worker(new URL('./penalty-worker.js', import.meta.url));
  workerRef.current.onmessage = ({ data }) => setPenalties(data);
  return () => workerRef.current.terminate();
}, []);
const calculate = useCallback(kpis => workerRef.current.postMessage(kpis), []);
```

5. **Stable Keys and useCallback**
```jsx
// BAD: new function reference on every render causes child re-renders
<KpiCard onDismiss={() => handleDismiss(kpi.id)} />

// GOOD: stable reference
const handleDismiss = useCallback(id => setAlerts(a => a.filter(x => x.id !== id)), []);
<KpiCard onDismiss={handleDismiss} id={kpi.id} />
```

6. **Vite Bundle Splitting Config**
```javascript
// vite.config.js
export default {
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'chart-libs': ['react-apexcharts', 'apexcharts'],
          'd3-bundle':  ['d3'],
          'table':      ['@tanstack/react-table', '@tanstack/react-virtual'],
        },
      },
    },
  },
};
```

## Standards
- Target Lighthouse performance score >= 85 for dashboard pages
- Wrap all chart components in React.memo; charts are expensive to re-render
- Never import an entire chart library; always use named imports or dynamic import
- Run `npx webpack-bundle-analyzer` or `npx vite-bundle-visualizer` before each major release
- Virtual scroll any list or table with more than 100 rows
- Offload calculations taking >16ms to a Web Worker to avoid blocking the main thread
