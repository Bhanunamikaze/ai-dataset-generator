from __future__ import annotations

import importlib
import re
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from typing import Any

from .base import build_bundle, build_relation, build_unit

_INCLUDE_PATTERN = re.compile(r'^\s*#\s*include\s*([<"])([^">]+)[">]', re.MULTILINE)
_NAMESPACE_PATTERN = re.compile(r'^\s*namespace\s+([A-Za-z_]\w*)', re.MULTILINE)
_TYPE_PATTERN = re.compile(r'^\s*(class|struct|enum(?:\s+class)?)\s+([A-Za-z_]\w*)', re.MULTILINE)
_MACRO_PATTERN = re.compile(r'^\s*#\s*define\s+([A-Za-z_]\w*)', re.MULTILINE)
_TYPEDEF_PATTERN = re.compile(r'^\s*typedef\b.*?\b([A-Za-z_]\w*)\s*;', re.MULTILINE)
_FUNCTION_PATTERN = re.compile(
    r'^\s*(?!if\b|for\b|while\b|switch\b|catch\b|return\b)'
    r'(?:template\s*<[^>]+>\s*)?'
    r'(?:inline\s+|static\s+|constexpr\s+|virtual\s+|extern\s+|friend\s+|consteval\s+|constinit\s+)*'
    r'[\w:\<\>\~\*&\s]+\s+([A-Za-z_~]\w*(?:::\w+)*)\s*\([^;{}]*\)\s*(?:const\s*)?(?:;|\{)',
    re.MULTILINE,
)
_ASM_PROC_PATTERN = re.compile(r'^\s*([A-Za-z_@?][\w@$?]*)\s+PROC\b', re.MULTILINE | re.IGNORECASE)
_ASM_LABEL_PATTERN = re.compile(r'^\s*([A-Za-z_@?][\w@$?]*)\s*:\s*(?:;.*)?$', re.MULTILINE)
_ASM_INCLUDE_PATTERN = re.compile(r'^\s*(?:INCLUDE|INCLUDELIB)\s+([^\s;]+)', re.MULTILINE | re.IGNORECASE)
_PROJECT_MEMBER_TAGS = {
    "ClCompile", "ClInclude", "None", "Text", "MASM", "CustomBuild", "CustomBuildStep"
}
_CPP_EXTENSIONS = {".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx", ".inl"}
_CPP_HEADER_HINTS = (
    "namespace ",
    "class ",
    "template<",
    "template <",
    "typename ",
    "public:",
    "private:",
    "protected:",
    "constexpr ",
    "consteval ",
    "::",
)
_TYPE_SPECIFIER_KINDS = {
    "class_specifier": "class",
    "struct_specifier": "struct",
    "union_specifier": "union",
    "enum_specifier": "enum",
}


def _strip_namespace(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _truncate(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 17)].rstrip() + "\n...[truncated]"


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _find_block_end(text: str, start_offset: int) -> int:
    brace_depth = 0
    seen_open = False
    for index in range(start_offset, len(text)):
        char = text[index]
        if char == "{":
            brace_depth += 1
            seen_open = True
        elif char == "}":
            if seen_open:
                brace_depth -= 1
                if brace_depth <= 0:
                    return index
    return min(len(text), start_offset + 1200)


@lru_cache(maxsize=1)
def _load_tree_sitter_language_pack() -> Any | None:
    try:
        return importlib.import_module("tree_sitter_language_pack")
    except Exception:
        return None


@lru_cache(maxsize=4)
def _get_tree_sitter_parser(language_name: str) -> Any | None:
    module = _load_tree_sitter_language_pack()
    if module is None:
        return None
    try:
        return module.get_parser(language_name)
    except Exception:
        return None


def _node_text(content_bytes: bytes, node: Any | None) -> str:
    if node is None:
        return ""
    return content_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")


def _iter_nodes(node: Any) -> Any:
    yield node
    for child in node.children:
        yield from _iter_nodes(child)


def _unwrap_named_declarator(node: Any | None) -> Any | None:
    current = node
    while current is not None:
        next_node = current.child_by_field_name("declarator")
        if next_node is None:
            return current
        current = next_node
    return None


