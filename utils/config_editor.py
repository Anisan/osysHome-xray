# -*- coding: utf-8 -*-
"""Чтение/запись корневого config.yaml с динамической схемой формы."""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml

from app.configuration import Config, _format_yaml_scalar, _replace_yaml_line_key

RESTART_WARNING = (
    "Changes are written to config.yaml only. "
    "Restart osysHome for most settings to take effect."
)

_KEY_LINE_RE = re.compile(r'^([a-zA-Z_][\w]*)\s*:\s*(.*)$')
# Машинночитаемый список допустимых значений в комментариях sample_config.yaml:
#   # choices: en, ru, de
#   # choices: null | FULL | NORMAL | OFF
_CHOICES_RE = re.compile(
    r'^choices\s*:\s*(.+)$',
    re.IGNORECASE,
)


def config_path() -> Path:
    return Path(Config.APP_DIR) / "config.yaml"


def sample_path() -> Path:
    return Path(Config.APP_DIR) / "sample_config.yaml"


def read_raw(path: Path | None = None) -> str:
    path = path or config_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Configuration file {path} not found. "
            f"Copy sample_config.yaml to config.yaml first."
        )
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_sample_raw() -> str:
    path = sample_path()
    if not path.exists():
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def validate_yaml(text: str) -> dict:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML parse error: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("Root of config.yaml must be a mapping (object).")
    return data


def read_structured(path: Path | None = None) -> dict:
    return validate_yaml(read_raw(path))


