"""Multi-agent research pipeline orchestration."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .agents.analyst import ReportSynthesizer
from .agents.orchestrator import OrchestratorAgent
from .agents.search_coordinator import SearchCoordinator
from .clients.openai_client import OpenAIClient
from .config import Settings
from .schemas import PipelineRunResult

logger = logging.getLogger(__name__)


class ResearchPipeline:
    """Orchestrator → parallel search (Gemini + Claude + Exa) → report synthesizer."""

    def __init__(self, settings: Settings) -> None:
        settings.validate_keys()
        self._settings = settings
        self._orchestrator = OrchestratorAgent(OpenAIClient(settings))
        self._search = SearchCoordinator.from_settings(settings)
        self._synthesizer = ReportSynthesizer(settings)

    async def run(self, research_goal: str) -> PipelineRunResult:
        errors: list[str] = []
        run_dir = self._allocate_run_dir()
        logger.info("Run directory: %s", run_dir)

        plan = await self._orchestrator.create_plan(research_goal)
        (run_dir / "01_orchestrator_plan.json").write_text(
            plan.model_dump_json(indent=2),
            encoding="utf-8",
        )

        bundle = await self._search.gather(plan)
        (run_dir / "02_gathered_research.json").write_text(
            bundle.model_dump_json(indent=2),
            encoding="utf-8",
        )

        report = None
        try:
            report = await self._synthesizer.synthesize(plan, bundle)
            (run_dir / "03_final_report.md").write_text(
                report.markdown_body,
                encoding="utf-8",
            )
            meta = {
                "title": report.title,
                "generated_at_utc": report.generated_at_utc.isoformat(),
                "successful_search_tasks": len(bundle.successful_results),
                "total_search_tasks": len(bundle.results),
            }
            (run_dir / "03_final_report.meta.json").write_text(
                json.dumps(meta, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            msg = f"Report synthesizer failed: {exc}"
            logger.exception(msg)
            errors.append(msg)

        manifest = {
            "research_goal_input": research_goal,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "output_dir": str(run_dir),
            "errors": errors,
        }
        (run_dir / "00_run_manifest.json").write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )

        return PipelineRunResult(
            plan=plan,
            bundle=bundle,
            report=report,
            output_dir=str(run_dir),
            errors=errors,
        )

    def _allocate_run_dir(self) -> Path:
        root = self._settings.research_output_dir.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        max_num = 0
        for p in root.iterdir():
            if p.is_dir() and p.name.startswith("run_"):
                suffix = p.name.removeprefix("run_")
                if suffix.isdigit():
                    max_num = max(max_num, int(suffix))
        run_dir = root / f"run_{max_num + 1:03d}"
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir
