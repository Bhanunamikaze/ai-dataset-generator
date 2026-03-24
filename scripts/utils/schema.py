from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT_DIR / "resources" / "internal-schema" / "canonical_schema.json"
PIPELINE_STATUSES = {"pending", "pass", "fail", "rewrite"}
TASK_TYPES = {"sft", "dpo"}


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_record(record: dict[str, Any]) -> list[str]:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return basic_validate_record(record)

    validator = Draft202012Validator(load_schema())
    errors = [error.message for error in validator.iter_errors(record)]
    if errors:
        return errors
    return basic_validate_record(record)


def basic_validate_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    required_fields = (
        "id",
        "task_type",
        "instruction",
        "context",
        "response",
        "metadata",
        "pipeline_status",
    )
    for field in required_fields:
        if field not in record:
            errors.append(f"Missing required field: {field}")

    if record.get("task_type") not in TASK_TYPES:
        errors.append("task_type must be either 'sft' or 'dpo'")

    response = record.get("response")
    if not isinstance(response, dict):
        errors.append("response must be an object")
        return errors

    response_format = response.get("format")
    if response_format == "single":
        if not isinstance(response.get("text"), str) or not response.get("text", "").strip():
            errors.append("single-format responses must include non-empty response.text")
    elif response_format == "preference_pair":
        chosen = response.get("chosen")
        rejected = response.get("rejected")
        if not isinstance(chosen, str) or not chosen.strip():
            errors.append("preference_pair responses must include non-empty response.chosen")
        if not isinstance(rejected, str) or not rejected.strip():
            errors.append("preference_pair responses must include non-empty response.rejected")
    else:
        errors.append("response.format must be 'single' or 'preference_pair'")

    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("metadata must be an object")
    else:
        for key in ("difficulty", "persona"):
            value = metadata.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"metadata.{key} must be a non-empty string")

    if record.get("pipeline_status") not in PIPELINE_STATUSES:
        errors.append("pipeline_status must be pending, pass, fail, or rewrite")

    instruction = record.get("instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        errors.append("instruction must be a non-empty string")

    context = record.get("context")
    if not isinstance(context, str):
        errors.append("context must be a string")

    return errors
