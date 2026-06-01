# responsive-layout

<!-- Source: migrated from ~/.claude/skills/responsive-layout/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: responsive-layout -->

**Summary.** Mobile-first responsive dashboard layouts: CSS Grid auto-fill/auto-fit patterns, container queries, Fluent UI Stack/StackItem for SPFx, mobile-first breakpoint system (320-1280px), horizontal scroll tables with sticky columns, touch-friendly 44px tap targets, viewport-aware chart heights, swipe gestures for mobile navigation, print layouts, CSS custom properties for spacing, dashboard shell patterns (sidebar + header + content), and responsive image optimization. Trigger on: 'responsive', 'mobile layout', 'breakpoints', 'grid layout', 'tablet dashboard', 'mobile-friendly', 'container query', 'swipe', 'touch target', 'print layout'.

# Responsive Dashboard Layouts

## Purpose & Scope

Builds mobile-first responsive grid systems for KPI dashboards. Covers CSS Grid patterns, container queries, Fluent UI layouts for SPFx, breakpoint systems, touch targets, swipe gestures, chart height adaptation, print-optimized layouts, and dashboard shell architecture (sidebar, header, content area).

## When to Trigger

- KPI dashboard needs to work on mobile, tablet, and desktop
- SPFx web part is embedded in a SharePoint page with variable column widths
- Table or chart is overflowing on small screens
- Touch targets are too small for mobile users
- Need dashboard shell (sidebar + header + main content)
- Print layout needed for executive reports
- Swipe gestures for mobile navigation between views

## When NOT to Trigger

- Chart configuration → **chart-builder** skill
- Theme colors and tokens → **theme-engine** skill
- KPI card components → **kpi-card-factory** skill
- Full design system → **PRESTIGE** agent

## Breakpoint System

```css
/* Mobile-first breakpoint tokens */
:root {
  --bp-xs: 320px;   /* Small phones */
  --bp-sm: 640px;   /* Large phones / landscape */
  --bp-md: 768px;   /* Tablets portrait */
  --bp-lg: 1024px;  /* Tablets landscape / small desktop */
  --bp-xl: 1280px;  /* Desktop */
  --bp-2xl: 1536px; /* Large desktop */
}

/* Usage: always mobile-first (min-width) */
@media (min-width: 640px)  { /* sm: 2-column grids */ }
@media (min-width: 768px)  { /* md: sidebar visible */ }
@media (min-width: 1024px) { /* lg: 3-column grids */ }
@media (min-width: 1280px) { /* xl: 4-column grids, full dashboard */ }
```

### Test Breakpoints

| Device | Width | Columns | Key Behavior |
|--------|-------|---------|-------------|
| iPhone SE | 375px | 1 | Stacked cards, hamburger nav, collapsed charts |
| iPhone 14 Pro | 393px | 1 | Same as SE with slightly wider cards |
| iPad Mini | 768px | 2 | Side-by-side cards, visible sidebar toggle |
| iPad Pro | 1024px | 3 | Sidebar visible, chart row |
| Desktop | 1280px | 4 | Full 4-column grid, all panels visible |
| Large Desktop | 1536px | 4 | Max-width container, centered content |

## Dashboard Shell Architecture

### Sidebar + Header + Content

```css
.dashboard-shell {
  display: grid;
  grid-template-columns: 1fr;
  grid-template-rows: auto 1fr;
  grid-template-areas:
    "header"
    "content";
  min-height: 100vh;
}

.dashboard-header {
  grid-area: header;
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  padding: var(--space-3) var(--space-4);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.dashboard-sidebar {
  display: none; /* Hidden on mobile */
  grid-area: sidebar;
  background: var(--color-surface-secondary);
  border-right: 1px solid var(--color-border);
  padding: var(--space-4);
  overflow-y: auto;
  width: 260px;
}

.dashboard-content {
  grid-area: content;
  padding: var(--space-4);
  overflow-y: auto;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}

@media (min-width: 768px) {
  .dashboard-shell {
    grid-template-columns: 260px 1fr;
    grid-template-areas:
      "sidebar header"
      "sidebar content";
  }
  .dashboard-sidebar { display: block; }
}
```

