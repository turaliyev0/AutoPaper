"""Tests for paper_input image validation gates."""

from __future__ import annotations

import pytest

from paper_input import image_validation as iv
from paper_input.image_validation import (
    ImageValidationError,
    MismatchAbortError,
    MismatchPolicy,
    assert_images_usable,
    collect_fatal_image_problems,
    collect_mismatch_warnings,
    resolve_mismatch_continuation,
)


def test_no_images_no_fatal() -> None:
    bundle = {"image_paths": []}
    cleaned = {"images": []}
    assert collect_fatal_image_problems(bundle, cleaned) == []
    assert_images_usable(bundle, cleaned)


def test_disk_failed_is_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = {
        "input_root": "/tmp/paper",
        "image_paths": ["images/bad.png"],
    }
    cleaned = {
        "images": [
            {
                "relative_path": "images/bad.png",
                "readable": False,
                "description": "corrupt",
            },
        ],
    }
    monkeypatch.setattr(
        iv,
        "load_images_from_bundle",
        lambda _b: ([], ["images/bad.png"]),
    )
    problems = collect_fatal_image_problems(bundle, cleaned)
    assert len(problems) == 1
    assert problems[0].kind == "disk_read_failed"

    with pytest.raises(ImageValidationError):
        assert_images_usable(bundle, cleaned)


def test_vision_unreadable_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = {
        "input_root": "/tmp/paper",
        "image_paths": ["images/fig.png"],
    }
    cleaned = {
        "images": [
            {
                "relative_path": "images/fig.png",
                "readable": False,
                "description": "Blank or illegible figure.",
            },
        ],
    }
    monkeypatch.setattr(
        iv,
        "load_images_from_bundle",
        lambda _b: ([("images/fig.png", b"jpeg")], []),
    )
    problems = collect_fatal_image_problems(bundle, cleaned)
    assert len(problems) == 1
    assert problems[0].kind == "vision_unreadable"


def test_mismatch_warnings_filtered() -> None:
    final = {
        "mismatch_flags": [
            {
                "image_path": "images/a.png",
                "severity": "likely_mismatch",
                "issue": "Figure shows X; text describes Y.",
                "text_paths": ["description/overview.md"],
            },
            {"image_path": "images/b.png", "severity": "aligned", "issue": "skip"},
        ],
    }
    warnings = collect_mismatch_warnings(final)
    assert len(warnings) == 1
    assert warnings[0].severity == "likely_mismatch"


def test_mismatch_abort_strict() -> None:
    warnings = collect_mismatch_warnings(
        {
            "mismatch_flags": [
                {
                    "image_path": "images/a.png",
                    "severity": "unclear",
                    "issue": "unclear link",
                },
            ],
        },
    )
    with pytest.raises(MismatchAbortError):
        resolve_mismatch_continuation(warnings, policy=MismatchPolicy.ABORT, is_tty=False)


def test_mismatch_continue_policy() -> None:
    warnings = collect_mismatch_warnings(
        {
            "mismatch_flags": [
                {
                    "image_path": "images/a.png",
                    "severity": "likely_mismatch",
                    "issue": "mismatch",
                },
            ],
        },
    )
    resolve_mismatch_continuation(warnings, policy=MismatchPolicy.CONTINUE, is_tty=False)


def test_mismatch_auto_non_tty_aborts() -> None:
    warnings = collect_mismatch_warnings(
        {
            "mismatch_flags": [
                {
                    "image_path": "images/a.png",
                    "severity": "weak_overlap",
                    "issue": "weak",
                },
            ],
        },
    )
    with pytest.raises(MismatchAbortError):
        resolve_mismatch_continuation(warnings, policy=MismatchPolicy.AUTO, is_tty=False)
