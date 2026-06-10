# Rollback Plan — KJVA-1 / XMIND-1 directory replacement

**Date:** 2026-06-09
**Applies to:** whole-directory replacement of `/Users/.../kjva-bible/KJVA`

The replacement is designed to be reversible at every step until the final swap, and even
after, because the prior tree is preserved verbatim. `canonical.gguf` is never modified, so
there is **no model rollback** — only a directory move.

---

## Preserved artifacts (created during replacement)

```
KJVA_BACKUP_<stamp>/        # cp -a of the prior KJVA, made in Phase 1 (never deleted)
KJVA_REPLACED_<stamp>/      # the prior KJVA, moved aside at the swap (Phase 4)
KJVA_OLD_FILE_INVENTORY_<stamp>.txt
```

The prior `training/weights.safetensors` (canonical base) lives in BOTH the backup and the
carried-forward new tree, so the base is never lost.

## Trigger

Roll back if ANY post-replacement gate fails (Phase 5), or on Creator instruction.

## Procedure A — revert the directory swap (primary)

```bash
ROOT="/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/kjva-bible"
OLD="$ROOT/KJVA"
STAMP="<the stamp used during replacement>"

# move the failed new tree aside, restore the prior tree
mv "$OLD" "$ROOT/KJVA_FAILED_REPLACEMENT_$STAMP"
mv "$ROOT/KJVA_REPLACED_$STAMP" "$OLD"
```

## Procedure B — restore from backup (if KJVA_REPLACED is unavailable)

```bash
rm -rf "$OLD"                      # only after confirming the backup is intact
cp -a "$ROOT/KJVA_BACKUP_$STAMP" "$OLD"
```

## Verify after rollback

```bash
cd "$OLD"
ls training/weights.safetensors                 # base present
shasum -a 256 training/weights.safetensors      # matches pre-replacement
# run whatever smoke the prior tree shipped
```

## Runtime authority note

`canonical.gguf` (SHA e59c6909…) is unchanged throughout. If any adapter/model was ever
promoted (it was NOT in this candidate), restore runtime authority by pointing to
`canonical.gguf` and clearing `TOKENLESS_ADAPTER` / `XMIND_ADAPTER`.

## Non-negotiables

- Do NOT delete `KJVA_BACKUP_<stamp>` until the replacement is confirmed good AND Creator-accepted.
- Do NOT delete `KJVA_REPLACED_<stamp>` until rollback is no longer desired.
- Do NOT promote any archived adapter as part of rollback.
