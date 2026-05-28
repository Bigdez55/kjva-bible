# ai-insights

<!-- Source: migrated from ~/.claude/skills/ai-insights/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: ai-insights -->

**Summary.** AI-powered KPI analysis and recommendation engine: performance health scoring (0-100), anomaly detection (Z-score, IQR, isolation forest), penalty elimination strategies, incentive achievement roadmaps, predictive trend extrapolation, what-if scenario modeling, Claude API narrative generation, financial impact quantification, ROI projections, natural language queries, and auto-generated executive summaries. Trigger on: 'AI insights', 'recommendations', 'health score', 'predict', 'anomaly', 'performance analysis', 'what-if', 'forecast', 'penalty strategy', 'executive summary', 'NLQ'.

# AI Insights & Recommendations Engine

## Purpose & Scope

Translates raw KPI data into actionable intelligence: performance health scores, anomaly detection, penalty elimination strategies, incentive roadmaps, predictive forecasting, what-if scenario modeling, and AI-generated executive narratives. Integrates Claude API for natural language insight generation and uses statistical methods for anomaly detection and trend analysis.

## When to Trigger

- User asks for AI analysis, health score calculation, or recommendations
- New KPI data needs penalty/incentive impact assessment
- Dashboard needs "predict next month" or "what-if" scenario modeling
- Anomaly detected (KPI jumps significantly from prior period)
- User wants prioritized action list to eliminate penalties
- Need executive summary or narrative for stakeholder reporting
- Natural language query against KPI data (e.g., "what drove the penalty increase?")

## When NOT to Trigger

- Chart configuration → **chart-builder** skill
- Data pipeline ETL → **data-pipeline** skill
- Alert threshold rules → **alert-system** skill
- Full AI architecture → **ORACLE** agent

## Performance Health Score

### Weighted Scoring Model

```javascript
const HEALTH_WEIGHTS = {
  pph: 0.30,             // Highest weight — drives $5K+ penalties/incentives
  lateTrips: 0.25,       // Critical — $10K penalty or $5K incentive
  excessivelyLate: 0.25, // Critical — $5K flat penalty
  otp: 0.20,             // Incentive opportunity — $2.5K per point above 93%
};

const SCORE_THRESHOLDS = {
  pph: [
    { min: 1.7, score: 100, label: 'Incentive Zone' },
    { min: 1.5, score: 80, label: 'On Target' },
    { min: 1.3, score: 60, label: 'Below Standard (No Penalty)' },
    { min: 0, score: 30, label: 'Penalty Zone' },
  ],
  lateTrips: [
    { max: 0, score: 100, label: 'Incentive Zone (0%)' },
    { max: 5, score: 75, label: 'On Target (<5%)' },
    { max: 8, score: 40, label: 'Penalty Zone (>5%)' },
    { max: Infinity, score: 10, label: 'Critical (>8%)' },
  ],
  excessivelyLate: [
    { max: 0.25, score: 100, label: 'On Target' },
    { max: 0.35, score: 50, label: 'Penalty Zone' },
    { max: Infinity, score: 20, label: 'Critical' },
  ],
  otp: [
    { min: 93, score: 100, label: 'Incentive Zone' },
    { min: 90, score: 70, label: 'On Target' },
    { min: 87, score: 40, label: 'Below Target' },
    { min: 0, score: 10, label: 'Critical' },
  ],
};

function calculateOverallHealth(kpis) {
  const scores = {};
  for (const [key, thresholds] of Object.entries(SCORE_THRESHOLDS)) {
    const value = kpis[key];
    for (const t of thresholds) {
      if ('min' in t && value >= t.min) { scores[key] = { score: t.score, label: t.label }; break; }
      if ('max' in t && value <= t.max) { scores[key] = { score: t.score, label: t.label }; break; }
    }
  }

  const weightedScore = Object.keys(HEALTH_WEIGHTS).reduce(
    (sum, k) => sum + (scores[k]?.score || 0) * HEALTH_WEIGHTS[k], 0
  );

  return {
    overall: Math.round(weightedScore),
    rating: weightedScore >= 81 ? 'Excellent' : weightedScore >= 61 ? 'Good'
      : weightedScore >= 41 ? 'Warning' : 'Critical',
    breakdown: scores,
  };
}
```

