# sentinel

<!-- Source: migrated from ~/.claude/skills/sentinel/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: sentinel -->

**Summary.** Dashboard testing strategies: Jest unit tests for KPI calculators and contract compliance, React Testing Library for component interactions, Playwright E2E for full dashboard flows, MSW for API mocking, Storybook component stories, and coverage thresholds. Trigger on: "testing", "unit test", "E2E test", "Playwright", "Jest", "test coverage", "MSW", "Storybook".

# Dashboard Testing Strategies

## Core Expertise
- Jest unit tests: KPI penalty calculations, contract threshold logic, data transformations
- React Testing Library: KPI card rendering, status chip text, accessibility assertions
- Playwright E2E: full dashboard load, data refresh, export flows
- MSW (Mock Service Worker): intercept API calls with realistic fixture data
- Storybook: isolated component development and visual regression
- Coverage thresholds: 80% for calculators, 60% for components

## When to Use
- Writing tests for KPI penalty/incentive calculation logic
- Testing that KPI cards display correct status based on contract thresholds
- Setting up E2E tests for the full dashboard workflow
- Mocking the TD Report API or SharePoint list endpoints in tests
- Creating Storybook stories for KPI card variants

## Key Patterns

1. **Jest Unit Test: Contract Penalty Calculation**
```javascript
// kpi-calculator.test.js
describe('calculateLateTripsStatus', () => {
  test('no penalty below 5% threshold', () => {
    expect(calculateLateTripsStatus(4.9)).toEqual({ penalty: 0, status: 'ON_TARGET' });
  });
  test('$10,000 penalty above 5% threshold', () => {
    expect(calculateLateTripsStatus(8.2)).toEqual({ penalty: 10000, status: 'CRITICAL' });
  });
  test('$5,000 incentive at exactly 0%', () => {
    expect(calculateLateTripsStatus(0)).toEqual({ incentive: 5000, status: 'INCENTIVE' });
  });
});
```

2. **React Testing Library: KPI Card**
```jsx
import { render, screen } from '@testing-library/react';
import KpiCard from './KpiCard';

test('shows CRITICAL status and penalty for late trips breach', () => {
  render(<KpiCard label="Late Trips" value={8.2} target={5} penalty={10000} />);
  expect(screen.getByText(/Late Trips/i)).toBeInTheDocument();
  expect(screen.getByText(/\$10,000/)).toBeInTheDocument();
  expect(screen.getByRole('article')).toHaveClass('kpi-card--critical');
});

test('is accessible — has no axe violations', async () => {
  const { container } = render(<KpiCard label="OTP" value={90.3} target={90} />);
  const results = await axe(container);
  expect(results).toHaveNoViolations();
});
```

3. **MSW Handler for KPI API**
```javascript
// src/mocks/handlers.js
import { http, HttpResponse } from 'msw';
import kpiFixture from './fixtures/kpis.json';

export const handlers = [
  http.get('/api/kpis.json', () => HttpResponse.json(kpiFixture)),
  http.get('/api/performance.json', () => HttpResponse.json({ healthScore: 72, penalties: 16650 })),
  http.post('/api/manual-entry', async ({ request }) => {
    const body = await request.json();
    return HttpResponse.json({ success: true, updated: body });
  }),
];
```

4. **Playwright E2E: Dashboard Load and Export**
```javascript
// tests/dashboard.spec.ts
import { test, expect } from '@playwright/test';

test('dashboard loads KPI cards with correct penalty total', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('$16,650')).toBeVisible();
  await expect(page.getByText('Late Trips')).toBeVisible();
  await expect(page.getByRole('article', { name: /Late Trips/ })).toHaveClass(/critical/);
});

test('PDF export downloads a file', async ({ page }) => {
  await page.goto('/');
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: /Export PDF/i }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/Transdev_KPI.*\.pdf/);
});
```

5. **Storybook Story: KPI Card Variants**
```jsx
// KpiCard.stories.jsx
export default { title: 'Dashboard/KpiCard', component: KpiCard };

export const Critical  = { args: { label: 'Late Trips',  value: 8.2,  target: 5,   penalty: 10000 } };
export const Warning   = { args: { label: 'Complaints',  value: 1.4,  target: 1.0, penalty: 400   } };
export const OnTarget  = { args: { label: 'OTP',         value: 90.3, target: 90,  penalty: 0     } };
export const Incentive = { args: { label: 'Late Trips',  value: 0,    target: 5,   incentive: 5000 } };
```

6. **Jest Coverage Config**
```json
{
  "jest": {
    "coverageThreshold": {
      "global": { "branches": 80, "functions": 80, "lines": 80 },
      "src/kpi-calculator.js":     { "branches": 95, "functions": 95 },
      "src/ai-recommendations.js": { "branches": 85, "functions": 85 }
    }
  }
}
```

## Standards
- KPI calculator functions must have 95%+ branch coverage — contract compliance is critical
- All component tests must include at least one accessibility assertion (axe or ARIA role)
- Use MSW for all network mocking; never mock fetch/axios directly in test files
- E2E tests should run against a production build, not the dev server
- Test file naming: `*.test.js` for units, `*.spec.ts` for Playwright E2E
- Run Playwright tests in CI with `--reporter=html` to generate failure screenshots
