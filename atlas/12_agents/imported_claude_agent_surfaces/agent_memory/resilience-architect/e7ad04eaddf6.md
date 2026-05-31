---
name: scc parser limitations (Stage 4 v0.4.x)
description: Two parse-time pitfalls in scc that silently inflate err counts on otherwise valid SC source.
type: feedback
---

When writing .sc source that must pass `scc check` (the lex+parse gate), avoid these constructs:

**1. Integer literals with type suffixes inside `while` conditions and many binary contexts**
- `while i < 32u32 { ... }` → parse errors
- `while i < 32 { ... }` → OK (type flows from declared LHS)
- Hex literals retain suffixes (`0x1fffffu64`) without issue.

**2. Parenthesized sub-expression on RHS of binary `|` (and likely other ops)**
- `let v: u64 = b0 | (b1 << 8);` → parse error
- Workaround: hoist into temp — `let s1: u64 = b1 << 8; let v: u64 = b0 | s1;`

**Why:** discovered while implementing `os/crypto/src/sc25519.sc` (V-OS-7b, 2026-05-06). err counts dropped from 15 → 0 once both rules were applied.

**How to apply:** when authoring crypto/numeric SC modules with bit-twiddling, declare types on `let`, drop suffixes from int-literal numerics, and split shifts/masks into named temps before combining with `|`/`&`/`^`. Keep hex constant suffixes — those parse fine in `const` declarations.
