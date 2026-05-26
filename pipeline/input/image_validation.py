"""Image validation gates: fatal unreadable images vs figure–text mismatch warnings."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .agents.gemini_client import load_images_from_bundle

_builtin_input = __import__("builtins").input

DISK_READ_DETAIL = "Could not read or encode image file (corrupt, missing, or truncated)."

# Severities that require user acknowledgment before continuing (non-strict auto mode).
_MISMATCH_PROMPT_SEVERITIES = frozenset({"likely_mismatch", "unclear", "weak_overlap"})


class MismatchPolicy(str, Enum):
    """How to handle joiner ``mismatch_flags``."""

    AUTO = "auto"  # prompt on TTY, abort otherwise
    CONTINUE = "continue"  # always proceed
    ABORT = "abort"  # always stop (``--strict``)


@dataclass(frozen=True)
class ImageProblem:
    relative_path: str
    kind: str  # disk_read_failed | vision_unreadable
    detail: str


@dataclass(frozen=True)
class MismatchWarning:
    image_path: str
    severity: str
    issue: str
    text_paths: tuple[str, ...] = ()


class ImageValidationError(Exception):
    """One or more images could not be used; pipeline must not continue."""

    def __init__(self, problems: list[ImageProblem]) -> None:
        self.problems = problems
        super().__init__(format_fatal_message(problems))


class MismatchAbortError(Exception):
    """Figure–text mismatches were not accepted; pipeline stops before research."""

    def __init__(self, warnings: list[MismatchWarning], *, reason: str) -> None:
        self.warnings = warnings
        self.reason = reason
        super().__init__(format_mismatch_message(warnings, reason=reason))


def collect_fatal_image_problems(
    bundle: dict[str, Any],
    cleaned_images: dict[str, Any],
) -> list[ImageProblem]:
    """
    Fatal when the project lists images under ``images/`` and any cannot be used.

    Sources: disk read/encode failure and Vision ``readable: false``.
    """
    expected = [p for p in bundle.get("image_paths") or [] if isinstance(p, str)]
    if not expected:
        return []

    _, disk_failed = load_images_from_bundle(bundle)
    disk_failed_set = set(disk_failed)

    problems: list[ImageProblem] = []
    for rel in disk_failed:
        problems.append(
            ImageProblem(rel, "disk_read_failed", DISK_READ_DETAIL),
        )

    seen = {p.relative_path for p in problems}
    for entry in cleaned_images.get("images") or []:
        if not isinstance(entry, dict):
            continue
        rel = entry.get("relative_path")
        if not isinstance(rel, str) or rel in seen:
            continue
        if entry.get("readable", True) is False:
            detail = str(entry.get("description") or "").strip()
            if not detail:
                detail = "Vision agent marked this figure as unreadable."
            problems.append(ImageProblem(rel, "vision_unreadable", detail))
            seen.add(rel)

    # Listed on disk but absent from vision output (should not happen).
    vision_paths = {
        e.get("relative_path")
        for e in cleaned_images.get("images") or []
        if isinstance(e, dict) and isinstance(e.get("relative_path"), str)
    }
    for rel in expected:
        if rel not in vision_paths and rel not in disk_failed_set:
            problems.append(
                ImageProblem(
                    rel,
                    "vision_unreadable",
                    "No vision output was produced for this image.",
                ),
            )

    return sorted(problems, key=lambda p: p.relative_path.lower())


def assert_images_usable(
    bundle: dict[str, Any],
    cleaned_images: dict[str, Any],
) -> None:
    problems = collect_fatal_image_problems(bundle, cleaned_images)
    if problems:
        raise ImageValidationError(problems)


def collect_mismatch_warnings(final: dict[str, Any]) -> list[MismatchWarning]:
    out: list[MismatchWarning] = []
    for raw in final.get("mismatch_flags") or []:
        if not isinstance(raw, dict):
            continue
        severity = str(raw.get("severity") or "unclear").strip().lower()
        if severity not in _MISMATCH_PROMPT_SEVERITIES:
            continue
        image_path = raw.get("image_path")
        issue = raw.get("issue")
        if not isinstance(image_path, str) or not isinstance(issue, str):
            continue
        paths = raw.get("text_paths") or []
        text_paths = tuple(p for p in paths if isinstance(p, str))
        out.append(
            MismatchWarning(
                image_path=image_path,
                severity=severity,
                issue=issue.strip(),
                text_paths=text_paths,
            ),
        )
    return sorted(out, key=lambda w: (w.severity, w.image_path.lower()))


def format_fatal_message(problems: list[ImageProblem]) -> str:
    lines = [
        "Image validation failed — fix the files under your paper project's images/ folder and re-run.",
        "",
    ]
    for p in problems:
        kind_label = "disk" if p.kind == "disk_read_failed" else "vision"
        lines.append(f"  [{kind_label}] {p.relative_path}")
        lines.append(f"    {p.detail}")
        lines.append("")
    lines.append("Replace or re-export the images, then run autopaper again.")
    return "\n".join(lines).rstrip()


def format_mismatch_message(
    warnings: list[MismatchWarning],
    *,
    reason: str | None = None,
) -> str:
    lines = ["Figure–text mismatch warnings (from joiner):", ""]
    for w in warnings:
        lines.append(f"  [{w.severity}] {w.image_path}")
        lines.append(f"    {w.issue}")
        if w.text_paths:
            lines.append(f"    text: {', '.join(w.text_paths)}")
        lines.append("")
    if reason:
        lines.append(reason)
    return "\n".join(lines).rstrip()


def resolve_mismatch_continuation(
    warnings: list[MismatchWarning],
    *,
    policy: MismatchPolicy = MismatchPolicy.AUTO,
    is_tty: bool | None = None,
) -> None:
    """
    Raise :class:`MismatchAbortError` when the pipeline must stop.

    ``AUTO``: prompt on TTY; abort when not a TTY (use ``--force-continue-on-mismatch`` in scripts).
    """
    if not warnings:
        return

    if policy is MismatchPolicy.CONTINUE:
        return

    if policy is MismatchPolicy.ABORT:
        raise MismatchAbortError(
            warnings,
            reason="Stopped due to figure–text mismatches (--strict).",
        )

    tty = sys.stdin.isatty() if is_tty is None else is_tty
    if not tty:
        raise MismatchAbortError(
            warnings,
            reason=(
                "Stopped due to figure–text mismatches (non-interactive). "
                "Pass --force-continue-on-mismatch to proceed, or fix images/text."
            ),
        )

    print(format_mismatch_message(warnings), file=sys.stderr)
    print(file=sys.stderr)
    while True:
        answer = _builtin_input("Continue anyway? [y/N]: ").strip().lower()
        if answer in ("y", "yes"):
            return
        if answer in ("n", "no", ""):
            raise MismatchAbortError(
                warnings,
                reason="Stopped: you chose not to continue after mismatch warnings.",
            )
        print("Please answer y or n.", file=sys.stderr)
