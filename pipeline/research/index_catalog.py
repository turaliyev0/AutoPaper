"""Deterministic research index Markdown (catalog from manifests)."""

from __future__ import annotations

import re
from typing import Any

from .manuscript_context import ManuscriptContext
from .schemas import (
    GatheredResearchBundle,
    OrchestratorPlan,
    ValidatedResearchBundle,
    ValidatedTaskResult,
)

_DOI_NOTICE = """## Important: Manual DOI verification required

The automated validator checks that citations are **well-formatted** (author, year, title present).
It **cannot** verify that a DOI resolves to the correct paper — language models frequently produce
plausible-looking but incorrect DOIs (wrong journal suffix, wrong issue/page numbers), and may
describe a paper's content incorrectly or confuse two papers by the same first author.

**Before using any cited source in a manuscript, independently verify:**
1. The DOI resolves to the correct paper (paste it into [doi.org](https://doi.org)).
2. The paper's actual content matches the description in the research file.
3. The quantitative values attributed to the paper (threshold values, sample sizes, durations, etc.) appear in the paper itself.

Validation status `pass` or `source_quality: clear` means the citation format is acceptable — not that the citations are correct."""


def _table_cell(text: str, *, max_len: int = 120) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    cleaned = cleaned.replace("|", "\\|")
    if len(cleaned) > max_len:
        return cleaned[: max_len - 1] + "…"
    return cleaned


def _short_task(task: str, *, max_len: int = 90) -> str:
    return _table_cell(task, max_len=max_len)


def _validation_by_slug(validated: ValidatedResearchBundle) -> dict[str, ValidatedTaskResult]:
    return {v.slug: v for v in validated.results}


def _preview_for_task(
    research_manifest: dict[str, Any],
    previews: dict[str, str],
) -> dict[str, str]:
    out: dict[str, str] = dict(previews)
    for entry in research_manifest.get("tasks") or []:
        slug = str(entry.get("slug") or "")
        if slug and entry.get("content_preview"):
            out[slug] = str(entry["content_preview"])
    return out


def _match_outputs_to_slugs(
    required_outputs: list[str],
    research_manifest: dict[str, Any],
) -> list[tuple[str, list[str]]]:
    rows: list[tuple[str, list[str]]] = []
    tasks = research_manifest.get("tasks") or []
    for output in required_outputs:
        output_l = output.lower()
        tokens = [t for t in re.findall(r"[a-z0-9]{4,}", output_l) if len(t) >= 4]
        matched: list[str] = []
        for entry in tasks:
            slug = str(entry.get("slug") or "")
            task = str(entry.get("task") or "").lower()
            haystack = f"{slug} {task}"
            if any(tok in haystack for tok in tokens[:8]):
                rel = f"{research_manifest.get('research_dir', '06_research')}/{entry.get('filename', slug + '.json')}"
                matched.append(rel)
        if not matched:
            matched = ["none clearly matched"]
        rows.append((output, matched))
    return rows


