# alert-system

<!-- Source: migrated from ~/.claude/skills/alert-system/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: alert-system -->

**Summary.** Threshold-based alert system: penalty warnings, KPI degradation alerts, anomaly detection (Z-score), multi-channel delivery (email, Slack, Teams, SMS, webhook), alert lifecycle management, deduplication, escalation policies, snooze/mute, and dashboard alert feed widget. Trigger on: 'alerts', 'notifications', 'threshold breach', 'warning system', 'penalty alert', 'escalation'.

# Threshold-Based Alert System

## Purpose & Scope

Manages threshold-based alerts with multi-channel delivery for KPI dashboards. Handles alert rules, lifecycle management, deduplication, escalation, and notification templates.

## When to Trigger

- User needs alerts for KPI threshold breaches
- User wants penalty warning notifications
- User asks for Slack/Teams/email alert integration
- User needs escalation policies or alert lifecycle management

## When NOT to Trigger

- Real-time WebSocket connections → **PULSE** agent
- AI-powered anomaly detection → **ORACLE** agent
- Dashboard UI components → framework APEX agent

## Alert Rule Engine

```javascript
const ALERT_RULES = [
  {
    id: 'late-trips-penalty', kpi: 'lateTripsPercent',
    condition: 'above', threshold: 5.0, severity: 'critical',
    message: 'Late Trips at {value}% — $10,000 penalty triggered (threshold: 5%)',
    channels: ['slack', 'email', 'sms'],
    cooldownMinutes: 60,
  },
  {
    id: 'excessive-late-penalty', kpi: 'excessivelyLatePercent',
    condition: 'above', threshold: 0.25, severity: 'critical',
    message: 'Excessively Late at {value}% — $5,000 penalty triggered (threshold: 0.25%)',
    channels: ['slack', 'email'],
    cooldownMinutes: 60,
  },
  {
    id: 'otp-incentive-near', kpi: 'otp',
    condition: 'above', threshold: 92.0, severity: 'info',
    message: 'OTP at {value}% — approaching incentive threshold (93%)',
    channels: ['slack'],
    cooldownMinutes: 1440, // Once per day
  },
  {
    id: 'pph-penalty-zone', kpi: 'pph',
    condition: 'below', threshold: 1.3, severity: 'critical',
    message: 'PPH at {value} — entering penalty zone (0.20+ below 1.5 standard)',
    channels: ['slack', 'email', 'sms'],
    cooldownMinutes: 60,
  },
  {
    id: 'data-stale', kpi: '_dataAge',
    condition: 'above', threshold: 24, severity: 'warning',
    message: 'KPI data is {value} hours old — may be stale',
    channels: ['slack'],
    cooldownMinutes: 240,
  },
];

function evaluateRules(kpiData, rules) {
  return rules.filter(rule => {
    const value = kpiData[rule.kpi];
    if (value == null) return false;
    return rule.condition === 'above' ? value > rule.threshold : value < rule.threshold;
  }).map(rule => ({
    ...rule,
    value: kpiData[rule.kpi],
    triggeredAt: new Date().toISOString(),
    status: 'triggered',
  }));
}
```

## Severity Levels

| Severity | Color | Action Required |
|----------|-------|----------------|
| `critical` | Red | Immediate — penalty is active |
| `warning` | Amber | Investigate — approaching threshold |
| `info` | Blue | Awareness — opportunity or trend |

## Multi-Channel Delivery

### Slack (Block Kit)

```javascript
function buildSlackMessage(alert) {
  return {
    blocks: [
      { type: 'header', text: { type: 'plain_text',
        text: `${alert.severity === 'critical' ? '🚨' : '⚠️'} KPI Alert: ${alert.kpi}` }},
      { type: 'section', text: { type: 'mrkdwn',
        text: alert.message.replace('{value}', alert.value) }},
      { type: 'section', fields: [
        { type: 'mrkdwn', text: `*Severity:* ${alert.severity}` },
        { type: 'mrkdwn', text: `*Triggered:* ${new Date(alert.triggeredAt).toLocaleString()}` },
      ]},
      { type: 'actions', elements: [
        { type: 'button', text: { type: 'plain_text', text: 'Acknowledge' },
          action_id: `ack_${alert.id}`, style: 'primary' },
        { type: 'button', text: { type: 'plain_text', text: 'View Dashboard' },
          url: 'https://dashboard.example.com' },
      ]},
    ],
  };
}
```

### Microsoft Teams (Adaptive Card)

