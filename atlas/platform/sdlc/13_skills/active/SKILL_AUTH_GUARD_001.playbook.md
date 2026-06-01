# auth-guard

<!-- Source: migrated from ~/.claude/skills/auth-guard/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: auth-guard -->

**Summary.** Authentication and authorization patterns for dashboards: JWT (access + refresh tokens), OAuth 2.0 PKCE, SAML SSO, SPFx context-based auth, PnPjs auth setup, RBAC role hierarchies, permission matrices, protected routes (React/Vue/Angular), API middleware, row-level security, session management, MSAL integration, and Microsoft Graph group membership. Trigger on: 'authentication', 'permissions', 'auth', 'RBAC', 'role-based', 'login', 'SSO', 'OAuth', 'JWT', 'SharePoint auth', 'PnPjs auth', 'Graph permissions'.

# Authentication & Authorization Patterns

## Purpose & Scope

Adds authentication and authorization to dashboards. Covers JWT tokens, OAuth 2.0 PKCE, SAML SSO, SPFx context-based auth, RBAC role hierarchies, protected routes, API middleware, row-level security, and session management.

## When to Trigger

- User needs authentication, login flows, or SSO integration
- User asks for role-based access control (RBAC) or permissions
- User needs SPFx authentication with PnPjs
- User needs protected routes or API middleware
- User asks about JWT, OAuth, SAML, or session management

## When NOT to Trigger

- Dashboard UI components → framework APEX agent
- Deployment → **Dashboard Deployer Agent**
- Data processing → **data-pipeline** skill
- Full enterprise architecture → **VAULT** agent

## Role Hierarchy & Permission Matrix

```javascript
const ROLES = {
  admin: {
    label: 'Administrator',
    permissions: ['view_dashboard', 'view_penalties', 'view_incentives', 'view_ai_insights',
      'export_reports', 'edit_manual_data', 'manage_users', 'view_audit_log'],
  },
  manager: {
    label: 'Operations Manager',
    permissions: ['view_dashboard', 'view_penalties', 'view_incentives', 'view_ai_insights',
      'export_reports', 'edit_manual_data'],
  },
  analyst: {
    label: 'Data Analyst',
    permissions: ['view_dashboard', 'view_penalties', 'view_incentives', 'export_reports'],
  },
  viewer: {
    label: 'Dashboard Viewer',
    permissions: ['view_dashboard'],
  },
};

function hasPermission(userRole, permission) {
  return ROLES[userRole]?.permissions.includes(permission) ?? false;
}

function canAccess(userRole, requiredPermission) {
  if (!hasPermission(userRole, requiredPermission)) {
    throw new Error(`Access denied: ${userRole} lacks ${requiredPermission}`);
  }
  return true;
}
```

## SPFx Authentication (SharePoint Framework)

### PnPjs Initialization

```typescript
import { spfi, SPFI } from '@pnp/sp';
import { graphfi, GraphFI } from '@pnp/graph';
import { SPFx } from '@pnp/sp/presets/all';
import { SPFx as GraphSPFx } from '@pnp/graph/presets/all';

let _sp: SPFI, _graph: GraphFI;

export function getSP(context?: WebPartContext): SPFI {
  if (context) _sp = spfi().using(SPFx(context));
  if (!_sp) throw new Error('PnPjs SP not initialized — call getSP(context) in onInit()');
  return _sp;
}

export function getGraph(context?: WebPartContext): GraphFI {
  if (context) _graph = graphfi().using(GraphSPFx(context));
  if (!_graph) throw new Error('PnPjs Graph not initialized');
  return _graph;
}
```

### SharePoint Group Role Check

```typescript
async function getUserRole(sp: SPFI): Promise<'owner' | 'member' | 'visitor'> {
  const groups = await sp.web.currentUser.groups();
  const groupTitles = groups.map(g => g.Title.toLowerCase());
  if (groupTitles.some(t => t.includes('owner')))  return 'owner';
  if (groupTitles.some(t => t.includes('member'))) return 'member';
  return 'visitor';
}
```

### Microsoft Graph Group Membership

```typescript
async function isMemberOfGroup(graph: GraphFI, groupId: string): Promise<boolean> {
  try {
    const membership = await graph.me.checkMemberObjects({ ids: [groupId] });
    return membership.includes(groupId);
  } catch {
    return false; // Fail closed — deny access on error
  }
}
```

### SPFx Token Acquisition for Custom API

```typescript
async function getApiToken(context: WebPartContext, resourceId: string): Promise<string> {
  const tokenProvider = await context.aadTokenProviderFactory.getTokenProvider();
  return tokenProvider.getToken(resourceId);
}
```

### Required App Registration Permissions

```
Microsoft Graph:
  User.Read              (Delegated) — basic user profile
  Sites.Read.All         (Delegated) — SharePoint List read
  Sites.ReadWrite.All    (Delegated) — SharePoint List write
  GroupMember.Read.All   (Delegated) — group membership checks

SharePoint:
  AllSites.Read          (Delegated) — read all sites
  AllSites.Write         (Delegated) — write to lists
```

## JWT Authentication (Non-SPFx)

