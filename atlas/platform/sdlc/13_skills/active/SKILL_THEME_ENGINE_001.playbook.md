# theme-engine

<!-- Source: migrated from ~/.claude/skills/theme-engine/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: theme-engine -->

**Summary.** Design system generator: CSS custom properties token system (colors, spacing, typography, shadows), Tailwind CSS configuration, dark/light mode toggle, colorblind-safe palettes, fluid typography with clamp(), brand customization, WCAG contrast validation, print overrides, and component-level token mapping. Trigger on: 'theming', 'dark mode', 'brand colors', 'CSS variables', 'design tokens', 'theme toggle', 'color palette', 'typography scale'.

# Design System Generator — Theme Engine

## Purpose & Scope

Generates complete design token systems for dashboards: CSS custom properties, Tailwind configs, dark/light mode, colorblind-safe palettes, and typography scales.

## When to Trigger

- User needs theming, dark mode, brand colors, CSS variables, design tokens
- User wants Fluent UI theme overrides for SPFx dashboards
- User asks for colorblind-safe palettes or WCAG contrast validation
- Setting up a design system for a new dashboard project

## When NOT to Trigger

- Chart-specific colors → **chart-builder** skill
- Component implementation → framework APEX agent
- Full design system architecture → **PRESTIGE** agent

## CSS Custom Properties Token System

```css
:root {
  /* === Primary Scale === */
  --color-primary-50: #EFF6FF;  --color-primary-100: #DBEAFE;
  --color-primary-200: #BFDBFE; --color-primary-300: #93C5FD;
  --color-primary-400: #60A5FA; --color-primary-500: #3B82F6;
  --color-primary-600: #2563EB; --color-primary-700: #1D4ED8;
  --color-primary-800: #1E40AF; --color-primary-900: #1E3A8A;

  /* === Neutral Scale === */
  --color-neutral-50: #F9FAFB;  --color-neutral-100: #F3F4F6;
  --color-neutral-200: #E5E7EB; --color-neutral-300: #D1D5DB;
  --color-neutral-400: #9CA3AF; --color-neutral-500: #6B7280;
  --color-neutral-600: #4B5563; --color-neutral-700: #374151;
  --color-neutral-800: #1F2937; --color-neutral-900: #111827;

  /* === Status Colors === */
  --color-success-500: #10B981; --color-warning-500: #F59E0B;
  --color-error-500: #EF4444;   --color-info-500: #3B82F6;

  /* === Semantic Tokens === */
  --color-text-primary: var(--color-neutral-900);
  --color-text-secondary: var(--color-neutral-600);
  --color-text-inverse: #FFFFFF;
  --color-surface: #FFFFFF;
  --color-surface-secondary: var(--color-neutral-50);
  --color-border: var(--color-neutral-200);
  --color-status-critical: var(--color-error-500);
  --color-status-warning: var(--color-warning-500);
  --color-status-on-target: var(--color-success-500);
  --color-status-incentive: var(--color-info-500);

  /* === Spacing (4px base) === */
  --space-1: 0.25rem; --space-2: 0.5rem; --space-3: 0.75rem;
  --space-4: 1rem; --space-6: 1.5rem; --space-8: 2rem;
  --space-10: 2.5rem; --space-12: 3rem; --space-16: 4rem;

  /* === Typography (fluid) === */
  --font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  --text-xs: clamp(0.6875rem, 0.65rem + 0.1vw, 0.75rem);
  --text-sm: clamp(0.8125rem, 0.78rem + 0.1vw, 0.875rem);
  --text-base: clamp(0.875rem, 0.85rem + 0.15vw, 1rem);
  --text-lg: clamp(1rem, 0.95rem + 0.2vw, 1.125rem);
  --text-xl: clamp(1.125rem, 1.05rem + 0.3vw, 1.25rem);
  --text-2xl: clamp(1.25rem, 1.15rem + 0.4vw, 1.5rem);
  --text-3xl: clamp(1.5rem, 1.35rem + 0.5vw, 1.875rem);
  --font-weight-normal: 400; --font-weight-medium: 500;
  --font-weight-semibold: 600; --font-weight-bold: 700;

  /* === Shadows === */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.1);
  --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1);
  --shadow-xl: 0 20px 25px -5px rgba(0,0,0,0.1);

  /* === Border Radius === */
  --radius-sm: 0.25rem; --radius-md: 0.5rem;
  --radius-lg: 0.75rem; --radius-xl: 1rem; --radius-full: 9999px;

  /* === Transitions === */
  --transition-fast: 150ms ease; --transition-base: 200ms ease;

  /* === Z-Index === */
  --z-dropdown: 10; --z-sticky: 20; --z-overlay: 30; --z-modal: 40; --z-toast: 50;
}
```