def _find_descendant_by_type(node: Any | None, node_types: set[str]) -> Any | None:
    if node is None:
        return None
    if node.type in node_types:
        return node
    for child in node.children:
        found = _find_descendant_by_type(child, node_types)
        if found is not None:
            return found
    return None


def _infer_tree_sitter_language(file_record: dict[str, Any]) -> str | None:
    kind = str(file_record.get("kind") or "")
    if kind in {"assembly_source", "assembly_include"}:
        return "asm"

    extension = str(file_record.get("metadata", {}).get("extension") or Path(str(file_record["source_path"])).suffix.lower())
    if extension == ".c":
        return "c"
    if extension in _CPP_EXTENSIONS:
        return "cpp"
    if extension != ".h":
        return "c"

    content = str(file_record.get("content") or "")
    if any(marker in content for marker in _CPP_HEADER_HINTS):
        return "cpp"
    return "c"


def _qualify_symbol_name(node: Any, symbol_name: str, content_bytes: bytes) -> str:
    parts = [symbol_name]
    current = getattr(node, "parent", None)
    while current is not None:
        if current.type == "namespace_definition":
            namespace_name = _node_text(content_bytes, current.child_by_field_name("name")).strip()
            if namespace_name:
                parts.append(namespace_name)
        elif current.type in _TYPE_SPECIFIER_KINDS:
            type_name = _node_text(content_bytes, current.child_by_field_name("name")).strip()
            if type_name:
                parts.append(type_name)
        current = getattr(current, "parent", None)
    return "::".join(reversed(parts))


def _build_symbol_unit(
    *,
    family: str,
    symbol_kind: str,
    source_path: str,
    language: str,
    content: str,
    symbol_name: str,
    start: int,
    end: int,
    parser_mode: str,
    file_id: str,
) -> dict[str, Any]:
    return build_unit(
        kind=f"{family}_{symbol_kind}",
        source_path=source_path,
        title=symbol_name,
        language=language,
        content=_truncate(content[start:end].strip(), 1200),
        metadata={
            "symbol_kind": symbol_kind,
            "symbol_name": symbol_name,
            "line_start": _line_number(content, start),
            "line_end": _line_number(content, end),
            "parser_mode": parser_mode,
            "file_id": file_id,
        },
        stable_payload={
            "source_path": source_path,
            "kind": symbol_kind,
            "name": symbol_name,
            "start": start,
            "end": end,
        },
    )


def _extract_symbols_heuristic(file_record: dict[str, Any]) -> list[dict[str, Any]]:
    content = str(file_record.get("content") or "")
    source_path = str(file_record["source_path"])
    language = str(file_record.get("language") or "c_cpp")
    symbols: list[dict[str, Any]] = []

    def add_symbol(kind: str, name: str, start: int, end: int) -> None:
        symbols.append(
            _build_symbol_unit(
                family="c_family",
                symbol_kind=kind,
                source_path=source_path,
                language=language,
                content=content,
                symbol_name=name,
                start=start,
                end=end,
                parser_mode="heuristic",
                file_id=str(file_record["id"]),
            )
        )

    for match in _NAMESPACE_PATTERN.finditer(content):
        add_symbol("namespace", match.group(1), match.start(), min(len(content), match.end() + 200))
    for match in _TYPE_PATTERN.finditer(content):
        add_symbol(match.group(1).replace(" ", "_"), match.group(2), match.start(), _find_block_end(content, match.start()))
    for match in _MACRO_PATTERN.finditer(content):
        add_symbol("macro", match.group(1), match.start(), min(len(content), match.end() + 160))
    for match in _TYPEDEF_PATTERN.finditer(content):
        add_symbol("typedef", match.group(1), match.start(), min(len(content), match.end() + 160))
    for match in _FUNCTION_PATTERN.finditer(content):
        add_symbol("function", match.group(1), match.start(), _find_block_end(content, match.start()))
    return symbols


