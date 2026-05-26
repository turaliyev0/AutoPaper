"""Build final standardized JSON without vision/joiner LLM calls (text-only runs)."""

from __future__ import annotations

from typing import Any


def finalize_without_images(cleaned_text: dict[str, Any]) -> dict[str, Any]:
    """Assemble ``04_final_standardized.json`` from text parser output only."""
    text_blocks_in = cleaned_text.get("text_blocks") or []
    metadata_notes = cleaned_text.get("metadata_notes") or []

    summary_parts: list[str] = []
    key_claims: list[str] = []
    text_blocks: list[dict[str, Any]] = []

    for block in text_blocks_in:
        if not isinstance(block, dict):
            continue
        out = dict(block)
        out["linked_images"] = []
        text_blocks.append(out)

        analysis = str(block.get("technical_analysis") or "").strip()
        if analysis:
            summary_parts.append(analysis)

        for claim in block.get("key_claims") or []:
            if isinstance(claim, str):
                c = claim.strip()
                if c and c not in key_claims:
                    key_claims.append(c)

    if summary_parts:
        summary = " ".join(summary_parts)
        if len(summary) > 2500:
            summary = summary[:2497] + "..."
    else:
        summary = "Text-only manuscript; no figures were provided."

    return {
        "summary": summary,
        "key_claims": key_claims,
        "text_blocks": text_blocks,
        "metadata_notes": metadata_notes,
        "images": [],
        "cross_references": [],
        "mismatch_flags": [],
    }