### Health Score Interpretation

| Score | Rating | Action |
|-------|--------|--------|
| 81-100 | Excellent | Maintain performance, pursue incentives |
| 61-80 | Good | Minor adjustments, incentive opportunities |
| 41-60 | Warning | Focused intervention needed, penalty risk |
| 0-40 | Critical | Immediate action required, active penalties |

## Anomaly Detection

### Z-Score Method (Standard)

```javascript
function detectAnomalyZScore(current, history, threshold = 2.0) {
  if (history.length < 3) return null; // Need minimum 3 data points

  const mean = history.reduce((s, v) => s + v, 0) / history.length;
  const stdDev = Math.sqrt(
    history.reduce((s, v) => s + (v - mean) ** 2, 0) / history.length
  );

  if (stdDev === 0) return null; // All values identical

  const zScore = (current - mean) / stdDev;
  const isAnomaly = Math.abs(zScore) > threshold;

  return isAnomaly ? {
    anomaly: true,
    zScore: parseFloat(zScore.toFixed(2)),
    direction: zScore > 0 ? 'above' : 'below',
    mean: parseFloat(mean.toFixed(2)),
    stdDev: parseFloat(stdDev.toFixed(2)),
    severity: Math.abs(zScore) > 3 ? 'critical' : 'warning',
    message: `Value ${current} is ${Math.abs(zScore).toFixed(1)} standard deviations ${zScore > 0 ? 'above' : 'below'} the mean (${mean.toFixed(2)})`,
  } : null;
}
```

### IQR Method (Robust to Outliers)

```javascript
function detectAnomalyIQR(current, history, multiplier = 1.5) {
  const sorted = [...history].sort((a, b) => a - b);
  const q1 = sorted[Math.floor(sorted.length * 0.25)];
  const q3 = sorted[Math.floor(sorted.length * 0.75)];
  const iqr = q3 - q1;

  const lowerBound = q1 - multiplier * iqr;
  const upperBound = q3 + multiplier * iqr;

  return (current < lowerBound || current > upperBound) ? {
    anomaly: true,
    bounds: { lower: lowerBound, upper: upperBound },
    direction: current > upperBound ? 'above' : 'below',
    severity: current > q3 + 3 * iqr || current < q1 - 3 * iqr ? 'critical' : 'warning',
  } : null;
}
```

### Multi-KPI Anomaly Scan

```javascript
function scanAllKPIs(currentKpis, kpiHistory) {
  const KPI_KEYS = ['pph', 'otp', 'lateTripsPercent', 'excessivelyLatePercent',
    'missedTripsPercent', 'holdTimePercent', 'complaintsPerThousand'];

  const anomalies = [];
  for (const key of KPI_KEYS) {
    const history = kpiHistory.map(h => h[key]).filter(v => v != null);
    const current = currentKpis[key];
    const result = detectAnomalyZScore(current, history);
    if (result) {
      anomalies.push({ kpi: key, current, ...result });
    }
  }
  return anomalies.sort((a, b) => Math.abs(b.zScore) - Math.abs(a.zScore));
}
```

## Penalty Elimination Strategies

### Priority Engine