```javascript
// Token generation (server-side)
import jwt from 'jsonwebtoken';

function generateTokens(user) {
  const accessToken = jwt.sign(
    { userId: user.id, role: user.role, permissions: ROLES[user.role].permissions },
    process.env.JWT_SECRET,
    { expiresIn: '15m' }
  );
  const refreshToken = jwt.sign(
    { userId: user.id },
    process.env.JWT_REFRESH_SECRET,
    { expiresIn: '7d' }
  );
  return { accessToken, refreshToken };
}

// Token validation middleware (Express)
function authMiddleware(req, res, next) {
  const authHeader = req.headers.authorization;
  if (!authHeader?.startsWith('Bearer ')) return res.status(401).json({ error: 'Missing token' });

  try {
    const token = authHeader.split(' ')[1];
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    req.user = decoded;
    next();
  } catch (err) {
    if (err.name === 'TokenExpiredError') return res.status(401).json({ error: 'Token expired' });
    return res.status(403).json({ error: 'Invalid token' });
  }
}

// Role-checking middleware
function requireRole(...roles) {
  return (req, res, next) => {
    if (!roles.includes(req.user.role)) {
      return res.status(403).json({ error: 'Insufficient permissions' });
    }
    next();
  };
}

// Usage
app.get('/api/penalties', authMiddleware, requireRole('admin', 'manager', 'analyst'), getPenalties);
app.post('/api/manual-data', authMiddleware, requireRole('admin', 'manager'), updateManualData);
```

## OAuth 2.0 PKCE Flow (SPA)

```javascript
// MSAL configuration for Microsoft 365
import { PublicClientApplication } from '@azure/msal-browser';

const msalConfig = {
  auth: {
    clientId: process.env.CLIENT_ID,
    authority: `https://login.microsoftonline.com/${process.env.TENANT_ID}`,
    redirectUri: window.location.origin,
  },
  cache: { cacheLocation: 'sessionStorage', storeAuthStateInCookie: false },
};

const msalInstance = new PublicClientApplication(msalConfig);

async function login() {
  try {
    const response = await msalInstance.loginPopup({
      scopes: ['User.Read', 'Sites.Read.All'],
    });
    return response.account;
  } catch (error) {
    console.error('Login failed:', error);
    throw error;
  }
}

async function getToken(scopes) {
  const accounts = msalInstance.getAllAccounts();
  if (accounts.length === 0) throw new Error('No accounts found — login required');
  try {
    const response = await msalInstance.acquireTokenSilent({ scopes, account: accounts[0] });
    return response.accessToken;
  } catch {
    const response = await msalInstance.acquireTokenPopup({ scopes });
    return response.accessToken;
  }
}
```

## React Protected Route

```tsx
function ProtectedRoute({ children, requiredPermission }: {
  children: React.ReactNode;
  requiredPermission: string;
}) {
  const { user, loading } = useAuth();

  if (loading) return <LoadingSpinner />;
  if (!user) return <Navigate to="/login" replace />;
  if (!hasPermission(user.role, requiredPermission)) {
    return <AccessDenied message={`You need '${requiredPermission}' permission to view this page.`} />;
  }
  return <>{children}</>;
}

// Usage in router
<Route path="/penalties" element={
  <ProtectedRoute requiredPermission="view_penalties">
    <PenaltyBreakdown />
  </ProtectedRoute>
} />
```

## Conditional Rendering by Role

```tsx
function KpiDashboard({ userRole }: { userRole: string }) {
  return (
    <div>
      <KpiSummaryCards />
      {hasPermission(userRole, 'view_penalties') && <PenaltyBreakdownPanel />}
      {hasPermission(userRole, 'view_ai_insights') && <AIRecommendationsPanel />}
      {hasPermission(userRole, 'edit_manual_data') && <ManualDataEntryForm />}
      {!hasPermission(userRole, 'view_penalties') && (
        <div role="alert">Contact your manager for full KPI details.</div>
      )}
    </div>
  );
}
```

## Session Security

```javascript
// Secure cookie settings
const SESSION_CONFIG = {
  httpOnly: true,        // Prevents XSS access to cookies
  secure: true,          // HTTPS only
  sameSite: 'strict',    // CSRF protection
  maxAge: 3600000,       // 1 hour
  path: '/',
};

// Security headers
const SECURITY_HEADERS = {
  'Content-Security-Policy': "default-src 'self'; script-src 'self'",
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'X-XSS-Protection': '1; mode=block',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
};
```

## Paratransit Dashboard Access Matrix

| Feature | Admin | Manager | Analyst | Viewer |
|---------|-------|---------|---------|--------|
| View Dashboard | Yes | Yes | Yes | Yes |
| View Penalties | Yes | Yes | Yes | No |
| View Incentives | Yes | Yes | Yes | No |
| View AI Insights | Yes | Yes | No | No |
| Export Reports | Yes | Yes | Yes | No |
| Edit Manual Data | Yes | Yes | No | No |
| Manage Users | Yes | No | No | No |
| View Audit Log | Yes | No | No | No |

## Integration

| Agent | Relationship |
|-------|-------------|
| **VAULT** (Enterprise) | Full enterprise auth architecture |
| **Dashboard Deployer** | M365 CLI certificate-based auth for deployment |
| **All framework agents** | Framework-specific auth patterns |

## Standards

- Initialize PnPjs in `onInit()`, never in component constructors
- Fail closed on permission checks — deny access when checks throw errors
- Never log access tokens to console or error messages
- Use SPFx context for SharePoint auth, never hardcoded credentials
- Cache role checks per session — avoid checking group membership on every render
- Sensitive data (penalty amounts) requires 'manager' role minimum
- JWT refresh tokens stored in httpOnly cookies, never localStorage

## Anti-Patterns

1. **Storing tokens in localStorage** — use httpOnly cookies for refresh tokens
2. **Client-side-only auth** — always validate on server/API layer too
3. **Hardcoded credentials** — use environment variables and certificate-based auth
4. **Fail open** — always deny access on error, never grant by default
5. **No role hierarchy** — admin inherits all lower-role permissions
6. **Missing CSRF protection** — use sameSite cookies and CSRF tokens
