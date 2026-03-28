from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __name__ == "__main__" or not getattr(sys.modules.get(__name__, None), "__package__", None):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.utils.artifacts import ensure_ingest_output_dir, write_ingest_outputs
from scripts.utils.canonical import build_record_id, normalize_record
from scripts.utils.db import get_connection, initialize_database, upsert_record, upsert_run
from scripts.utils.discovery import discover_source_files
from scripts.utils.files import write_json
from scripts.utils.parsers import parse_discovered_files
from scripts.utils.schema import validate_record, validate_source_artifact


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Structured local ingestion pipeline. Discover supported source files, "
            "parse them into artifacts and bundles, build canonical dataset drafts, "
            "and import them into the SQLite pipeline state."
        )
    )
    parser.add_argument(
        "--paths",
        nargs="+",
        required=True,
        help="Local files or directories to ingest.",
    )
    parser.add_argument(
        "--task-type",
        choices=("sft",),
        default="sft",
        help="Structured ingestion currently emits SFT-style canonical drafts.",
    )
    parser.add_argument(
        "--tool-context",
        default="generic",
        help="Originating tool context, for example codex, claude, or antigravity.",
    )
    parser.add_argument(
        "--user-query",
        help="Optional run description. Defaults to the joined input paths.",
    )
    parser.add_argument(
        "--run-id",
        help="Optional run identifier. Defaults to ingest_<uuid>.",
    )
    parser.add_argument(
        "--output-dir",
        help="Optional output directory for parsed artifacts and drafts. Defaults to workspace/ingest_runs/<run_id>.",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Optional path to the SQLite database. Defaults to workspace/run_state.sqlite.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=500,
        help="Maximum supported files to ingest. Default: 500.",
    )
    parser.add_argument(
        "--bundle-max-chars",
        type=int,
        default=12000,
        help="Maximum characters for generated source bundles. Default: 12000.",
    )
    parser.add_argument(
        "--drafts-only",
        action="store_true",
        help="Write artifacts and drafts but skip importing drafts into SQLite.",
    )
    parser.add_argument("--report", help="Optional path to write the JSON summary report.")
    return parser.parse_args()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _language_display_name(language: str) -> str:
    mapping = {
        "c": "C",
        "cpp": "C++",
        "c_cpp": "C++",
        "assembly": "assembly",
        "python": "Python",
        "powershell": "PowerShell",
        "bash": "Bash",
        "html": "HTML",
        "json": "JSON",
        "yaml": "YAML",
        "sql": "SQL",
    }
    return mapping.get(language, language or "code")


def _is_code_snippet_language(language: str) -> bool:
    return language in {
        "c", "cpp", "c_cpp", "assembly", "python", "powershell", "bash",
        "html", "json", "yaml", "sql", "javascript", "typescript",
    }


def _extract_code_subject(snippet: str, language: str) -> str:
    language_label = _language_display_name(language)
    function_match = re.search(
        r"^\s*(?:[A-Za-z_][\w\s\*\:&<>\[\]]*\s+)?([A-Za-z_~]\w*)\s*\([^;]*\)\s*\{",
        snippet,
        re.MULTILINE,
    )
    if function_match and function_match.group(1).lower() not in {"if", "for", "while", "switch", "return"}:
        return f"{language_label} function `{function_match.group(1)}`"

    procedure_match = re.search(r"^\s*([A-Za-z_@?][\w@$?]*)\s+PROC\b", snippet, re.IGNORECASE | re.MULTILINE)
    if procedure_match:
        return f"{language_label} procedure `{procedure_match.group(1)}`"

    struct_match = re.search(r"^\s*typedef\s+struct\s+([A-Za-z_]\w+)?", snippet, re.IGNORECASE | re.MULTILINE)
    if struct_match:
        struct_name = struct_match.group(1)
        if struct_name:
            return f"{language_label} struct definition `{struct_name}`"
        return f"{language_label} struct definition"

    class_match = re.search(r"^\s*(?:class|struct|enum(?:\s+class)?)\s+([A-Za-z_]\w*)", snippet, re.MULTILINE)
    if class_match:
        return f"{language_label} type definition `{class_match.group(1)}`"

    api_call_match = re.search(r"^\s*[A-Za-z_]\w*\s*=\s*[A-Za-z_]\w+\(", snippet, re.MULTILINE)
    if api_call_match:
        return f"{language_label} API call snippet"

    return f"{language_label} code snippet"


