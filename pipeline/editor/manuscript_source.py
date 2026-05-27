"""Format ``04_final_standardized.json`` text for editor agents."""

from __future__ import annotations

from typing import Any

DEFAULT_BLOCK_CHAR_LIMIT = 8000
DEFAULT_TOTAL_CHAR_LIMIT = 32000


def _claims_from_block(block: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for item in block.get("key_claims") or []:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            claim = str(item.get("claim") or "").strip()
            if claim:
                out.append(claim)
    return out


def format_text_block(
    block: dict[str, Any],
    *,
    char_limit: int = DEFAULT_BLOCK_CHAR_LIMIT,
) -> dict[str, Any]:
    """One source file from Joiner ``text_blocks`` for section writers."""
    path = str(block.get("relative_path") or "").strip()
    content = str(block.get("technical_analysis") or "").strip()
    truncated = len(content) > char_limit
    if truncated:
        content = content[: char_limit - 3] + "..."
    return {
        "path": path,
        "content": content,
        "claims_in_block": _claims_from_block(block),
        "citation_gap": bool(block.get("citation_gap")),
        "truncated": truncated,
    }


def format_metadata_notes(notes: list[dict[str, Any]]) -> list[dict[str, str]]:
    formatted: list[dict[str, str]] = []
    for note in notes:
        if not isinstance(note, dict):
            continue
        path = str(note.get("relative_path") or "").strip()
        points = note.get("key_points") or []
        if not path or not isinstance(points, list):
            continue
        formatted.append({
            "path": path,
            "key_points": "\n".join(str(p) for p in points if str(p).strip()),
        })
    return formatted


def build_primary_manuscript_source(
    data: dict[str, Any],
    *,
    path_filter: str | None = None,
    block_char_limit: int = DEFAULT_BLOCK_CHAR_LIMIT,
    total_char_limit: int = DEFAULT_TOTAL_CHAR_LIMIT,
) -> dict[str, Any]:
    """
    Primary authoritative source from step 04 for section writers.

    ``path_filter``: if set, only blocks whose ``relative_path`` contains this
    substring (case-insensitive).
    """
    blocks_in = [b for b in (data.get("text_blocks") or []) if isinstance(b, dict)]
    if path_filter:
        frag = path_filter.lower()
        blocks_in = [
            b
            for b in blocks_in
            if frag in str(b.get("relative_path") or "").lower()
        ]

    source_blocks: list[dict[str, Any]] = []
    total_chars = 0
    for block in blocks_in:
        formatted = format_text_block(block, char_limit=block_char_limit)
        add_len = len(formatted.get("content") or "")
        if total_chars + add_len > total_char_limit and source_blocks:
            break
        source_blocks.append(formatted)
        total_chars += add_len

    omitted = max(0, len(blocks_in) - len(source_blocks))
    return {
        "source": "04_final_standardized.json",
        "role": "primary_manuscript_text",
        "instruction": (
            "This is the author's manuscript from the input bundle (Joiner step 04). "
            "Paraphrase and structure for IEEE; do not replace with research-agent summaries. "
            "Research summaries are for citations and external context only."
        ),
        "joiner_summary": str(data.get("summary") or "").strip()[:2500],
        "blocks": source_blocks,
        "metadata_notes": format_metadata_notes(
            [n for n in (data.get("metadata_notes") or []) if isinstance(n, dict)]
        ),
        "blocks_omitted_due_to_size": omitted,
    }


def source_block_index(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Compact catalog for the editor orchestrator (paths + previews only)."""
    index: list[dict[str, Any]] = []
    for block in data.get("text_blocks") or []:
        if not isinstance(block, dict):
            continue
        path = str(block.get("relative_path") or "").strip()
        content = str(block.get("technical_analysis") or "").strip()
        preview = content[:280].replace("\n", " ")
        if len(content) > 280:
            preview += "..."
        index.append({
            "path": path,
            "chars": len(content),
            "claims_count": len(_claims_from_block(block)),
            "preview": preview,
        })
    return index
