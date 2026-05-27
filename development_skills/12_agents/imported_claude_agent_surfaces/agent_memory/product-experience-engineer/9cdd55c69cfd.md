# Product Experience Engineer — Agent Memory

## Build System: Vite (migrated from CRA, 2026-03-02)

- Build: `npm run build` = `tsc --noEmit && vite build` → outputs to `dist/`
- Dev: `npm start` = `vite` (port 3000, proxies /api and /ws to localhost:8000)
- Tests: `npm test` = still `react-scripts test` (Jest preserved, do NOT migrate to Vitest)
- Vite entry: `frontend/index.html` (root level, not `public/index.html`)
- CRA `public/index.html` still exists but is only used by `react-scripts test`

## Environment Variables: process.env → vite.config.ts define map

All `REACT_APP_*` vars are mapped in `vite.config.ts` `define` block.
Codebase uses `process.env.REACT_APP_*` — these are NOT changed in source files.
At build time, set `VITE_*` equivalents (e.g. `VITE_API_URL` maps to `REACT_APP_API_URL`).
`process.env.NODE_ENV` is also mapped. Safety net `'process.env': '{}'` is last in define.

Files using REACT_APP vars:
- `src/utils/monitoring.ts` — SENTRY_DSN, ENVIRONMENT, GA_TRACKING_ID, VERSION
- `src/services/baseUrl.ts` — API_URL, ALLOW_CROSS_ORIGIN_API
- `src/services/websocketService.ts` — WS_URL
- `src/pages/AccountPage.tsx` — SUPPORT_EMAIL, SUPPORT_PHONE, VERSION
- `src/hooks/useStreamingAdvisory.ts` — API_URL

## Key Config Files

- `frontend/vite.config.ts` — Vite config with plugins, proxy, define block, manualChunks
- `frontend/index.html` — Vite entry HTML (no %PUBLIC_URL%, has `<script type="module" src="/src/index.tsx">`)
- `frontend/tsconfig.json` — `target: ES2020`, `module: ESNext`, `moduleResolution: bundler`
- `frontend/Dockerfile` — builder copies `dist/` (was `build/`)

## tsconfig Notes

- `moduleResolution: "bundler"` is required for Vite (was "node" for CRA)
- `target: "ES2020"` (was "es5" for CRA)
- `lib: ["ES2020", "DOM", "DOM.Iterable"]` (was ["dom","dom.iterable","es6"])
- All test exclusions preserved so CRA Jest still type-checks correctly
- `vite.config.ts` added to `include` array

## Plugins Installed

- `vite@^5.4.0` — core build tool
- `@vitejs/plugin-react@^4.3.0` — JSX transform + Fast Refresh
- `vite-plugin-wasm@^3.3.0` — WASM imports (Rust/wasm-pack output in src/wasm/pkg)
- `vite-plugin-top-level-await@^1.4.4` — top-level await support
- NO vite-plugin-svgr needed — no ReactComponent SVG imports in codebase

## .gitignore

- Root `.gitignore` at repo root already covers `/frontend/dist/` and `/frontend/build/`
- No frontend-specific `.gitignore` file exists

## manualChunks Strategy

vendor: react + react-dom | mui: @mui/material + icons | charts: recharts + lightweight-charts | redux: @reduxjs/toolkit + react-redux

## UI/UX Audit Findings Summary (2026-03-17)
See `audit-findings.md` for full detail. Top issues:
- `RegisterPage.tsx:236` navigates to `/dashboard` — route does not exist, should be `/`
- `TwoFactorAuthPage.tsx:19` reads `?redirect=` but `useAuth.ts:51` stores `?from=` — 2FA redirect broken
- `NotificationPanel` uses hardcoded `DEFAULT_NOTIFICATIONS` array — never shows real data
- `hasUnread` in `MobileLayout` is always hardcoded `true` — bell badge always shows
- State dropdown in `RegisterPage` only has 10 states (not all 50 US states)
- `VerifyEmailPage` and `TwoFactorAuthPage` use `borderRadius: 2` (1px) — design inconsistency
- `DesktopSideNav` references CSS animation `slideInLeft`/`slideUpFade` with no keyframe definition
- `AccountPage.tsx:869` — pre-existing TS error: `Type 'number' is not assignable to type 'string'`

## Accessibility Fixes Applied (2026-03-17)
- `Input.tsx`: `useId()` generates stable ID; `id={inputId}` on `<input>`, `htmlFor={inputId}` on `<label>`; caller `props.id` takes precedence.
- `MobileHeader.tsx`: both search `<input>` elements (desktop + mobile) have `aria-label="Search stocks, crypto, and more"`. Both Paper/Live toggle button sets have `aria-pressed={mode === m}` and explicit `aria-label`.
- `MobileBottomNav.tsx`: bottom nav buttons changed from `padding: 8` to `padding: '6px 0'` with `minHeight: 44` for WCAG 2.5.5.
- `DesktopSideNav.tsx`: NavItem button gets `aria-current={isActive ? 'page' : undefined}`.
- `ErrorBoundary.tsx`: fallback container outer div gets `role="alert"`.
- `TradingModeIndicator.tsx`: `TradingModeBanner` live and blocked divs get `role="alert"`; emoji `<span>` elements get `aria-hidden="true"`.
- `LoadingSpinner.tsx`: gold variant uses `border-[#C9A227]/20 border-t-[#C9A227]` Tailwind classes; removed conflicting inline `borderTopColor` style and `isGold` branch logic.

## Phase 4.5/4.7/4.8 Components (2026-03-02)

- All 4 new analytics/options/monitoring components use `// @ts-nocheck` at line 1
- Reference pattern: `SectorHeatmap.tsx` (inline styles) | `UnderwaterPlot.tsx` (LW Charts) | `PerformanceDashboard.tsx` (Recharts)
- LW Charts cleanup: always `chartRef.current.remove()` + `chartRef.current = null` in both `buildChart()` and `useEffect` cleanup
- Period toggle: gold button group pill — `rgba(26,34,85,0.45)` bg, `C.glassBorder` border, `borderRadius:12`, `padding:3`
- Active button: `background: C.gold, color: C.bg` | Inactive: `background: transparent, color: C.gray`
- Recharts horizontal bar chart: `BarChart layout="vertical"`, `<Cell>` per entry for dynamic colors
- Options calendar: 31-cell grid, event cells use gold token color scheme, popover on click
- Monitoring 30s auto-refresh: `setInterval` countdown with `setCountdown` + `setLastUpdated`
- Barrel locations: analytics `index.ts`, `frontend/src/components/options/index.ts`, `frontend/src/components/monitoring/index.ts`
