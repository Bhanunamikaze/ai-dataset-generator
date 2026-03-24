from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable


def ensure_parent_dir(path: Path | str) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def detect_format(path: Path | str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".jsonl":
        return "jsonl"
    if suffix == ".json":
        return "json"
    if suffix == ".csv":
        return "csv"
    raise ValueError(f"Unsupported file format for {path}")


def load_records(path: Path | str) -> list[dict[str, Any]]:
    file_path = Path(path)
    data_format = detect_format(file_path)
    if data_format == "jsonl":
        return load_jsonl(file_path)
    if data_format == "json":
        return load_json(file_path)
    if data_format == "csv":
        return load_csv(file_path)
    raise ValueError(f"Unsupported record format: {data_format}")


def load_json(path: Path | str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return [dict(item) for item in payload]
    if isinstance(payload, dict):
        return [dict(payload)]
    raise ValueError("JSON input must be an object or an array of objects")


def load_jsonl(path: Path | str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError(f"JSONL line {line_number} must be an object")
            records.append(dict(item))
    return records


def load_csv(path: Path | str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_json(path: Path | str, payload: Any) -> Path:
    destination = ensure_parent_dir(path)
    with open(destination, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    return destination


def write_jsonl(path: Path | str, records: Iterable[dict[str, Any]]) -> Path:
    destination = ensure_parent_dir(path)
    with open(destination, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True))
            handle.write("\n")
    return destination


def write_csv(
    path: Path | str,
    rows: Iterable[dict[str, Any]],
    *,
    fieldnames: list[str],
) -> Path:
    destination = ensure_parent_dir(path)
    with open(destination, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return destination