```javascript
function generatePenaltyStrategies(kpis) {
  const strategies = [];

  // Late Trips — highest ROI (saves $10,000 or earns $5,000)
  if (kpis.lateTripsPercent > 5) {
    strategies.push({
      id: 'eliminate-late-trips',
      priority: 'CRITICAL',
      kpi: 'lateTrips',
      currentValue: kpis.lateTripsPercent,
      targetValue: 4.9,
      penaltySavings: 10000,
      incentiveGain: kpis.lateTripsPercent <= 5 ? 5000 : 0,
      timeline: '2-4 weeks',
      effort: 'high',
      roi: 10000 / 8, // savings / effort score
      actions: [
        'Analyze late trip root causes by route and time-of-day',
        'Add 5-minute buffer to routes with >10% late rate',
        'Pre-position vehicles at high-demand zones during peak hours',
        'Implement real-time GPS monitoring with dispatch alerts at 80% threshold',
        'Review driver scheduling for fatigue-related patterns',
      ],
      metrics: {
        currentPenalty: '$10,000/month',
        targetSavings: '$10,000/month',
        annualImpact: '$120,000/year',
      },
    });
  }

  // Excessively Late Trips — high value, targeted fix
  if (kpis.excessivelyLatePercent > 0.25) {
    strategies.push({
      id: 'eliminate-excessive-late',
      priority: 'CRITICAL',
      kpi: 'excessivelyLate',
      currentValue: kpis.excessivelyLatePercent,
      targetValue: 0.24,
      penaltySavings: 5000,
      timeline: '1-2 weeks',
      effort: 'medium',
      roi: 5000 / 5,
      actions: [
        'Flag trips exceeding 30-minute late threshold in dispatch system',
        'Assign backup vehicles for routes with historical excessive delays',
        'Implement mandatory dispatch escalation at 20-minute delay mark',
        'Review and optimize scheduling for longest routes',
      ],
      metrics: {
        currentPenalty: '$5,000/month',
        targetSavings: '$5,000/month',
        annualImpact: '$60,000/year',
      },
    });
  }

  // Hold Time — process improvement
  if (kpis.holdTimePercent < 95) {
    const pointsBelow = 95 - kpis.holdTimePercent;
    strategies.push({
      id: 'improve-hold-time',
      priority: 'HIGH',
      kpi: 'holdTime',
      currentValue: kpis.holdTimePercent,
      targetValue: 95,
      penaltySavings: pointsBelow * 400,
      timeline: '2-4 weeks',
      effort: 'medium',
      roi: (pointsBelow * 400) / 5,
      actions: [
        'Optimize IVR menu to reduce unnecessary transfers',
        'Add call-back option during peak hold periods',
        'Cross-train agents for multi-skill call handling',
        'Review staffing levels against call volume patterns',
      ],
    });
  }

  // OTP Incentive — requires PPH prerequisite
  if (kpis.otp < 93 && kpis.otp >= 90) {
    strategies.push({
      id: 'achieve-otp-incentive',
      priority: 'MEDIUM',
      kpi: 'otp',
      currentValue: kpis.otp,
      targetValue: 93.0,
      incentiveGain: Math.ceil(93 - kpis.otp) * 2500,
      prerequisite: 'Requires PPH >= 1.5 for incentive qualification',
      timeline: '1-3 months',
      effort: 'high',
      actions: [
        'Optimize route scheduling for on-time arrivals',
        'Reduce dwell time at stops through operational efficiency',
        'Implement predictive dispatch based on traffic patterns',
      ],
    });
  }

  // Sort by ROI descending
  return strategies.sort((a, b) => (b.roi || 0) - (a.roi || 0));
}
```

## Predictive Trend Analysis

### Linear Regression Forecasting

```javascript
function predictNextPeriod(history) {
  const n = history.length;
  if (n < 3) return null;

  const xMean = (n - 1) / 2;
  const yMean = history.reduce((s, v) => s + v, 0) / n;

  const numerator = history.reduce((s, v, i) => s + (i - xMean) * (v - yMean), 0);
  const denominator = history.reduce((s, _, i) => s + (i - xMean) ** 2, 0);
  const slope = numerator / denominator;
  const intercept = yMean - slope * xMean;

  const prediction = intercept + slope * n;

  // R-squared for confidence
  const ssRes = history.reduce((s, v, i) => s + (v - (intercept + slope * i)) ** 2, 0);
  const ssTot = history.reduce((s, v) => s + (v - yMean) ** 2, 0);
  const rSquared = ssTot > 0 ? 1 - ssRes / ssTot : 0;

  // Standard error for confidence interval
  const se = Math.sqrt(ssRes / (n - 2));
  const margin = 1.96 * se; // 95% confidence

  return {
    predicted: parseFloat(prediction.toFixed(2)),
    confidence: parseFloat(rSquared.toFixed(3)),
    confidenceInterval: {
      lower: parseFloat((prediction - margin).toFixed(2)),
      upper: parseFloat((prediction + margin).toFixed(2)),
    },
    trend: slope > 0.01 ? 'improving' : slope < -0.01 ? 'declining' : 'stable',
    slope: parseFloat(slope.toFixed(4)),
    reliability: rSquared > 0.7 ? 'high' : rSquared > 0.4 ? 'moderate' : 'low',
  };
}
```

