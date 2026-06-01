# beacon

<!-- Source: migrated from ~/.claude/skills/beacon/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: beacon -->

**Summary.** WCAG 2.1 AA accessibility implementation for dashboards: ARIA labels, keyboard navigation, screen reader compatibility, color contrast ratios, focus management, and accessible chart alternatives. Ensures paratransit KPI dashboards meet accessibility standards for all users including those using assistive technology. Trigger on: "accessibility", "a11y", "WCAG", "screen reader", "aria", "keyboard navigation", "color contrast".

# WCAG 2.1 AA Accessibility for Dashboards

## Core Expertise
- ARIA landmark roles, labels, and live regions for dynamic KPI updates
- Keyboard navigation patterns: tab order, focus trapping in modals, skip links
- Screen reader-compatible chart alternatives (data tables, aria-describedby summaries)
- Color contrast compliance: 4.5:1 normal text, 3:1 large text and UI components
- Focus management after route changes, modal opens, and data refreshes
- Accessible status indicators that don't rely on color alone

## When to Use
- Building or auditing any dashboard component
- Adding chart, table, or card components that display KPI data
- Implementing modals, drawers, or expandable accordion sections
- User reports screen reader or keyboard navigation issues
- CI pipeline runs accessibility audit (axe-core, Lighthouse a11y)

## Key Patterns

1. **ARIA Live Region for KPI Updates**
```jsx
// Announce KPI changes to screen readers without focus move
<div aria-live="polite" aria-atomic="true" className="sr-only">
  {lastUpdatedMessage}
</div>
// Use aria-live="assertive" only for CRITICAL penalty alerts
```

2. **Accessible KPI Card**
```jsx
<article
  aria-labelledby={`kpi-title-${id}`}
  aria-describedby={`kpi-desc-${id}`}
  role="article"
>
  <h3 id={`kpi-title-${id}`}>{title}</h3>
  <p id={`kpi-desc-${id}`} className="sr-only">
    Current value {value}. Status: {status}. {penaltyMessage}
  </p>
  <span aria-hidden="true">{displayValue}</span> {/* visual only */}
</article>
```

3. **Chart Accessibility with Data Table Fallback**
```jsx
<figure role="figure" aria-labelledby="chart-caption">
  <figcaption id="chart-caption">Late Trips trend — last 6 months</figcaption>
  <ApexChart ... aria-hidden="true" /> {/* decorative; data in table */}
  <details>
    <summary>View data table</summary>
    <table>
      <caption>Late Trips percentage by month</caption>
      <thead><tr><th scope="col">Month</th><th scope="col">Late Trips %</th></tr></thead>
      <tbody>{data.map(row => <tr key={row.month}><td>{row.month}</td><td>{row.value}%</td></tr>)}</tbody>
    </table>
  </details>
</figure>
```

4. **Focus Trap for Modal Dialogs**
```javascript
function trapFocus(modalEl) {
  const focusable = modalEl.querySelectorAll(
    'a, button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  const first = focusable[0], last = focusable[focusable.length - 1];
  modalEl.addEventListener('keydown', e => {
    if (e.key !== 'Tab') return;
    if (e.shiftKey ? document.activeElement === first : document.activeElement === last) {
      e.preventDefault();
      (e.shiftKey ? last : first).focus();
    }
  });
  first.focus();
}
```

5. **Status Indicator Without Color-Only Encoding**
```jsx
const STATUS_ICONS = { CRITICAL: '!', WARNING: '▲', ON_TARGET: '✓', INCENTIVE: '★' };
<span className={`status-chip status-chip--${status.toLowerCase()}`}>
  <span aria-hidden="true">{STATUS_ICONS[status]}</span>
  <span className="sr-only">{status.replace('_', ' ')}</span>
  {label}
</span>
```

6. **Skip Navigation Link**
```jsx
<a href="#main-content" className="skip-link">Skip to main content</a>
// CSS: .skip-link { position: absolute; top: -40px; } .skip-link:focus { top: 0; }
```

## Standards
- Minimum contrast ratio 4.5:1 for all text; use contrast checker before finalizing colors
- Never convey information through color alone — always add icon, pattern, or text label
- All interactive elements must be reachable and operable via keyboard
- Modal dialogs must trap focus and restore focus to trigger element on close
- Dynamic data updates must use aria-live regions, not just visual changes
- Every image and icon must have either alt text or aria-hidden="true" if decorative
- Run axe-core or @axe-core/react in development to catch violations early
