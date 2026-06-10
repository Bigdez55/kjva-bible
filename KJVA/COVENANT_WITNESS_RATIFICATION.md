# Covenant Counter-Witness Ratification

Agent-drafted scripture witnesses are **NOT production-canonical** until the Creator ratifies
them here. They are gated OFF in code (`_DRAFT_ENRICHMENT_PRODUCTION_ENABLED = False` in
`ai/tokenless-agent/src/retrieval/counter_witness.py`). Until ratified, COV-003 and COV-006
denials ground on their **owner-authored registry-primary** witness only.

To ratify: review each verse below, mark **APPROVE** or **REJECT**, then set
`_DRAFT_ENRICHMENT_PRODUCTION_ENABLED = True` (and/or move approved witnesses into the owner's
authored map `alignment_counter_witness_v1.jsonl`).

---

## Owner-authored (already canonical — for reference, no action needed)

| Covenant | Category | Witnesses |
|----------|----------|-----------|
| COV-001 Harm prevention | harm_prevention | Exodus 20:13, Deuteronomy 5:17, Proverbs 3:29, Proverbs 6:17, Wisdom 1:13 |
| COV-002 Truth / false witness | false_witness | Exodus 20:16, Deuteronomy 5:20, Proverbs 12:22 |
| COV-007 No manipulation | manipulation | Proverbs 12:20, Proverbs 6:16 |
| COV-009 Identity integrity | identity_integrity | Galatians 1:8, Deuteronomy 4:2 |
| COV-010 Canonical weight authority | canonical_weight_authority | 2 Timothy 2:15, Deuteronomy 19:15 |

---

## AGENT-DRAFTED — pending your ratification

### COV-003 — Privacy  (registry primary, already canonical: Proverbs 11:13)

| Proposed witness | Text (retrieved, exact) | Decision |
|------------------|--------------------------|----------|
| Proverbs 20:19 | "He that goeth about as a talebearer revealeth secrets: therefore meddle not with him that flattereth with his lips." | ☐ APPROVE ☐ REJECT |
| Sirach 27:16 (Apocrypha) | "Whoso discovereth secrets loseth his credit; and shall never find friend to his mind." | ☐ APPROVE ☐ REJECT |
| Sirach 19:8 (Apocrypha) | "Whether it be to friend or foe, talk not of other men's lives; and if thou canst without offence, reveal them not." | ☐ APPROVE ☐ REJECT |

### COV-006 — Respect  (registry primary, already canonical: Proverbs 15:1)

| Proposed witness | Text (retrieved, exact) | Decision |
|------------------|--------------------------|----------|
| Proverbs 12:18 | "There is that speaketh like the piercings of a sword: but the tongue of the wise is health." | ☐ APPROVE ☐ REJECT |
| Ephesians 4:29 | "Let no corrupt communication proceed out of your mouth, but that which is good to the use of edifying…" | ☐ APPROVE ☐ REJECT |
| Sirach 28:17 (Apocrypha) | "The stroke of the whip maketh marks in the flesh: but the stroke of the tongue breaketh the bones." | ☐ APPROVE ☐ REJECT |

---

## Activation

```
After marking decisions above:
  - Keep only APPROVED witnesses.
  - Either move them into alignment_counter_witness_v1.jsonl (owner-authored),
    or set _DRAFT_ENRICHMENT_PRODUCTION_ENABLED = True with the approved set.
  - Re-run: pytest, production_smoke.py, regression_gate.py.

Creator Sovereign ratification: ____________________________   Date: __________
```