def _claims_coverage(
    key_claims: list[str],
    research_manifest: dict[str, Any],
    validated: ValidatedResearchBundle,
) -> list[tuple[str, list[str]]]:
    rows: list[tuple[str, list[str]]] = []
    tasks = research_manifest.get("tasks") or []
    val_by_slug = _validation_by_slug(validated)
    research_dir = str(research_manifest.get("research_dir") or "06_research")

    for claim in key_claims:
        claim_l = claim.lower()
        tokens = [t for t in re.findall(r"[a-z0-9]{3,}", claim_l) if len(t) >= 4][:10]
        matched: list[str] = []
        for entry in tasks:
            slug = str(entry.get("slug") or "")
            task = str(entry.get("task") or "").lower()
            overview = (val_by_slug.get(slug).overview if slug in val_by_slug else "").lower()
            haystack = f"{task} {overview}"
            hits = sum(1 for tok in tokens if tok in haystack)
            if hits >= max(1, len(tokens) // 4):
                fname = str(entry.get("filename") or f"{slug}.json")
                matched.append(f"{research_dir}/{fname}")
        if not matched:
            matched = ["not addressed"]
        rows.append((claim, matched))
    return rows


def render_research_index_markdown(
    plan: OrchestratorPlan,
    bundle: GatheredResearchBundle,
    validated: ValidatedResearchBundle,
    *,
    research_manifest: dict[str, Any],
    validation_manifest: dict[str, Any],
    previews: dict[str, str],
    manuscript: ManuscriptContext | None = None,
) -> str:
    """Build the research catalog Markdown from structured manifests (no LLM)."""
    topic = plan.research_goal.main_topic.strip()
    research_dir = str(research_manifest.get("research_dir") or "06_research")
    validation_dir = str(validation_manifest.get("validation_dir") or "07_validation")

    verdicts = [v.verdict for v in validated.results]
    pass_n = verdicts.count("pass")
    warn_n = verdicts.count("warn")
    fail_n = verdicts.count("fail")
    success_n = sum(1 for r in bundle.results if r.success)
    total_n = len(bundle.results)

    val_by_slug = _validation_by_slug(validated)
    preview_map = _preview_for_task(research_manifest, previews)

    lines: list[str] = [
        f"# Research Run Catalog: {topic}",
        "",
        "## Run overview",
        "",
        f"- Search tasks executed: {total_n} ({success_n} succeeded)",
        f"- Validation verdicts: {pass_n} pass, {warn_n} warn, {fail_n} fail",
        f"- Research files: `{research_dir}/`",
        f"- Validation files: `{validation_dir}/`",
        "",
        _DOI_NOTICE,
        "",
        "## Research artifacts",
        "",
        "| File | Agent | Subtask (short) | Success | Validation | One-line contents |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for entry in research_manifest.get("tasks") or []:
        slug = str(entry.get("slug") or "")
        filename = str(entry.get("filename") or f"{slug}.json")
        agent = str(entry.get("agent_id") or "")
        task = str(entry.get("task") or "")
        success = "yes" if entry.get("success") else "no"
        val = val_by_slug.get(slug)
        verdict = val.verdict if val else "n/a"
        preview = preview_map.get(slug) or (val.overview if val else "") or "-"
        rel_path = f"{research_dir}/{filename}"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_table_cell(rel_path, max_len=80)}`",
                    _table_cell(agent, max_len=20),
                    _short_task(task),
                    success,
                    verdict,
                    _table_cell(preview, max_len=100),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Validation summary", ""])
    warn_fail = [v for v in validated.results if v.verdict in ("warn", "fail")]
    if not warn_fail:
        lines.append("- All tasks passed validation.")
    else:
        for v in warn_fail:
            lines.append(f"- **{v.verdict}** — `{research_dir}/{v.research_filename}` ({v.agent_id})")
            for issue in v.issues[:4]:
                lines.append(f"  - {_table_cell(issue, max_len=200)}")

    lines.extend(["", "## Required outputs map", ""])
    for output, files in _match_outputs_to_slugs(plan.research_goal.required_outputs, research_manifest):
        lines.append(f"- **{_table_cell(output, max_len=160)}**")
        for f in files:
            lines.append(f"  - `{f}`")

    key_claims = list(manuscript.key_claims) if manuscript else []
    if key_claims:
        lines.extend(["", "## Key claims coverage", ""])
        for claim, files in _claims_coverage(key_claims, research_manifest, validated):
            lines.append(f"- \"{_table_cell(claim, max_len=160)}\"")
            for f in files:
                lines.append(f"  - `{f}`")

    lines.extend(["", "## Limitations", ""])
    failed_search = [r for r in bundle.results if not r.success]
    if failed_search:
        lines.append("- Failed search tasks:")
        for r in failed_search:
            lines.append(f"  - [{r.agent_id}] {_table_cell(r.task, max_len=120)}")
            if r.error:
                lines.append(f"    - Error: {_table_cell(r.error, max_len=120)}")
    else:
        lines.append("- All search tasks completed successfully.")

    if warn_fail:
        lines.append(f"- {len(warn_fail)} validation task(s) returned warn/fail — review before citing sources.")

    if key_claims:
        not_addressed = sum(
            1
            for _, files in _claims_coverage(key_claims, research_manifest, validated)
            if files == ["not addressed"]
        )
        if not_addressed:
            lines.append(f"- {not_addressed} manuscript key claim(s) not clearly addressed by any research file.")

    return "\n".join(lines).strip() + "\n"
