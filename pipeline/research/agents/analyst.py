"""Research index builder — catalog of per-task files (deterministic Markdown)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..config import Settings
from ..index_catalog import render_research_index_markdown
from ..manuscript_context import ManuscriptContext
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
        self._settings = settings

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
        validation_manifest: dict = {}
        if validation_manifest_path.is_file():
            validation_manifest = json.loads(validation_manifest_path.read_text(encoding="utf-8"))

        previews: dict[str, str] = {}
        for idx, r in enumerate(bundle.results, start=1):
            slug = task_artifact_slug(r.agent_id, idx, r.task)
            previews[slug] = (r.summary or r.error or "")[:240]

        markdown = render_research_index_markdown(
            plan,
            bundle,
            validated,
            research_manifest=research_manifest,
            validation_manifest=validation_manifest,
            previews=previews,
            manuscript=manuscript,
        )
        if not markdown.strip():
            raise ValueError("Research index builder returned empty document")

        title = f"Research catalog: {plan.research_goal.main_topic}"
        logger.info("Research index generated (%d chars)", len(markdown))
        return SynthesisReport(title=title, markdown_body=markdown)


