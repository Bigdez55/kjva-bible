# Internationalization and Localization Playbook

**Skill:** `SKILL_I18N_L10N_001`
**Corpus category:** Internationalization & L10n (Production-Readiness Corpus, `53_production_readiness`)
**Layer:** frontend (with backend and mobile reach)

## When to use

Use this playbook whenever a product must serve more than one language, region,
or script — or before a release that claims multi-locale support. Trigger it when
you see hardcoded UI text, hand-rolled date/number/currency formatting, naive
`n == 1` pluralization, missing RTL support, raw translation keys leaking to
users, or no translation-coverage gate. Also use it when the production-readiness
audit reaches the "Internationalization & L10n" category.

i18n (internationalization) is the engineering work that makes a product
*capable* of localization. l10n (localization) is the per-locale content and
formatting. This skill covers both, end to end.

---

## Key practices by corpus section

### 1. String Externalization & Catalogs

- **Externalize every user-facing string** into message catalogs. No string the
  user can read should be a literal inside a component, template, or business
  rule. This is the prerequisite for every other practice — untranslated text
  cannot be translated, and pseudolocalization cannot catch what it cannot see.
- **Pick one canonical catalog format** and use it everywhere: ICU MessageFormat,
  gettext PO, or Fluent. Mixing formats fragments tooling and breaks coverage
  measurement. ICU MessageFormat is the usual default because it carries plurals,
  selects, and number/date skeletons inline.
- **Stable, namespaced, documented keys.** Use a hierarchy like
  `checkout.button.pay` rather than reusing display text as the key. Audit for
  duplicate and orphaned keys; orphans rot and duplicates drift apart.
- **The default-locale catalog is the single source of truth** and is
  version-controlled. Translators branch from it; it never branches from them.
- **Define the missing-translation fallback chain** (`locale -> region ->
  default`). A missing key must resolve to a real string in a fallback locale —
  it must NEVER render the raw key to a user.

### 2. Locale-Aware Formatting

- **Format via Intl/CLDR, never by hand.** Dates, times, numbers, currencies,
  and percentages all go through a locale-aware library (`Intl.DateTimeFormat`,
  `Intl.NumberFormat`, ICU, CLDR-backed equivalents on other platforms).
- **Time zones are explicit.** Store timestamps in UTC; render in the user's
  locale and zone. Never persist wall-clock local time without an offset.
- **Money is never a float.** Store minor units (integer cents) or a decimal
  type. Format with the locale's correct symbol, decimal separator, and grouping
  separator — `1,234.56` in en-US, `1.234,56` in de-DE.
- **Collation uses locale-aware comparison** (CLDR / `Intl.Collator`), not
  byte or ASCII order. Swedish sorts `ä` differently than German does.
- **Measurement units and first-day-of-week respect locale conventions**
  (metric vs imperial; week starting Sunday vs Monday).

### 3. Pluralization & Grammar

- **Use CLDR plural categories** — `zero / one / two / few / many / other` — via
  the catalog format's plural support. `if (n == 1)` is English-only logic and is
  wrong for Polish, Russian, Arabic, Welsh, and many others.
- **Handle gender and grammatical agreement** where target languages require it
  (ICU `select` for gender; gendered articles and adjective endings).
- **Named placeholders, not positional assumptions.** Word order changes across
  languages; use `{count} items in {cart}`, never assume the order is fixed.
- **No sentence concatenation.** A full sentence lives as one catalog entry.
  Building "You have " + count + " messages" produces ungrammatical results once
  translated — the whole sentence must be translatable as a unit.

### 4. Bidirectional & Script Support

- **RTL locales (Arabic, Hebrew) mirror the layout.** Set `dir="rtl"` and verify
  the full layout flips — navigation, icons, progress, and form flow.
- **CSS logical properties over physical.** Use `margin-inline-start`,
  `inset-inline-end`, `text-align: start` instead of `left`/`right` so direction
  flips automatically and bidi-safely.
- **Fonts cover every shipped script** (CJK, Cyrillic, Arabic, Devanagari).
  Verify glyph coverage; a missing glyph renders tofu (□) and looks broken.
- **Text input, truncation, and ellipsis handle multibyte and combining
  characters.** Truncate by grapheme cluster, not by byte or UTF-16 code unit, so
  emoji and combining marks are never split.

### 5. Translation Workflow & Coverage

