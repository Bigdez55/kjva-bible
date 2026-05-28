# chart-builder

<!-- Source: migrated from ~/.claude/skills/chart-builder/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: chart-builder -->

**Summary.** Universal chart configuration generator: Recharts, ECharts, Chart.js, Plotly, D3, Nivo, ApexCharts. Chart type selection guide, responsive wrappers, theme-aware palettes, axis config, tooltips, animations, data formatting, performance for large datasets, and accessibility. Trigger on: 'chart', 'visualization', 'graph', 'gauge', 'sparkline', 'Recharts', 'ECharts', 'Chart.js', 'Plotly', 'D3', 'Nivo', 'ApexCharts'.

# Universal Chart Configuration Generator

## Purpose & Scope

Generates chart configurations for any supported visualization library. Handles chart type selection, responsive sizing, theming, data formatting, tooltips, animations, and accessibility.

## When to Trigger

- User needs charts, graphs, gauges, sparklines, or data visualizations
- User asks for specific library configs (Recharts, ECharts, Chart.js, Plotly, etc.)
- User needs responsive chart wrappers or theme-aware palettes
- User wants chart type recommendations for specific data shapes

## When NOT to Trigger

- Custom bespoke D3 visualizations → **CANVAS** agent
- Design system colors → **theme-engine** skill
- Data transformation before charting → **data-pipeline** skill

## Chart Type Selection Guide

| Data Shape | Chart | Best Library |
|-----------|-------|-------------|
| KPI value vs target | Gauge / Radial Bar | ApexCharts, ECharts |
| Trend over time | Line / Area | Recharts, Chart.js |
| Category comparison | Horizontal Bar | Recharts, Nivo |
| Part-of-whole | Donut / Pie | Recharts, ECharts |
| Penalty breakdown | Waterfall / Stacked Bar | ECharts, Plotly |
| Distribution | Histogram / Box | Plotly, D3 |
| Correlation | Scatter / Bubble | Plotly, Nivo |
| Multi-metric | Radar | Chart.js, ECharts |
| Inline trend | Sparkline | Recharts, ApexCharts |
| Geographic | Choropleth Map | D3, Plotly |
| Hierarchical | Treemap / Sunburst | ECharts, D3 |

## Recharts (React)

```tsx
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine } from 'recharts';

function KpiTrendChart({ data, target, label }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
        <XAxis dataKey="month" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} />
        <Tooltip contentStyle={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: '8px' }}
          formatter={(value) => [`${value.toFixed(1)}%`, label]} />
        <ReferenceLine y={target} stroke="var(--color-success)" strokeDasharray="5 5"
          label={{ value: `Target: ${target}%`, position: 'right' }} />
        <Line type="monotone" dataKey="value" stroke="var(--color-primary)"
          strokeWidth={2} dot={{ r: 4 }} activeDot={{ r: 6 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}
```

## ECharts Gauge

```javascript
function createGaugeConfig(value, target, label) {
  return {
    series: [{
      type: 'gauge', startAngle: 200, endAngle: -20, min: 0, max: 100,
      pointer: { show: true, length: '60%', width: 6 },
      axisLine: { lineStyle: { width: 20, color: [
        [target / 100 * 0.9, '#EF4444'], [target / 100, '#F59E0B'], [1, '#10B981'],
      ]}},
      axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false },
      detail: { formatter: '{value}%', fontSize: 24, fontWeight: 'bold', offsetCenter: [0, '70%'] },
      data: [{ value, name: label }],
    }],
  };
}
```

## Chart.js Bar + Line Overlay