def _is_article_code_bundle(bundle: dict[str, Any]) -> bool:
    metadata = dict(bundle.get("metadata") or {})
    if str(bundle.get("kind") or "") != "article_snippet_context":
        return False
    snippet_language = str(metadata.get("snippet_language") or bundle.get("language") or "")
    snippet_text = str(metadata.get("snippet_text") or "")
    return bool(snippet_text.strip()) and _is_code_snippet_language(snippet_language)


def _article_code_instruction(bundle: dict[str, Any]) -> str:
    metadata = dict(bundle.get("metadata") or {})
    snippet_text = str(metadata.get("snippet_text") or "")
    heading = str(metadata.get("heading") or metadata.get("document_title") or bundle.get("title") or "").strip()
    snippet_language = str(metadata.get("snippet_language") or bundle.get("language") or "")
    subject = _extract_code_subject(snippet_text, snippet_language)
    if heading:
        return (
            f"Write the {subject} from the '{heading}' section. "
            "Use the provided article context to match the same behavior, API usage, and structure."
        )
    return (
        f"Write the {subject} shown in the reference. "
        "Use the provided article context to match the same behavior, API usage, and structure."
    )


def _article_code_context(bundle: dict[str, Any]) -> str:
    metadata = dict(bundle.get("metadata") or {})
    document_title = str(metadata.get("document_title") or bundle.get("title") or "")
    heading = str(metadata.get("heading") or "")
    declared_language = str(metadata.get("declared_language") or "")
    snippet_language = str(metadata.get("snippet_language") or bundle.get("language") or "")
    before_context = [_normalize_spaces(str(item)) for item in metadata.get("before_context") or [] if str(item).strip()]
    after_context = [_normalize_spaces(str(item)) for item in metadata.get("after_context") or [] if str(item).strip()]

    sections = []
    if document_title:
        sections.append(f"Document Title: {document_title}")
    if heading:
        sections.append(f"Section Heading: {heading}")
    if declared_language and declared_language != snippet_language:
        sections.append(f"Original Fence Language: {declared_language}")
    if before_context:
        sections.append("Reference Context Before:\n" + "\n".join(before_context))
    if after_context:
        sections.append("Reference Context After:\n" + "\n".join(after_context))
    return "\n\n".join(section for section in sections if section.strip())


def _bundle_instruction(bundle: dict[str, Any]) -> str:
    kind = str(bundle.get("kind") or "")
    metadata = dict(bundle.get("metadata") or {})
    if _is_article_code_bundle(bundle):
        return _article_code_instruction(bundle)
    if kind == "c_family_context":
        primary_file = metadata.get("primary_file") or bundle.get("source_path")
        return (
            f"Explain the C/C++ source bundle centered on {primary_file}. "
            "Describe file relationships, major symbols, project context, and include behavior using only the provided source context."
        )
    if kind == "article_snippet_context":
        heading = metadata.get("heading") or metadata.get("document_title") or bundle.get("title")
        return (
            f"Explain the code snippet documented under '{heading}'. "
            "Use the surrounding article context to describe what the snippet does and how the source text frames it."
        )
    return (
        f"Summarize the structured source material for {bundle.get('title') or bundle.get('source_path')}. "
        "Stay grounded in the provided context."
    )


def _bundle_context(bundle: dict[str, Any]) -> str:
    if _is_article_code_bundle(bundle):
        return _article_code_context(bundle)
    return str(bundle.get("content") or "")


