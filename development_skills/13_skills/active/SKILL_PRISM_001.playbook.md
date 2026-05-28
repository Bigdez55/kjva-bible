# prism

<!-- Source: migrated from ~/.claude/skills/prism/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: prism -->

**Summary.** React 18+ / Next.js 14+ dashboard engineering with Codename PRISM. Covers Recharts and Nivo chart composition, TanStack Table and Query, Zustand state management, shadcn/ui components, RSC data loading, ISR for KPI pages, Suspense boundaries, and type-safe data layers. Trigger on: "React dashboard", "Next.js KPI", "Recharts chart", "Nivo heatmap", "TanStack Table", "Zustand store", "shadcn dashboard", "PRISM".

# React 18+ / Next.js 14+ Dashboard Engineering (PRISM)

## Core Expertise
- React Server Components for server-fetched KPI data with zero client JS
- Suspense boundaries with skeleton fallbacks for independent chart loading
- Recharts declarative bar/line/area/pie charts with responsive containers
- Nivo heatmaps, sankey diagrams, and calendar views for complex visualizations
- TanStack Table v8 headless tables with sorting, filtering, virtual scroll
- TanStack Query v5 for server state caching and background refetching
- Zustand stores with persist middleware for dashboard filter state

## When to Use
- Building a React or Next.js KPI dashboard from scratch
- User references Recharts, Nivo, TanStack Table, shadcn/ui, or Zustand
- Migrating an existing dashboard (HTML, Vue, Angular) to React/Next.js
- Dashboard needs ISR for pages that update hourly or daily
- Performance optimization of React dashboard components (memo, useDeferredValue)

## Key Patterns

1. **RSC Dashboard Page with ISR**
```tsx
// app/(dashboard)/page.tsx — Server Component
import { Suspense } from 'react';
import { KPICardGrid } from '@/components/cards/KPICardGrid';
import { PenaltyChart } from '@/components/charts/PenaltyChart';
import { getKPIData } from '@/lib/api';

export const revalidate = 3600; // ISR: revalidate hourly

export default async function DashboardPage() {
  const kpiData = await getKPIData();
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 p-6">
      <Suspense fallback={<div className="h-32 animate-pulse bg-muted rounded-lg" />}>
        <KPICardGrid data={kpiData.metrics} />
      </Suspense>
      <Suspense fallback={<div className="h-64 animate-pulse bg-muted rounded-lg" />}>
        <PenaltyChart penalties={kpiData.penalties} />
      </Suspense>
    </div>
  );
}
```

2. **KPI Card with memo and Status Colors**
```tsx
'use client';
import { memo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import type { KPIMetric } from '@/types/kpi';

const statusColors = {
  critical: 'border-red-500 bg-red-50 dark:bg-red-950',
  warning: 'border-yellow-500 bg-yellow-50 dark:bg-yellow-950',
  'on-target': 'border-green-500 bg-green-50 dark:bg-green-950',
  exceeding: 'border-blue-500 bg-blue-50 dark:bg-blue-950',
} as const;

export const KPICard = memo(function KPICard({ metric }: { metric: KPIMetric }) {
  return (
    <Card className={cn('border-l-4', statusColors[metric.status])}
          role="button" aria-label={`${metric.name}: ${metric.value}`}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-muted-foreground">{metric.name}</CardTitle>
      </CardHeader>
      <CardContent>
        <span className="text-2xl font-bold">{metric.value}</span>
        {metric.penaltyAmount > 0 && (
          <p className="text-xs font-semibold text-red-600">
            Penalty: ${metric.penaltyAmount.toLocaleString()}
          </p>
        )}
      </CardContent>
    </Card>
  );
});
```

3. **Recharts Bar Chart Wrapper**
```tsx
'use client';
import { memo, useMemo } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

export const PenaltyBarChart = memo(function PenaltyBarChart({
  data, height = 300,
}: { data: { name: string; value: number }[]; height?: number }) {
  const colored = useMemo(() =>
    data.map(d => ({ ...d, fill: d.value > 0 ? '#ef4444' : '#22c55e' })), [data]);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={colored}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name" />
        <YAxis />
        <Tooltip />
        <Bar dataKey="value" radius={[4, 4, 0, 0]}>
          {colored.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
});
```

4. **TanStack Query Hook with Zod Validation**
```typescript
// hooks/useKPIData.ts
import { useSuspenseQuery } from '@tanstack/react-query';
import { z } from 'zod';

const KPISchema = z.object({
  metrics: z.array(z.object({
    id: z.string(), name: z.string(), value: z.number(),
    target: z.number(), status: z.enum(['critical', 'warning', 'on-target', 'exceeding']),
    penaltyAmount: z.number().default(0),
  })),
  penalties: z.object({ total: z.number(), breakdown: z.record(z.number()) }),
  healthScore: z.number().min(0).max(100),
});

export function useKPIData() {
  return useSuspenseQuery({
    queryKey: ['kpi-data'],
    queryFn: async () => KPISchema.parse(await fetch('/api/kpis').then(r => r.json())),
    staleTime: 5 * 60_000,
    refetchInterval: 60_000,
  });
}
```

5. **Zustand Dashboard Store with Persist**
```typescript
// stores/dashboardStore.ts
import { create } from 'zustand';
import { persist, devtools } from 'zustand/middleware';

interface DashboardState {
  dateRange: { start: Date; end: Date };
  activeView: 'overview' | 'kpis' | 'reports';
  sidebarOpen: boolean;
  selectedKPIs: string[];
  setDateRange: (range: DashboardState['dateRange']) => void;
  toggleKPI: (id: string) => void;
  resetFilters: () => void;
}

export const useDashboardStore = create<DashboardState>()(
  devtools(persist((set) => ({
    dateRange: { start: new Date(Date.now() - 30 * 86400000), end: new Date() },
    activeView: 'overview',
    sidebarOpen: true,
    selectedKPIs: [],
    setDateRange: (range) => set({ dateRange: range }),
    toggleKPI: (id) => set((s) => ({
      selectedKPIs: s.selectedKPIs.includes(id)
        ? s.selectedKPIs.filter(k => k !== id)
        : [...s.selectedKPIs, id],
    })),
    resetFilters: () => set({ selectedKPIs: [], dateRange: { start: new Date(Date.now() - 30 * 86400000), end: new Date() } }),
  }), { name: 'dashboard-state' }))
);
```

6. **Error Boundary for Chart Failures**
```tsx
'use client';
import { Component, ReactNode } from 'react';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';

export class ChartErrorBoundary extends Component<
  { children: ReactNode; chartName: string },
  { hasError: boolean; error: Error | null }
> {
  state = { hasError: false, error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { hasError: true, error }; }
  render() {
    if (this.state.hasError) {
      return (
        <Alert variant="destructive">
          <AlertTitle>Chart Error: {this.props.chartName}</AlertTitle>
          <AlertDescription>{this.state.error?.message}</AlertDescription>
        </Alert>
      );
    }
    return this.props.children;
  }
}
```

## Standards
- Use React.memo on all KPI cards and chart wrappers receiving stable props
- useMemo for penalty calculations and data transformations; useDeferredValue for filter inputs
- Every async section needs a Suspense boundary with a skeleton, not a spinner
- All chart wrappers include role="img" and aria-label for accessibility
- Fetch static/semi-static KPI data in RSC; reserve client-side fetching for real-time updates
- TypeScript strict mode with Zod validation at API boundaries
- Dynamic imports (next/dynamic) for heavy chart libraries below the fold
