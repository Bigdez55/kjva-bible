# pulse

<!-- Source: migrated from ~/.claude/skills/pulse/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: pulse -->

**Summary.** Real-time dashboard updates: WebSocket integration, Server-Sent Events (SSE), intelligent polling strategies, optimistic UI updates, stale data handling with visual indicators, and SignalR integration for SharePoint environments. Trigger on: "real-time", "live updates", "WebSocket", "polling", "auto-refresh", "SignalR", "SSE", "stale data".

# Real-Time Dashboard Updates

## Core Expertise
- WebSocket client with auto-reconnect and exponential backoff
- Server-Sent Events (SSE) for server-push without bidirectional overhead
- Polling strategies: adaptive interval based on data change frequency
- Optimistic UI: apply updates instantly, roll back on server error
- Stale data indicators: visual timestamps and freshness warnings
- SignalR for SharePoint/Azure environments

## When to Use
- Dashboard needs live KPI updates without manual refresh
- User requests "auto-refresh" or "live" data display
- Building a real-time alert system for threshold breaches
- SharePoint environment needs SignalR for push notifications
- Polling an API for new TD Report data on a schedule

## Key Patterns

1. **WebSocket with Auto-Reconnect**
```javascript
class KpiWebSocket {
  constructor(url) { this.url = url; this.retryDelay = 1000; this.connect(); }
  connect() {
    this.ws = new WebSocket(this.url);
    this.ws.onmessage = ({ data }) => this.onUpdate(JSON.parse(data));
    this.ws.onclose   = () => {
      console.warn('WS closed, reconnecting in', this.retryDelay, 'ms');
      setTimeout(() => this.connect(), this.retryDelay);
      this.retryDelay = Math.min(this.retryDelay * 2, 30000); // cap at 30s
    };
    this.ws.onopen = () => { this.retryDelay = 1000; }; // reset on success
  }
  onUpdate(kpiData) { /* dispatch to state manager */ }
}
```

2. **Server-Sent Events (SSE) Hook**
```jsx
function useKpiStream(url) {
  const [data, setData] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  useEffect(() => {
    const es = new EventSource(url);
    es.onmessage = ({ data }) => {
      setData(JSON.parse(data));
      setLastUpdated(new Date());
    };
    es.onerror = () => es.close(); // will retry automatically
    return () => es.close();
  }, [url]);
  return { data, lastUpdated };
}
```

3. **Adaptive Polling Hook**
```jsx
function useAdaptivePolling(fetchFn, { baseInterval = 60000, fastInterval = 10000 } = {}) {
  const [data, setData] = useState(null);
  const intervalRef = useRef(baseInterval);
  useEffect(() => {
    let timer;
    async function poll() {
      const prev = data;
      const next = await fetchFn();
      const changed = JSON.stringify(prev) !== JSON.stringify(next);
      setData(next);
      // Poll faster when data is changing
      intervalRef.current = changed ? fastInterval : baseInterval;
      timer = setTimeout(poll, intervalRef.current);
    }
    poll();
    return () => clearTimeout(timer);
  }, [fetchFn]);
  return data;
}
```

4. **Stale Data Indicator**
```jsx
function FreshnessIndicator({ lastUpdated, maxAgeMinutes = 60 }) {
  const [age, setAge] = useState(0);
  useEffect(() => {
    const interval = setInterval(() => {
      setAge(Math.floor((Date.now() - new Date(lastUpdated)) / 60000));
    }, 30000);
    return () => clearInterval(interval);
  }, [lastUpdated]);
  const isStale = age > maxAgeMinutes;
  return (
    <span className={isStale ? 'stale-indicator' : 'fresh-indicator'} aria-live="polite">
      {isStale ? `Data is ${age}m old — may be outdated` : `Updated ${age}m ago`}
    </span>
  );
}
```

5. **Optimistic Update Pattern**
```javascript
async function updateKpiOptimistic(kpiKey, newValue, dispatch) {
  const snapshot = store.getState().kpis; // save rollback snapshot
  dispatch({ type: 'KPI_UPDATE_OPTIMISTIC', key: kpiKey, value: newValue });
  try {
    await api.updateKpi(kpiKey, newValue);
  } catch (err) {
    dispatch({ type: 'KPI_ROLLBACK', snapshot }); // restore on failure
    showErrorAlert(`Failed to update ${kpiKey}: ${err.message}`);
  }
}
```

6. **SignalR for SharePoint (Azure Functions)**
```javascript
import * as signalR from '@microsoft/signalr';
const connection = new signalR.HubConnectionBuilder()
  .withUrl('/api/kpi-hub', { accessTokenFactory: () => getSharePointToken() })
  .withAutomaticReconnect([0, 2000, 10000, 30000])
  .build();
connection.on('KpiUpdated', kpiData => dispatch(kpiUpdateReceived(kpiData)));
await connection.start();
```

## Standards
- Always implement auto-reconnect for WebSocket and SignalR connections
- Show visual freshness indicator when data age exceeds the expected update interval
- Use SSE (not WebSocket) when communication is server-to-client only; simpler and more reliable
- Adaptive polling: reduce interval to 10s when changes detected, back to 60s when stable
- Always clean up EventSource, WebSocket, and SignalR connections in component unmount
- Optimistic updates must always have a rollback path on API failure
