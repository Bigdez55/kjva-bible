# OWNER_AUTHORITY_RECORD.md - Legacy Filename

This compatibility file replaces the old project-specific authority record with
a neutral Tokenless Models policy.

## Policy

| Area | Authority |
|---|---|
| Repository maintenance | Repository owner |
| Model exports | Export manifest plus owner approval |
| Runtime contracts | Change through tests and audit notes |
| Consuming projects | Defined by each consuming project |

## Boundaries

- Do not embed personal machine paths or external project names in reusable
  runtime docs.
- Do not make a consuming project inherit this repository's name or authority
  language.
- Do not change verified model class/export names without a tested migration.