def _extract_tree_sitter_symbols(file_record: dict[str, Any]) -> tuple[list[dict[str, Any]] | None, list[str]]:
    language_name = _infer_tree_sitter_language(file_record)
    if language_name is None:
        return None, []

    parser = _get_tree_sitter_parser(language_name)
    if parser is None:
        return None, []

    content = str(file_record.get("content") or "")
    source_path = str(file_record["source_path"])
    content_bytes = content.encode("utf-8")

    try:
        tree = parser.parse(content_bytes)
    except Exception as exc:
        return None, [f"Tree-sitter parsing failed for {source_path}: {exc}"]

    if language_name == "asm":
        return _extract_tree_sitter_assembly_symbols(file_record, tree.root_node, content, content_bytes), []
    return _extract_tree_sitter_c_cpp_symbols(
        file_record,
        language_name=language_name,
        root_node=tree.root_node,
        content=content,
        content_bytes=content_bytes,
    ), []


def _extract_tree_sitter_c_cpp_symbols(
    file_record: dict[str, Any],
    *,
    language_name: str,
    root_node: Any,
    content: str,
    content_bytes: bytes,
) -> list[dict[str, Any]]:
    source_path = str(file_record["source_path"])
    symbols: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, int]] = set()

    def add_symbol(kind: str, name: str, node: Any, start: int | None = None, end: int | None = None) -> None:
        raw_name = name.strip()
        if not raw_name:
            return
        qualified_name = _qualify_symbol_name(node, raw_name, content_bytes)
        start_offset = node.start_byte if start is None else start
        end_offset = node.end_byte if end is None else end
        symbol_key = (kind, qualified_name, start_offset, end_offset)
        if symbol_key in seen:
            return
        seen.add(symbol_key)
        symbols.append(
            _build_symbol_unit(
                family="c_family",
                symbol_kind=kind,
                source_path=source_path,
                language="assembly" if language_name == "asm" else "c_cpp",
                content=content,
                symbol_name=qualified_name,
                start=start_offset,
                end=end_offset,
                parser_mode="tree_sitter",
                file_id=str(file_record["id"]),
            )
        )

    for node in _iter_nodes(root_node):
        if node.type == "namespace_definition":
            add_symbol("namespace", _node_text(content_bytes, node.child_by_field_name("name")), node)
            continue
        if node.type in _TYPE_SPECIFIER_KINDS:
            add_symbol(_TYPE_SPECIFIER_KINDS[node.type], _node_text(content_bytes, node.child_by_field_name("name")), node)
            continue
        if node.type in {"preproc_def", "preproc_function_def"}:
            add_symbol("macro", _node_text(content_bytes, node.child_by_field_name("name")), node)
            continue
        if node.type in {"type_definition", "alias_declaration"}:
            declarator_node = _unwrap_named_declarator(
                node.child_by_field_name("declarator") or node.child_by_field_name("name")
            )
            add_symbol("typedef", _node_text(content_bytes, declarator_node), node)
            continue
        if node.type == "function_definition":
            declarator_node = _unwrap_named_declarator(node.child_by_field_name("declarator"))
            add_symbol("function", _node_text(content_bytes, declarator_node), node)
            continue
        if node.type == "declaration":
            function_declarator = _find_descendant_by_type(node, {"function_declarator"})
            declarator_node = _unwrap_named_declarator(function_declarator)
            if declarator_node is not None:
                add_symbol("function", _node_text(content_bytes, declarator_node), node)
    return symbols


def _extract_assembly_symbols_heuristic(file_record: dict[str, Any]) -> list[dict[str, Any]]:
    content = str(file_record.get("content") or "")
    source_path = str(file_record["source_path"])
    symbols: list[dict[str, Any]] = []

    def add_symbol(kind: str, name: str, start: int, end: int) -> None:
        symbols.append(
            _build_symbol_unit(
                family="assembly",
                symbol_kind=kind,
                source_path=source_path,
                language="assembly",
                content=content,
                symbol_name=name,
                start=start,
                end=end,
                parser_mode="heuristic",
                file_id=str(file_record["id"]),
            )
        )

    for match in _ASM_PROC_PATTERN.finditer(content):
        proc_name = match.group(1)
        end_match = re.search(rf'^\s*{re.escape(proc_name)}\s+ENDP\b', content[match.end():], re.MULTILINE | re.IGNORECASE)
        if end_match:
            end_offset = match.end() + end_match.end()
        else:
            end_offset = min(len(content), match.end() + 600)
        add_symbol("proc", proc_name, match.start(), end_offset)

    seen_labels: set[str] = {str(item["metadata"].get("symbol_name", "")).lower() for item in symbols}
    for match in _ASM_LABEL_PATTERN.finditer(content):
        label = match.group(1)
        if label.lower() in seen_labels:
            continue
        add_symbol("label", label, match.start(), min(len(content), match.end() + 200))
    return symbols