def _bundle_response(bundle: dict[str, Any]) -> str:
    metadata = dict(bundle.get("metadata") or {})
    kind = str(bundle.get("kind") or "")
    if _is_article_code_bundle(bundle):
        return str(metadata.get("snippet_text") or "")
    lines: list[str] = []
    if kind == "c_family_context":
        lines.append(f"Primary file: {metadata.get('primary_file') or bundle.get('source_path')}")
        project_names = metadata.get("project_names") or []
        if project_names:
            lines.append("Projects: " + ", ".join(project_names))
        file_paths = metadata.get("file_paths") or bundle.get("related_paths") or []
        if file_paths:
            lines.append("Related files: " + ", ".join(file_paths))
        symbol_names = metadata.get("symbol_names") or []
        if symbol_names:
            lines.append("Detected symbols: " + ", ".join(symbol_names[:20]))
        include_lines = metadata.get("include_lines") or []
        if include_lines:
            lines.append("Include relationships:\n" + "\n".join(include_lines[:12]))
        filters = metadata.get("filters") or {}
        visible_filters = [f"{path} -> {value}" for path, value in filters.items() if value]
        if visible_filters:
            lines.append("Visual Studio filters:\n" + "\n".join(visible_filters[:12]))
        lines.append("Grounding: use the attached source bundle excerpts for exact implementation details.")
        return "\n\n".join(lines)

    if kind == "article_snippet_context":
        document_title = metadata.get("document_title") or bundle.get("title")
        heading = metadata.get("heading") or ""
        snippet_language = metadata.get("snippet_language") or bundle.get("language") or "unknown"
        lines.append(f"Document: {document_title}")
        if heading:
            lines.append(f"Section: {heading}")
        lines.append(f"Snippet language: {snippet_language}")
        before = metadata.get("before_context") or []
        after = metadata.get("after_context") or []
        if before:
            lines.append("Preceding context: " + " ".join(before))
        if after:
            lines.append("Following context: " + " ".join(after))
        lines.append("Grounding: use the attached snippet and surrounding prose as the source of truth.")
        return "\n\n".join(lines)

    lines.append(f"Source title: {bundle.get('title') or bundle.get('source_path')}")
    lines.append("Grounding: use the provided structured source context.")
    return "\n\n".join(lines)


def build_drafts_from_bundles(
    bundles: list[dict[str, Any]],
    *,
    task_type: str,
) -> list[dict[str, Any]]:
    drafts: list[dict[str, Any]] = []
    for bundle in bundles:
        instruction = _bundle_instruction(bundle)
        context = _bundle_context(bundle)
        response_text = _bundle_response(bundle)
        bundle_metadata = dict(bundle.get("metadata") or {})
        is_article_code = _is_article_code_bundle(bundle)
        tags = ["structured_ingest"]
        if is_article_code:
            tags.append("code_example")
        draft = {
            "id": build_record_id(
                {
                    "bundle_id": bundle["id"],
                    "task_type": task_type,
                    "instruction": instruction,
                    "response": response_text,
                }
            ),
            "task_type": task_type,
            "instruction": instruction,
            "context": context,
            "response": {
                "format": "single",
                "text": response_text,
            },
            "metadata": {
                "difficulty": "medium",
                "persona": "implementation_assistant" if is_article_code else "source_analyst",
                "source_type": "structured_source",
                "source_origin": "real_world",
                "bundle_id": bundle["id"],
                "bundle_kind": bundle.get("kind"),
                "bundle_title": bundle.get("title"),
                "task_family": "code_generation" if is_article_code else "source_grounded_explanation",
                "snippet_language": bundle_metadata.get("snippet_language"),
                "declared_language": bundle_metadata.get("declared_language"),
                "document_title": bundle_metadata.get("document_title"),
                "section_title": bundle_metadata.get("heading"),
                "related_paths": bundle.get("related_paths") or [],
                "tags": tags,
            },
            "pipeline_status": "pending",
            "status": "raw_generated",
            "source_type": "structured_source",
            "source_uri": bundle["source_path"],
        }
        drafts.append(draft)
    return drafts


