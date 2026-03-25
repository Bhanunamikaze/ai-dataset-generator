# LLM Audit Rubric

Use this when judging whether a record should pass the dataset.

## Core questions

Score on all six dimensions. Fail immediately if any dimension scores 1.

1. Does the record match the requested task type?
2. Is the instruction clear and specific, free from trope preambles ("As an AI…", "Here is…", "In summary")?
3. Is the response useful, coherent, and fit for training?
4. Does it avoid obvious refusal or placeholder language?
5. Would keeping this record improve the final dataset? Is it non-redundant?
6. **Behavioral delta** — Does this record demonstrate a reasoning pattern, constraint adherence, or capability a base model would typically fail at? Score low if the task is trivial or the base model already handles it confidently without fine-tuning signal.

## Factuality & grounding check

Before scoring dimensions 3 and 6:
- If a `context` field is present, cross-reference all claims in the response against it. Fail records that introduce unsupported facts.
- If no context is provided, evaluate for internal logical consistency. Flag self-contradictions or implausible claims.

## Verbosity fit

Penalise dimension 3 when:
- The response is disproportionately long for a simple instruction (padding, excessive caveats, repetition).
- The response is disproportionately short for a complex instruction (skips required steps, hand-waves reasoning).
- The response length would train the model toward a poor verbosity calibration for the task type.

## Pass guidance

- `5`: strong example, ready to keep, clear behavioral delta
- `4`: good example, minor weakness in one dimension
- `3`: borderline — keep only if coverage of an underrepresented subtopic is needed
- `2`: weak, likely fail
- `1`: unusable — fail immediately

Map final decision to:

- `pass` for scores ≥ 4 (or 3 when explicit underrepresented-subtopic coverage is needed)
- `fail` for scores ≤ 2 or any dimension scored 1