def _extract_tree_sitter_assembly_symbols(
    file_record: dict[str, Any],
    root_node: Any,
    content: str,
    content_bytes: bytes,
) -> list[dict[str, Any]]:
    source_path = str(file_record["source_path"])
    symbols: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    open_procs: dict[str, tuple[str, int]] = {}

    def add_symbol(kind: str, name: str, start: int, end: int) -> None:
        if not name.strip():
            return
        symbols.append(
            _build_symbol_unit(
                family="assembly",
                symbol_kind=kind,
                source_path=source_path,
                language="assembly",
                content=content,
                symbol_name=name.strip(),
                start=start,
                end=end,
                parser_mode="tree_sitter",
                file_id=str(file_record["id"]),
            )
        )

    for node in root_node.children:
        if not getattr(node, "is_named", False):
            continue
        if node.type == "instruction":
            tokens = [
                _node_text(content_bytes, child).strip()
                for child in node.children
                if getattr(child, "is_named", False) and _node_text(content_bytes, child).strip()
            ]
            if len(tokens) >= 2 and tokens[1].upper() == "PROC":
                open_procs[tokens[0].lower()] = (tokens[0], node.start_byte)
            elif len(tokens) >= 2 and tokens[1].upper() == "ENDP":
                proc_name = tokens[0]
                _, start_offset = open_procs.pop(proc_name.lower(), (proc_name, node.start_byte))
                add_symbol("proc", proc_name, start_offset, node.end_byte)
                seen_labels.add(proc_name.lower())
            continue
        if node.type == "label":
            label_name = _node_text(content_bytes, node.child_by_field_name("name"))
            if not label_name:
                named_children = [child for child in node.children if getattr(child, "is_named", False)]
                label_name = _node_text(content_bytes, named_children[0] if named_children else None)
            if label_name and label_name.lower() not in seen_labels:
                add_symbol("label", label_name, node.start_byte, node.end_byte)
                seen_labels.add(label_name.lower())

    for _, (proc_name, start_offset) in open_procs.items():
        add_symbol("proc", proc_name, start_offset, min(len(content), start_offset + 600))
    return symbols


def _extract_symbols(file_record: dict[str, Any]) -> tuple[list[dict[str, Any]], str, list[str]]:
    tree_sitter_symbols, warnings = _extract_tree_sitter_symbols(file_record)
    if tree_sitter_symbols is not None:
        return tree_sitter_symbols, "tree_sitter", warnings
    if str(file_record.get("kind")) in {"assembly_source", "assembly_include"}:
        return _extract_assembly_symbols_heuristic(file_record), "heuristic", warnings
    return _extract_symbols_heuristic(file_record), "heuristic", warnings


def _extract_includes(file_record: dict[str, Any]) -> list[dict[str, Any]]:
    content = str(file_record.get("content") or "")
    includes: list[dict[str, Any]] = []
    is_assembly = str(file_record.get("kind")) in {"assembly_source", "assembly_include"}
    pattern = _ASM_INCLUDE_PATTERN if is_assembly else _INCLUDE_PATTERN
    for match in pattern.finditer(content):
        include_name = match.group(1 if is_assembly else 2).strip()
        includes.append(
            {
                "include": include_name,
                "delimiter": "" if is_assembly else match.group(1),
                "line": _line_number(content, match.start()),
                "syntax": "assembly" if is_assembly else "preprocessor",
            }
        )
    return includes


