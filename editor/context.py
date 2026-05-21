"""EditorContext — loads all pipeline artifacts needed to write the manuscript."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from paper_input.image_registry import apply_image_exclusions, excluded_image_paths, usable_images

from .schemas import CitationEntry, IeeeFormat


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class ResearchArtifact:
    """One validated research task file (06_research + 07_validation pair)."""

    __slots__ = (
        "slug", "task", "agent_id", "summary", "sources_raw",
        "verdict", "validation_issues",
    )

    def __init__(
        self,
        slug: str,
        task: str,
        agent_id: str,
        summary: str,
        sources_raw: list[dict[str, Any]],
        verdict: str,
        validation_issues: list[str],
    ) -> None:
        self.slug = slug
        self.task = task
        self.agent_id = agent_id
        self.summary = summary
        self.sources_raw = sources_raw
        self.verdict = verdict
        self.validation_issues = validation_issues

    @property
    def is_trusted(self) -> bool:
        return self.verdict in ("pass", "warn")

    def short_summary(self, limit: int = 500) -> str:
        return self.summary[:limit]


class ManuscriptData:
    """Structured content from 04_final_standardized.json."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @property
    def summary(self) -> str:
        return str(self._data.get("summary") or "")

    @property
    def key_claims(self) -> list[str]:
        return [str(c) for c in (self._data.get("key_claims") or []) if isinstance(c, str)]

    @property
    def text_blocks(self) -> list[dict[str, Any]]:
        return [b for b in (self._data.get("text_blocks") or []) if isinstance(b, dict)]

    @property
    def images(self) -> list[dict[str, Any]]:
        return [i for i in (self._data.get("images") or []) if isinstance(i, dict)]

    @property
    def excluded_images(self) -> list[dict[str, Any]]:
        return [e for e in (self._data.get("excluded_images") or []) if isinstance(e, dict)]

    def excluded_paths(self) -> frozenset[str]:
        return excluded_image_paths(self._data)

    def usable_images(self) -> list[dict[str, Any]]:
        return usable_images(self._data)

    @property
    def mismatch_flags(self) -> list[dict[str, Any]]:
        return [f for f in (self._data.get("mismatch_flags") or []) if isinstance(f, dict)]

    @property
    def duplicate_images(self) -> list[dict[str, Any]]:
        return [d for d in (self._data.get("duplicate_images") or []) if isinstance(d, dict)]

    def experimental_design_bullets(self) -> list[str]:
        """Pull method / design lines from text_blocks (mirrors research.manuscript_context logic)."""
        from research.manuscript_context import extract_experimental_design
        return extract_experimental_design(self._data)

    def get_text_block(self, path_fragment: str) -> str:
        """Return combined technical_analysis from blocks whose path contains fragment."""
        out: list[str] = []
        for block in self.text_blocks:
            if path_fragment.lower() in str(block.get("relative_path") or "").lower():
                out.append(str(block.get("technical_analysis") or ""))
        return "\n\n".join(filter(None, out))


