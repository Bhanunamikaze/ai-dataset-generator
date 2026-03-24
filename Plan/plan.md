
# SYSTEM DIRECTIVE: Agentic Dataset Generation Skill 

## 1. Project Overview
You are tasked with building the `Dataset-Generator-Skill`, an enterprise-grade, agentic pipeline for generating Supervised Fine-Tuning (SFT) and preference (DPO) datasets. The architecture separates cognitive reasoning (Markdown agent prompts) from deterministic execution (Async Python scripts).

**Core Constraints:**
* All API calls must be asynchronous (`asyncio`, `aiohttp`) with concurrency limits (semaphores) to respect rate limits.
* Pipeline state must be aggressively tracked in a local SQLite database to prevent data loss during long generation runs.
* The system must anticipate and gracefully handle API safety filter refusals (as the user frequently generates offensive security/red-teaming datasets).

## 2. Target Directory Structure
Create this exact folder structure. Do not deviate.

Dataset-Generator-Skill/
├── SKILL.md                  
├── install.sh                
├── workspace/                
│   ├── run_state.sqlite      
│   └── canonical.jsonl       
├── sub-skills/               
│   ├── dataset-strategy.md   
│   ├── seed-generator.md     
│   ├── diversity-engine.md   
│   ├── quality-filter.md     
│   ├── llm-judge.md          
│   ├── deduplicator.md       
│   ├── formatter-exporter.md 
│   ├── data-card.md          
│   └── data-verifier.md      
├── scripts/                  
│   ├── generate.py           
│   ├── augment.py            
│   ├── verify.py             
│   ├── dedup.py              
│   └── export.py             
└── resources/                
    ├── internal-schema/      
    ├── target-schemas/       
    ├── templates/            
    └── references/           

## 3. Execution Phases (Build Order)

### Phase 1: Data Foundations & Environment
1. **Create `install.sh`**: Write a bash script to set up a Python virtual environment and install requirements (`aiohttp`, `sqlite3`, `datasketch` for MinHash, `pandas`).
2. **Define `resources/internal-schema/canonical_schema.json`**: Define a strict JSON schema for how intermediate data will be passed between agents. It must contain fields for `id`, `instruction`, `context`, `response`, `metadata` (difficulty, persona), and `pipeline_status` (pending, pass, fail, rewrite).
3. **Database Initialization**: Write a helper function in `scripts/utils/db.py` to initialize `workspace/run_state.sqlite`. It should have a main `records` table tracking the canonical schema fields plus a `status` column to allow pausing/resuming.

### Phase 2: The Execution Scripts (Python)
Write the Python scripts in `scripts/`. These scripts do NOT contain prompts; they take system prompts and data as inputs and execute them against LLM APIs asynchronously.
1. **`generate.py`**: Async script that reads a prompt template, fans out `N` concurrent requests to the target LLM API, and writes the raw responses to the SQLite DB with status `raw_generated`.
2. **`augment.py`**: Reads records marked `raw_generated`, applies diversity permutations (e.g., changes tone/difficulty via API), and updates the DB.
3. **`verify.py`**: 
    * *Step A (Heuristics):* Use regex to immediately fail records containing AI refusals (e.g., "I cannot fulfill this request", "As an AI language model"). 
    * *Step B (LLM Judge):* Async call to evaluate the remaining records against a rubric. Updates DB status to `verified_pass` or `verified_fail`.
4. **`dedup.py`**: Implement MinHash + LSH using the `datasketch` library to find and drop near-duplicate records from the SQLite DB.
5. **`export.py`**: Queries all `verified_pass` records from SQLite, translates them into HuggingFace or OpenAI JSONL formats, performs a Train/Test split, and saves them to `workspace/`.

### Phase 3: The Cognitive Layer (Sub-Skills)
Write the markdown files in `sub-skills/`. These are the system prompts and operational guidelines for the agents.
1. **`dataset-strategy.md`**: Prompt instructing the LLM to take a user's topic and design a taxonomy and column layout.
2. **`seed-generator.md`**: Prompt defining how to create highly diverse initial seed data.
3. **`quality-filter.md` & `llm-judge.md`**: Strict grading rubrics. The judge must output a JSON response containing `{"score": 1-5, "reason": "...", "status": "pass/fail"}`.
4. **`formatter-exporter.md`**: Instructions on how to map the canonical schema to target schemas like ChatML or OpenAI Messages.
5. **`data-verifier.md`**: A standalone agent flow that bypasses generation and only runs the `verify.py` and `dedup.py` steps on an existing user-provided file to generate a statistical audit report.

### Phase 4: The Orchestrator (`SKILL.md`)
Write the master `SKILL.md` file. This acts as the CLI entry point. 
It must define the following commands:
* `dataset generate "topic" --count 1000`: Triggers the full pipeline (Strategy -> Seed -> Generate -> Augment -> Verify -> Dedup -> Export). It must explicitly check the SQLite DB first to ask the user if they want to resume a previous run or start fresh.
* `dataset verify path/to/dataset.jsonl`: Triggers the `data-verifier.md` sub-skill.
* `dataset export --format openai --split 0.1`: Runs `export.py` on the current state of the workspace.

## Execution Directive for AI:
Acknowledge these instructions. Begin by executing Phase 1. Do not proceed to Phase 2 until Phase 1 is fully coded and the directory structure is created.