def _parse_solution_file(file_record: dict[str, Any]) -> list[dict[str, Any]]:
    content = str(file_record.get("content") or "")
    solution_path = Path(file_record["source_path"])
    projects: list[dict[str, Any]] = []
    for match in re.finditer(
        r'Project\("(?P<project_type>[^"]+)"\)\s*=\s*"(?P<name>[^"]+)",\s*"(?P<path>[^"]+)",\s*"(?P<guid>[^"]+)"',
        content,
    ):
        project_path = (solution_path.parent / match.group("path")).resolve()
        projects.append(
            {
                "solution_path": str(solution_path),
                "project_name": match.group("name"),
                "project_path": str(project_path),
                "project_guid": match.group("guid"),
            }
        )
    return projects


def _parse_xml_file(path: str) -> ET.Element | None:
    try:
        return ET.fromstring(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def _parse_vcxproj_files(file_record: dict[str, Any]) -> dict[str, Any]:
    project_path = Path(file_record["source_path"])
    root = _parse_xml_file(str(project_path))
    project_name = project_path.stem
    includes: list[str] = []
    if root is None:
        return {
            "project_name": project_name,
            "project_path": str(project_path),
            "members": includes,
        }

    for node in root.iter():
        tag = _strip_namespace(node.tag)
        if tag not in _PROJECT_MEMBER_TAGS:
            continue
        include = node.attrib.get("Include")
        if not include:
            continue
        includes.append(str((project_path.parent / include).resolve()))

    return {
        "project_name": project_name,
        "project_path": str(project_path),
        "members": includes,
    }


def _parse_vcxproj_filters(file_record: dict[str, Any]) -> dict[str, str]:
    filters_path = Path(file_record["source_path"])
    root = _parse_xml_file(str(filters_path))
    if root is None:
        return {}
    filters: dict[str, str] = {}
    for node in root.iter():
        tag = _strip_namespace(node.tag)
        if tag not in _PROJECT_MEMBER_TAGS:
            continue
        include = node.attrib.get("Include")
        if not include:
            continue
        filter_text = ""
        for child in node:
            if _strip_namespace(child.tag) == "Filter" and child.text:
                filter_text = child.text.strip()
                break
        filters[str((filters_path.parent / include).resolve())] = filter_text
    return filters


def _resolve_include(
    include_name: str,
    source_path: str,
    files_by_path: dict[str, dict[str, Any]],
    files_by_name: dict[str, list[dict[str, Any]]],
) -> str | None:
    source_dir = Path(source_path).parent
    direct_candidate = str((source_dir / include_name).resolve())
    if direct_candidate in files_by_path:
        return direct_candidate

    base_name = Path(include_name).name.lower()
    candidates = files_by_name.get(base_name, [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return str(candidates[0]["source_path"])

    same_dir = [
        str(item["source_path"]) for item in candidates
        if Path(item["source_path"]).parent == source_dir
    ]
    if same_dir:
        return same_dir[0]
    return str(candidates[0]["source_path"])


def _build_bundle_content(
    *,
    primary_file: dict[str, Any],
    related_files: list[dict[str, Any]],
    project_names: list[str],
    symbol_names: list[str],
    include_lines: list[str],
    bundle_max_chars: int,
) -> str:
    sections = [
        "Bundle Type: C/C++/Assembly source context",
        f"Primary File: {primary_file['source_path']}",
    ]
    if project_names:
        sections.append("Projects: " + ", ".join(project_names))
    sections.append("Related Files: " + ", ".join(str(item["source_path"]) for item in related_files))
    if symbol_names:
        sections.append("Detected Symbols: " + ", ".join(symbol_names[:20]))
    if include_lines:
        sections.append("Include Map:\n" + "\n".join(include_lines[:20]))

    remaining = max(bundle_max_chars - len("\n\n".join(sections)) - 64, 1200)
    excerpt_budget = max(600, remaining // max(1, len(related_files)))
    for item in related_files:
        excerpt = _truncate(str(item.get("content") or ""), excerpt_budget)
        sections.append(f"File: {item['source_path']}\n{excerpt}")

    content = "\n\n".join(section for section in sections if section.strip())
    return _truncate(content, bundle_max_chars)


def parse_c_family_corpus(
    files: list[dict[str, Any]],
    *,
    bundle_max_chars: int = 12000,
) -> dict[str, Any]:
    units: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    bundles: list[dict[str, Any]] = []
    warnings: list[str] = []

    files_by_path = {str(item["source_path"]): item for item in files}
    files_by_name: dict[str, list[dict[str, Any]]] = {}
    for item in files:
        files_by_name.setdefault(Path(str(item["source_path"])).name.lower(), []).append(item)

    solution_entries: list[dict[str, Any]] = []
    project_memberships: dict[str, list[dict[str, Any]]] = {}
    project_filters: dict[str, dict[str, str]] = {}

    for item in files:
        kind = str(item["kind"])
        if kind == "visual_studio_solution":
            parsed_projects = _parse_solution_file(item)
            solution_entries.extend(parsed_projects)
            for project in parsed_projects:
                relations.append(
                    build_relation(
                        kind="solution_references_project",
                        source_path=str(item["source_path"]),
                        related_paths=[project["project_path"]],
                        metadata=project,
                        stable_payload=project,
                    )
                )
        elif kind == "visual_studio_project":
            project = _parse_vcxproj_files(item)
            for member_path in project["members"]:
                project_memberships.setdefault(member_path, []).append(project)
                relations.append(
                    build_relation(
                        kind="project_contains_file",
                        source_path=project["project_path"],
                        related_paths=[member_path],
                        metadata={
                            "project_name": project["project_name"],
                            "project_path": project["project_path"],
                            "member_path": member_path,
                        },
                        stable_payload={
                            "project_path": project["project_path"],
                            "member_path": member_path,
                        },
                    )
                )
        elif kind == "visual_studio_filters":
            project_filters[str(Path(item["source_path"]).with_suffix(""))] = _parse_vcxproj_filters(item)

    c_code_files = [
        item for item in files
        if str(item["kind"]) in {"c_source", "c_header", "assembly_source", "assembly_include"}
    ]

    includes_by_path: dict[str, list[dict[str, Any]]] = {}
    symbols_by_path: dict[str, list[dict[str, Any]]] = {}
    parser_modes_by_path: dict[str, str] = {}
    for item in c_code_files:
        symbols, parser_mode, parser_warnings = _extract_symbols(item)
        source_path = str(item["source_path"])
        symbols_by_path[source_path] = symbols
        parser_modes_by_path[source_path] = parser_mode
        units.extend(symbols)
        warnings.extend(parser_warnings)
        includes = _extract_includes(item)
        includes_by_path[source_path] = includes

        for include in includes:
            resolved_path = _resolve_include(
                include["include"],
                source_path,
                files_by_path,
                files_by_name,
            )
            metadata = {
                "include": include["include"],
                "delimiter": include["delimiter"],
                "line": include["line"],
                "resolved_path": resolved_path,
            }
            relations.append(
                build_relation(
                    kind="includes",
                    source_path=str(item["source_path"]),
                    related_paths=[resolved_path] if resolved_path else [],
                    metadata=metadata,
                    stable_payload={
                        "source_path": str(item["source_path"]),
                        "include": include["include"],
                        "resolved_path": resolved_path,
                    },
                )
            )
            if resolved_path is None:
                warnings.append(f"Unresolved include {include['include']} from {item['source_path']}")

    groups_by_stem: dict[str, list[dict[str, Any]]] = {}
    for item in c_code_files:
        key = Path(str(item["source_path"])).stem.lower()
        groups_by_stem.setdefault(key, []).append(item)

    processed: set[str] = set()
    for group_items in groups_by_stem.values():
        sorted_group = sorted(
            group_items,
            key=lambda item: (
                0 if str(item["kind"]) == "c_source" else
                1 if str(item["kind"]) == "c_header" else
                2 if str(item["kind"]) == "assembly_source" else
                3,
                str(item["source_path"]),
            ),
        )
        primary = sorted_group[0]
        primary_path = str(primary["source_path"])
        if primary_path in processed:
            continue

        related_map = {str(item["source_path"]): item for item in sorted_group}
        for item in sorted_group:
            path = str(item["source_path"])
            for include in includes_by_path.get(path, []):
                resolved_path = _resolve_include(
                    include["include"],
                    path,
                    files_by_path,
                    files_by_name,
                )
                if resolved_path and resolved_path in files_by_path and files_by_path[resolved_path]["kind"] in {"c_source", "c_header", "assembly_source", "assembly_include"}:
                    related_map.setdefault(resolved_path, files_by_path[resolved_path])
            processed.add(path)

        project_paths_for_group = {
            project["project_path"]
            for item in list(related_map.values())
            for project in project_memberships.get(str(item["source_path"]), [])
        }
        if project_paths_for_group:
            for candidate in c_code_files:
                candidate_path = str(candidate["source_path"])
                memberships = project_memberships.get(candidate_path, [])
                if not memberships:
                    continue
                if any(project["project_path"] in project_paths_for_group for project in memberships):
                    related_map.setdefault(candidate_path, candidate)
                    processed.add(candidate_path)

        related_files = list(related_map.values())
        related_files.sort(key=lambda item: str(item["source_path"]))
        for left in related_files:
            for right in related_files:
                if left["id"] >= right["id"]:
                    continue
                relations.append(
                    build_relation(
                        kind="companion_of",
                        source_path=str(left["source_path"]),
                        related_paths=[str(right["source_path"])],
                        metadata={
                            "left_kind": left["kind"],
                            "right_kind": right["kind"],
                        },
                        stable_payload={
                            "left": str(left["source_path"]),
                            "right": str(right["source_path"]),
                        },
                    )
                )

        project_info = {
            str(item["source_path"]): project_memberships.get(str(item["source_path"]), [])
            for item in related_files
        }
        project_names = sorted({
            project["project_name"]
            for projects in project_info.values()
            for project in projects
        })
        symbol_names = []
        for item in related_files:
            for symbol in symbols_by_path.get(str(item["source_path"]), []):
                name = str(symbol["metadata"].get("symbol_name") or "")
                if name:
                    symbol_names.append(name)

        include_lines = []
        for item in related_files:
            for include in includes_by_path.get(str(item["source_path"]), []):
                resolved_path = _resolve_include(
                    include["include"],
                    str(item["source_path"]),
                    files_by_path,
                    files_by_name,
                )
                display = include["include"]
                if resolved_path:
                    display = f"{include['include']} -> {resolved_path}"
                include_lines.append(f"{item['source_path']}:{include['line']} {display}")

        bundle_content = _build_bundle_content(
            primary_file=primary,
            related_files=related_files,
            project_names=project_names,
            symbol_names=symbol_names,
            include_lines=include_lines,
            bundle_max_chars=bundle_max_chars,
        )
        bundle = build_bundle(
            kind="c_family_context",
            source_path=primary_path,
            title=Path(primary_path).name,
            language="assembly" if str(primary.get("kind")) in {"assembly_source", "assembly_include"} else "c_cpp",
            content=bundle_content,
            related_paths=[str(item["source_path"]) for item in related_files],
            metadata={
                "primary_file": primary_path,
                "file_paths": [str(item["source_path"]) for item in related_files],
                "assembly_files": [
                    str(item["source_path"])
                    for item in related_files
                    if str(item["kind"]) in {"assembly_source", "assembly_include"}
                ],
                "project_names": project_names,
                "project_paths": sorted({
                    project["project_path"]
                    for projects in project_info.values()
                    for project in projects
                }),
                "symbol_names": sorted(dict.fromkeys(symbol_names)),
                "include_lines": include_lines[:50],
                "bundle_type": "code",
                "parser_mode": parser_modes_by_path.get(primary_path, "heuristic"),
                "parser_modes": {
                    str(item["source_path"]): parser_modes_by_path.get(str(item["source_path"]), "heuristic")
                    for item in related_files
                },
                "filters": {
                    path: project_filters.get(str(Path(project["project_path"])), {}).get(path, "")
                    for path, projects in project_info.items()
                    for project in projects
                },
            },
            stable_payload={
                "primary_file": primary_path,
                "related_files": [str(item["source_path"]) for item in related_files],
            },
        )
        bundles.append(bundle)

    return {
        "units": units,
        "relations": relations,
        "bundles": bundles,
        "warnings": sorted(dict.fromkeys(warnings)),
    }