### React Dashboard Shell Component

```tsx
function DashboardShell({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const isMobile = useMediaQuery('(max-width: 767px)');

  return (
    <div className="dashboard-shell">
      <header className="dashboard-header">
        {isMobile && (
          <button className="hamburger" onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label="Toggle navigation" aria-expanded={sidebarOpen}>
            <span className="hamburger-icon" />
          </button>
        )}
        <h1 className="dashboard-title">KPI Dashboard</h1>
        <div className="header-actions">
          <MonthSelector />
          <ExportMenu />
        </div>
      </header>

      {(sidebarOpen || !isMobile) && (
        <nav className="dashboard-sidebar" aria-label="Dashboard navigation">
          <SidebarNav onItemClick={() => isMobile && setSidebarOpen(false)} />
        </nav>
      )}

      {/* Overlay to close sidebar on mobile */}
      {isMobile && sidebarOpen && (
        <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)}
          aria-hidden="true" />
      )}

      <main className="dashboard-content" role="main">
        {children}
      </main>
    </div>
  );
}
```

## KPI Card Grid

### CSS Grid (Mobile-First)

```css
.kpi-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-4);
  padding: var(--space-4);
}

@media (min-width: 640px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
}

@media (min-width: 1024px) {
  .kpi-grid { grid-template-columns: repeat(3, 1fr); }
}

@media (min-width: 1280px) {
  .kpi-grid { grid-template-columns: repeat(4, 1fr); }
}

/* Auto-fill pattern: cards fill available space */
.kpi-grid-auto {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-4);
}
```

### Container Queries (Modern Browsers)

```css
.kpi-grid-container {
  container-type: inline-size;
  container-name: kpi-grid;
}

@container kpi-grid (min-width: 480px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
}

@container kpi-grid (min-width: 720px) {
  .kpi-grid { grid-template-columns: repeat(3, 1fr); }
}

@container kpi-grid (min-width: 960px) {
  .kpi-grid { grid-template-columns: repeat(4, 1fr); }
}
```

### Fluent UI Stack Layout (SPFx)

```tsx
import { Stack, IStackTokens } from '@fluentui/react';

const gridTokens: IStackTokens = { childrenGap: 16 };

function KpiGridSPFx({ kpis }: { kpis: IKpiData[] }) {
  return (
    <Stack horizontal wrap tokens={gridTokens}>
      {kpis.map(kpi => (
        <Stack.Item key={kpi.id}
          styles={{ root: { flexBasis: 'calc(25% - 12px)', minWidth: 240 } }}>
          <KpiCard {...kpi} />
        </Stack.Item>
      ))}
    </Stack>
  );
}
```

## Responsive Data Tables

### Horizontal Scroll with Sticky First Column

```css
.table-container {
  width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  border: 1px solid var(--color-border);
  border-radius: 8px;
}

.table-container table {
  min-width: 800px;
  border-collapse: collapse;
  width: 100%;
}

/* Sticky first column for row labels */
.table-container td:first-child,
.table-container th:first-child {
  position: sticky;
  left: 0;
  z-index: 1;
  background: var(--color-surface);
  box-shadow: 2px 0 4px rgba(0, 0, 0, 0.06);
}

/* Sticky header row */
.table-container thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--color-surface);
}

/* First column AND header intersection gets highest z-index */
.table-container thead th:first-child {
  z-index: 3;
}

/* Scroll indicator gradient */
.table-container::after {
  content: '';
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 24px;
  pointer-events: none;
  background: linear-gradient(to left, rgba(0, 0, 0, 0.06), transparent);
}
```

### Card Layout for Mobile Tables

```css
/* Transform table to card layout on small screens */
@media (max-width: 640px) {
  .responsive-table thead { display: none; }
  .responsive-table tr {
    display: block;
    border: 1px solid var(--color-border);
    border-radius: 8px;
    margin-bottom: var(--space-3);
    padding: var(--space-3);
  }
  .responsive-table td {
    display: flex;
    justify-content: space-between;
    padding: var(--space-2) 0;
    border-bottom: 1px solid var(--color-border-light);
  }
  .responsive-table td::before {
    content: attr(data-label);
    font-weight: 600;
    color: var(--color-text-secondary);
  }
  .responsive-table td:last-child { border-bottom: none; }
}
```