```javascript
function createBarChartConfig(labels, values, thresholds) {
  return {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Current', data: values,
        backgroundColor: values.map((v, i) => v > thresholds[i] ? '#EF4444' : '#10B981'),
        borderRadius: 4, barThickness: 40,
      }, {
        label: 'Target', data: thresholds, type: 'line',
        borderColor: '#6B7280', borderDash: [5, 5], pointRadius: 0, fill: false,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom' },
        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%` } } },
      scales: { y: { beginAtZero: true }, x: { grid: { display: false } } },
    },
  };
}
```

## ApexCharts Sparkline

```javascript
function createSparklineConfig(data) {
  return {
    chart: { type: 'line', sparkline: { enabled: true }, height: 40, width: 120 },
    series: [{ data }],
    stroke: { width: 2, curve: 'smooth' },
    colors: [data[data.length - 1] >= data[0] ? '#10B981' : '#EF4444'],
    tooltip: { fixed: { enabled: false }, y: { formatter: (val) => val.toFixed(1) } },
  };
}
```

## Plotly Waterfall (Penalty Breakdown)

```javascript
function createWaterfallConfig(penalties) {
  return {
    data: [{
      type: 'waterfall', orientation: 'v',
      x: penalties.map(p => p.label),
      y: penalties.map(p => p.amount),
      connector: { line: { color: 'rgb(63, 63, 63)' } },
      decreasing: { marker: { color: '#EF4444' } },
      increasing: { marker: { color: '#10B981' } },
      totals: { marker: { color: '#3B82F6' } },
    }],
    layout: { title: 'Monthly Penalty Breakdown', showlegend: false },
  };
}
```

## Theme-Aware Palettes

```javascript
const CHART_PALETTES = {
  light: {
    primary: ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899'],
    status: { critical: '#EF4444', warning: '#F59E0B', onTarget: '#10B981', incentive: '#3B82F6' },
    grid: 'rgba(0,0,0,0.06)', text: '#374151', background: '#FFFFFF',
  },
  dark: {
    primary: ['#60A5FA', '#34D399', '#FBBF24', '#F87171', '#A78BFA', '#F472B6'],
    status: { critical: '#F87171', warning: '#FBBF24', onTarget: '#34D399', incentive: '#60A5FA' },
    grid: 'rgba(255,255,255,0.08)', text: '#E5E7EB', background: '#1F2937',
  },
  colorblindSafe: {
    primary: ['#0072B2', '#009E73', '#D55E00', '#CC79A7', '#F0E442', '#56B4E9'],
    status: { critical: '#D55E00', warning: '#F0E442', onTarget: '#009E73', incentive: '#0072B2' },
  },
};
```

## Responsive Wrapper

```tsx
function ResponsiveChart({ children, minHeight = 300, aspectRatio }) {
  const containerRef = useRef(null);
  const [dims, setDims] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const observer = new ResizeObserver(entries => {
      const { width } = entries[0].contentRect;
      setDims({ width, height: aspectRatio ? width / aspectRatio : Math.max(minHeight, width * 0.5) });
    });
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [aspectRatio, minHeight]);
  return (
    <div ref={containerRef} style={{ width: '100%', minHeight }}>
      {dims.width > 0 && children(dims)}
    </div>
  );
}
```

## Data Formatters

```javascript
const formatters = {
  percentage: (v, d = 1) => `${v.toFixed(d)}%`,
  currency: (v) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v),
  number: (v, d = 0) => new Intl.NumberFormat('en-US', { maximumFractionDigits: d }).format(v),
  pph: (v) => v.toFixed(2),
  compact: (v) => new Intl.NumberFormat('en-US', { notation: 'compact' }).format(v),
};
```

## Accessibility

- `aria-label` on chart containers describing what the chart shows
- `<table>` fallback with same data for screen readers
- Patterns/textures in addition to color for status differentiation
- 4.5:1 contrast ratio for text on chart backgrounds
- Keyboard navigation for interactive elements
- Alt text for exported chart images

## Performance for Large Datasets

- **>1000 points**: Downsample to ~200 visible points
- **>10K points**: Use Canvas rendering (Chart.js, ECharts)
- **>100K points**: Use WebGL (Plotly.js)
- **Tooltips**: Only compute for visible/hovered points
- **Lazy load**: Dynamic `import()` for chart libraries

## Integration

| Agent | Relationship |
|-------|-------------|
| **CANVAS** (D3) | Custom visualizations beyond standard charts |
| **PRESTIGE** (Design) | Color palettes and visual hierarchy |
| **TURBO** (Performance) | Chart rendering optimization |
| **All framework agents** | Library-specific chart configs |

## Anti-Patterns

1. **3D charts** — distort data perception
2. **Pie charts for >5 categories** — use bar charts
3. **Dual Y-axes without clear labels** — confuses readers
4. **Animation on every render** — only on data change
5. **Missing baselines** — Y-axis starts at 0 for bars
6. **Hardcoded colors** — use theme tokens
7. **No responsive wrapper** — charts must resize with container
