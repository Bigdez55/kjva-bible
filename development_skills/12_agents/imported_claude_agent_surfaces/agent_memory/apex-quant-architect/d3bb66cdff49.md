# Account Tab API Data Flow Audit (2026-02-12)

## Files Audited
- `frontend/src/services/deviceManagementApi.ts` (26 endpoints)
- `frontend/src/services/tradingApi.ts` (12 endpoints)
- `frontend/src/services/subscriptionApi.ts` (7 endpoints, RTK Query)
- `frontend/src/services/subscriptionService.ts` (legacy imperative, NOT used by Account tab)
- `frontend/src/store/slices/authSlice.ts` (state.auth.user)
- `frontend/src/store/store.ts` (all 4 slices registered correctly)
- `frontend/src/components/elson-v2/hooks/useAccountData.ts` (aggregation hook)
- `frontend/src/components/elson-v2/types/index.ts` (V2 SubscriptionPlan type)
- `frontend/src/pages/AccountPage.tsx` (presentation, 1022 lines)

## Findings Summary (10 total)

### P0 - Runtime Crash
1. SubscriptionPlan type mismatch: API returns {price_monthly, price_yearly}, UI reads {price, apy, trades}. plan.price.toFixed(2) throws TypeError.

### P1 - Wrong/Missing Data
2. LoginAttempt: UI reads device_info/user_agent (don't exist), type has device_fingerprint. Always "Unknown Device".
3. Sessions: realSessions destructured but hardcoded array rendered. Revoke/Sign-out-all not wired.
4. TradingAccount: account_id/created_at/account_type all hardcoded strings.

### P2 - Hardcoded Over Real Data
5. 2FA card: Always "Enabled" badge, ignores twoFactorConfig.is_enabled
6. Security score: Always "Strong" + all complete, ignores computed securityScore
7. Security alert toggles: All on={true}, not wired to securitySettings

### P3 - Cleanup
8. Unused useState import in useAccountData.ts
9. Triple SubscriptionPlan type definitions
10. Phone field from localStorage, no API endpoint

## What Works
- Store registration (all 4 API slices)
- useAccountData hook (correct queries, mutations, score computation)
- Auth user -> profile name/email flow
- Subscription tier via getActiveSubscription