## Touch-Friendly Tap Targets

```css
/* WCAG 2.5.8: minimum 44x44px touch targets */
.touch-target {
  min-height: 44px;
  min-width: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
}

/* Apply to all interactive elements */
.kpi-card__accordion-toggle,
.export-button,
.alert-dismiss,
.nav-link,
.filter-chip,
.month-selector button,
.pagination button {
  min-height: 44px;
  min-width: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

/* Ensure adequate spacing between adjacent targets */
.button-group > * + * {
  margin-left: var(--space-2);
}

/* Larger targets on touch-only devices */
@media (pointer: coarse) {
  .filter-chip { padding: 12px 16px; font-size: 16px; }
  .pagination button { min-width: 48px; min-height: 48px; }
}
```

## Viewport-Aware Chart Heights

```tsx
function useChartHeight(desktopHeight = 300, mobileHeight = 180) {
  const [height, setHeight] = useState(desktopHeight);

  useEffect(() => {
    const update = () => {
      const width = window.innerWidth;
      if (width < 640) setHeight(mobileHeight);
      else if (width < 1024) setHeight(Math.round((desktopHeight + mobileHeight) / 2));
      else setHeight(desktopHeight);
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, [desktopHeight, mobileHeight]);

  return height;
}

// Usage
function TrendChart({ data }) {
  const chartHeight = useChartHeight(320, 200);
  return (
    <div style={{ width: '100%', height: chartHeight }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <XAxis dataKey="month" tick={{ fontSize: 12 }} />
          <YAxis width={40} />
          <Line type="monotone" dataKey="otp" stroke="var(--color-primary)" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

### useMediaQuery Hook

```tsx
function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(query).matches : false
  );

  useEffect(() => {
    const mql = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, [query]);

  return matches;
}

// Usage
const isMobile = useMediaQuery('(max-width: 639px)');
const isTablet = useMediaQuery('(min-width: 640px) and (max-width: 1023px)');
const isDesktop = useMediaQuery('(min-width: 1024px)');
```

## Swipe Gestures for Mobile Navigation

```tsx
function useSwipe(onSwipeLeft: () => void, onSwipeRight: () => void, threshold = 50) {
  const touchStart = useRef<{ x: number; y: number } | null>(null);

  const handlers = useMemo(() => ({
    onTouchStart: (e: React.TouchEvent) => {
      touchStart.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    },
    onTouchEnd: (e: React.TouchEvent) => {
      if (!touchStart.current) return;
      const deltaX = e.changedTouches[0].clientX - touchStart.current.x;
      const deltaY = e.changedTouches[0].clientY - touchStart.current.y;

      // Only trigger if horizontal swipe is dominant
      if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > threshold) {
        if (deltaX > 0) onSwipeRight();
        else onSwipeLeft();
      }
      touchStart.current = null;
    },
  }), [onSwipeLeft, onSwipeRight, threshold]);

  return handlers;
}

// Usage: swipe between dashboard views
function DashboardViews({ views }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const swipeHandlers = useSwipe(
    () => setActiveIndex(i => Math.min(i + 1, views.length - 1)),
    () => setActiveIndex(i => Math.max(i - 1, 0))
  );

  return (
    <div {...swipeHandlers} className="view-container">
      <div className="view-track" style={{ transform: `translateX(-${activeIndex * 100}%)` }}>
        {views.map((View, i) => (
          <div key={i} className="view-slide"><View /></div>
        ))}
      </div>
      <div className="view-dots" role="tablist">
        {views.map((_, i) => (
          <button key={i} role="tab" aria-selected={i === activeIndex}
            className={`dot ${i === activeIndex ? 'active' : ''}`}
            onClick={() => setActiveIndex(i)} />
        ))}
      </div>
    </div>
  );
}
```

## SPFx Web Part Container Awareness

```css
/* SPFx zones have variable widths; use max-width guards */
.dashboard-root {
  max-width: 1400px;
  margin: 0 auto;
  container-type: inline-size;
}

