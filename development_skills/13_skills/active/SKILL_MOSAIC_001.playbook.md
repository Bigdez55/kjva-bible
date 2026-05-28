# mosaic

<!-- Source: migrated from ~/.claude/skills/mosaic/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: mosaic -->

**Summary.** Vue 3 / Nuxt 3 dashboard engineering with Codename MOSAIC. Covers Composition API with script setup, Pinia setup stores, VueUse composables, Vuetify 3 and Element Plus components, Vue-ECharts charting, Nuxt server routes, and SSR hydration patterns for KPI dashboards. Trigger on: "Vue dashboard", "Nuxt 3", "Vuetify data table", "Element Plus", "Pinia store", "Vue-ECharts", "Vue 3 composable", "MOSAIC".

# Vue 3 / Nuxt 3 Dashboard Engineering (MOSAIC)

## Core Expertise
- Composition API with `<script setup lang="ts">` for all dashboard components
- Pinia setup stores (function syntax) for dashboard state with devtools integration
- VueUse composables: useDark, useBreakpoints, useWebSocket, useResizeObserver
- Vuetify 3 MatTable, navigation drawers, and dense data display components
- Element Plus tables, forms, and date pickers as an alternative UI framework
- Vue-ECharts for bar, line, gauge, heatmap, treemap, and radar charts
- Nuxt 3 server routes, useFetch/useAsyncData, and auto-imports

## When to Use
- Building a Vue 3 or Nuxt 3 KPI dashboard from scratch
- User references Vuetify, Element Plus, Pinia, VueUse, or Vue-ECharts
- Migrating an existing dashboard to Vue 3 / Nuxt 3
- Dashboard needs server-side rendering with Nuxt for fast initial paint
- Creating composable patterns for reusable KPI data fetching logic

## Key Patterns

1. **Nuxt useFetch Composable for KPI Data**
```typescript
// composables/useKPIData.ts
export function useKPIData(options?: { autoRefresh?: boolean }) {
  const { data, pending, error, refresh } = useFetch<KPIDataResponse>('/api/kpis', {
    transform: (response) => ({
      ...response,
      metrics: response.metrics.map(m => ({
        ...m,
        formattedValue: formatKPIValue(m.value, m.unit),
        statusColor: getStatusColor(m.status),
      })),
    }),
  });

  if (options?.autoRefresh) {
    const interval = ref<ReturnType<typeof setInterval>>();
    onMounted(() => { interval.value = setInterval(refresh, 60_000); });
    onUnmounted(() => { if (interval.value) clearInterval(interval.value); });
  }

  const criticalKPIs = computed(() => data.value?.metrics.filter(m => m.status === 'critical') ?? []);
  const totalPenalties = computed(() => data.value?.penalties.total ?? 0);

  return { kpiData: data, isLoading: pending, error, refresh, criticalKPIs, totalPenalties };
}
```

2. **Pinia Setup Store for Dashboard State**
```typescript
// stores/dashboard.ts
import { defineStore } from 'pinia';

export const useDashboardStore = defineStore('dashboard', () => {
  const dateRange = ref({ start: new Date(Date.now() - 30 * 86400000), end: new Date() });
  const activeView = ref<'overview' | 'kpis' | 'reports'>('overview');
  const sidebarCollapsed = ref(false);
  const selectedKPIIds = ref<string[]>([]);
  const darkMode = useDark();

  const hasActiveFilters = computed(() => selectedKPIIds.value.length > 0);

  function toggleKPI(id: string) {
    const idx = selectedKPIIds.value.indexOf(id);
    idx === -1 ? selectedKPIIds.value.push(id) : selectedKPIIds.value.splice(idx, 1);
  }
  function resetFilters() {
    selectedKPIIds.value = [];
    dateRange.value = { start: new Date(Date.now() - 30 * 86400000), end: new Date() };
  }

  return { dateRange, activeView, sidebarCollapsed, selectedKPIIds, darkMode, hasActiveFilters, toggleKPI, resetFilters };
});
```

