### Phase 1: Overhauling Evaluation & The Quality Gate
*Objective: Stop the pipeline from approving low-value, redundant, or overly simplistic records.*

**1. Update `sub-skills/llm-audit-rubric.md` (The Scoring Rubric)**
* **Add "Behavioral Delta" Criterion:** Introduce a mandatory 6th scoring dimension. The rubric must ask: *"Does this record demonstrate a reasoning pattern, constraint adherence, or capability that a base model would typically fail at?"* Score records low if they represent trivial tasks.
* **Add Factuality/Grounding Checks:** Require a verification step where the judge cross-references claims in the output against provided context or strictly evaluates logical consistency if no context is provided.

**2. Update `sub-skills/llm-judge.md` (The Evaluator)**
* **Implement Adversarial Judging (Self-Bias Mitigation):** Instruct the agent acting as the judge to adopt a "red team" mindset. Before assigning a final score, the prompt must force the judge to generate a 2-sentence argument on *why the record should be rejected*.
* **Separate Pass Validations:** Split the evaluation into distinct passes: one for structural formatting (JSON/Markdown), one for instruction-following fidelity, and one for capability-fit.

`llm-judge.md` uses the same model that generated the records to judge them. This means the model's systematic errors and blind spots are invisible to the judge — the judge will score highly the exact patterns the generator was confident about. This is a well-known problem in synthetic data generation.

The skill should at minimum acknowledge this and suggest mitigations: adversarial judging prompts ("argue why this record should fail before deciding"), multi-angle evaluation (separate coherence pass vs. instruction-following pass vs. capability-fit pass), and encouraging manual review of high-confidence passes rather than just flagged records.

**Proposed addition to `llm-judge.md`:** Add a section on judge calibration and self-bias: instruct the judge to actively look for reasons to fail each record before scoring it, and to flag records where instruction-following fidelity is ambiguous (not just coherence).


### Phase 2: Upgrading Generation & Diversity Mechanics
*Objective: Force the generator out of its latent comfort zone to create hard, unique, and edge-case-heavy data.*

**1. Update `sub-skills/seed-generator.md` (The Seed Prompter)**
* **Mandate Multi-Constraint Prompts:** Update the prompt generation instructions to require at least 2-3 specific constraints per seed (e.g., negative constraints like "do not use the `requests` library", or formatting constraints like "return only valid JSON").
* **Anti-Trope Guardrails:** Explicitly list forbidden phrases (e.g., "As an AI...", "Here is the...", "In summary") and instruct the generator to drop preambles entirely.

**2. Update `sub-skills/diversity-engine.md` (The Augmenter)**
* **Semantic Coverage Auditing:** Before generating new variants, instruct the engine to group existing seeds by intent/subtopic. Force it to target the *underrepresented* edge cases rather than creating variations of the most common path.
* **Structural & Adversarial Edge Cases:** Add axes for structural diversity (e.g., dense text vs. pure code vs. Socratic dialogue) and adversarial inputs (typos, ambiguous phrasing requiring clarification, inherently contradictory instructions).

`diversity-engine.md` varies persona, difficulty, tone, intent, and phrasing. These are _surface axes_. For fine-tuning, what matters is _semantic task coverage_ — whether the dataset covers the intended capability space uniformly, including edge cases and underrepresented subtopics.

The skill doesn't guide the agent to think about: what fraction of records cover the easy/common case vs. the rare/tricky cases? There's no prompt to check for mode collapse — where a dataset generated on "customer support" might be 80% polite billing inquiries and nearly zero angry escalation or multilingual requests, even after persona augmentation.

The diversity engine also has no notion of **slot-filling** — generating examples systematically to cover all combinations of: (task category × difficulty × user type × edge case type), which is the actual way fine-tuning practitioners ensure coverage.

**Proposed change to `diversity-engine.md`:** Add a "coverage audit" step before augmentation that groups existing records by semantic subtopic (can be heuristic via instruction keyword clustering) and flags undertopics. Augmentation should target undertopics, not just create surface variants of the already-well-represented cases.

### Phase 3: Strategic Targeting & DPO Infrastructure
*Objective: Align the generated data with the specific training paradigm (SFT vs. DPO) and the target platform.*

**1. Create New File: `sub-skills/dpo-pair-generator.md`**
* **Define Hard Negatives:** Create dedicated logic for generating the `rejected` response. Explicitly state that rejected responses cannot be random garbage. They must be *plausible but fundamentally flawed* (e.g., syntactically correct code with a subtle logic bug, or a polite response that misses the core constraint).
* **Contrastive Rules:** Ensure the delta between the `chosen` and `rejected` responses is isolated to the specific behavior being taught, preventing the model from learning to just "prefer longer answers."

The skill claims DPO support in the description and in `dataset-strategy.md`, but none of the sub-skills say anything specific about DPO. This matters enormously because generating good DPO pairs is fundamentally different from SFT generation.

For DPO to work during training, the **rejected response must be plausible but suboptimal** — not obviously wrong, not random garbage. If rejected responses are too easy to distinguish, the model learns a trivial signal. The ideal rejected response for DPO is one the base model would actually produce, or a response that's stylistically plausible but has a subtle error, missed nuance, or wrong prioritization.

Right now, the skill generates SFT-style responses and would presumably create rejected responses with no specific guidance, which would likely produce junk DPO pairs.

**Proposed addition:** A new sub-skill `sub-skills/dpo-pair-generator.md` covering: what makes a valid rejected response, how to generate "plausible but wrong" alternatives, how to avoid rejected responses that are just shorter or more polite versions of the chosen response, and how to audit DPO pairs for signal quality.

**2. Update `sub-skills/dataset-strategy.md` (The Planner)**
* **Introduce Platform Profiles:** Add routing logic based on the target LLM.
    * *Codex:* Prioritize raw code, inline comments, FIM (Fill-in-the-Middle) structures.
    * *Claude Code:* Prioritize multi-turn agentic workflows, tool-use XML formatting, and conversational clarification.
* **Benchmark Contamination Guards:** Add a hard rule during the planning phase to explicitly avoid naming conventions, variable names, or problem structures commonly found in HumanEval, MMLU, or GSM8K.

### Phase 4: Robust Deduplication & Filtering Hooks
*Objective: Eliminate near-duplicates and enforce hard quality baselines programmatically.*

**1. Update `sub-skills/deduplicator.md` & `scripts/dedup.py`**
* **Semantic Deduplication:** Move beyond exact-match hashing. Outline the logic for MinHash, TF-IDF, or lightweight embedding-based clustering to group and eliminate records that ask the same conceptual question using different words.
* **Sampling Strategy:** Instruct the agent to sample *one* high-quality representative from each semantic cluster rather than keeping all near-duplicates.

**2. Update `sub-skills/quality-filter.md`**
* **Task-Relative Minimum Lengths:** Instead of a blanket "ultra-short" filter, implement heuristics based on intent (e.g., a "code review" intent requires a minimum word/line count, whereas a "regex generation" intent does not).
* **Syntax Hooks:** Add placeholders or instructions for integrating lightweight linters (e.g., `ast.parse` for Python) before a record ever reaches the LLM judge.