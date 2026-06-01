# Apex Verified Machine Encoding Playbook

## Purpose

Prevent silent compiler/runtime defects from hand-computed machine-code constants in SUPER C / seedc / scc emit paths.

## Activation Rule

Use this skill when work touches:

- ARM64/AArch64 instruction-word constants.
- Future x86_64, QIR, or other ISA constants.
- `*_emit.*` files.
- Intrinsic machine-code emission.
- LDR, STR, LDUR, STUR, LDRB, STRB, or other load/store encodings.
- SIGSEGV/miscompile debugging traced to emitted bytes.
- Commit messages or reports that decode instruction words.

## Core Rule

No hand-computed machine-code constant lands.

Every constant must be:

1. Expressed as intended assembler mnemonic and operands.
2. Encoded by a test-time oracle or sovereign encoder.
3. Compared bit-for-bit to the claimed value.
4. Paired with a regression assertion.
5. Documented with mnemonic intent when a transitional literal is unavoidable.

## Required Gate

```text
STEP 1: Write intended instruction as assembler text.
STEP 2: Run oracle encode.
STEP 3: Compare claimed constant to oracle truth.
STEP 4: If mismatch, claimed value is wrong.
STEP 5: Land only with assertion/regression coverage.
```

## Oracle Boundary

Permitted:

- `llvm-mc`, `as`, `otool`, or equivalent as test-time oracle.
- Helper scripts used only by tests.

Forbidden:

- External tools in the emit path.
- External tools in shipped runtime artifacts.
- Hand-decoded prose as authority.
- Constants without assertions.

Permanent endpoint:

- In-tree SUPER C encoder/decoder pair.
- `decode(encode(instr)) == instr`.
- `encode(decode(word)) == word`.

## Required Output Shape

When this skill triggers, produce:

- Target file/function and ISA.
- Intended mnemonic and operands.
- Oracle command used.
- Oracle bytes and integer word.
- Claimed constant comparison.
- Assertion/regression file path.
- Final allow/block verdict.

## Stop Conditions

- About to type an instruction-word literal with no oracle assertion.
- Oracle disagrees with claimed value.
- Oracle tooling unavailable and no fallback exists.
- Constant would land without regression test.
- Commit/report contains unverified hand-decoding.

## Known Origin

`SC-MISS-005`: three hand-computed ARM64 emit-constant typos in one session. The representative typo was `0xB93FFDE1` corrected to `0xB94003E1`; even one nibble changed runtime behavior. The rule is empirical: no manual constant is trusted until oracle-verified.