### Multi-KPI Forecast

```javascript
function forecastAllKPIs(kpiHistory) {
  const KPI_KEYS = ['pph', 'otp', 'lateTripsPercent', 'excessivelyLatePercent'];
  const forecasts = {};

  for (const key of KPI_KEYS) {
    const values = kpiHistory.map(h => h[key]).filter(v => v != null);
    const forecast = predictNextPeriod(values);
    if (forecast) {
      forecasts[key] = {
        ...forecast,
        currentValue: values[values.length - 1],
        willBreachThreshold: checkThresholdBreach(key, forecast.predicted),
      };
    }
  }

  return forecasts;
}

function checkThresholdBreach(kpi, predictedValue) {
  const thresholds = {
    pph: { direction: 'below', value: 1.3, penalty: '$5,000' },
    lateTripsPercent: { direction: 'above', value: 5.0, penalty: '$10,000' },
    excessivelyLatePercent: { direction: 'above', value: 0.25, penalty: '$5,000' },
    otp: { direction: 'below', value: 90.0, penalty: '$5,000/point' },
  };

  const t = thresholds[kpi];
  if (!t) return null;

  const breached = t.direction === 'above' ? predictedValue > t.value : predictedValue < t.value;
  return breached ? { threshold: t.value, penalty: t.penalty, direction: t.direction } : null;
}
```

## What-If Scenario Modeling

```javascript
function whatIfScenario(currentKpis, changes) {
  const scenario = { ...currentKpis, ...changes };

  const currentPenalties = calculateTotalPenalties(currentKpis);
  const scenarioPenalties = calculateTotalPenalties(scenario);
  const currentIncentives = calculateTotalIncentives(currentKpis);
  const scenarioIncentives = calculateTotalIncentives(scenario);

  const currentHealth = calculateOverallHealth(currentKpis);
  const scenarioHealth = calculateOverallHealth(scenario);

  return {
    current: {
      penalties: currentPenalties,
      incentives: currentIncentives,
      netFinancial: currentIncentives - currentPenalties,
      healthScore: currentHealth.overall,
    },
    scenario: {
      penalties: scenarioPenalties,
      incentives: scenarioIncentives,
      netFinancial: scenarioIncentives - scenarioPenalties,
      healthScore: scenarioHealth.overall,
    },
    delta: {
      penaltySavings: currentPenalties - scenarioPenalties,
      incentiveGain: scenarioIncentives - currentIncentives,
      netImprovement: (scenarioIncentives - scenarioPenalties) - (currentIncentives - currentPenalties),
      healthImprovement: scenarioHealth.overall - currentHealth.overall,
    },
    summary: generateWhatIfSummary(currentKpis, scenario, changes),
  };
}

function generateWhatIfSummary(current, scenario, changes) {
  const parts = [];
  for (const [key, value] of Object.entries(changes)) {
    const direction = value > current[key] ? 'increase' : 'decrease';
    parts.push(`${key}: ${current[key]} → ${value} (${direction})`);
  }
  return parts.join('; ');
}
```

## Claude API Narrative Generation

```javascript
async function generateExecutiveSummary(kpis, penalties, strategies, history) {
  const prompt = `You are a paratransit operations analyst. Generate a concise executive summary.

Current KPI Data:
- PPH: ${kpis.pph} (standard: 1.5, incentive: 1.7+)
- OTP: ${kpis.otp}% (target: 90%, incentive: 93%+)
- Late Trips: ${kpis.lateTripsPercent}% (threshold: 5%)
- Excessively Late: ${kpis.excessivelyLatePercent}% (threshold: 0.25%)
- Total Monthly Penalties: $${penalties.total.toLocaleString()}

Top Strategies:
${strategies.slice(0, 3).map(s => `- ${s.kpi}: ${s.actions[0]} (saves $${s.penaltySavings}/mo)`).join('\n')}

3-Month Trend: ${JSON.stringify(history.slice(-3).map(h => ({ month: h.reportMonth, pph: h.pph, otp: h.otp, late: h.lateTripsPercent })))}

