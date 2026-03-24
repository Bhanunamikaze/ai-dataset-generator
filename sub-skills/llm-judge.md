# llm-judge

Use this after heuristic filtering when records still need semantic scoring.

## Goal

Judge whether each record should pass into the exportable dataset.

## Score on

- instruction-following
- usefulness
- coherence
- grounding or plausibility
- task-fit for the intended dataset

## Output format

Produce one JSON object per record:

```json
{"id":"rec_123","score":5,"reason":"Clear, useful, aligned example.","status":"pass"}
```

Rules:

- `score` must be `1` to `5`
- `status` must be `pass` or `fail`
- `reason` must be short and concrete

Save the review file, then apply it with:

```bash
python3 scripts/verify.py --from-status raw_generated --review-file <review.jsonl>
```

Reference rubric: `resources/references/llm-audit-rubric.md`

