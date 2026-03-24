# Dataset-Generator-Skill Task Tracker

## Build Contract

- Status: `in_progress`
- Goal: Build an agentic dataset generation skill that supports SFT and DPO workflows, async execution, resumable SQLite state, verification, deduplication, export, and data-card generation.
- Source documents:
  - `Plan/plan.md`
  - `Plan/dataset_skill_architecture.svg`
  - `Plan/llm_dataset_industry_pipeline.svg`

## Confirmed Decisions

- Status: `completed`
- Support both SFT and DPO automatically based on the user's request.
- Prefer `target-schemas/` naming for export schemas and keep the structure internally consistent.
- Generate the data card automatically as an artifact of export instead of as a separate top-level command.
- Support both JSONL and CSV inputs/outputs in v1.
- Start with one provider integration first, while structuring the code so additional providers can be added later.
- Support three primary user entry paths:
  - User asks the LLM to generate a dataset from a topic or task description.
  - User provides URLs or reference data to be structured into a dataset.
  - User provides existing datasets from various sources to be normalized, verified, deduplicated, and exported.

## Task List

| ID | Task | Details | Status |
| --- | --- | --- | --- |
| T01 | Repository bootstrap | Initialize git, create the required folder structure, and add baseline ignore rules where needed. | `pending` |
| T02 | Tracker maintenance | Keep this file current with scope, progress, and change summaries across the build. | `in_progress` |
| T03 | Environment installer | Create `install.sh` to bootstrap a virtual environment and install runtime dependencies for async HTTP, deduplication, and data processing. | `pending` |
| T04 | Canonical schema | Define `resources/internal-schema/canonical_schema.json` for a unified record model that can represent both SFT and DPO examples. | `pending` |
| T05 | Workspace bootstrap | Create `workspace/` artifacts and a SQLite initialization layer in `scripts/utils/db.py` for resumable runs and record lifecycle tracking. | `pending` |
| T06 | Shared runtime utilities | Add reusable utilities for config loading, provider selection, prompt loading, schema helpers, CSV/JSONL parsing, and structured record conversion. | `pending` |
| T07 | Generation pipeline | Implement `scripts/generate.py` for async batch generation from prompt templates and structured upstream inputs with concurrency control. | `pending` |
| T08 | Augmentation pipeline | Implement `scripts/augment.py` for diversity transformations such as tone shifts, persona changes, difficulty changes, and adversarial variations. | `pending` |
| T09 | Verification pipeline | Implement `scripts/verify.py` with heuristic refusal detection, schema validation, and LLM-as-judge scoring. | `pending` |
| T10 | Deduplication pipeline | Implement `scripts/dedup.py` with exact and near-duplicate detection using MinHash/LSH. | `pending` |
| T11 | Export pipeline | Implement `scripts/export.py` for OpenAI/Hugging Face style JSONL and CSV exports, dataset splits, and automatic data-card output. | `pending` |
| T12 | Input ingestion | Support URL/reference-data workflows and existing dataset ingestion workflows that normalize external content into the canonical schema. | `pending` |
| T13 | Sub-skill prompts | Create the markdown prompt files in `sub-skills/` for strategy, seeding, diversity, filtering, judging, deduplication guidance, export formatting, data card generation, and verification-only flows. | `pending` |
| T14 | Skill orchestrator | Create `SKILL.md` as the orchestration entry point for `dataset generate`, `dataset verify`, and `dataset export`, including resume detection and route selection by user intent. | `pending` |
| T15 | Verification and QA | Run local smoke checks, validate the schema and scripts, and document any limits that require future provider/network access. | `pending` |

## Open Technical Notes

- Status: `in_progress`
- The canonical schema needs to support both single-response and preference-pair records without forcing separate pipelines.
- Provider integration will be implemented behind an adapter boundary so a second provider can be added without reworking the scripts.
- URL ingestion and internet-assisted collection will be designed into the architecture, but any live network-dependent paths may need to remain unexecuted in this sandboxed environment.

## Change Log

- Status: `in_progress`
- 2026-03-24: Read the planning documents, resolved the main contract questions with the user, and created the initial tracked task ledger.
