"""Interactive and API pause/resume when input is incomplete before research."""

from __future__ import annotations

import json
import sys
from enum import Enum
from pathlib import Path
from typing import Any

from .completeness import CompletenessReport, InputGap, analyze_completeness

_builtin_input = __import__("builtins").input

INPUT_GAPS_FILENAME = "04_input_gaps.json"
INPUT_GAPS_EXIT_CODE = 3


class CompletenessPolicy(str, Enum):
    AUTO = "auto"  # prompt on TTY; pause (exit 3) when non-interactive
    CONTINUE = "continue"  # skip gate
    STRICT = "strict"  # abort if blocking gaps


class InputCompletenessPause(Exception):
    """Pipeline stops before research; user must supply supplements."""

    def __init__(
        self,
        report: CompletenessReport,
        *,
        run_path: Path,
        input_root: Path,
        reason: str,
    ) -> None:
        self.report = report
        self.run_path = run_path
        self.input_root = input_root
        self.reason = reason
        super().__init__(format_pause_message(report, reason=reason))


class InputCompletenessAbortError(Exception):
    """Blocking gaps and policy forbids continuing."""

    def __init__(self, report: CompletenessReport, *, reason: str) -> None:
        self.report = report
        self.reason = reason
        super().__init__(format_pause_message(report, reason=reason))


def write_gaps_file(run_path: Path, report: CompletenessReport) -> Path:
    path = run_path / INPUT_GAPS_FILENAME
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_gaps_file(run_path: Path) -> CompletenessReport | None:
    path = run_path / INPUT_GAPS_FILENAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    gaps: list[InputGap] = []
    for raw in data.get("gaps") or []:
        if not isinstance(raw, dict):
            continue
        gid = str(raw.get("id") or "").strip()
        if not gid:
            continue
        sev = str(raw.get("severity") or "recommended").lower()
        if sev not in ("required", "recommended"):
            sev = "recommended"
        gaps.append(
            InputGap(
                id=gid,
                severity=sev,  # type: ignore[arg-type]
                question=str(raw.get("question") or ""),
                hint=str(raw.get("hint") or ""),
                reason=str(raw.get("reason") or ""),
                target_path=str(raw.get("target_path") or f"details/{gid}.txt"),
            )
        )
    return CompletenessReport(gaps=gaps)


def format_pause_message(report: CompletenessReport, *, reason: str | None = None) -> str:
    lines = [
        "Input completeness check — additional information needed before research:",
        "",
    ]
    for g in report.gaps:
        tag = "REQUIRED" if g.severity == "required" else "optional"
        lines.append(f"  [{tag}] {g.id}")
        lines.append(f"    {g.reason}")
        lines.append(f"    Q: {g.question}")
        if g.hint:
            lines.append(f"    Hint: {g.hint}")
        lines.append("")
    if reason:
        lines.append(reason)
    return "\n".join(lines).rstrip()


def _gap_targets(report: CompletenessReport) -> dict[str, str]:
    return {g.id: g.target_path for g in report.gaps}


def collect_answers_interactive(report: CompletenessReport) -> dict[str, str]:
    """Prompt on TTY for each gap; empty line skips optional gaps only."""
    answers: dict[str, str] = {}
    print(format_pause_message(report), file=sys.stderr)
    print(file=sys.stderr)
    for gap in report.gaps:
        optional = gap.severity == "recommended"
        label = "optional" if optional else "required"
        print(f"--- {gap.id} ({label}) ---", file=sys.stderr)
        print(gap.question, file=sys.stderr)
        if gap.hint:
            print(f"Hint: {gap.hint}", file=sys.stderr)
        while True:
            print("(Enter text; blank line to finish multi-line input)", file=sys.stderr)
            chunks: list[str] = []
            while True:
                line = _builtin_input("> " if not chunks else "> ")
                if line.strip() == "" and chunks:
                    break
                if line.strip() == "" and not chunks:
                    break
                chunks.append(line)
            text = "\n".join(chunks).strip()
            if text:
                answers[gap.id] = text
                break
            if optional:
                break
            print("This field is required — please provide an answer.", file=sys.stderr)
    return answers


def resolve_completeness_continuation(
    final: dict[str, Any],
    bundle: dict[str, Any],
    *,
    input_root: Path,
    run_path: Path,
    policy: CompletenessPolicy = CompletenessPolicy.AUTO,
    is_tty: bool | None = None,
    prefilled_answers: dict[str, str] | None = None,
) -> dict[str, str] | None:
    """
    Check completeness after step 04.

    Returns answers dict if user supplied data and pipeline should continue.
    Returns None if no gaps.
    Raises InputCompletenessPause when non-interactive and gaps remain.
    Raises InputCompletenessAbortError when policy is STRICT.
    """
    report = analyze_completeness(final, bundle)
    if not report.gaps:
        return None

    if policy is CompletenessPolicy.CONTINUE:
        return None

    write_gaps_file(run_path, report)

    if policy is CompletenessPolicy.STRICT and report.has_blocking_gaps:
        raise InputCompletenessAbortError(
            report,
            reason="Stopped due to incomplete input (--strict-input-gaps).",
        )

    if prefilled_answers:
        answers = {k: v for k, v in prefilled_answers.items() if str(v).strip()}
        missing_required = [
            g.id
            for g in report.gaps
            if g.severity == "required" and g.id not in answers
        ]
        if missing_required:
            raise InputCompletenessAbortError(
                report,
                reason=f"Missing required answers: {', '.join(missing_required)}",
            )
        return answers

    tty = sys.stdin.isatty() if is_tty is None else is_tty
    if not tty:
        print(f"Run directory: {run_path.resolve()}", flush=True)
        print(
            f"[STEP] Paused — input gaps saved to {INPUT_GAPS_FILENAME}",
            flush=True,
        )
        raise InputCompletenessPause(
            report,
            run_path=run_path,
            input_root=input_root,
            reason=(
                "Pipeline paused: input is incomplete (non-interactive). "
                "Submit supplements via API or re-run with answers, then continue."
            ),
        )

    answers = collect_answers_interactive(report)
    missing_required = [
        g.id for g in report.gaps if g.severity == "required" and g.id not in answers
    ]
    if missing_required:
        raise InputCompletenessAbortError(
            report,
            reason=f"Required gaps not answered: {', '.join(missing_required)}",
        )
    return answers if answers else None


def gap_targets_from_report(report: CompletenessReport) -> dict[str, str]:
    return _gap_targets(report)