Write a 3-paragraph executive summary covering:
1. Current performance status and financial impact
2. Key risk areas and recommended actions
3. Improvement trajectory and projected outcomes`;

  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': process.env.ANTHROPIC_API_KEY,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: 'claude-sonnet-4-6-20250514',
      max_tokens: 500,
      messages: [{ role: 'user', content: prompt }],
    }),
  });

  const data = await response.json();
  return data.content[0].text;
}
```

## Recommendation Output Structure

```typescript
interface Recommendation {
  id: string;
  priority: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  kpi: string;
  currentValue: number;
  targetValue: number;
  penaltySavings: number;
  incentiveGain: number;
  timeline: string;
  effort: 'low' | 'medium' | 'high';
  roi: number;
  actions: string[];
  metrics: {
    currentPenalty: string;
    targetSavings: string;
    annualImpact: string;
  };
  prerequisite?: string;
}

interface HealthScore {
  overall: number;
  rating: 'Excellent' | 'Good' | 'Warning' | 'Critical';
  breakdown: Record<string, { score: number; label: string }>;
}

interface Forecast {
  predicted: number;
  confidence: number;
  confidenceInterval: { lower: number; upper: number };
  trend: 'improving' | 'declining' | 'stable';
  reliability: 'high' | 'moderate' | 'low';
  willBreachThreshold: { threshold: number; penalty: string } | null;
}
```

## React Integration

```tsx
function AIInsightsPanel({ kpis, history }) {
  const [insights, setInsights] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function analyze() {
      setLoading(true);
      const health = calculateOverallHealth(kpis);
      const anomalies = scanAllKPIs(kpis, history);
      const strategies = generatePenaltyStrategies(kpis);
      const forecasts = forecastAllKPIs(history);

      let narrative = null;
      try {
        narrative = await generateExecutiveSummary(kpis, { total: 16650 }, strategies, history);
      } catch (err) {
        console.warn('AI narrative generation failed, using fallback', err);
      }

      setInsights({ health, anomalies, strategies, forecasts, narrative });
      setLoading(false);
    }
    analyze();
  }, [kpis, history]);

  if (loading) return <InsightsSkeleton />;

  return (
    <section aria-label="AI Performance Insights">
      <HealthScoreGauge score={insights.health.overall} rating={insights.health.rating} />
      {insights.anomalies.length > 0 && <AnomalyAlert anomalies={insights.anomalies} />}
      <StrategyList strategies={insights.strategies} />
      <ForecastChart forecasts={insights.forecasts} />
      {insights.narrative && <NarrativeSummary text={insights.narrative} />}
    </section>
  );
}
```

## Integration

| Agent | Relationship |
|-------|-------------|
| **ORACLE** (AI) | Full AI architecture with advanced models |
| **alert-system** | Anomalies feed into threshold alert rules |
| **data-pipeline** | Clean Gold-tier data feeds AI analysis |
| **chart-builder** | Forecast visualization configs |
| **export-suite** | Executive summary in PDF reports |

## Standards

- Always express financial impact in monthly dollar amounts
- Health score thresholds: 0-40 Critical, 41-60 Warning, 61-80 Good, 81-100 Excellent
- PPH incentive requires BOTH PPH >= 1.7 AND OTP >= 93% — never recommend one without the other
- Sort recommendations by ROI (penaltySavings / effortScore) descending
- Anomaly threshold: flag when current value deviates >2 standard deviations from 3-month rolling average
- Never fabricate historical data; return null when history is insufficient (<3 data points)
- Predictions must include confidence intervals and reliability ratings
- What-if scenarios must show both current and projected states for comparison
- AI-generated narratives are supplementary — always show raw data alongside

## Anti-Patterns

1. **Presenting predictions without confidence intervals** — always show reliability
2. **Recommending OTP incentive without PPH prerequisite** — contract requires both
3. **Using mean for anomaly detection on skewed data** — use IQR for robustness
4. **Fabricating trends from <3 data points** — return null, not a guess
5. **Hiding the math** — show health score breakdown, not just the number
6. **Single-strategy focus** — always prioritize by ROI across all KPIs
7. **Static thresholds** — anomaly detection should adapt to rolling baselines
