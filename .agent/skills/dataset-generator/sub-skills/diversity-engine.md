# diversity-engine

Use this when the base dataset is too narrow and needs broader coverage.

## Goal

Increase coverage without collapsing into duplicates.

## Apply variation across

- persona
- difficulty
- tone
- intent
- adversarial or tricky edge cases
- phrasing style

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

- Do not create variants that only rename the same example.
- Keep semantic coverage wider than surface paraphrase.

