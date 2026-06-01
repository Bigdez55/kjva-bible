# pipeline-connection-map-authoring

<!-- Source: migrated from ~/.claude/skills/pipeline-connection-map-authoring/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: pipeline-connection-map-authoring -->

**Summary.** Forces authoring of a written Connection Map BEFORE any change that crosses three or more stages of a data or transformation pipeline. Project-agnostic discipline applicable to compilers (source → AST → IR → codegen → runtime), ETL pipelines (extract → transform → load), render pipelines, HTTP middleware chains, message-queue topologies, and ML inference pipelines. The map is the artifact; the change is downstream. Triggers on phrases: "pipeline change", "data flow", "end-to-end trace", "source to sink", "multi-stage", "ETL change", "compiler pipeline", "parser to codegen", "request middleware chain", "message queue topology", "ML inference pipeline", or any change touching three or more stages of a transformation chain. Without the map, dependencies are guessed and downstream stages regress invisibly. Anchored by SUPER C v31.5.I.F1 field-lowering connection map (~400 lines, 8 sections + 2 appendices) that exposed two architectural assumptions and let F1.b/F1.c land clean with zero rework.

# Pipeline Connection Map Authoring

## When to invoke
Triggers: "pipeline change", "data flow", "end-to-end trace", "source to sink", "multi-stage", "ETL change", "compiler pipeline", "parser to codegen", "request middleware chain", "message queue topology", "ML inference pipeline", any change touching ≥3 stages of a transformation chain.

## Core directive
**Any change crossing ≥3 stages of a data/transformation pipeline MUST be preceded by a written Connection Map.** The map is the artifact; the change is downstream. Without the map, dependencies are guessed and downstream stages regress invisibly.

## Map template

```markdown
# <Pipeline> Connection Map for <Change>

## §1 Pipeline Overview (ASCII diagram)
<source input> → stage1 → stage2 → … → <final output>

Walk through a CONCRETE input example end-to-end. Name each stage,
the in-type, out-type, and the transformation.

## §2 Per-Stage Data Carried
| Stage | File:Line | In-type | Out-type | Invariant | Test fixture |
|---|---|---|---|---|---|
| Lexer | lexer.sc:XXX | bytes | tokens | well-formed UTF-8 | empty/single/multi |
| Parser | parser.sc:XXX | tokens | AST | tree well-formed | minimal/full |
| ... | ... | ... | ... | ... | ... |

## §3 What This Change Adds at Each Stage
For each stage, EXACTLY what new/modified handling.

## §4 What Connections Are MISSING Today
Cite file:line for each gap; classify as parser-side, sema-side, lower-side, codegen-side, runtime-side.

## §5 What Connections Will Be Added
Per sub-cycle, the EXACT connections to wire.

## §6 Wrapper/Helper Patterns to Reuse
Cite EXISTING functions/helpers that fit the pattern.

## §7 Routing — How a Value Flows End-to-End
Step-by-step trace of one input value through every transformation.

## §8 Simplification Opportunities
What complexity can be removed by this change.
```

## When required (mandatory)
- Change crosses ≥3 stages
- Cross-module (modifies code in 2+ directories)
- Cross-process (e.g., parent + child communication)
- Cross-language (e.g., C-side parser + SC-side lower)
- ML/data pipelines with intermediate representations

## When optional
- Single-file change within one stage
- Bug fix with known root-cause + known fix site

## Map validation gate
Every row must cite a real file:line. Reviewer (or advisor()) verifies the cited code matches the claim before signoff.

## Map-as-onboarding artifact
After landing, the connection map becomes onboarding material for new contributors. Keep it under `docs/connections/<pipeline_name>.md` (or equivalent).

## Empirical anchor
SUPER C v31.5.I.F1 — `docs/reports/v31_5I_F1_connection_map.md` (~400 lines, 8 sections + 2 appendices) traced field-lowering end-to-end: SC source → C-side lexer → parser → AST → Pass 4.20/4.21 stamping → lower_walker → SCIR-Low → codegen_arm64 → ARM64 Mach-O → JIT/runtime. Exposed 2 architectural assumptions that would have caused F1.b/F1.c reverts (ARM64 codegen already wired for inst.field_index; struct schema needs per-field metadata extension). Map authored BEFORE F1.b/c implementation; both sub-cycles landed clean (no rework).

## Application domains (project-agnostic)
- Compilers (source → AST → IR → codegen → runtime)
- ETL pipelines (source → extract → transform → load → analytics)
- Render pipelines (scene → vertex → rasterize → fragment → framebuffer)
- HTTP middleware chains (request → auth → routing → business → response)
- Message-queue topologies (producer → broker → consumer → dead-letter)
- ML inference (input → preproc → model → postproc → output)

## Cross-references
- `compiler-discipline` (SHIRL opcode tables for SC compiler maps)
- `data-pipeline` (medallion architecture for ETL maps)
- `one-shot-execution-planning` (map IS the One Shot Plan's §3 Failure Map deepened)
- `audit-assess-analyze` (depth standard)

## Anti-patterns
- Map authored AFTER implementation → recursive sunk-cost defense of incorrect assumptions
- Map without file:line citations → unfalsifiable, unauditable
- Map that doesn't trace a concrete input → no proof of completeness
