# diversity-engine

Use this when the base dataset is too narrow and needs broader coverage.

## Goal

Increase coverage without collapsing into duplicates.

## Apply variation across

**Surface axes (existing):**
- persona
- difficulty
- tone
- intent
- adversarial or tricky edge cases
- phrasing style

**Semantic axes (required — do not skip):**
- task category (e.g. code generation vs. code review vs. debugging)
- structural format (dense prose, pure code, Socratic dialogue, step-by-step numbered list)
- adversarial inputs (typos in the instruction, ambiguous phrasing requiring clarification, inherently contradictory requirements)
- user expertise level (novice making a category error vs. expert needing a subtle edge case)

## Coverage audit before augmentation

Before generating any variant, run a coverage audit:

1. Group existing records by intent/subtopic (use instruction keywords as a heuristic cluster key).
2. Count records per cluster. Flag any cluster with < 5% of total records as **undertopic**.
3. Flag any cluster with > 40% of total records as **mode collapse risk**.
4. Target augmentation at undertopics first. Do not create variants of already well-represented clusters unless undertopics are covered.

This prevents surface paraphrase of the easy/common case while rare edge cases stay at near-zero.

## Slot-filling matrix

For systematic capability coverage, plan augmentation using a matrix of:

```
task category × difficulty × user type × edge case type
```

Each cell should have at least one record. Cells that are empty after base generation are augmentation targets. Cells that already have 5+ records are low-priority.

## Two execution paths

### Agent-authored augmentations

- Write fully rewritten canonical records to a file.
- Load them with:

```bash
python3 scripts/augment.py --input <augmented.jsonl> --tool-context <codex|claude|antigravity>
```

### Deterministic metadata variants

- Use when you want the pipeline to stamp variant rows first and rewrite them later.

```bash
python3 scripts/augment.py --from-status raw_generated --persona expert --persona reviewer --difficulty medium --difficulty hard
```

## Guardrails

- **Ban "Mad-Libs" slot-filling**: Do not create variants that merely swap entity names or variable names while keeping the exact same reasoning structure.
- **Enforce Structural Diversity**: Force the LLM to vary the entire reasoning pathway, paragraph structure, and code complexity.
- Keep semantic coverage wider than surface paraphrase.

