# ATLAS Vercel Release Checklist

## Project
- Vercel project root: `apps/atlas`
- Framework: Next.js
- Product name: ATLAS

## Preflight
- `npm install`
- `npm run lint`
- `npm run build`
- `python3 25_automation/atlas_core/atlas.py tenants --check`
- `python3 25_automation/atlas_core/atlas.py repo-event --repo ATLAS --event-type commit --check`
- Confirm no secrets are committed.
- Confirm `NEXT_PUBLIC_APP_URL` is optional or configured.

## Preview
- Push branch or run Vercel preview deploy.
- Capture preview URL.
- Verify home route loads.
- Verify tenant/repo connector surface is visible.
- Verify product naming and proprietary subsystem names.

## Promotion
- Promote only after proof gates pass.
- Record commit SHA, preview URL, validation commands, and known risks.

## Rollback
- Use Vercel rollback or promote the previous validated deployment.
