# kpi-card-factory

<!-- Source: migrated from ~/.claude/skills/kpi-card-factory/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: kpi-card-factory -->

**Summary.** KPI card component factory: status indicators (Critical/Warning/On Target/Incentive), trend arrows, sparklines, penalty/incentive amounts, contract threshold bars, count-up animations, responsive grid, accessibility (ARIA, screen reader), and print optimization. Supports React, Vue, Svelte, vanilla JS. Trigger on: 'KPI card', 'metric card', 'status chip', 'KPI component', 'dashboard card'.

# KPI Card Component Factory

## Purpose & Scope

Creates KPI card components with status indicators, trend arrows, sparklines, penalty/incentive amounts, and contract threshold references. Framework-agnostic patterns that work in React, Vue, Svelte, and vanilla JS.

## When to Trigger

- User needs KPI cards, metric cards, status chips, or dashboard card components
- User wants status coloring tied to contract thresholds
- User needs trend indicators or sparklines in cards
- User asks for penalty/incentive amount display

## When NOT to Trigger

- Chart configurations → **chart-builder** skill
- Design tokens → **theme-engine** skill
- Data processing → **data-pipeline** skill

## KPI Card Anatomy

```
┌─────────────────────────────────┐
│ [Status Badge]  [Trend Arrow]   │
│                                 │
│      1.38                       │  ← Value (large, prominent)
│   Passengers Per Hour           │  ← Label
│                                 │
│  ▁▂▃▅▆▇█▇▆▅                    │  ← Sparkline (7-day trailing)
│                                 │
│  Target: 1.50  │  No Penalty    │  ← Threshold + status
│  ──────────────────────────     │  ← Progress bar to target
└─────────────────────────────────┘
```

## Status System

| Status | Color | Condition | Badge Text |
|--------|-------|-----------|-----------|
| CRITICAL | `#EF4444` (red) | Value triggers penalty | Penalty Active |
| WARNING | `#F59E0B` (amber) | Value approaching threshold | At Risk |
| ON_TARGET | `#10B981` (green) | Value meets contract standard | On Target |
| INCENTIVE | `#3B82F6` (blue) | Value qualifies for incentive | Earning Incentive |

```javascript
function getKpiStatus(value, target, penaltyThreshold, incentiveThreshold) {
  if (penaltyThreshold && exceedsPenalty(value, penaltyThreshold)) return 'CRITICAL';
  if (isNearThreshold(value, target, 0.05)) return 'WARNING';
  if (incentiveThreshold && meetsIncentive(value, incentiveThreshold)) return 'INCENTIVE';
  return 'ON_TARGET';
}
```

## React Component

```tsx
interface KpiCardProps {
  label: string;
  value: number;
  target: number;
  format: 'percentage' | 'decimal' | 'currency';
  trend?: { direction: 'up' | 'down' | 'stable'; percent: number };
  sparklineData?: number[];
  penalty?: number;
  incentive?: number;
  contractClause?: string;
  status: 'CRITICAL' | 'WARNING' | 'ON_TARGET' | 'INCENTIVE';
}

function KpiCard({ label, value, target, format, trend, sparklineData, penalty, incentive, status, contractClause }: KpiCardProps) {
  const statusColors = {
    CRITICAL: 'border-red-500 bg-red-50', WARNING: 'border-amber-500 bg-amber-50',
    ON_TARGET: 'border-green-500 bg-green-50', INCENTIVE: 'border-blue-500 bg-blue-50',
  };
  const formatted = formatValue(value, format);

  return (
    <article role="article" aria-label={`${label}: ${formatted}`}
      className={`rounded-lg border-l-4 p-4 shadow-sm ${statusColors[status]}`}>
      <div className="flex items-center justify-between mb-2">
        <StatusBadge status={status} />
        {trend && <TrendArrow direction={trend.direction} percent={trend.percent} />}
      </div>
      <div className="text-3xl font-bold text-gray-900" aria-live="polite">{formatted}</div>
      <div className="text-sm text-gray-600 mt-1">{label}</div>
      {sparklineData && <Sparkline data={sparklineData} className="mt-3" />}
      <div className="flex justify-between items-center mt-3 text-xs text-gray-500">
        <span>Target: {formatValue(target, format)}</span>
        {penalty > 0 && <span className="text-red-600 font-semibold">-${penalty.toLocaleString()}</span>}
        {incentive > 0 && <span className="text-blue-600 font-semibold">+${incentive.toLocaleString()}</span>}
      </div>
      {contractClause && <div className="text-xs text-gray-400 mt-1">{contractClause}</div>}
    </article>
  );
}
```

