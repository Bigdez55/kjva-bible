# Playbook: SKILL_DIAGRAM_RENDER_001 — Diagram Render

## Skill ID
SKILL_DIAGRAM_RENDER_001

## Version
1.0.0

## Purpose
Validate `.mmd` Mermaid diagram syntax and render each diagram to SVG (and optionally
PNG) in the `04_architecture/diagrams/rendered/` output directory. Also updates the
diagram registry to reflect render status and timestamps.

---

## Inputs

| Field        | Type   | Required | Default                                       | Description                        |
|--------------|--------|----------|-----------------------------------------------|------------------------------------|
| `target_dir` | path   | no       | `atlas/04_architecture/diagrams/source/` | Directory to scan for `.mmd` files |
| `output_dir` | path   | no       | `atlas/04_architecture/diagrams/rendered/` | Directory to write SVG/PNG output |
| `mode`       | enum   | no       | `render`                                      | `check` (validate only) or `render` (validate + render) |
| `file`       | path   | no       | —                                             | If set, process only this single `.mmd` file |

---

## Prerequisites

### Check for mermaid-cli
```bash
npx --yes @mermaid-js/mermaid-cli --version
```

If the command fails or returns an error, install globally:
```bash
npm install -g @mermaid-js/mermaid-cli
```

Verify installation:
```bash
mmdc --version
```

**OneDrive path note:** All paths passed to `mmdc` MUST be quoted with double-quotes.
OneDrive paths contain spaces (e.g. `OneDrive-Personal`) that will break unquoted shell
arguments. Always use:
```bash
mmdc -i "<input_path>" -o "<output_path>"
```

---

## Step-by-Step Execution

### Step 1: Enumerate .mmd Files

If `file` input is provided, process only that file. Otherwise:
```bash
find "<target_dir>" -name "*.mmd" -type f | sort
```

Build a list of absolute paths. Each path becomes one render job.

### Step 2: Ensure Output Directory Exists

```bash
mkdir -p "<output_dir>"
```

Preserve the source sub-directory structure in the output directory.
Example: if source is `source/architecture/genesys/genesys_system_context.mmd`,
output is `rendered/architecture/genesys/genesys_system_context.svg`.

```bash
mkdir -p "<output_dir>/architecture/<name>/"
```

### Step 3: Validate Each .mmd File (--check mode)

For each `.mmd` file, run a syntax-only check by attempting a dry render to `/dev/null`:
```bash
mmdc -i "<source>.mmd" -o "/tmp/validate_check.svg" 2>&1
```

Capture stdout and stderr. A passing file produces no output or only informational lines.
A failing file produces error output containing `Error` or `ParseError`.

**Valid SVG check:** After render, verify the output is not an error SVG:
```bash
grep -c "<svg" "<output>.svg"
# must return 1 (exactly one <svg element)
grep -c "Error" "<output>.svg"
# must return 0
```

If the SVG file is 0 bytes or contains the word `Error` in the SVG body, the render
failed silently. Treat this as a validation failure.

### Step 4: Render Each .mmd File to SVG

```bash
mmdc -i "<source>.mmd" -o "<output>.svg"
```

Capture exit code. Exit code 0 = success. Non-zero = failure.

Log each result:
```
[OK]   genesys_system_context.mmd  →  genesys_system_context.svg
[FAIL] genesys_data_flow.mmd       →  syntax error on line 12
```

### Step 5: Render to PNG (optional)

If PNG output is required:
```bash
mmdc -i "<source>.mmd" -o "<output>.png"
```

PNG rendering requires a headless Chromium. If Chromium is not available,
skip PNG silently and log:
```
[SKIP-PNG] Chromium not available — SVG only
```

### Step 6: Batch Render the Full Atlas