/* Compact mode for narrow SharePoint columns */
@container (max-width: 480px) {
  .kpi-card__value { font-size: var(--text-xl); }
  .kpi-card__header { flex-direction: column; gap: var(--space-1); }
  .status-chip { font-size: 11px; padding: 2px 6px; }
  .chart-container { display: none; } /* Hide charts in narrow columns */
  .kpi-card__trend { display: none; }
}

@container (min-width: 481px) and (max-width: 768px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .chart-container { height: 200px; }
}

@container (min-width: 769px) {
  .kpi-grid { grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
  .chart-container { height: 300px; }
}
```

## Print Layout

```css
@media print {
  /* Reset to clean white background */
  body {
    font-size: 10pt;
    color: #000;
    background: #FFF;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  /* Hide non-essential UI */
  .no-print,
  .dashboard-sidebar,
  .dashboard-header .hamburger,
  .export-buttons,
  .alert-feed,
  .swipe-dots,
  .filter-bar { display: none !important; }

  /* Optimize KPI grid for print */
  .kpi-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }

  .kpi-card {
    border: 1px solid #CCC;
    page-break-inside: avoid;
    break-inside: avoid;
    padding: 8px;
  }

  /* Table optimization */
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid #CCC; padding: 4px 8px; font-size: 9pt; }

  /* Chart sizing for print */
  .chart-container {
    height: 200px !important;
    page-break-inside: avoid;
  }

  /* Page setup */
  @page { margin: 1.5cm; size: landscape; }
  @page :first { margin-top: 2cm; }
  .page-break { page-break-before: always; break-before: page; }

  /* Report header and footer */
  .print-header {
    display: block !important;
    text-align: center;
    margin-bottom: 16px;
  }
  .print-footer {
    display: block !important;
    text-align: center;
    font-size: 8pt;
    color: #666;
    margin-top: 16px;
  }
}
```

## Responsive Image Optimization

```tsx
function ResponsiveLogo() {
  return (
    <picture>
      <source srcSet="/logo-small.webp" media="(max-width: 639px)" type="image/webp" />
      <source srcSet="/logo-medium.webp" media="(max-width: 1023px)" type="image/webp" />
      <source srcSet="/logo-large.webp" media="(min-width: 1024px)" type="image/webp" />
      <img src="/logo-large.png" alt="Transdev KPI Dashboard" loading="lazy"
        width={200} height={50} style={{ maxWidth: '100%', height: 'auto' }} />
    </picture>
  );
}
```

## Integration

| Agent | Relationship |
|-------|-------------|
| **PRESTIGE** (Design) | Full design system with responsive tokens |
| **TURBO** (Performance) | Responsive image optimization, lazy loading |
| **BEACON** (Accessibility) | Touch target compliance, print accessibility |
| **All framework agents** | Framework-specific responsive patterns |

## Standards

- Mobile-first: write base styles for 320px, add breakpoints upward with `min-width`
- Minimum touch target size: 44x44px for all buttons, links, and interactive chips
- KPI card minimum width: 240px; use `minmax(240px, 1fr)` in grid definitions
- Horizontal scroll tables must have `-webkit-overflow-scrolling: touch` for iOS momentum
- Chart heights must be explicitly set; never rely on auto height inside flex/grid containers
- Test at 375px (iPhone SE), 768px (iPad), and 1280px (desktop) as core breakpoints
- Container queries preferred over media queries for component-level responsiveness
- Print layout must use `page-break-inside: avoid` on cards and charts
- Swipe gestures must check `deltaX > deltaY` to avoid hijacking vertical scroll

## Anti-Patterns

1. **Desktop-first breakpoints** — always start mobile-first with `min-width`
2. **Fixed pixel widths** — use `minmax()`, `%`, and `fr` units for flexibility
3. **Hiding content on mobile** — restructure layout, don't hide critical data
4. **Small touch targets** — 44px minimum, larger on `pointer: coarse` devices
5. **Media queries for SPFx** — use container queries; SPFx zone widths vary independently of viewport
6. **Auto-height charts** — always set explicit height; charts collapse in flex/grid without it
7. **No print styles** — executives print dashboards; always include `@media print`