## Dark Mode

```css
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --color-text-primary: var(--color-neutral-100);
    --color-text-secondary: var(--color-neutral-400);
    --color-surface: var(--color-neutral-900);
    --color-surface-secondary: var(--color-neutral-800);
    --color-border: var(--color-neutral-700);
  }
}
[data-theme="dark"] {
  --color-text-primary: var(--color-neutral-100);
  --color-text-secondary: var(--color-neutral-400);
  --color-surface: var(--color-neutral-900);
  --color-surface-secondary: var(--color-neutral-800);
  --color-border: var(--color-neutral-700);
}
```

### Toggle Script

```javascript
function initThemeToggle() {
  const saved = localStorage.getItem('theme');
  if (saved) document.documentElement.setAttribute('data-theme', saved);
  return {
    toggle() {
      const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('theme', next);
    },
    get current() {
      return document.documentElement.getAttribute('data-theme')
        || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    },
  };
}
```

## Colorblind-Safe Palettes

| CVD Type | Prevalence | Affected Colors |
|----------|-----------|----------------|
| Protanopia | 1.3% males | Red-green |
| Deuteranopia | 1.2% males | Red-green |
| Tritanopia | 0.001% | Blue-yellow |

```css
[data-colorblind="deuteranopia"] {
  --color-status-critical: #D55E00;
  --color-status-on-target: #0072B2;
  --color-status-warning: #F0E442;
  --color-status-incentive: #009E73;
}
```

## Tailwind CSS Configuration

```javascript
export default {
  content: ['./src/**/*.{ts,tsx,vue,svelte}'],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        primary: { 50: 'var(--color-primary-50)', 500: 'var(--color-primary-500)', 700: 'var(--color-primary-700)' },
        surface: 'var(--color-surface)',
        border: 'var(--color-border)',
        status: {
          critical: 'var(--color-status-critical)', warning: 'var(--color-status-warning)',
          'on-target': 'var(--color-status-on-target)', incentive: 'var(--color-status-incentive)',
        },
      },
      fontFamily: { sans: ['var(--font-family)'], mono: ['var(--font-mono)'] },
    },
  },
};
```

## WCAG Contrast Validation

```javascript
function getContrastRatio(hex1, hex2) {
  const lum1 = getRelativeLuminance(hex1);
  const lum2 = getRelativeLuminance(hex2);
  const [lighter, darker] = lum1 > lum2 ? [lum1, lum2] : [lum2, lum1];
  return (lighter + 0.05) / (darker + 0.05);
}
function validateContrast(fg, bg, level = 'AA') {
  const ratio = getContrastRatio(fg, bg);
  return { ratio: ratio.toFixed(2), passes: ratio >= (level === 'AAA' ? 7 : 4.5) };
}
```

## Print Overrides

```css
@media print {
  :root {
    --color-text-primary: #000; --color-surface: #FFF; --color-border: #CCC;
    --shadow-sm: none; --shadow-md: none;
  }
  * { transition: none !important; animation: none !important; }
}
```

## Brand Customization

1. Replace `--color-primary-*` scale with brand primary
2. Update `--font-family` with brand typeface
3. Validate contrast ratios with `validateContrast()`
4. Update Tailwind config to consume new tokens
5. Test in light + dark + print modes

## Integration

| Agent | Relationship |
|-------|-------------|
| **PRESTIGE** | Full design system using theme-engine tokens |
| **BEACON** | Contrast validation and colorblind palettes |
| **chart-builder** | Chart palettes from theme-engine colors |
| **kpi-card-factory** | Status colors from semantic tokens |

## Anti-Patterns

1. **Hardcoded hex values** — always use CSS custom properties
2. **No dark mode** — every dashboard needs light + dark
3. **Ignoring contrast** — validate WCAG 4.5:1 for all text/bg pairs
4. **Mixing token tiers** — components use semantic, not primitive tokens
5. **No print styles** — dashboards get printed
6. **Forgetting reduced motion** — respect `prefers-reduced-motion`
