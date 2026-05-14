from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _default_prompts_dir() -> Path:
    return Path(__file__).resolve().parent


def load_manifest(*, prompts_dir: Path | None = None) -> dict[str, dict[str, str]]:
    """Load manifest.json: each group maps slot name -> relative path (one file = one prompt version)."""
    base = prompts_dir or _default_prompts_dir()
    path = base / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest.json must be a JSON object")
    out: dict[str, dict[str, str]] = {}
    for group, slots in data.items():
        if not isinstance(slots, dict):
            continue
        cleaned: dict[str, str] = {}
        for slot, rel in slots.items():
            if isinstance(rel, str):
                cleaned[str(slot)] = rel
        out[str(group)] = cleaned
    return out


def load_assistants_config(*, prompts_dir: Path | None = None) -> dict[str, Any]:
    base = prompts_dir or _default_prompts_dir()
    path = base / "assistants.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def read_prompt_file(*, prompts_dir: Path, relative_path: str) -> str:
    path = (prompts_dir / relative_path).resolve()
    root = prompts_dir.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise FileNotFoundError(f"Unsafe prompt path: {relative_path}") from exc
    if not path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {relative_path}")
    return path.read_text(encoding="utf-8")


def load_prompt_slot_group(
    group: str, *, prompts_dir: Path | None = None
) -> tuple[dict[str, str], dict[str, str]]:
    """Return (slot_texts, slot_relative_paths) for one manifest group."""
    base = prompts_dir or _default_prompts_dir()
    manifest = load_manifest(prompts_dir=base)
    if group not in manifest:
        raise KeyError(f"Unknown prompt group {group!r}; define it in manifest.json")
    texts: dict[str, str] = {}
    sources: dict[str, str] = {}
    for slot, rel in manifest[group].items():
        texts[slot] = read_prompt_file(prompts_dir=base, relative_path=rel)
        sources[slot] = rel
    return texts, sources


def build_input_formalization_run(
    llm_bundle: dict[str, Any],
    *,
    prompts_dir: Path | None = None,
) -> dict[str, Any]:
    """Assemble system/user messages from versioned prompt files + bundle JSON (no API call)."""
    base = prompts_dir or _default_prompts_dir()
    texts, sources = load_prompt_slot_group("input_formalization", prompts_dir=base)
    if "system" not in texts or "user" not in texts:
        raise KeyError("input_formalization requires 'system' and 'user' slots in manifest.json")

    bundle_json = json.dumps(llm_bundle, ensure_ascii=False, indent=2)
    system = texts["system"]
    user_tpl = texts["user"]
    if "{{RAW_INPUT_BUNDLE_JSON}}" in user_tpl:
        user = user_tpl.replace("{{RAW_INPUT_BUNDLE_JSON}}", bundle_json)
    else:
        user = user_tpl.rstrip() + "\n\n--- raw_input_bundle.json ---\n\n" + bundle_json

    assistants = load_assistants_config(prompts_dir=base)
    return {
        "pipeline": "input_formalization",
        "assistants": assistants,
        "prompt_files": sources,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "note": (
            "Assembled locally only. Edit prompts under src/autopaper/prompts/ "
            "and assistants.json; switch versions by changing manifest.json paths."
        ),
    }
