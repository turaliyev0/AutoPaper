"""Normalize research-source author strings for IEEEtran BibTeX."""

from __future__ import annotations

import re

_ET_AL = re.compile(r",?\s*et\s+al\.?", re.IGNORECASE)
_MULTI_SPACE = re.compile(r"\s+")
# Parser artifacts like "S. C. E. S. E. A. Ereifej, E. S. et al."
_GARBAGE_INITIAL_RUN = re.compile(r"(?:\b[A-Z]\.\s*){4,}")
# Last name + 1–3 uppercase initials without comma: "Lewicki MS", "Chung JE"
_LAST_INITIALS = re.compile(r"^([A-Za-z][A-Za-z\-']+)\s+([A-Z]{1,3})$")
# "Salatino JW" with optional trailing junk already stripped
# "Kozai TDY" three initials


def _initials_dotted(letters: str) -> str:
    return " ".join(f"{c}." for c in letters)


def _collapse_garbage_author_run(s: str) -> str:
    """Reduce over-parsed initial chains to 'Surname and others'."""
    if not _GARBAGE_INITIAL_RUN.search(s):
        return s
    m = re.search(r"\b([A-Z][A-Za-z\-']{2,})\b(?:\s*,|\s+et\s+al)", s)
    if m:
        return f"{m.group(1)} and others"
    words = [w for w in re.split(r"[\s,]+", s) if w and not re.fullmatch(r"[A-Z]\.?", w)]
    if words:
        return f"{words[-1]} and others"
    return "and others"


def normalize_bibtex_authors(raw: str) -> str:
    """
    Convert LLM-style author strings to BibTeX-safe ``author = {...}`` values.

    Fixes common failures: ``et al.`` → ``and others``, ``&`` → ``and``,
    ``Lewicki MS`` → ``Lewicki, M. S.``
    """
    s = _MULTI_SPACE.sub(" ", (raw or "").strip())
    if not s:
        return s

    s = _collapse_garbage_author_run(s)
    s = s.replace("&", " and ")

    if _ET_AL.search(s):
        s = _ET_AL.sub("", s).rstrip(", ").strip()
        if s and " and others" not in s.lower():
            s = f"{s} and others"

    m = _LAST_INITIALS.match(s)
    if m:
        last, ini = m.group(1), m.group(2)
        return f"{last}, {_initials_dotted(ini)}"

    # "Last, FI et al" already handled; "Last FI, Coauthor" rare — leave if comma present
    return s