def validate_artifacts(collections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for item in collections:
        errors = validate_source_artifact(item)
        if errors:
            failures.append({"id": item.get("id"), "errors": errors})
    return failures


def import_drafts(
    drafts: list[dict[str, Any]],
    *,
    run_id: str,
    user_query: str,
    tool_context: str,
    db_path: str | Path | None,
) -> tuple[dict[str, Any], Path]:
    resolved_db = initialize_database(db_path) if db_path else initialize_database()
    summary = {
        "imported": 0,
        "failed": 0,
        "errors": [],
        "record_ids": [],
    }
    connection = get_connection(resolved_db)
    try:
        upsert_run(
            connection,
            run_id=run_id,
            user_query=user_query,
            mode="ingest",
            source_type="structured_source",
            tool_context=tool_context,
            status="in_progress",
        )
        for draft in drafts:
            normalized = normalize_record(
                draft,
                default_task_type="sft",
                source_type="structured_source",
            )
            normalized["run_id"] = run_id
            normalized["status"] = "raw_generated"
            normalized["source_type"] = "structured_source"
            errors = validate_record(normalized)
            if errors:
                summary["failed"] += 1
                summary["errors"].append({"id": normalized.get("id"), "errors": errors})
                continue
            upsert_record(connection, normalized)
            summary["imported"] += 1
            summary["record_ids"].append(normalized["id"])
        upsert_run(
            connection,
            run_id=run_id,
            user_query=user_query,
            mode="ingest",
            source_type="structured_source",
            tool_context=tool_context,
            status="completed",
        )
        connection.commit()
    finally:
        connection.close()
    return summary, resolved_db


def main() -> None:
    args = parse_args()
    run_id = args.run_id or f"ingest_{uuid.uuid4().hex[:12]}"
    user_query = args.user_query or f"dataset ingest {' '.join(args.paths)}"
    output_dir = ensure_ingest_output_dir(run_id, args.output_dir)

    discovered = discover_source_files(args.paths, max_files=args.max_files)
    parsed = parse_discovered_files(
        discovered["files"],
        bundle_max_chars=args.bundle_max_chars,
    )
    drafts = build_drafts_from_bundles(parsed["bundles"], task_type=args.task_type)

    manifest = {
        "run_id": run_id,
        "created_at": _utc_now(),
        "tool_context": args.tool_context,
        "task_type": args.task_type,
        "source_type": "structured_source",
        "input_paths": args.paths,
        "roots": discovered["roots"],
        "counts": {
            "files": len(discovered["files"]),
            "units": len(parsed["units"]),
            "relations": len(parsed["relations"]),
            "bundles": len(parsed["bundles"]),
            "drafts": len(drafts),
        },
    }

    artifact_failures = validate_artifacts(
        discovered["files"] + parsed["units"] + parsed["relations"] + parsed["bundles"]
    )

    import_summary = {
        "imported": 0,
        "failed": 0,
        "errors": [],
        "record_ids": [],
    }
    db_path = None
    if not args.drafts_only:
        import_summary, db_path = import_drafts(
            drafts,
            run_id=run_id,
            user_query=user_query,
            tool_context=args.tool_context,
            db_path=args.db,
        )

    report = {
        "run_id": run_id,
        "output_dir": str(output_dir),
        "db_path": str(db_path) if db_path else None,
        "source_type": "structured_source",
        "tool_context": args.tool_context,
        "counts": manifest["counts"],
        "discovery": {
            "roots": discovered["roots"],
            "skipped": discovered["skipped"],
        },
        "warnings": parsed["warnings"],
        "artifact_validation_errors": artifact_failures,
        "import": import_summary,
    }

    output_paths = write_ingest_outputs(
        output_dir,
        manifest=manifest,
        files=discovered["files"],
        units=parsed["units"],
        relations=parsed["relations"],
        bundles=parsed["bundles"],
        drafts=drafts,
        report=report,
    )

    if args.report:
        write_json(args.report, report)

    print(
        json.dumps(
            {
                "run_id": run_id,
                "output_dir": str(output_dir),
                "db_path": str(db_path) if db_path else None,
                "artifacts": {key: str(value) for key, value in output_paths.items()},
                "counts": manifest["counts"],
                "warnings": parsed["warnings"],
                "artifact_validation_errors": artifact_failures,
                "import": import_summary,
            },
            indent=2,
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
