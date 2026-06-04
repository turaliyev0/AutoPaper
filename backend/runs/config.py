"""Pipeline subprocess options for API-started runs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PipelineRunConfig:
    full_research: bool = True
    ieee_edit: bool = True
    log_editor: bool = True
    ingest_only: bool = False
    mismatch_policy: str = "continue"  # continue | strict
    completeness_policy: str = "auto"  # auto | continue | strict