3. **KPI Card Component with defineProps**
```vue
<!-- components/cards/KPICard.vue -->
<script setup lang="ts">
import type { KPIMetric } from '@/types/kpi';

const props = withDefaults(defineProps<{ metric: KPIMetric; compact?: boolean }>(), { compact: false });
const emit = defineEmits<{ select: [metricId: string] }>();

const statusClasses = computed(() => {
  const map: Record<string, string> = {
    critical: 'border-l-red-500 bg-red-50 dark:bg-red-950',
    warning: 'border-l-yellow-500 bg-yellow-50 dark:bg-yellow-950',
    'on-target': 'border-l-green-500 bg-green-50 dark:bg-green-950',
    exceeding: 'border-l-blue-500 bg-blue-50 dark:bg-blue-950',
  };
  return `rounded-lg border-l-4 p-4 cursor-pointer hover:shadow-md ${map[props.metric.status] ?? ''}`;
});
</script>

<template>
  <div :class="statusClasses" role="button" :aria-label="`${metric.name}: ${metric.value}`"
       @click="emit('select', metric.id)">
    <p class="text-sm font-medium text-gray-500 dark:text-gray-400">{{ metric.name }}</p>
    <span class="text-2xl font-bold">{{ metric.value }}</span>
    <p v-if="metric.penaltyAmount > 0" class="text-xs font-semibold text-red-600">
      Penalty: ${{ metric.penaltyAmount.toLocaleString() }}
    </p>
  </div>
</template>
```

4. **Vue-ECharts Bar Chart with Dark Mode**
```typescript
// composables/useChartOptions.ts
import type { EChartsOption } from 'echarts';

export function useChartOptions() {
  const darkMode = useDark();
  const theme = computed(() => ({
    bg: darkMode.value ? '#1e1e2e' : '#ffffff',
    text: darkMode.value ? '#cdd6f4' : '#1e293b',
    grid: darkMode.value ? '#313244' : '#e2e8f0',
    colors: ['#3b82f6', '#22c55e', '#ef4444', '#f59e0b', '#8b5cf6'],
  }));

  function buildBarChart(data: { name: string; value: number }[], title: string): EChartsOption {
    return {
      backgroundColor: theme.value.bg,
      title: { text: title, textStyle: { color: theme.value.text, fontSize: 14 } },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: data.map(d => d.name), axisLabel: { color: theme.value.text } },
      yAxis: { type: 'value', splitLine: { lineStyle: { color: theme.value.grid } } },
      series: [{ type: 'bar', data: data.map(d => d.value), itemStyle: { borderRadius: [4, 4, 0, 0] } }],
    };
  }

  function buildGauge(value: number, title: string): EChartsOption {
    return {
      series: [{
        type: 'gauge', min: 0, max: 100, data: [{ value, name: title }],
        axisLine: { lineStyle: { width: 20, color: [[0.5, '#ef4444'], [0.75, '#f59e0b'], [1, '#22c55e']] } },
      }],
    };
  }

  return { theme, buildBarChart, buildGauge };
}
```

5. **Nuxt Server Route for KPI API**
```typescript
// server/api/kpis.get.ts
import { readFile } from 'fs/promises';
import { resolve } from 'path';

export default defineEventHandler(async () => {
  const raw = await readFile(resolve('data/processed/current-kpis.json'), 'utf-8');
  const kpis = JSON.parse(raw);
  return {
    metrics: kpis.metrics,
    penalties: kpis.penalties,
    healthScore: kpis.healthScore,
    lastUpdated: kpis.lastUpdated,
  };
});
```

6. **Dashboard Layout with Sidebar**
```vue
<!-- layouts/dashboard.vue -->
<script setup lang="ts">
const store = useDashboardStore();
</script>

<template>
  <div class="flex h-screen overflow-hidden bg-background">
    <aside :class="['transition-all', store.sidebarCollapsed ? 'w-16' : 'w-64']">
      <nav class="p-4 space-y-2">
        <NuxtLink to="/" class="nav-link">Overview</NuxtLink>
        <NuxtLink to="/kpis" class="nav-link">KPI Details</NuxtLink>
        <NuxtLink to="/reports" class="nav-link">Reports</NuxtLink>
      </nav>
    </aside>
    <main class="flex-1 overflow-y-auto p-6">
      <slot />
    </main>
  </div>
</template>
```

## Standards
- All components use `<script setup lang="ts">`; never use Options API or setup() return
- Prefer `computed` over `watch` for derived values; reserve `watch` for side effects only
- Use `shallowRef` for large datasets (1000+ rows) to avoid deep proxy overhead
- Pinia stores use function syntax (setup stores); never use option syntax or Vuex
- Nuxt auto-imports: do not add manual import statements for composables or components
- All composables follow the `use` prefix naming convention in the `composables/` directory
- Use `<ClientOnly>` for components that access `window` or `document` during SSR