def write_raw(text: str, path: Path | None = None) -> None:
    """Атомарная запись после успешной валидации YAML."""
    path = path or config_path()
    validate_yaml(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".config_",
        suffix=".yaml.tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            if text and not text.endswith("\n"):
                f.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _infer_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "list"
    return "str"


def _parse_choices_token(token: str) -> Any:
    token = token.strip().strip("'\"")
    if not token:
        return None
    # Только YAML-null; строка "None" (напр. SameSite) остаётся строкой.
    if token == "~" or token.lower() == "null":
        return None
    low = token.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        if "." in token:
            return float(token)
        return int(token)
    except ValueError:
        return token


def parse_choices_line(comment_body: str) -> list[Any] | None:
    """Если строка комментария — `choices: ...`, вернуть список значений."""
    match = _CHOICES_RE.match(comment_body.strip())
    if not match:
        return None
    raw = match.group(1).strip()
    parts = re.split(r"\s*[|,]\s*", raw)
    return [_parse_choices_token(p) for p in parts if p.strip()]


def extract_key_meta(text: str) -> dict[str, dict]:
    """
    Метаданные из комментариев над ключами sample YAML.
    path → {help: str, choices: list|None}
    Строки `choices: ...` не попадают в help.
    """
    meta: dict[str, dict] = {}
    if not text:
        return meta

    pending_help: list[str] = []
    pending_choices: list[Any] | None = None
    stack: list[tuple[int, str]] = []

    for raw in text.splitlines():
        stripped = raw.lstrip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            body = stripped[1:].strip()
            choices = parse_choices_line(body)
            if choices is not None:
                pending_choices = choices
            elif body:
                pending_help.append(body)
            continue

        indent = len(raw) - len(stripped)
        match = _KEY_LINE_RE.match(stripped)
        if not match:
            pending_help = []
            pending_choices = None
            continue

        key = match.group(1)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = ".".join(k for _, k in stack)
        path = f"{parent}.{key}" if parent else key
        entry: dict[str, Any] = {
            "help": "\n".join(pending_help) if pending_help else "",
            "choices": pending_choices,
        }
        if entry["help"] or entry["choices"] is not None:
            meta[path] = entry
        pending_help = []
        pending_choices = None
        stack.append((indent, key))

    return meta


def extract_key_comments(text: str) -> dict[str, str]:
    """Совместимость: path → help (без строк choices)."""
    return {
        path: (info.get("help") or "")
        for path, info in extract_key_meta(text).items()
        if info.get("help")
    }


def _build_node(
    key: str,
    path: str,
    sample_val: Any,
    config_val: Any,
    meta: dict[str, dict],
) -> dict:
    sample_is_dict = isinstance(sample_val, dict)
    config_is_dict = isinstance(config_val, dict)
    info = meta.get(path) or {}
    help_text = info.get("help") or ""
    choices = info.get("choices")

    if sample_is_dict or config_is_dict:
        ordered: list = []
        if sample_is_dict:
            ordered.extend(sample_val.keys())
        if config_is_dict:
            for k in config_val.keys():
                if k not in ordered:
                    ordered.append(k)
        children = []
        for child_key in ordered:
            child_path = f"{path}.{child_key}" if path else child_key
            children.append(
                _build_node(
                    child_key,
                    child_path,
                    sample_val.get(child_key) if sample_is_dict else None,
                    config_val.get(child_key) if config_is_dict else None,
                    meta,
                )
            )
        return {
            "key": key,
            "path": path,
            "type": "object",
            "help": help_text,
            "children": children,
        }

    type_src = sample_val if sample_val is not None else config_val
    node_type = _infer_type(type_src)
    value = config_val if config_val is not None else sample_val

    if node_type == "list":
        node = {
            "key": key,
            "path": path,
            "type": "list",
            "help": help_text,
            "value": value,
        }
        if choices is not None:
            node["choices"] = choices
        return node

    if node_type == "object":
        node_type = "str"

    node = {
        "key": key,
        "path": path,
        "type": node_type,
        "help": help_text,
        "value": value,
    }
    if choices is not None:
        # текущее значение всегда доступно в списке
        normalized = list(choices)
        if value not in normalized and not (
            value is None and any(c is None for c in normalized)
        ):
            normalized = [value] + normalized
        node["choices"] = normalized
    return node


def build_schema(
    sample_dict: dict | None,
    config_dict: dict | None,
    sample_text: str = "",
) -> dict:
    """Динамическая схема формы из sample ∪ config."""
    sample_dict = sample_dict or {}
    config_dict = config_dict or {}
    meta = extract_key_meta(sample_text)
    ordered: list = list(sample_dict.keys())
    for key in config_dict.keys():
        if key not in ordered:
            ordered.append(key)
    children = [
        _build_node(
            key,
            key,
            sample_dict.get(key),
            config_dict.get(key),
            meta,
        )
        for key in ordered
    ]
    return {
        "type": "object",
        "key": "",
        "path": "",
        "children": children,
    }


def get_editor_payload() -> dict:
    text = read_raw()
    structured = validate_yaml(text)
    sample_text = read_sample_raw()
    sample_dict: dict = {}
    if sample_text:
        try:
            loaded = yaml.safe_load(sample_text)
            if isinstance(loaded, dict):
                sample_dict = loaded
        except yaml.YAMLError:
            sample_dict = {}
    schema = build_schema(sample_dict, structured, sample_text)
    return {
        "text": text,
        "structured": structured,
        "schema": schema,
        "path": str(config_path()),
        "warning": RESTART_WARNING,
    }


def flatten_values(data: Any, prefix: str = "") -> dict[str, Any]:
    """Вложенный dict → { 'a.b.c': value } для листьев."""
    out: dict[str, Any] = {}
    if isinstance(data, dict):
        for key, val in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(val, dict):
                out.update(flatten_values(val, path))
            else:
                out[path] = val
    return out


def unflatten_values(flat: dict[str, Any]) -> dict:
    root: dict = {}
    for path, value in flat.items():
        parts = str(path).split(".")
        cur = root
        for part in parts[:-1]:
            nxt = cur.setdefault(part, {})
            if not isinstance(nxt, dict):
                cur[part] = {}
                nxt = cur[part]
            cur = nxt
        cur[parts[-1]] = value
    return root


def _replace_line_value(line: str, key: str, value: Any) -> str:
    if isinstance(value, list):
        dumped = yaml.dump(value, default_flow_style=True, allow_unicode=True).strip()
        newline = ""
        body = line
        if line.endswith("\r\n"):
            newline = "\r\n"
            body = line[:-2]
        elif line.endswith("\n"):
            newline = "\n"
            body = line[:-1]
        match = re.match(rf"^(\s*{re.escape(key)}:\s*)(.*)$", body)
        if not match:
            return line
        prefix, rest = match.group(1), match.group(2)
        existing_eol = ""
        for sep in ("  #", " #"):
            idx = rest.find(sep)
            if idx != -1:
                existing_eol = rest[idx:]
                break
        return f"{prefix}{dumped}{existing_eol}{newline}"
    if value is None:
        newline = ""
        body = line
        if line.endswith("\r\n"):
            newline = "\r\n"
            body = line[:-2]
        elif line.endswith("\n"):
            newline = "\n"
            body = line[:-1]
        match = re.match(rf"^(\s*{re.escape(key)}:\s*)(.*)$", body)
        if not match:
            return line
        prefix, rest = match.group(1), match.group(2)
        existing_eol = ""
        for sep in ("  #", " #"):
            idx = rest.find(sep)
            if idx != -1:
                existing_eol = rest[idx:]
                break
        return f"{prefix}null{existing_eol}{newline}"
    return _replace_yaml_line_key(line, key, value)


def _format_value_for_append(value: Any) -> str:
    if isinstance(value, list):
        return yaml.dump(value, default_flow_style=True, allow_unicode=True).strip()
    if value is None:
        return "null"
    return _format_yaml_scalar(value)


def _find_section_header(lines: list[str], path: str) -> int | None:
    if not path:
        return 0
    parts = path.split(".")
    stack: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(stripped)
        match = _KEY_LINE_RE.match(stripped)
        if not match:
            continue
        key = match.group(1)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, key))
        keys = [k for _, k in stack]
        if keys == parts:
            return idx
    return None


def _find_section_end(lines: list[str], path: str) -> int | None:
    """Индекс сразу после последнего потомка секции path."""
    if not path:
        return len(lines)
    header = _find_section_header(lines, path)
    if header is None:
        return None
    header_line = lines[header]
    header_indent = len(header_line) - len(header_line.lstrip())
    end = header + 1
    while end < len(lines):
        line = lines[end]
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            end += 1
            continue
        indent = len(line) - len(stripped)
        if indent <= header_indent:
            break
        end += 1
    return end


def _ensure_section_path(lines: list[str], path: str) -> list[str]:
    """Гарантирует цепочку секций path в файле."""
    parts = path.split(".") if path else []
    out = list(lines)
    current = ""
    for i, part in enumerate(parts):
        current = f"{current}.{part}" if current else part
        if _find_section_header(out, current) is not None:
            continue
        parent = ".".join(parts[:i])
        insert_at = _find_section_end(out, parent) if parent else len(out)
        if insert_at is None:
            insert_at = len(out)
        indent = "  " * i
        out.insert(insert_at, f"{indent}{part}:\n")
    return out


def _append_missing_keys(text: str, missing: dict[str, Any]) -> str:
    """Добавляет отсутствующие ключи в конец секции."""
    lines = text.splitlines(keepends=True)
    by_parent: dict[str, list[tuple[str, Any]]] = {}
    for path, value in missing.items():
        parts = path.split(".")
        parent = ".".join(parts[:-1])
        key = parts[-1]
        by_parent.setdefault(parent, []).append((key, value))

    for parent, items in by_parent.items():
        if parent and _find_section_header(lines, parent) is None:
            lines = _ensure_section_path(lines, parent)
        insert_at = _find_section_end(lines, parent) if parent else len(lines)
        if insert_at is None:
            insert_at = len(lines)
        indent = "  " * (parent.count(".") + 1) if parent else ""
        chunk = [
            f"{indent}{key}: {_format_value_for_append(value)}\n"
            for key, value in items
        ]
        for i, cl in enumerate(chunk):
            lines.insert(insert_at + i, cl)

    return "".join(lines)


def merge_structured(updates: dict, path: Path | None = None) -> str:
    """
    Точечно обновляет скаляры в тексте config.yaml, сохраняя комментарии.
    updates — вложенный dict как structured.
    """
    path = path or config_path()
    original = read_raw(path)
    flat = flatten_values(updates)
    lines = original.splitlines(keepends=True)
    if not lines and original:
        lines = [original]

    stack: list[tuple[int, str]] = []
    out: list[str] = []
    seen: set[str] = set()

    for line in lines:
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            out.append(line)
            continue

        indent = len(line) - len(stripped)
        match = _KEY_LINE_RE.match(stripped)
        if not match:
            out.append(line)
            continue

        key = match.group(1)
        rest = match.group(2)

        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = ".".join(k for _, k in stack)
        full_path = f"{parent}.{key}" if parent else key

        scalar_part = rest
        for sep in ("  #", " #"):
            idx = scalar_part.find(sep)
            if idx != -1:
                scalar_part = scalar_part[:idx]
                break
        is_nested_header = scalar_part.strip() == ""

        if is_nested_header:
            stack.append((indent, key))
            out.append(line)
            continue

        if full_path in flat:
            out.append(_replace_line_value(line, key, flat[full_path]))
            seen.add(full_path)
        else:
            out.append(line)

        stack.append((indent, key))

    missing = {p: v for p, v in flat.items() if p not in seen}
    if missing:
        return _append_missing_keys("".join(out), missing)
    return "".join(out)


def _normalize_form_values(values: dict) -> dict:
    if not isinstance(values, dict):
        raise ValueError("values must be an object")
    if values and not any(isinstance(v, dict) for v in values.values()):
        return unflatten_values(values)
    return values


def apply_form_values(values: dict) -> dict:
    nested = _normalize_form_values(values)
    new_text = merge_structured(nested)
    write_raw(new_text)
    return get_editor_payload()


def apply_text(text: str) -> dict:
    write_raw(text)
    return get_editor_payload()
