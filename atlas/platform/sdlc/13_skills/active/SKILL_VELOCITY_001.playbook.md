# velocity

<!-- Source: migrated from ~/.claude/skills/velocity/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: velocity -->

**Summary.** Svelte 5 and SvelteKit dashboard engineering with Codename VELOCITY. Covers Svelte Runes for reactive state, Svelte stores, SvelteKit layouts and routing, Chart.js integration, and building lightweight high-performance KPI dashboards without the overhead of larger frameworks. Trigger on: "Svelte dashboard", "SvelteKit", "Svelte charts", "Runes", "VELOCITY", "svelte store".

# Svelte 5 / SvelteKit Dashboard Engineering (VELOCITY)

## Core Expertise
- Svelte 5 Runes: $state, $derived, $effect for reactive KPI data
- Svelte stores: writable, readable, derived for shared dashboard state
- SvelteKit layouts, +page.svelte, load functions for data fetching
- Chart.js integration with Svelte component wrappers
- Lightweight bundle output: typically 40-80KB vs 150KB+ for React equivalents
- Server-side rendering with SvelteKit for fast initial dashboard load

## When to Use
- Building a lightweight, standalone dashboard (not embedded in SharePoint)
- User references Svelte, SvelteKit, or Runes specifically
- Performance-critical dashboard where bundle size is a priority
- Simple KPI display dashboard without complex state management needs

## Key Patterns

1. **KPI Store with Runes ($state)**
```svelte
<script>
  // Svelte 5 Runes — class-based store
  class KpiStore {
    data = $state(null);
    loading = $state(false);
    error = $state(null);
    get penalties() {
      return $derived(this.data ? calculateTotalPenalties(this.data) : 0);
    }
    async load() {
      this.loading = true;
      try { this.data = await fetchKpis(); }
      catch (e) { this.error = e.message; }
      finally { this.loading = false; }
    }
  }
  export const kpiStore = new KpiStore();
</script>
```

2. **Reactive KPI Card Component**
```svelte
<!-- KpiCard.svelte -->
<script>
  let { label, value, target, penalty = 0 } = $props();
  let status = $derived(
    penalty > 0 ? 'critical' : value >= target ? 'on-target' : 'warning'
  );
  let statusLabel = $derived(
    penalty > 0 ? `$${penalty.toLocaleString()} penalty` : 'On Target'
  );
</script>

<article class="kpi-card kpi-card--{status}">
  <h3>{label}</h3>
  <div class="kpi-value">{value}</div>
  <span class="status-chip status-chip--{status}">{statusLabel}</span>
</article>
```

3. **SvelteKit Load Function for KPI Data**
```javascript
// src/routes/dashboard/+page.js
export async function load({ fetch }) {
  const response = await fetch('/api/kpis.json');
  if (!response.ok) throw error(500, 'Failed to load KPI data');
  const kpis = await response.json();
  return { kpis, generatedAt: new Date().toISOString() };
}
```

4. **SvelteKit Layout with Theme Provider**
```svelte
<!-- src/routes/+layout.svelte -->
<script>
  import { page } from '$app/stores';
  let { children } = $props();
</script>

<div class="dashboard-shell" data-theme="transdev">
  <nav class="sidebar">
    <a href="/dashboard" class:active={$page.url.pathname === '/dashboard'}>Dashboard</a>
    <a href="/reports"   class:active={$page.url.pathname === '/reports'}>Reports</a>
  </nav>
  <main id="main-content">{@render children()}</main>
</div>
```

5. **Chart.js Integration**
```svelte
<!-- LineChart.svelte -->
<script>
  import { onMount, onDestroy } from 'svelte';
  import Chart from 'chart.js/auto';
  let { data, labels } = $props();
  let canvas, chart;
  onMount(() => {
    chart = new Chart(canvas, {
      type: 'line',
      data: { labels, datasets: [{ label: 'KPI Trend', data, borderColor: '#DB0717', tension: 0.4 }] },
    });
  });
  $effect(() => {
    if (chart) { chart.data.datasets[0].data = data; chart.update(); }
  });
  onDestroy(() => chart?.destroy());
</script>
<canvas bind:this={canvas} aria-label="KPI trend chart"></canvas>
```

6. **Derived Store for Penalty Summary**
```javascript
import { derived } from 'svelte/store';
import { kpis } from './kpi-store';
export const penaltySummary = derived(kpis, $kpis => ({
  total: calculateTotalPenalties($kpis),
  breakdown: getPenaltyBreakdown($kpis),
  healthScore: calculateOverallHealth($kpis),
}));
```

## Standards
- Use Runes ($state, $derived, $effect) for all new Svelte 5 components; avoid legacy stores where possible
- Chart.js instances must be destroyed in onDestroy to prevent memory leaks
- SvelteKit load functions throw error() for non-200 responses; never return null silently
- Reactive declarations ($derived) for any value computed from props or state
- Keep component files under 150 lines; extract logic into .js/ts files alongside .svelte files
- Use SvelteKit's server-side load for SEO-critical or initial-paint-critical KPI data
