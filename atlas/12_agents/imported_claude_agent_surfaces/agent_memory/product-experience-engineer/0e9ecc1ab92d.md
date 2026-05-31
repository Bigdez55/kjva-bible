---
name: Frontend Full Audit 2026-03-14
description: Complete end-to-end audit of frontend/src — P0 through P3 findings, architectural notes, and fix priorities
type: project
---

# Frontend Audit — 2026-03-14

## P0 Open Issues (ship-blockers)

1. **`AdvancedOrderEntry` has NO mode prop** — `frontend/src/components/trading/AdvancedOrderEntry.tsx:222`. No paper/live awareness, no "REAL MONEY" banner. Fix: add `mode: 'paper'|'live'` to props, render red live-mode banner.

2. **`Math.random()` in production charts** — `UnderwaterPlot.tsx:62–70`, `BenchmarkChart.tsx:77–78` (both `@ts-nocheck`). `MonitoringDashboard.tsx:98`. Fake financial data shown to real users. Fix: wire real APIs or show "Simulated Data" badge.

3. **Dual auth slice** — `authSlice` manages `isAuthenticated`, `userSlice` manages the actual login flow via `authService`. After `userSlice.login` succeeds, `auth.isAuthenticated` stays false until `checkAuth` is dispatched. Route guard in `App.tsx` reads `state.auth.isAuthenticated` only. Fix: consolidate into single slice.

4. **`AlertManager` shows hardcoded mock alerts as user's real alerts** — `components/alerts/AlertManager.tsx:46,470`. `MOCK_ALERTS` is the `useState` initial value. No API wired. Fix: empty array + empty state UI.

## P1 Open Issues

- **10 files with `@ts-nocheck`** — including 3 trading-path files: `AdvancedChart.tsx`, `PositionsPanel.tsx`, `OrderBlotter.tsx`. Also: `TradingWorkspace.tsx`, `MonitoringDashboard.tsx`, `OptionsDashboard.tsx`, `UnderwaterPlot.tsx`, `BenchmarkChart.tsx`, `CorrelationMatrix.tsx`, `useTradingWorkspace.ts`.

- **76+ localStorage token reads** — httpOnly cookie migration is incomplete and stalled. Every RTK Query `prepareHeaders` reads `localStorage.getItem('token')`. `AdvancedOrderEntry.tsx:48` makes a raw `fetch()` with manual Authorization header from localStorage — bypasses Axios interceptor, no token refresh.

- **`CorrelationMatrix` uses hardcoded mock data** — `analytics/CorrelationMatrix.tsx:27–36`. `analyticsApi.useGetCorrelationMatrixQuery` is wired and ready but not used.

- **`SectorHeatmap` (analytics) uses hardcoded mock data** — `analytics/SectorHeatmap.tsx:35`. `analyticsApi.useGetSectorPerformanceQuery` is ready but not used.

- **`Button` component missing `aria-label` prop and `:focus-visible` ring** — `elson-v2/ui/Button.tsx`. No `aria-label` in interface, no visible keyboard focus indicator.

- **`Card` component only handles Enter key, not Space** — `elson-v2/ui/Card.tsx:106`. WCAG 2.1 SC 2.1.1 violation. Fix: `(e.key === 'Enter' || e.key === ' ')`.

- **`Inner` component with `onClick` is not keyboard accessible** — no `tabIndex`, no `onKeyDown`, no `role`. Used as clickable rows throughout the app.

- **`hasUnread` hardcoded to `true`** — `MobileLayout.tsx:173,231`. Notification bell always shows badge. Fix: wire to real notification data.

- **`OptionsDashboard` is 100% mock data** — `components/options/OptionsDashboard.tsx`. All positions, greeks, calendar, IV ranks are hardcoded constants. Gate with "Coming Soon" until backend is live.

- **`MonitoringDashboard` shows mock service health** — `MOCK_SERVICES` always shows all services as healthy. Ops risk.

## P2 Architectural Issues

- **No 404 page** — `App.tsx:169` catch-all silently redirects. Create a `NotFoundPage`.

- **`App.tsx` only calls `checkAuth` when localStorage token exists** — cookie-based sessions (future auth model) will never be restored on page load. Line 88–91.

- **`TradingContext` uses MUI components** — rest of app is off MUI. Also, `mode` in `TradingContext` and `mode` in `MobileLayout.tsx` are independent states not reliably synchronized.

- **`ThemeContext` is effectively unused** — dark/light toggle not exposed in UI, `useTheme()` has near-zero callsites.

- **`useWebSocketControl` hook has zero consumers** — exported from `LiveDataProvider.tsx` but never called.

- **Tailwind classes mixed into `LiveDataProvider`** — lines 83, 95 use `className="fixed top-16..."`. Rest of app uses inline styles with `C.*` tokens.

- **`CandlestickChart.tsx` and `PortfolioChart.tsx` not removed** — chart migration to `LineChart` is complete (2026-02-20) but these deprecated files still exist in `elson-v2/charts/`.

- **`wasm/pkg/` should be excluded from tsconfig** — auto-generated `.d.ts` files with `any` types are being type-checked.

## P3 Debt

- `transformApiDataToChartData` in `PerformanceDashboard.tsx:26` uses `any[]` param instead of `DailyPnl[]`.
- `userSlice.ts:42–44`: `user: any | null`, `currentUser: any | null` — use `User` from `../../types`.
- `WebSocketEventHandler` type is `(data: any) => void` — `types/websocket.ts:85`.
- `useMarketWebSocket` cleanup removes ALL handlers for event type, not just the specific callback — multi-instance unsafe.
- No tests for order placement, trade confirmation, paper/live mode switching, or `useAutoTrading` auto-start.
- `StrategyBuilder.tsx:82,338`: `Date.now() + Math.random()` ID — use `crypto.randomUUID()`.

## Architecture Grades (2026-03-14)

| Area | Grade |
|------|-------|
| Routing / lazy loading | A |
| Error boundaries | A |
| Component architecture | B |
| Performance / polling | B+ |
| API integration (RTK Query) | C+ |
| Dead code | C |
| Accessibility | C |
| Security (XSS: none found; localStorage: stalled) | C |
| Type safety | D+ |
| Auth state | D |
| Testing | D |
| Mock data in production | F |
