# LLM Audit Rubric

Use this when judging whether a record should pass the dataset.

## Core questions

1. Does the record match the requested task type?
2. Is the instruction clear and specific?
3. Is the response useful, coherent, and fit for training?
4. Does it avoid obvious refusal or placeholder language?
5. Would keeping this record improve the final dataset?

## Pass guidance

- `5`: strong example, ready to keep
- `4`: good example, minor weakness
- `3`: borderline, keep only if coverage is needed
- `2`: weak, likely fail
- `1`: unusable

Map final decision to:

- `pass` for high-confidence keepers
- `fail` for records that should not reach export

