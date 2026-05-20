"""Research index builder — catalog of per-task files (Gemini)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..clients.gemini_client import index_client
from ..config import Settings
from ..manuscript_context import ManuscriptContext
from ..prompts.loader import load_research_index_instruction
from ..research_storage import load_research_manifest, task_artifact_slug
from ..schemas import (
    GatheredResearchBundle,
    OrchestratorPlan,
    SynthesisReport,
    ValidatedResearchBundle,
)

logger = logging.getLogger(__name__)


class ResearchIndexBuilder:
    """Final step: Markdown catalog of which file contains what (not a merged literature report)."""

    def __init__(self, settings: Settings) -> None:
        self._client = index_client(settings)
        self._system = load_research_index_instruction()

    async def build_index(
        self,
        plan: OrchestratorPlan,
        bundle: GatheredResearchBundle,
        validated: ValidatedResearchBundle,
        *,
        research_dir: Path,
        validation_dir: Path,
        manuscript: ManuscriptContext | None = None,
    ) -> SynthesisReport:
        research_manifest = load_research_manifest(research_dir)
        validation_manifest_path = validation_dir / "manifest.json"
        validation_manifest: dict[str, Any] = {}
        if validation_manifest_path.is_file():
            validation_manifest = json.loads(validation_manifest_path.read_text(encoding="utf-8"))

        previews: dict[str, str] = {}
        for idx, r in enumerate(bundle.results, start=1):
            slug = task_artifact_slug(r.agent_id, idx, r.task)
            previews[slug] = (r.summary or r.error or "")[:240]

        for entry in research_manifest.get("tasks") or []:
            slug = str(entry.get("slug", ""))
            if slug in previews:
                entry["content_preview"] = previews[slug]

        user_payload: dict[str, Any] = {
            "research_goal": plan.research_goal.model_dump(),
            "research_manifest": research_manifest,
            "validation_manifest": validation_manifest,
            "validation_results": [v.model_dump() for v in validated.results],
            "research_dir": research_dir.name,
            "validation_dir": validation_dir.name,
        }
        if manuscript is not None:
            user_payload["manuscript"] = {
                "summary": manuscript.summary,
                "target_journal": manuscript.target_journal,
            }

        markdown = await self._client.generate_markdown(
            system=self._system,
            user=json.dumps(user_payload, indent=2, default=str),
            trace_label="research_index",
        )
        if not markdown.strip():
            raise ValueError("Research index builder returned empty document")

        title = f"Research catalog: {plan.research_goal.main_topic}"
        logger.info("Research index generated (%d chars)", len(markdown))
        return SynthesisReport(title=title, markdown_body=markdown)


