# oracle

<!-- Source: migrated from ~/.claude/skills/oracle/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: oracle -->

**Summary.** Integrating AI and ML capabilities into dashboards: Claude API streaming responses, embeddings for semantic search, confidence scoring, recommendation UI patterns, and client-side inference. Covers prompt engineering for KPI analysis, streaming text into dashboard panels, and displaying AI-generated insights with appropriate uncertainty indicators. Trigger on: "Claude API", "AI integration", "ML model", "streaming", "embeddings in dashboard", "LLM response".

# AI/ML Dashboard Integration

## Core Expertise
- Claude API integration: streaming completions into dashboard panels
- Prompt templates for KPI analysis and contract compliance assessment
- Confidence scoring display: showing AI certainty alongside recommendations
- Embeddings for semantic similarity of KPI descriptions and historical notes
- Recommendation UI: structured output rendering from LLM JSON responses
- Rate limiting, error handling, and fallback strategies for AI calls

## When to Use
- Dashboard needs a "generate analysis" or "explain this KPI" feature
- Implementing streaming AI responses in a side panel or modal
- Building semantic search over historical KPI notes or reports
- Displaying AI recommendations with confidence levels
- User asks to integrate Claude or another LLM into the dashboard

## Key Patterns

1. **Streaming Claude API Response into Dashboard Panel**
```javascript
async function streamKPIAnalysis(kpis, onChunk) {
  const response = await fetch('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kpis }),
  });
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    onChunk(decoder.decode(value, { stream: true }));
  }
}
```

2. **KPI Analysis Prompt Template**
```javascript
function buildKPIPrompt(kpis, contractTerms) {
  return `You are a paratransit contract compliance analyst.
Current KPIs: ${JSON.stringify(kpis, null, 2)}
Contract thresholds: ${JSON.stringify(contractTerms, null, 2)}

Analyze the data and respond with JSON:
{
  "healthScore": <0-100>,
  "topPriority": "<kpi name>",
  "recommendations": [{ "action": "", "impact": "$X/month", "timeline": "" }],
  "riskFlags": ["<description>"]
}`;
}
```

3. **Structured JSON Output Renderer**
```jsx
function AIRecommendationPanel({ analysis }) {
  if (!analysis) return <Skeleton />;
  return (
    <section aria-label="AI Analysis">
      <div className="health-score" aria-label={`Health score ${analysis.healthScore} out of 100`}>
        {analysis.healthScore}/100
      </div>
      <ul>
        {analysis.recommendations.map((rec, i) => (
          <li key={i}>
            <strong>{rec.action}</strong>
            <span className="impact-badge">{rec.impact}</span>
            <span className="timeline">{rec.timeline}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

4. **Confidence Score Indicator**
```jsx
function ConfidenceBadge({ score }) {
  // score: 0.0 - 1.0
  const label = score >= 0.8 ? 'High' : score >= 0.5 ? 'Medium' : 'Low';
  const color = score >= 0.8 ? '#16A34A' : score >= 0.5 ? '#D97706' : '#DC2626';
  return (
    <span style={{ color }} title={`AI confidence: ${Math.round(score * 100)}%`}>
      {label} confidence
    </span>
  );
}
```

5. **Fallback When AI Unavailable**
```javascript
async function getAnalysis(kpis) {
  try {
    return await fetchAIAnalysis(kpis);
  } catch (err) {
    console.warn('AI service unavailable, using rule-based fallback:', err);
    return generateRuleBasedInsights(kpis); // deterministic fallback
  }
}
```

6. **Rate Limit Aware Request Queue**
```javascript
const aiQueue = [];
let processing = false;
async function queueAIRequest(fn) {
  return new Promise((resolve, reject) => {
    aiQueue.push({ fn, resolve, reject });
    if (!processing) processQueue();
  });
}
async function processQueue() {
  processing = true;
  while (aiQueue.length) {
    const { fn, resolve, reject } = aiQueue.shift();
    try { resolve(await fn()); } catch (e) { reject(e); }
    await new Promise(r => setTimeout(r, 1000)); // 1 req/sec rate limit
  }
  processing = false;
}
```

## Standards
- Always provide a rule-based fallback when AI service is unavailable
- Display confidence level alongside every AI-generated recommendation
- Stream responses for any expected output > 200 tokens to avoid perceived latency
- Validate AI JSON output with schema check before rendering; handle malformed responses
- Never send PII or personally identifiable trip data to external AI APIs
- Cache AI responses keyed by data hash to avoid redundant API calls
