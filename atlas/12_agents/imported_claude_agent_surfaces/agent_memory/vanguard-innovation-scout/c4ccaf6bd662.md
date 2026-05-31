# Design Vision SOTA Audit v2 (2026-03-02)

## Key Deprecated API Alert
- `BrowserView` deprecated since Electron 30
- 18+ references in `browser/genesys-browser/electron/main.ts`
- Migration target: `WebContentsView`
- Effort: 1-2 days
- Risk: future Electron versions WILL remove BrowserView

## Model Comparison Results
- Phi-4-mini 3.8B: 67.3% MMLU, 128K context, ~2.8 GB Q4
- Gemma 3 1B: ~45% MMLU, 128K context, ~0.8 GB Q4
- Gemma-3n-E2B: ~60% MMLU, 128K context, multimodal, ~1.5 GB
- Llama 3.2 3B (current): ~55% MMLU, 8K context, ~2.4 GB Q4
- SmolLM2 1.7B: ~50% MMLU, 8K context, ~1.3 GB Q4

## Immutable OS Options Evaluated
1. OSTree (C-based, Debian-compatible via Endless OS): 4-6 weeks
2. A/B partitions (AetherBoot integration): 2-3 weeks
3. Btrfs snapshots (fastest path, kernel-native): 1-2 weeks

## Contra-Rotation Prior Art Conclusion
Searched: Linux EAS, Intel Thread Director, ARM DynamIQ, DVFS thermal scheduling
Result: The specific 3-phase contra-rotation with thermal ceiling as scheduling primitive is NOVEL
No direct prior art found in operating systems or scheduler research

## XKABI vs Competition
- vs seL4: XKABI lacks formal verification but has richer lineage/audit
- vs Zircon: XKABI has epoch-based bulk revocation (unique), narrower syscall surface
- Both seL4 and Zircon lack lineage chain tracking

## Sprint Priority Queue (from this audit)
1. P0: Choose immutable rootfs strategy
2. P0: Migrate BrowserView -> WebContentsView
3. P1: Evaluate Phi-4-mini and Gemma 3 1B models
4. P1: Upgrade React 18 -> 19
5. P1: Wire design tokens into production apps
6. P1: Add HMAC to XKABI handles
7. P2: Implement dual-model AI strategy
8. P2: Move Ollama into k3s (remove hostNetwork)
