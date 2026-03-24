---
name: dataset-generator
description: Use this when the user wants to generate, normalize, verify, deduplicate, or export training datasets for Codex, Antigravity, or Claude Code from topics, URLs, reference material, web research, or existing JSONL/CSV files. Supports SFT and DPO workflows, custom export schemas, and deterministic local pipeline scripts.
---

# Dataset Generator

This skill is a tool-native dataset pipeline for Codex, Antigravity, and Claude Code.

- Use the IDE's own tools for browsing, reading, search, and reasoning.
- Use local Python scripts for deterministic normalization, state tracking, verification, deduplication, and export.
- Do not call external LLM-provider APIs as part of this skill.

## Command surface

- `dataset generate "<request>" --count <n>`
- `dataset verify <path/to/file>`
- `dataset export --format <openai|huggingface|csv|jsonl|all> [--schema-file path] [--split 0.1]`

## Core architecture

- `sub-skills/` contains the cognitive instructions.
- `scripts/` contains deterministic helpers.
- `resources/internal-schema/canonical_schema.json` is the fixed pipeline backbone.
- `resources/target-schemas/` contains preset export profiles.
- `resources/templates/custom_flat_schema.json` is the starting point for custom headers.

## Fixed vs flexible schema

- The canonical internal schema is fixed.
- The final export schema is not universal and must be chosen per user request.
- For custom CSV or flat JSONL headers, create or update a schema file and pass it to `scripts/export.py`.

Read `sub-skills/dataset-strategy.md` first whenever the target output schema is not already obvious.

## Workflow selection

### 1. `dataset generate`

Use this when the user wants a new dataset or wants source material structured into one.

1. Read `sub-skills/dataset-strategy.md`.
2. If the request needs generated or normalized draft records, read `sub-skills/seed-generator.md`.
3. If broader coverage is required, read `sub-skills/diversity-engine.md`.
4. If existing runs may matter, inspect the SQLite state before generating:

```bash
python3 -c "from scripts.utils.db import initialize_database, get_connection, list_runs; initialize_database(); conn = get_connection(); print([dict(row) for row in list_runs(conn, limit=5)]); conn.close()"
```

If there is a relevant unfinished or recent run, ask whether to resume or start fresh.

5. Load draft records into SQLite:

```bash
python3 scripts/generate.py --input <drafts.jsonl> --tool-context <codex|claude|antigravity>
```

6. If augmentation is needed:

```bash
python3 scripts/augment.py --input <augmented.jsonl> --tool-context <codex|claude|antigravity>
```

Or deterministic metadata variants:

```bash
python3 scripts/augment.py --from-status raw_generated --persona expert --difficulty hard
```

7. Run heuristic verification:

```bash
python3 scripts/verify.py --from-status raw_generated --from-status augmented
```

8. If semantic judging is needed, read `sub-skills/llm-judge.md`, produce a review file, then apply it:

```bash
python3 scripts/verify.py --from-status raw_generated --review-file <review.jsonl>
```

9. Deduplicate passing records:

```bash
python3 scripts/dedup.py --from-status verified_pass
```

10. Export the dataset and data card:

```bash
python3 scripts/export.py --format <openai|huggingface|csv|jsonl|all> [--schema-file <schema.json>] [--split 0.1]
```

### 2. `dataset verify`

Use this when the user already has a file and wants an audit or cleanup pass.

Read `sub-skills/data-verifier.md`, then run:

```bash
python3 scripts/verify.py --input <dataset.jsonl_or_csv> [--review-file <review.jsonl>]
python3 scripts/dedup.py --from-status verified_pass
python3 scripts/export.py --format csv --split 0.0
```

### 3. `dataset export`

Use this when the verified data already exists in SQLite and the user wants a specific output shape.

Read `sub-skills/formatter-exporter.md` if the schema is not obvious.

Preset export:

```bash
python3 scripts/export.py --format openai --split 0.1
```

Custom flat export:

```bash
python3 scripts/export.py --format csv --schema-file <custom_schema.json> --split 0.1
```

## Reference files

- `sub-skills/dataset-strategy.md`
- `sub-skills/seed-generator.md`
- `sub-skills/diversity-engine.md`
- `sub-skills/quality-filter.md`
- `sub-skills/llm-judge.md`
- `sub-skills/deduplicator.md`
- `sub-skills/formatter-exporter.md`
- `sub-skills/data-card.md`
- `sub-skills/data-verifier.md`
- `resources/references/llm-audit-rubric.md`
- `resources/references/export-schema-pattern.md`