## Trend Arrow Component

```tsx
function TrendArrow({ direction, percent }: { direction: 'up' | 'down' | 'stable'; percent: number }) {
  const icons = { up: '↑', down: '↓', stable: '→' };
  const colors = { up: 'text-green-600', down: 'text-red-600', stable: 'text-gray-500' };
  return (
    <span className={`text-sm font-medium ${colors[direction]}`}
      aria-label={`${direction === 'up' ? 'Increased' : direction === 'down' ? 'Decreased' : 'Stable'} by ${percent}%`}>
      {icons[direction]} {percent.toFixed(1)}%
    </span>
  );
}
```

## Sparkline (Inline SVG)

```tsx
function Sparkline({ data, width = 120, height = 32 }: { data: number[]; width?: number; height?: number }) {
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data.map((v, i) =>
    `${(i / (data.length - 1)) * width},${height - ((v - min) / range) * height}`
  ).join(' ');
  const trending = data[data.length - 1] >= data[0];
  return (
    <svg width={width} height={height} role="img" aria-label={`Trend: ${trending ? 'improving' : 'declining'}`}>
      <polyline points={points} fill="none"
        stroke={trending ? 'var(--color-status-on-target)' : 'var(--color-status-critical)'}
        strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
```

## Count-Up Animation

```javascript
function animateValue(element, start, end, duration = 1000) {
  const startTime = performance.now();
  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3); // easeOutCubic
    element.textContent = formatValue(start + (end - start) * eased);
    if (progress < 1) requestAnimationFrame(update);
  }
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
    element.textContent = formatValue(end);
  } else {
    requestAnimationFrame(update);
  }
}
```

## Responsive Grid

```css
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--space-4);
  padding: var(--space-4);
}
@media (max-width: 640px) {
  .kpi-grid { grid-template-columns: 1fr; }
}
@media print {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); gap: 8px; }
}
```

## Paratransit KPI Examples

```javascript
const PARATRANSIT_CARDS = [
  { label: 'Passengers Per Hour', value: 1.38, target: 1.5, format: 'decimal',
    status: 'ON_TARGET', contractClause: '$5K penalty only when 0.20+ below 1.5' },
  { label: 'On-Time Performance', value: 90.3, target: 90, format: 'percentage',
    status: 'ON_TARGET', contractClause: '$5K per point below 90%' },
  { label: 'Late Trips', value: 8.2, target: 5, format: 'percentage',
    status: 'CRITICAL', penalty: 10000, contractClause: '$10K flat penalty when >5%' },
  { label: 'Excessively Late', value: 0.35, target: 0.25, format: 'percentage',
    status: 'CRITICAL', penalty: 5000, contractClause: '$5K flat penalty when >0.25%' },
  { label: 'Hold Time', value: 92, target: 95, format: 'percentage',
    status: 'WARNING', penalty: 1200, contractClause: '$400 per point below 95%' },
];
```

## Accessibility

- `role="article"` with `aria-label` including KPI name and value
- `aria-live="polite"` on value display for screen reader updates
- Status badge uses both color AND text (never color-only indicators)
- Trend arrows include `aria-label` with direction and percentage
- Sparkline SVG has `role="img"` with descriptive `aria-label`
- Focus ring visible on interactive cards (keyboard navigation)
- Print variant: no animations, high contrast borders

## Integration

| Agent | Relationship |
|-------|-------------|
| **PRESTIGE** | Design token consumption for card styling |
| **theme-engine** | Status colors from semantic tokens |
| **chart-builder** | Sparkline configurations |
| **All framework agents** | Framework-specific card implementations |

## Anti-Patterns

1. **Color-only status** — always pair color with text/icon
2. **Hardcoded thresholds** — use contract calculator for status determination
3. **Missing ARIA** — every card needs proper accessibility markup
4. **Animation without reduced-motion** — check `prefers-reduced-motion`
5. **Fixed-width cards** — use responsive grid with auto-fit
6. **No print variant** — cards must render cleanly in print
