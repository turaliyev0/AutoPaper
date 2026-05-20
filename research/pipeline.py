"""Multi-agent research pipeline orchestration."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from .agents.analyst import ResearchIndexBuilder
from .agents.orchestrator import OrchestratorAgent
from .agents.search_coordinator import SearchCoordinator
from .agents.validator import ResearchValidator
from .clients.openai_client import OpenAIClient
from .config import Settings
from .manuscript_context import load_manuscript_context_from_execution
from .research_storage import (
    EXEC_GATHERED_AGGREGATE,
    EXEC_INDEX_MD,
    EXEC_INDEX_META,
    EXEC_RESEARCH_DIR,
    EXEC_VALIDATION_DIR,
    RUN_GATHERED_AGGREGATE,
    RUN_INDEX_MD,
    RUN_INDEX_META,
    RUN_RESEARCH_DIR,
    RUN_VALIDATION_DIR,
    layout_for_run_dir,
    write_research_bundle,
    write_validation_bundle,
)
from .schemas import (
    GatheredResearchBundle,
    OrchestratorPlan,
    PipelineRunResult,
    SynthesisReport,
    ValidatedResearchBundle,
)

logger = logging.getLogger(__name__)

PLAN_FILENAME = "05_orchestrator_plan.json"
# Legacy aggregate filename (still written for tooling).
GATHERED_FILENAME = EXEC_GATHERED_AGGREGATE
REPORT_FILENAME = EXEC_INDEX_MD
REPORT_META_FILENAME = EXEC_INDEX_META


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
    """Orchestrator → parallel search (one file per task) → validator → research index."""

    def __init__(self, settings: Settings, *, plan_only: bool = False) -> None:
        settings.validate_keys(plan_only=plan_only)
        self._settings = settings
        self._plan_only = plan_only
        self._orchestrator = OrchestratorAgent(
            OpenAIClient(settings),
            settings=settings,
        )
        self._search = SearchCoordinator.from_settings(settings)
        self._validator = ResearchValidator(settings)
        self._index_builder = ResearchIndexBuilder(settings)

    async def _run_search_validate_index(
        self,
        run_dir: Path,
        plan: OrchestratorPlan,
        *,
        manuscript=None,
    ) -> tuple[GatheredResearchBundle, ValidatedResearchBundle, SynthesisReport | None, list[str]]:
        errors: list[str] = []
        research_dir_name, aggregate_name, validation_dir_name, index_name = layout_for_run_dir(
            run_dir,
        )

        bundle = await self._search.gather(plan, manuscript=manuscript)
        research_dir = write_research_bundle(
            run_dir,
            bundle,
            research_dir_name=research_dir_name,
            aggregate_filename=aggregate_name,
        )

        validated = await self._validator.validate_all(plan, research_dir)
        validation_dir = write_validation_bundle(
            run_dir,
            validated,
            validation_dir_name=validation_dir_name,
        )

        report: SynthesisReport | None = None
        try:
            report = await self._index_builder.build_index(
                plan,
                bundle,
                validated,
                research_dir=research_dir,
                validation_dir=validation_dir,
                manuscript=manuscript,
            )
            (run_dir / index_name).write_text(report.markdown_body, encoding="utf-8")
            meta_name = index_name.replace(".md", ".meta.json")
            self._write_index_meta(
                run_dir,
                plan,
                bundle,
                validated,
                report,
                filename=meta_name,
                research_dir=research_dir_name,
                validation_dir=validation_dir_name,
            )
        except Exception as exc:
            msg = f"Research index builder failed: {exc}"
            logger.exception(msg)
            errors.append(msg)

        return bundle, validated, report, errors

    async def run(self, research_goal: str) -> PipelineRunResult:
        errors: list[str] = []
        run_dir = self._allocate_run_dir()
        logger.info("Run directory: %s", run_dir)

        plan = await self._orchestrator.create_plan(research_goal)
        (run_dir / "01_orchestrator_plan.json").write_text(
            plan.model_dump_json(indent=2),
            encoding="utf-8",
        )

        bundle, validated, report, step_errors = await self._run_search_validate_index(
            run_dir,
            plan,
        )
        errors.extend(step_errors)

        manifest = {
            "research_goal_input": research_goal,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "output_dir": str(run_dir),
            "research_dir": RUN_RESEARCH_DIR,
            "validation_dir": RUN_VALIDATION_DIR,
            "index_file": RUN_INDEX_MD,
            "errors": errors,
        }
        (run_dir / "00_run_manifest.json").write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )

        return PipelineRunResult(
            plan=plan,
            bundle=bundle,
            validated=validated,
            report=report,
            output_dir=str(run_dir),
            errors=errors,
        )

    def _write_index_meta(
        self,
        run_dir: Path,
        plan: OrchestratorPlan,
        bundle: GatheredResearchBundle,
        validated: ValidatedResearchBundle,
        report: SynthesisReport,
        *,
        filename: str,
        research_dir: str,
        validation_dir: str,
    ) -> None:
        source_count = sum(len(r.sources) for r in bundle.results if r.success)
        verdicts = [v.verdict for v in validated.results]
        meta = {
            "title": report.title,
            "generated_at_utc": report.generated_at_utc.isoformat(),
            "artifact_layout": {
                "research_dir": research_dir,
                "validation_dir": validation_dir,
            },
            "successful_search_tasks": len(bundle.successful_results),
            "total_search_tasks": len(bundle.results),
            "validation_pass": verdicts.count("pass"),
            "validation_warn": verdicts.count("warn"),
            "validation_fail": verdicts.count("fail"),
            "total_sources_cited": source_count,
            "models": {
                "orchestrator": self._settings.orchestrator_model,
                "gemini_search": self._settings.gemini_search_model,
                "openai_search": self._settings.openai_search_model,
                "research_validator": self._settings.research_validator_model,
                "research_index": self._settings.research_index_model,
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
        """Continue a paper_input run: write ``05_``–``08_`` artifacts beside ``04_``."""
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
        validated = None
        report = None
        if not self._plan_only:
            bundle, validated, report, step_errors = await self._run_search_validate_index(
                run_dir,
                plan,
                manuscript=manuscript,
            )
            errors.extend(step_errors)

        manifest_path = run_dir / "00_run_manifest.json"
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                manifest = {}
        else:
            manifest = {}
        steps = list(manifest.get("steps") or [])
        for name in (
            PLAN_FILENAME,
            EXEC_RESEARCH_DIR,
            EXEC_GATHERED_AGGREGATE,
            EXEC_VALIDATION_DIR,
            EXEC_INDEX_MD,
        ):
            path = run_dir / name
            if path.exists() and name not in steps:
                steps.append(name)
        manifest["steps"] = steps
        manifest["research_continuation"] = {
            "plan_only": self._plan_only,
            "reused_plan": reused_plan,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "research_dir": EXEC_RESEARCH_DIR,
            "validation_dir": EXEC_VALIDATION_DIR,
            "index_file": EXEC_INDEX_MD,
            "errors": errors,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        return PipelineRunResult(
            plan=plan,
            bundle=bundle,
            validated=validated,
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
