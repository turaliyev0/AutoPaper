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
from .clients.gemini_client import orchestrator_followup_client
from .clients.openai_client import OpenAIClient
from .config import ACTIVE_SEARCH_AGENT_IDS, Settings
from .manuscript_context import ManuscriptContext, load_manuscript_context_from_execution
from .research_storage import (
    EXEC_GATHERED_AGGREGATE,
    EXEC_INDEX_MD,
    EXEC_RESEARCH_DIR,
    EXEC_VALIDATION_DIR,
    RUN_INDEX_MD,
    RUN_RESEARCH_DIR,
    RUN_VALIDATION_DIR,
    layout_for_run_dir,
    write_research_bundle,
    write_validation_bundle,
)
from .schemas import (
    ExecutionStrategy,
    GatheredResearchBundle,
    OrchestratorConfig,
    OrchestratorPlan,
    PipelineRunResult,
    ResearchGoal,
    SynthesisReport,
    TargetAgent,
    ValidatedResearchBundle,
)
from .utils import short_step_label

logger = logging.getLogger(__name__)

PLAN_FILENAME = "05_orchestrator_plan.json"

_LEGACY_SEARCH_IDS: dict[str, str] = {
    "gemini_explorer": "gemini_search",
}


def _print_research_plan(plan: OrchestratorPlan) -> None:
    """Emit planned literature tasks for the UI (SSE step/log stream)."""
    print(f"[STEP] Research focus: {plan.research_goal.main_topic}", flush=True)
    n_search = 0
    for target in plan.execution_strategy.target_agents:
        agent_id = _LEGACY_SEARCH_IDS.get(target.agent_id, target.agent_id)
        if agent_id not in ACTIVE_SEARCH_AGENT_IDS:
            continue
        label = agent_id.replace("_", " ")
        for task in target.tasks:
            n_search += 1
            print(
                f"[STEP] Research plan ({label}): {short_step_label(task)}",
                flush=True,
            )
    if n_search:
        print(f"[STEP] Running {n_search} literature search task(s)", flush=True)


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
            orchestrator_followup_client(settings),
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
        manuscript: ManuscriptContext | None = None,
    ) -> tuple[GatheredResearchBundle, ValidatedResearchBundle, SynthesisReport | None, list[str]]:
        errors: list[str] = []
        research_dir_name, aggregate_name, validation_dir_name, index_name = layout_for_run_dir(
            run_dir,
        )

        # --- Round 1: initial search + validate ---
        print("[STEP] Running literature search (round 1)", flush=True)
        bundle = await self._search.gather(plan, manuscript=manuscript)

        print("[STEP] Validating research sources (round 1)", flush=True)
        validated = await self._validator.validate_bundle(plan, bundle, start_index=1)

        # --- Follow-up rounds: orchestrator reads validation, requests gap-filling tasks ---
        followup_log: list[dict] = []
        max_rounds = max(0, int(self._settings.research_followup_rounds))
        max_followup_tasks = max(1, int(self._settings.research_followup_max_tasks))

        for round_idx in range(1, max_rounds + 1):
            print(
                f"[STEP] Reviewing validation report (follow-up round {round_idx})",
                flush=True,
            )
            try:
                decision = await self._orchestrator.refine_plan(
                    plan=plan,
                    bundle=bundle,
                    validated=validated,
                    max_followup_tasks=max_followup_tasks,
                )
            except Exception as exc:
                msg = (
                    f"Follow-up orchestrator call failed (round {round_idx}): {exc}"
                )
                logger.exception(msg)
                errors.append(msg)
                followup_log.append({"round": round_idx, "error": str(exc)})
                break

            followup_log.append(
                {
                    "round": round_idx,
                    "reasoning": decision.reasoning,
                    "gemini_tasks": decision.gemini_tasks,
                    "openai_tasks": decision.openai_tasks,
                },
            )

            if not decision.has_tasks:
                print(
                    f"[STEP] Follow-up round {round_idx}: coverage sufficient — "
                    "no new tasks",
                    flush=True,
                )
                break

            n_new = len(decision.gemini_tasks) + len(decision.openai_tasks)
            print(
                f"[STEP] Follow-up round {round_idx}: orchestrator requested "
                f"{n_new} new task(s)",
                flush=True,
            )
            for t in decision.gemini_tasks:
                print(
                    f"[STEP] Follow-up plan (gemini search): {short_step_label(t)}",
                    flush=True,
                )
            for t in decision.openai_tasks:
                print(
                    f"[STEP] Follow-up plan (openai search): {short_step_label(t)}",
                    flush=True,
                )

            followup_plan = self._build_followup_plan(plan, decision)
            print(
                f"[STEP] Running literature search (follow-up round {round_idx})",
                flush=True,
            )
            followup_bundle = await self._search.gather(
                followup_plan,
                manuscript=manuscript,
            )

            print(
                f"[STEP] Validating research sources (follow-up round {round_idx})",
                flush=True,
            )
            followup_validated = await self._validator.validate_bundle(
                plan,
                followup_bundle,
                start_index=len(bundle.results) + 1,
            )

            bundle = GatheredResearchBundle(
                plan=plan,
                results=[*bundle.results, *followup_bundle.results],
            )
            validated = ValidatedResearchBundle(
                plan=plan,
                results=[*validated.results, *followup_validated.results],
            )

        # --- Write final combined artifacts (one set per run) ---
        research_dir = write_research_bundle(
            run_dir,
            bundle,
            research_dir_name=research_dir_name,
            aggregate_filename=aggregate_name,
        )
        validation_dir = write_validation_bundle(
            run_dir,
            validated,
            validation_dir_name=validation_dir_name,
        )
        if followup_log:
            self._write_followup_log(run_dir, plan, followup_log)

        print("[STEP] Building research index", flush=True)
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

    def _build_followup_plan(
        self,
        plan: OrchestratorPlan,
        decision,
    ) -> OrchestratorPlan:
        """Construct a minimal plan that the search coordinator can execute for the new tasks."""
        targets: list[TargetAgent] = []
        if decision.gemini_tasks:
            targets.append(
                TargetAgent(
                    agent_id="gemini_search",
                    model=self._settings.gemini_search_model,
                    tasks=list(decision.gemini_tasks),
                ),
            )
        if decision.openai_tasks:
            targets.append(
                TargetAgent(
                    agent_id="openai_search",
                    model=self._settings.openai_search_model,
                    tasks=list(decision.openai_tasks),
                ),
            )
        validator_agent = plan.validator_agent()
        validator_tasks = (
            list(validator_agent.tasks) if validator_agent else ["Follow-up validation"]
        )
        targets.append(
            TargetAgent(
                agent_id="research_validator",
                model=self._settings.research_validator_model,
                tasks=validator_tasks,
            ),
        )
        return OrchestratorPlan(
            orchestrator_config=OrchestratorConfig(),
            research_goal=ResearchGoal(
                main_topic=plan.research_goal.main_topic,
                required_outputs=list(plan.research_goal.required_outputs),
            ),
            execution_strategy=ExecutionStrategy(target_agents=targets),
        )

    def _write_followup_log(
        self,
        run_dir: Path,
        plan: OrchestratorPlan,
        rounds: list[dict],
    ) -> None:
        layout = layout_for_run_dir(run_dir)
        # Use the same numeric prefix as the orchestrator plan file in each layout.
        if layout[0] == EXEC_RESEARCH_DIR:
            filename = "05_orchestrator_followups.json"
        else:
            filename = "01_orchestrator_followups.json"
        payload = {
            "main_topic": plan.research_goal.main_topic,
            "max_rounds": int(self._settings.research_followup_rounds),
            "max_tasks_per_round": int(self._settings.research_followup_max_tasks),
            "rounds": rounds,
        }
        (run_dir / filename).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    async def run(self, research_goal: str) -> PipelineRunResult:
        errors: list[str] = []
        run_dir = self._allocate_run_dir()
        logger.info("Run directory: %s", run_dir)

        print("[STEP] Building research plan", flush=True)
        plan = await self._orchestrator.create_plan(research_goal)
        _print_research_plan(plan)
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
        coverages = [v.coverage for v in validated.results]
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
            "coverage_sufficient": coverages.count("sufficient"),
            "coverage_partial": coverages.count("partial"),
            "coverage_insufficient": coverages.count("insufficient"),
            "total_sources_cited": source_count,
            "models": {
                "orchestrator": self._settings.orchestrator_model,
                "gemini_search": self._settings.gemini_search_model,
                "openai_search": self._settings.openai_search_model,
                "research_validator": self._settings.research_validator_model,
                "research_index": self._settings.research_index_model,
            },
            "main_topic": plan.research_goal.main_topic,
            "followup_rounds_enabled": int(self._settings.research_followup_rounds),
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
        """Continue a pipeline.input run: write ``05_``–``08_`` artifacts beside ``04_``."""
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
            print("[STEP] Building research plan", flush=True)
            plan = await self._orchestrator.create_plan(research_goal)
            plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        _print_research_plan(plan)

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
