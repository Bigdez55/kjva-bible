# prestige

<!-- Source: migrated from ~/.claude/skills/prestige/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: prestige -->

**Summary.** Dashboard UI/UX design systems for paratransit dashboards: Transdev brand guidelines (red #DB0717), Fluent UI theming, shadcn/ui customization, color palettes for KPI status indicators, typography systems, spacing scales, and component visual hierarchy. Trigger on: "design system", "brand guidelines", "UI theme", "color palette", "Transdev styling", "Fluent UI theme", "shadcn".

# Dashboard Design Systems

## Core Expertise
- Transdev brand color system: primary red #DB0717, neutrals, status colors
- Fluent UI v9 theme tokens and component customization
- shadcn/ui component variants for dashboard-specific patterns
- Status color semantics: Critical, Warning, On Target, Incentive
- Typography scale using Segoe UI (Microsoft/SharePoint environment)
- 8px spacing grid, card elevation system, responsive breakpoints

## When to Use
- Creating or restyling dashboard components to match Transdev branding
- Defining color palette for KPI status indicators
- Setting up Fluent UI theme provider with brand overrides
- Choosing typography, spacing, or shadow tokens for new components
- Ensuring visual consistency across KPI cards, charts, and tables

## Key Patterns

1. **Transdev Brand Color Tokens**
```javascript
const TRANSDEV_TOKENS = {
  // Brand
  colorBrandPrimary:     '#DB0717', // Transdev red
  colorBrandDark:        '#A8050F',
  colorBrandLight:       '#F5A0A4',

  // Status semantics
  colorStatusCritical:   '#DB0717',
  colorStatusWarning:    '#D97706',
  colorStatusOnTarget:   '#16A34A',
  colorStatusIncentive:  '#7C3AED',
  colorStatusNeutral:    '#6B7280',

  // Surface
  colorSurfaceCard:      '#FFFFFF',
  colorSurfacePage:      '#F3F4F6',
  colorSurfaceDark:      '#111827',

  // Text
  colorTextPrimary:      '#111827',
  colorTextSecondary:    '#6B7280',
  colorTextOnRed:        '#FFFFFF',
};
```

2. **Fluent UI v9 Theme Override**
```javascript
import { createLightTheme } from '@fluentui/react-components';
export const transdevTheme = createLightTheme({
  10:  '#2D0003', 20: '#5A0007', 30: '#870009', 40: '#B4000D',
  50:  '#DB0717', 60: '#E53B3E', 70: '#ED6568', 80: '#F38F91',
  90:  '#F7B5B6', 100: '#FAD4D5', 110: '#FDE9EA', 120: '#FFF2F3',
  130: '#FFF7F7', 140: '#FFFBFB', 150: '#FFFDFD', 160: '#FFFFFF',
});
```

3. **Status Chip Styles**
```css
.status-chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 10px; border-radius: 12px;
  font-size: 12px; font-weight: 600; font-family: 'Segoe UI', sans-serif;
}
.status-chip--critical  { background: #FEE2E2; color: #991B1B; }
.status-chip--warning   { background: #FEF3C7; color: #92400E; }
.status-chip--on-target { background: #DCFCE7; color: #166534; }
.status-chip--incentive { background: #EDE9FE; color: #4C1D95; }
```

4. **Typography Scale (Segoe UI)**
```css
:root {
  --font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  --text-xs:   11px;
  --text-sm:   13px;
  --text-base: 15px;
  --text-lg:   18px;
  --text-xl:   22px;
  --text-2xl:  28px;
  --text-3xl:  36px;
  --font-normal: 400;
  --font-medium: 500;
  --font-semibold: 600;
  --font-bold: 700;
}
```

5. **8px Spacing Grid**
```css
:root {
  --space-1: 4px;  --space-2: 8px;  --space-3: 12px;
  --space-4: 16px; --space-5: 20px; --space-6: 24px;
  --space-8: 32px; --space-10: 40px; --space-12: 48px;
}
/* KPI card padding: --space-6; card gap: --space-4 */
```

6. **Card Elevation Levels**
```css
.card-flat    { box-shadow: none; border: 1px solid #E5E7EB; }
.card-raised  { box-shadow: 0 1px 3px rgba(0,0,0,.10), 0 1px 2px rgba(0,0,0,.06); }
.card-lifted  { box-shadow: 0 4px 6px rgba(0,0,0,.07), 0 2px 4px rgba(0,0,0,.06); }
.card-overlay { box-shadow: 0 10px 15px rgba(0,0,0,.10), 0 4px 6px rgba(0,0,0,.05); }
```

## Standards
- Primary brand color is always #DB0717 — never approximate with a similar red
- Status colors must pass 4.5:1 contrast against their background chip color
- Use Segoe UI as primary font family to match SharePoint/Microsoft 365 environment
- Spacing must use the 8px grid; avoid arbitrary pixel values
- Dark mode surface: #111827 page, #1F2937 card — maintain same status color palette
- Status chips must include an icon or text label, never use color alone as the sole indicator
