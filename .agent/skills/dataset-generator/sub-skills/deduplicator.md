# deduplicator

Use this after verification and before export.

## Goal

Keep the strongest record in each duplicate cluster and suppress the rest.

## Policy

- Prefer the earliest or already-reviewed record as the keeper.
- Mark duplicates instead of silently dropping provenance.
- Run dedup on passing records before export.

## Command

```bash
python3 scripts/dedup.py --from-status verified_pass --threshold 0.85
```