To render all 7 diagrams for a repo named `<name>` in one pass:
```bash
ATLAS_DIR="atlas/04_architecture/diagrams/source/architecture/<name>"
OUT_DIR="atlas/04_architecture/diagrams/rendered/architecture/<name>"
mkdir -p "$OUT_DIR"

for mmd in "$ATLAS_DIR"/*.mmd; do
  base=$(basename "$mmd" .mmd)
  mmdc -i "$mmd" -o "$OUT_DIR/$base.svg" && echo "[OK] $base" || echo "[FAIL] $base"
done
```

### Step 7: Update diagram.registry.yaml

After all renders complete, update the registry entry for each processed diagram.
Add or update the following fields on each item:
```yaml
- id: <name>_system_context
  path: source/architecture/<name>/<name>_system_context.mmd
  rendered_svg: rendered/architecture/<name>/<name>_system_context.svg
  render_status: ok        # ok | failed | skipped
  last_rendered: <ISO date>
```

Run SKILL_REGISTRY_SYNC_001 `--write` if the diagram registry is tracked by
`sync_registries.py`. Otherwise update the registry file directly.

---

## CI Integration

The `diagram-validate` GitHub Actions job uses this skill in `check` mode:

```yaml
jobs:
  diagram-validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install mermaid-cli
        run: npm install -g @mermaid-js/mermaid-cli
      - name: Validate all diagrams
        run: |
          find "atlas/04_architecture/diagrams/source" -name "*.mmd" | \
          while read f; do
            mmdc -i "$f" -o /tmp/check.svg || { echo "FAIL: $f"; exit 1; }
          done
```

Exit code 1 on any failure fails the job. PRs cannot merge if any `.mmd` file has
a syntax error.

---

## Validating SVG Output Quality

A rendered SVG is considered **valid** if all of the following are true:
1. File size > 0 bytes.
2. File contains exactly one `<svg` opening tag.
3. File does NOT contain the string `Error` as text content within the SVG body.
4. File contains at least one `<g` group element (indicates actual diagram nodes).

An **error SVG** is produced by mermaid-cli when it encounters a syntax error but
does not exit non-zero. Always check the SVG content, not just the exit code.

---

## Failure Modes and Mitigations

| Failure                          | Symptom                                              | Mitigation                                                        |
|----------------------------------|------------------------------------------------------|-------------------------------------------------------------------|
| Syntax error in .mmd             | `mmdc` exits non-zero or produces error SVG          | Open the `.mmd` file, fix the Mermaid syntax at the reported line.|
| mermaid-cli not installed        | `mmdc: command not found`                            | Run `npm install -g @mermaid-js/mermaid-cli` then retry.          |
| OneDrive path with spaces        | Shell argument splitting error                       | Quote ALL paths with double-quotes. Use `"$var"` not `$var`.      |
| Output SVG is empty (0 bytes)    | Render appears to succeed but SVG is empty           | Check for Chromium/Puppeteer missing; try `--puppeteerConfigFile`.|
| Chromium not found (PNG mode)    | `Error: Could not find Chromium`                     | Skip PNG; SVG-only is acceptable. Install chromium if PNG needed. |
| Output directory does not exist  | `mmdc` fails with directory-not-found                | Run `mkdir -p "<output_dir>"` before first render.                |
| Diagram registry out of date     | CI registry-validate job fails after new .mmd added  | Run SKILL_REGISTRY_SYNC_001 `--write` after adding diagrams.      |
| .mmd file missing header comment | Not a render failure, but violates atlas standard    | Add the 4-line `%% diagram_type` header comment block.            |

---

## Validation
See `08_verification/skill_tests/TEST_SKILL_DIAGRAM_RENDER_001_001.yaml`.

The test asserts:
- A known-valid `.mmd` file renders to an SVG that passes all 4 validity checks.
- A known-invalid `.mmd` file (with deliberate syntax error) is detected as failed.
- All paths passed to `mmdc` are quoted (path-with-spaces test).
- `diagram.registry.yaml` is updated with `render_status: ok` after a successful render.
- CI `diagram-validate` job fails on any `.mmd` with a syntax error.