- **Define the translation pipeline** (a TMS or a file-based flow). New keys must
  reach translators *before* the release that depends on them.
- **Measure coverage per locale** and **gate the release** on a declared minimum
  threshold. A locale below threshold either ships with explicit fallback or does
  not ship.
- **Run pseudolocalization in CI.** Pseudoloc (e.g. `[!!! Ŝéttîñgŝ !!!]` with
  ~40% length expansion) surfaces hardcoded strings (they stay English) and
  layout truncation (expanded text overflows) automatically, every build.
- **Declare and test the supported locale set** explicitly. The list of
  shipped languages/regions is a tracked artifact, not an accident of which files
  exist.

### 6. Locale Negotiation & Fallback

- **Negotiate locale from a documented precedence:** explicit user preference >
  account settings > `Accept-Language` > default. Write the precedence down.
- **Locale switching preserves user state** and persists across sessions
  (cookie, account record, or stored preference) — switching language must not
  discard a form or reset navigation.
- **Untranslated content falls back gracefully** without breaking layout or
  meaning — partial translation degrades to the fallback locale, never to a blank
  or a raw key.
- **SSR and client locale resolution agree.** Server-rendered and
  client-rendered locale must match, or you get a hydration mismatch. Resolve the
  locale once, server-side, and hand it to the client deterministically.

---

## Concrete workflow / checklist

1. **Inventory.** Grep for hardcoded user-facing strings and hand-rolled
   formatters. Establish the canonical catalog format and the default-locale
   source of truth.
2. **Externalize.** Move every user-facing string into the catalog with stable,
   namespaced keys. Replace literal text with key references.
3. **Route formatting through Intl/CLDR.** Replace every manual date/number/
   currency string with a locale-aware formatter. Convert money to minor units.
4. **Convert plurals and sentences.** Replace `n == 1` with CLDR plural rules;
   collapse concatenated fragments into whole catalog sentences with named
   placeholders.
5. **Make it bidi- and script-safe.** Swap physical CSS for logical properties;
   confirm font glyph coverage for every shipped script; truncate by grapheme.
6. **Stand up the pipeline.** Wire keys to translators (TMS or file-based); add a
   per-locale coverage report; add a pseudolocalization step to CI.
7. **Wire negotiation and fallback.** Implement the documented precedence,
   persist the choice, define `locale -> region -> default` fallback, and align
   SSR/client resolution.
8. **Gate the release.** Block on coverage threshold, pseudoloc pass, RTL render
   check, and no-raw-key check before shipping.

---

## Anti-patterns

| Anti-pattern | Why it fails | Do instead |
|---|---|---|
| Hardcoded UI strings in components | Invisible to translators and pseudoloc; ships English to every locale | Externalize into the catalog with namespaced keys |
| `new Date().toLocaleString()` ad hoc / manual `$` + number | Wrong separators, symbols, and order per locale; floats money | `Intl.DateTimeFormat` / `Intl.NumberFormat`; money in minor units |
| `if (count === 1) "item" else "items"` | English-only; wrong for few/many languages | ICU/CLDR plural categories |
| `"You have " + n + " messages"` | Word order and grammar break in translation | One catalog sentence with named placeholders |
| `margin-left` / `text-align: right` | Does not mirror for RTL | `margin-inline-start` / `text-align: start` |
| Missing key renders the key (`checkout.pay`) | Leaks internals; looks broken | Fallback chain to a real string; never the raw key |
| Storing local wall-clock time | Ambiguous across zones and DST | UTC storage, locale/zone-aware rendering |
| No coverage gate | Ships locales with large untranslated gaps | Per-locale coverage threshold gates release |
| Different SSR vs client locale | Hydration mismatch / flicker | Resolve locale once server-side, pass deterministically |
| Byte/UTF-16 truncation | Splits emoji and combining marks | Truncate by grapheme cluster |

---

## Related

- `SKILL_PRODUCTION_READINESS_AUDIT_001` — owns the corpus; this skill satisfies its "Internationalization & L10n" category.
- `SKILL_UI_INTERACTION_WIRING_001` — locale switching, persisted state, and bidi-aware UI wiring.
- `SKILL_AUTOMATED_REGRESSION_TESTING_001` — pseudolocalization, RTL, and plural-category checks as regression tests.
- `SKILL_CI_PIPELINE_001` — runs pseudoloc and coverage gates in CI.
