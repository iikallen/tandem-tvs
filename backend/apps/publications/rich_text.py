import re
import unicodedata
import uuid
from collections.abc import Mapping
from typing import Never, cast
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError

MAX_DOCUMENT_DEPTH = 16
MAX_DOCUMENT_NODES = 5_000
MAX_DOCUMENT_TEXT = 100_000
MAX_LINK_LENGTH = 2_048

BLOCK_NODES = {
    "paragraph",
    "heading",
    "bulletList",
    "orderedList",
    "blockquote",
    "table",
    "assetImage",
    "internalVideo",
    "attachment",
}
INLINE_NODES = {"text", "hardBreak"}
LIST_NODES = {"listItem"}
LIST_ITEM_NODES = {"paragraph", "bulletList", "orderedList"}
TABLE_ROW_NODES = {"tableRow"}
TABLE_CELL_NODES = {"tableCell", "tableHeader"}
MARKS = {"bold", "italic", "link"}


def empty_rich_text_document() -> dict[str, object]:
    return {"type": "doc", "content": []}


def validate_rich_text_document(value: object) -> None:
    state = {"nodes": 0, "text": 0}
    _validate_node(value, allowed={"doc"}, depth=0, state=state)


def rich_text_to_plain_text(value: object) -> str:
    validate_rich_text_document(value)
    parts: list[str] = []
    _collect_text(value, parts)
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", " ".join(parts))).strip()


def rich_text_asset_ids(value: object) -> set[uuid.UUID]:
    validate_rich_text_document(value)
    found: set[uuid.UUID] = set()
    _collect_asset_ids(value, found)
    return found


def _validate_node(
    value: object,
    *,
    allowed: set[str],
    depth: int,
    state: dict[str, int],
) -> None:
    if depth > MAX_DOCUMENT_DEPTH:
        _invalid("Rich-text document is nested too deeply.")
    if not isinstance(value, Mapping):
        _invalid("Every rich-text node must be an object.")

    node = cast("Mapping[str, object]", value)
    node_type = node.get("type")
    if not isinstance(node_type, str) or node_type not in allowed:
        _invalid("Rich-text document contains an unsupported node.")

    state["nodes"] += 1
    if state["nodes"] > MAX_DOCUMENT_NODES:
        _invalid("Rich-text document contains too many nodes.")

    if node_type == "doc":
        _require_keys(node, required={"type", "content"}, optional=set())
        _validate_children(node, allowed=BLOCK_NODES, depth=depth, state=state)
    elif node_type == "paragraph":
        _require_keys(node, required={"type"}, optional={"content"})
        _validate_children(node, allowed=INLINE_NODES, depth=depth, state=state)
    elif node_type == "heading":
        _require_keys(node, required={"type", "attrs"}, optional={"content"})
        attrs = _mapping(node["attrs"], "Heading attributes must be an object.")
        _require_keys(attrs, required={"level"}, optional=set())
        if type(attrs["level"]) is not int or attrs["level"] not in {2, 3}:
            _invalid("Only H2 and H3 headings are supported.")
        _validate_children(node, allowed=INLINE_NODES, depth=depth, state=state)
    elif node_type in {"bulletList", "orderedList"}:
        optional = {"attrs"} if node_type == "orderedList" else set()
        _require_keys(node, required={"type", "content"}, optional=optional)
        if node_type == "orderedList" and "attrs" in node:
            attrs = _mapping(node["attrs"], "Ordered-list attributes must be an object.")
            _require_keys(attrs, required={"start"}, optional=set())
            if type(attrs["start"]) is not int or not 1 <= attrs["start"] <= 100_000:
                _invalid("Ordered-list start must be a positive integer.")
        _validate_children(node, allowed=LIST_NODES, depth=depth, state=state)
    elif node_type == "listItem":
        _require_keys(node, required={"type", "content"}, optional=set())
        _validate_children(node, allowed=LIST_ITEM_NODES, depth=depth, state=state)
    elif node_type == "blockquote":
        _require_keys(node, required={"type", "content"}, optional=set())
        _validate_children(node, allowed=BLOCK_NODES, depth=depth, state=state)
    elif node_type == "table":
        _require_keys(node, required={"type", "content"}, optional=set())
        _validate_children(node, allowed=TABLE_ROW_NODES, depth=depth, state=state)
    elif node_type == "tableRow":
        _require_keys(node, required={"type", "content"}, optional=set())
        _validate_children(node, allowed=TABLE_CELL_NODES, depth=depth, state=state)
    elif node_type in {"tableCell", "tableHeader"}:
        _require_keys(node, required={"type", "content"}, optional={"attrs"})
        if "attrs" in node:
            attrs = _mapping(node["attrs"], "Table cell attributes must be an object.")
            _require_keys(attrs, required=set(), optional={"colspan", "rowspan", "colwidth"})
        _validate_children(node, allowed=BLOCK_NODES - {"table"}, depth=depth, state=state)
    elif node_type in {"assetImage", "internalVideo", "attachment"}:
        _require_keys(node, required={"type", "attrs"}, optional=set())
        attrs = _mapping(node["attrs"], "Media attributes must be an object.")
        _require_keys(attrs, required={"asset_id"}, optional=set())
        asset_id = attrs["asset_id"]
        if not isinstance(asset_id, str):
            _invalid("Media asset identifier must be a UUID.")
        try:
            uuid.UUID(asset_id)
        except ValueError:
            _invalid("Media asset identifier must be a UUID.")
    elif node_type == "text":
        _require_keys(node, required={"type", "text"}, optional={"marks"})
        text = node["text"]
        if not isinstance(text, str):
            _invalid("Rich-text node text must be a string.")
        state["text"] += len(text)
        if state["text"] > MAX_DOCUMENT_TEXT:
            _invalid("Rich-text document is too long.")
        _validate_marks(node.get("marks", []))
    elif node_type == "hardBreak":
        _require_keys(node, required={"type"}, optional=set())