```javascript
function buildTeamsCard(alert) {
  return {
    type: 'message',
    attachments: [{
      contentType: 'application/vnd.microsoft.card.adaptive',
      content: {
        type: 'AdaptiveCard', version: '1.4',
        body: [
          { type: 'TextBlock', text: `KPI Alert: ${alert.kpi}`,
            size: 'Large', weight: 'Bolder',
            color: alert.severity === 'critical' ? 'Attention' : 'Warning' },
          { type: 'TextBlock', text: alert.message.replace('{value}', alert.value), wrap: true },
          { type: 'FactSet', facts: [
            { title: 'Severity', value: alert.severity },
            { title: 'Time', value: new Date(alert.triggeredAt).toLocaleString() },
          ]},
        ],
        actions: [
          { type: 'Action.OpenUrl', title: 'View Dashboard', url: 'https://dashboard.example.com' },
        ],
      },
    }],
  };
}
```

### Email (HTML)

```javascript
function buildEmailHTML(alert) {
  const severityColor = { critical: '#EF4444', warning: '#F59E0B', info: '#3B82F6' };
  return `
    <div style="font-family: 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto;">
      <div style="background: ${severityColor[alert.severity]}; color: white; padding: 16px; border-radius: 8px 8px 0 0;">
        <h2 style="margin: 0;">KPI Alert: ${alert.kpi}</h2>
      </div>
      <div style="border: 1px solid #E5E7EB; padding: 24px; border-radius: 0 0 8px 8px;">
        <p style="font-size: 16px;">${alert.message.replace('{value}', alert.value)}</p>
        <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
          <tr><td style="padding: 8px; border-bottom: 1px solid #E5E7EB;"><strong>Severity</strong></td>
              <td style="padding: 8px; border-bottom: 1px solid #E5E7EB;">${alert.severity}</td></tr>
          <tr><td style="padding: 8px;"><strong>Triggered</strong></td>
              <td style="padding: 8px;">${new Date(alert.triggeredAt).toLocaleString()}</td></tr>
        </table>
        <a href="https://dashboard.example.com" style="display: inline-block; background: #3B82F6; color: white;
          padding: 12px 24px; border-radius: 6px; text-decoration: none;">View Dashboard</a>
      </div>
    </div>`;
}
```

## Alert Lifecycle

```
triggered → acknowledged → investigating → resolved → post-mortem
```

```javascript
const VALID_TRANSITIONS = {
  triggered: ['acknowledged'],
  acknowledged: ['investigating', 'resolved'],
  investigating: ['resolved'],
  resolved: ['post-mortem'],
};

function transitionAlert(alert, newStatus) {
  if (!VALID_TRANSITIONS[alert.status]?.includes(newStatus)) {
    throw new Error(`Invalid transition: ${alert.status} → ${newStatus}`);
  }
  return { ...alert, status: newStatus, [`${newStatus}At`]: new Date().toISOString() };
}
```

## Deduplication & Cooldown

```javascript
const cooldownRegistry = new Map();

function shouldSendAlert(alert) {
  const key = alert.id;
  const lastSent = cooldownRegistry.get(key);
  if (lastSent && Date.now() - lastSent < alert.cooldownMinutes * 60000) return false;
  cooldownRegistry.set(key, Date.now());
  return true;
}
```

## Escalation Policies

```javascript
const ESCALATION_TIERS = [
  { tier: 1, role: 'Operations Analyst', waitMinutes: 0 },
  { tier: 2, role: 'Operations Manager', waitMinutes: 30 },
  { tier: 3, role: 'Director of Operations', waitMinutes: 120 },
];

function getEscalationTier(alert) {
  const ageMinutes = (Date.now() - new Date(alert.triggeredAt)) / 60000;
  const tier = ESCALATION_TIERS.filter(t => ageMinutes >= t.waitMinutes).pop();
  return tier || ESCALATION_TIERS[0];
}
```

## Dashboard Alert Feed Widget

```tsx
function AlertFeed({ alerts }) {
  return (
    <div role="log" aria-label="KPI Alerts" aria-live="polite">
      {alerts.map(alert => (
        <div key={alert.id} className={`alert-item alert-${alert.severity}`}>
          <span className="alert-time">{new Date(alert.triggeredAt).toLocaleTimeString()}</span>
          <span className="alert-message">{alert.message.replace('{value}', alert.value)}</span>
          <button onClick={() => acknowledgeAlert(alert.id)}>Acknowledge</button>
        </div>
      ))}
    </div>
  );
}
```

## Integration

| Agent | Relationship |
|-------|-------------|
| **PULSE** | Real-time alert delivery via WebSocket/SSE |
| **ORACLE** | AI-powered anomaly detection enhances rule-based alerts |
| **KPI Analyst** | Penalty calculations trigger alert rules |
| **Dashboard Deployer** | Deployment status alerts |

## Anti-Patterns

1. **No cooldown** — same alert fires every minute, flooding channels
2. **Missing severity levels** — everything marked critical loses meaning
3. **No acknowledgement flow** — alerts fire and are forgotten
4. **Hardcoded thresholds** — use configurable rules from contract terms
5. **Single channel only** — critical alerts need multi-channel redundancy
