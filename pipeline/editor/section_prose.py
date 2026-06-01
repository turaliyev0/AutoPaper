"""Deterministic cleanup of section writer LaTeX (forbidden meta-commentary)."""

from __future__ import annotations

import re

# Whole-sentence removals — pipeline must never admit missing input in the paper text.
_BANNED_SENTENCE = re.compile(
    r"[^.]*\b(?:"
    r"not provided in the (?:experimental )?protocol|"
    r"was not (?:provided|detailed) in the (?:provided )?experimental (?:protocol|design)|"
    r"provided experimental (?:protocol|design) did not|"
    r"the (?:provided )?experimental (?:protocol|design) did not (?:explicitly )?detail|"
    r"typically involving weekly recording|"
    r"typically fabricated using"
    r")[^.]*\.\s*",
    re.IGNORECASE | re.DOTALL,
)

# Phrase-level softening when sentence split fails
_BANNED_PHRASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bnot provided in the (?:experimental )?protocol\b", re.I), ""),
    (re.compile(r"\bprovided experimental (?:protocol|design)\b", re.I), "the study design"),
    (re.compile(r"\btypically involving\b", re.I), "with"),
    (re.compile(r"\btypically fabricated\b", re.I), "were fabricated"),
]


def sanitize_section_latex(latex: str) -> str:
    """Remove admissions of missing protocol / pipeline gaps from generated prose."""
    text = (latex or "").strip()
    if not text:
        return text
    prev = None
    while prev != text:
        prev = text
        text = _BANNED_SENTENCE.sub("", text)
    for pattern, repl in _BANNED_PHRASES:
        text = pattern.sub(repl, text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"  +", " ", text)
    return text.strip()
