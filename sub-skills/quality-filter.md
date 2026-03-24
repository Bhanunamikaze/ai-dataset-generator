# quality-filter

Use this before or during `verify.py`.

## Fail fast on

- placeholder responses like `[PENDING_RESPONSE]`
- refusal language
- empty or trivial answers
- broken schema structure
- ultra-short instructions or responses
- records that clearly ignore the user task

## Heuristic expectation

If the record fails deterministic checks, mark it as failed before asking for a judge pass.

## Deterministic command

```bash
python3 scripts/verify.py --from-status raw_generated --from-status augmented
```

