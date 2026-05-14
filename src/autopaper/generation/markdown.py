from __future__ import annotations

from pathlib import Path

from autopaper.inputs import PaperDraft


def render_markdown(draft: PaperDraft) -> str:
    lines = [f"# {draft.title}\n"]
    for s in draft.sections:
        lines.append(f"\n## {s.section.value.replace('_', ' ').title()}\n\n{s.content}\n")
    if draft.peer_review_notes:
        lines.append("\n## Peer review (internal)\n\n" + draft.peer_review_notes + "\n")
    if draft.validation_report:
        lines.append("\n## Validation report (internal)\n\n" + draft.validation_report + "\n")
    return "".join(lines)


def write_markdown(draft: PaperDraft, path: str | Path) -> None:
    Path(path).write_text(render_markdown(draft), encoding="utf-8")
