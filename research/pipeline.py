"""Multi-agent research pipeline orchestration."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from .agents.analyst import ReportSynthesizer
from .agents.orchestrator import OrchestratorAgent
from .agents.search_coordinator import SearchCoordinator
from .clients.openai_client import OpenAIClient
from .config import Settings
from .manuscript_context import load_manuscript_context_from_execution
from .schemas import (
    GatheredResearchBundle,
    OrchestratorPlan,
    PipelineRunResult,
    SynthesisReport,
)

logger = logging.getLogger(__name__)

PLAN_FILENAME = "05_orchestrator_plan.json"
GATHERED_FILENAME = "06_gathered_research.json"
REPORT_FILENAME = "07_final_report.md"
REPORT_META_FILENAME = "07_final_report.meta.json"


def _force_replan() -> bool:
    return os.environ.get("RESEARCH_FORCE_REPLAN", "").strip().lower() in ("1", "true", "yes")


def _load_existing_plan(path: Path) -> OrchestratorPlan | None:
    if not path.is_file():
        return None
    try:
        return OrchestratorPlan.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not load existing plan %s: %s", path, exc)
        return None


class ResearchPipeline:
    """GPT-4o orchestrator → parallel gemini_search + openai_search → Gemini report."""

    def __init__(self, settings: Settings, *, plan_only: bool = False) -> None:
        settings.validate_keys(plan_only=plan_only)
        self._settings = settings
        self._plan_only = plan_only
        self._orchestrator = OrchestratorAgent(
            OpenAIClient(settings),
            settings=settings,
        )
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
            self._write_report_meta(run_dir, plan, bundle, report, filename="03_final_report.meta.json")
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

    def _write_report_meta(
        self,
        run_dir: Path,
        plan: OrchestratorPlan,
        bundle: GatheredResearchBundle,
        report: SynthesisReport,
        *,
        filename: str,
    ) -> None:
        source_count = sum(len(r.sources) for r in bundle.results)
        meta = {
            "title": report.title,
            "generated_at_utc": report.generated_at_utc.isoformat(),
            "successful_search_tasks": len(bundle.successful_results),
            "total_search_tasks": len(bundle.results),
            "total_sources_cited": source_count,
            "models": {
                "orchestrator": self._settings.orchestrator_model,
                "gemini_search": self._settings.gemini_search_model,
                "openai_search": self._settings.openai_search_model,
                "report_synthesizer": self._settings.report_synthesizer_model,
            },
            "main_topic": plan.research_goal.main_topic,
        }
        (run_dir / filename).write_text(json.dumps(meta, indent=2), encoding="utf-8")

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

    async def run_in_execution_dir(
        self,
        execution_dir: Path,
        research_goal: str,
        *,
        reuse_plan: bool = True,
    ) -> PipelineRunResult:
        """Continue a paper_input run: write ``05_``–``07_`` artifacts beside ``04_``."""
        run_dir = execution_dir.expanduser().resolve()
        errors: list[str] = []
        logger.info("Research continuation in: %s", run_dir)

        manuscript = load_manuscript_context_from_execution(run_dir)
        plan_path = run_dir / PLAN_FILENAME

        plan: OrchestratorPlan | None = None
        reused_plan = False
        if reuse_plan and not _force_replan():
            plan = _load_existing_plan(plan_path)
            if plan is not None:
                reused_plan = True
                logger.info("Reusing existing orchestrator plan: %s", plan_path)

        if plan is None:
            plan = await self._orchestrator.create_plan(research_goal)
            plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")

        bundle = None
        report = None
        if not self._plan_only:
            bundle = await self._search.gather(plan, manuscript=manuscript)
            (run_dir / GATHERED_FILENAME).write_text(
                bundle.model_dump_json(indent=2),
                encoding="utf-8",
            )
            try:
                report = await self._synthesizer.synthesize(
                    plan,
                    bundle,
                    manuscript=manuscript,
                )
                (run_dir / REPORT_FILENAME).write_text(
                    report.markdown_body,
                    encoding="utf-8",
                )
                self._write_report_meta(run_dir, plan, bundle, report, filename=REPORT_META_FILENAME)
            except Exception as exc:
                msg = f"Report synthesizer failed: {exc}"
                logger.exception(msg)
                errors.append(msg)

        manifest_path = run_dir / "00_run_manifest.json"
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                manifest = {}
        else:
            manifest = {}
        steps = list(manifest.get("steps") or [])
        for name in (PLAN_FILENAME, GATHERED_FILENAME, REPORT_FILENAME):
            if (run_dir / name).is_file() and name not in steps:
                steps.append(name)
        manifest["steps"] = steps
        manifest["research_continuation"] = {
            "plan_only": self._plan_only,
            "reused_plan": reused_plan,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "errors": errors,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        return PipelineRunResult(
            plan=plan,
            bundle=bundle,
            report=report,
            output_dir=str(run_dir),
            errors=errors,
        )


def format_plan_summary(plan: OrchestratorPlan) -> str:
    """Human-readable orchestrator output for CLI."""
    lines = [
        f"Topic: {plan.research_goal.main_topic}",
        "Required outputs:",
    ]
    for item in plan.research_goal.required_outputs:
        lines.append(f"  - {item}")
    lines.append("Subtasks by agent:")
    for agent in plan.execution_strategy.target_agents:
        lines.append(f"  [{agent.agent_id}] (model hint: {agent.model})")
        for task in agent.tasks:
            lines.append(f"    - {task}")
    return "\n".join(lines)