def _validate_children(
    node: Mapping[str, object],
    *,
    allowed: set[str],
    depth: int,
    state: dict[str, int],
) -> None:
    content = node.get("content", [])
    if not isinstance(content, list):
        _invalid("Rich-text node content must be a list.")
    for child in cast("list[object]", content):
        _validate_node(child, allowed=allowed, depth=depth + 1, state=state)


def _validate_marks(value: object) -> None:
    if not isinstance(value, list):
        _invalid("Rich-text marks must be a list.")

    seen: set[str] = set()
    for value_mark in cast("list[object]", value):
        mark = _mapping(value_mark, "Every rich-text mark must be an object.")
        mark_type = mark.get("type")
        if not isinstance(mark_type, str) or mark_type not in MARKS or mark_type in seen:
            _invalid("Rich-text document contains an unsupported or duplicate mark.")
        seen.add(mark_type)

        if mark_type in {"bold", "italic"}:
            _require_keys(mark, required={"type"}, optional=set())
            continue

        _require_keys(mark, required={"type", "attrs"}, optional=set())
        attrs = _mapping(mark["attrs"], "Link attributes must be an object.")
        _require_keys(
            attrs,
            required={"href"},
            optional={"target", "rel", "class"},
        )
        href = attrs["href"]
        if not isinstance(href, str) or len(href) > MAX_LINK_LENGTH or not _safe_href(href):
            _invalid("Link uses an unsupported URL.")
        target = attrs.get("target")
        rel = attrs.get("rel")
        if target is not None and (
            not isinstance(target, str) or target not in {"_self", "_blank"}
        ):
            _invalid("Link target is not supported.")
        if rel is not None and (
            not isinstance(rel, str)
            or rel not in {"noopener noreferrer", "noopener noreferrer nofollow"}
        ):
            _invalid("Link rel is not supported.")
        if target == "_blank" and (not isinstance(rel, str) or "noopener" not in rel.split()):
            _invalid("Links opening a new window must use noopener.")
        if attrs.get("class") is not None:
            _invalid("Link classes are not supported.")


def _safe_href(href: str) -> bool:
    normalized = href.strip()
    if not normalized or any(
        character.isspace() or unicodedata.category(character).startswith("C")
        for character in normalized
    ):
        return False
    if normalized.startswith("//"):
        return False
    try:
        parsed = urlsplit(normalized)
    except ValueError:
        return False
    scheme = parsed.scheme.casefold()
    if scheme in {"http", "https"}:
        return bool(parsed.netloc)
    if scheme == "mailto":
        return bool(parsed.path)
    return not scheme and (normalized.startswith("/") or normalized.startswith("#"))


def _collect_text(value: object, parts: list[str]) -> None:
    if not isinstance(value, Mapping):
        return
    node = cast("Mapping[str, object]", value)
    if node.get("type") == "text" and isinstance(node.get("text"), str):
        parts.append(cast("str", node["text"]))
    content = node.get("content", [])
    if not isinstance(content, list):
        return
    for child in cast("list[object]", content):
        _collect_text(child, parts)


def _collect_asset_ids(value: object, found: set[uuid.UUID]) -> None:
    if not isinstance(value, Mapping):
        return
    node = cast("Mapping[str, object]", value)
    if node.get("type") in {"assetImage", "internalVideo", "attachment"}:
        attrs = node.get("attrs")
        if isinstance(attrs, Mapping) and isinstance(attrs.get("asset_id"), str):
            found.add(uuid.UUID(cast("str", attrs["asset_id"])))
    content = node.get("content", [])
    if isinstance(content, list):
        for child in cast("list[object]", content):
            _collect_asset_ids(child, found)


def _mapping(value: object, message: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _invalid(message)
    return cast("Mapping[str, object]", value)


def _require_keys(
    value: Mapping[str, object],
    *,
    required: set[str],
    optional: set[str],
) -> None:
    keys = set(value)
    if not required <= keys or not keys <= required | optional:
        _invalid("Rich-text node or mark has unsupported attributes.")


def _invalid(message: str) -> Never:
    raise ValidationError(message, code="invalid_rich_text")