class EditorContext:
    """
    Everything the editor orchestrator and section writers need from disk.

    Loaded once per pipeline run via :func:`load_editor_context`.
    """

    def __init__(
        self,
        *,
        execution_dir: Path,
        input_root: Path | None,
        manuscript: ManuscriptData,
        research_artifacts: list[ResearchArtifact],
        research_index_md: str,
        paper_meta: dict[str, Any],
        ieee_format: IeeeFormat,
    ) -> None:
        self.execution_dir = execution_dir
        self.input_root = input_root  # original paper folder (examples/neuro_stability)
        self.manuscript = manuscript
        self.research_artifacts = research_artifacts
        self.research_index_md = research_index_md
        self.paper_meta = paper_meta
        self.ieee_format = ieee_format

    @property
    def trusted_artifacts(self) -> list[ResearchArtifact]:
        return [a for a in self.research_artifacts if a.is_trusted]

    @property
    def title(self) -> str:
        return str(self.paper_meta.get("project_title") or "")

    @property
    def authors(self) -> list[dict[str, Any]]:
        return list(self.paper_meta.get("authors") or [])

    @property
    def target_journal(self) -> str:
        return str(self.paper_meta.get("target_journal") or "")

    @property
    def citation_pool(self) -> list[CitationEntry]:
        """Union of sources from all trusted research artifacts, deduplicated by title."""
        seen: set[str] = set()
        pool: list[CitationEntry] = []
        idx = 1
        for artifact in self.trusted_artifacts:
            for src in artifact.sources_raw:
                title = str(src.get("title") or "").strip()
                if not title:
                    continue
                key = title.lower()[:80]
                if key in seen:
                    continue
                seen.add(key)
                authors = str(src.get("authors") or "")
                year = src.get("year") or ""
                journal = str(src.get("journal") or "")
                doi = str(src.get("doi") or "")
                citekey = _make_citekey(authors, year, idx)
                pool.append(CitationEntry(
                    citekey=citekey,
                    authors=authors,
                    year=year,
                    title=title,
                    journal=journal,
                    doi=doi,
                ))
                idx += 1
        return pool

    def artifact_by_slug(self, slug: str) -> ResearchArtifact | None:
        for a in self.research_artifacts:
            if a.slug == slug:
                return a
        return None

    def to_orchestrator_block(self) -> str:
        """Compact context string passed to the editor orchestrator."""
        lines: list[str] = []
        lines.append(f"Title: {self.title}")
        lines.append(f"Authors: {', '.join(a.get('name', '') for a in self.authors)}")
        lines.append(f"Target journal: {self.target_journal}")
        lines.append(f"IEEE format: {self.ieee_format}")
        lines.append("")
        lines.append("## Manuscript summary")
        lines.append(self.manuscript.summary[:1200])
        lines.append("")
        lines.append("## Key quantitative claims")
        for claim in self.manuscript.key_claims[:12]:
            lines.append(f"  - {claim}")
        lines.append("")
        lines.append("## Mismatch flags (figure–text issues)")
        for flag in self.manuscript.mismatch_flags:
            img = flag.get("image_path", "")
            issue = flag.get("issue", "")
            sev = flag.get("severity", "note")
            lines.append(f"  - [{sev}] {img}: {issue}")
        lines.append("")
        lines.append("## Trusted research artifacts")
        for art in self.trusted_artifacts:
            lines.append(f"  [{art.verdict.upper()}] {art.slug}")
            lines.append(f"    task: {art.task[:100]}")
        lines.append("")
        lines.append("## Images available for reuse_path (usable only — do NOT use excluded paths)")
        usable = self.manuscript.usable_images()
        for img in usable:
            path = img.get("relative_path") or img.get("image_path") or ""
            desc = img.get("description") or ""
            lines.append(f"  - {path}: {str(desc)[:80]}")
        if not usable:
            lines.append("  (no usable images — generate new figures with matplotlib instead)")
        if self.manuscript.excluded_images:
            lines.append("")
            lines.append("## Excluded images (NEVER reuse_path or cite as manuscript figures)")
            for ex in self.manuscript.excluded_images:
                path = ex.get("path") or ""
                reason = ex.get("reason") or "excluded"
                issue = str(ex.get("issue") or "")[:100]
                lines.append(f"  - {path} [{reason}]: {issue}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _make_citekey(authors: str, year: Any, idx: int) -> str:
    first_last = (authors.split(",")[0].split(" ")[-1]).lower()
    first_last = re.sub(r"[^\w]", "", first_last) or f"ref{idx}"
    return f"{first_last}{year}"


def _load_validation_map(validation_dir: Path) -> dict[str, dict[str, Any]]:
    """slug → validation record."""
    result: dict[str, dict[str, Any]] = {}
    if not validation_dir.is_dir():
        return result
    for vf in validation_dir.glob("*.validation.json"):
        try:
            data = json.loads(vf.read_text(encoding="utf-8"))
            slug = str(data.get("slug") or vf.stem.replace(".validation", ""))
            result[slug] = data
        except Exception:
            pass
    return result


def _load_research_artifacts(
    research_dir: Path,
    validation_map: dict[str, dict[str, Any]],
) -> list[ResearchArtifact]:
    manifest_path = research_dir / "manifest.json"
    if not manifest_path.is_file():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    artifacts: list[ResearchArtifact] = []
    for entry in manifest.get("tasks") or []:
        slug = str(entry.get("slug") or "")
        filename = str(entry.get("filename") or "")
        agent_id = str(entry.get("agent_id") or "")
        task = str(entry.get("task") or "")

        task_path = research_dir / filename
        summary = ""
        sources_raw: list[dict[str, Any]] = []
        if task_path.is_file():
            try:
                task_data = json.loads(task_path.read_text(encoding="utf-8"))
                summary = str(task_data.get("summary") or "")
                # sources live in raw_notes as JSON string
                raw_notes_str = task_data.get("raw_notes") or ""
                if raw_notes_str:
                    try:
                        raw_notes = json.loads(raw_notes_str)
                        sources_raw = [
                            s for s in (raw_notes.get("sources") or [])
                            if isinstance(s, dict)
                        ]
                    except Exception:
                        pass
            except Exception:
                pass

        val = validation_map.get(slug) or {}
        verdict = str(val.get("verdict") or "unknown")
        issues = [str(i) for i in (val.get("issues") or [])]

        artifacts.append(ResearchArtifact(
            slug=slug,
            task=task,
            agent_id=agent_id,
            summary=summary,
            sources_raw=sources_raw,
            verdict=verdict,
            validation_issues=issues,
        ))
    return artifacts


def load_editor_context(
    execution_dir: Path,
    *,
    ieee_format: IeeeFormat = "journal",
) -> EditorContext:
    """
    Load EditorContext from an execution directory.

    Expects files produced by the full autopaper pipeline:
      - ``04_final_standardized.json``
      - ``06_research/`` directory + ``manifest.json``
      - ``07_validation/`` directory
      - ``08_research_index.md``
      - The originating paper folder's ``metadata/paper_meta.json`` is resolved
        from ``00_run_manifest.json`` when available.
    """
    # --- 04 ---
    final_path = execution_dir / "04_final_standardized.json"
    if not final_path.is_file():
        raise FileNotFoundError(f"04_final_standardized.json not found in {execution_dir}")
    manuscript_data = json.loads(final_path.read_text(encoding="utf-8"))
    manuscript_data = apply_image_exclusions(manuscript_data)
    manuscript = ManuscriptData(manuscript_data)

    # --- 07 validation ---
    validation_dir = execution_dir / "07_validation"
    validation_map = _load_validation_map(validation_dir)

    # --- 06 research ---
    research_dir = execution_dir / "06_research"
    artifacts = _load_research_artifacts(research_dir, validation_map)

    # --- 08 index ---
    index_path = execution_dir / "08_research_index.md"
    research_index_md = ""
    if index_path.is_file():
        research_index_md = index_path.read_text(encoding="utf-8")

    # --- paper_meta.json + input_root ---
    paper_meta: dict[str, Any] = {}
    input_root: Path | None = None
    run_manifest_path = execution_dir / "00_run_manifest.json"
    if run_manifest_path.is_file():
        try:
            rm = json.loads(run_manifest_path.read_text(encoding="utf-8"))
            input_root_str = rm.get("input_root") or ""
            if input_root_str:
                input_root = Path(input_root_str)
                meta_path = input_root / "metadata" / "paper_meta.json"
                if meta_path.is_file():
                    paper_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    return EditorContext(
        execution_dir=execution_dir,
        input_root=input_root,
        manuscript=manuscript,
        research_artifacts=artifacts,
        research_index_md=research_index_md,
        paper_meta=paper_meta,
        ieee_format=ieee_format,
    )
