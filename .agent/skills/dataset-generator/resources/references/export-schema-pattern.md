# Export Schema Pattern

## Rule

Do not assume one universal final header set for every dataset.

## Architecture

- Canonical schema: fixed
- Export schema: selected per run

This keeps verification, deduplication, and resume logic stable while still allowing user-specific outputs.

## Custom flat schema shape

```json
{
  "name": "my-custom-export",
  "mode": "flat",
  "columns": [
    {"name": "prompt", "source": "instruction"},
    {"name": "answer", "source": "response.text"},
    {"name": "difficulty", "source": "metadata.difficulty"}
  ]
}
```

Use dotted `source` paths from canonical data.

