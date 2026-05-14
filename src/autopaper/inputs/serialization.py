from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autopaper.inputs.models import PaperDraft, ResearchInput


def research_input_to_dict(ri: ResearchInput) -> dict[str, Any]:
    return {
        "description": ri.description,
        "details": ri.details,
        "technical_details": ri.technical_details,
        "extra_context": ri.extra_context,
    }


def paper_draft_to_dict(draft: PaperDraft) -> dict[str, Any]:
    return {
        "title": draft.title,
        "sections": [
            {
                "section": s.section.value,
                "content": s.content,
                "metadata": s.metadata,
            }
            for s in draft.sections
        ],
        "raw_research_summary": draft.raw_research_summary,
        "peer_review_notes": draft.peer_review_notes,
        "validation_report": draft.validation_report,
    }
