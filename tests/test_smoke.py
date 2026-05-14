import pytest

from autopaper.inputs import PaperSection, ResearchInput
from autopaper.validation.ieee_format import IEEEFormatHints


def test_ieee_scan_empty_issues_for_short_text() -> None:
    h = IEEEFormatHints.scan("Short.")
    assert isinstance(h.issues, list)


@pytest.mark.asyncio
async def test_orchestrator_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    from autopaper.orchestration import Orchestrator
    from autopaper.providers.base import BaseLLMProvider

    class FakeLLM(BaseLLMProvider):
        name = "fake"

        async def complete(
            self,
            messages: list[dict[str, str]],
            *,
            temperature: float = 0.3,
            max_tokens: int | None = None,
        ) -> str:
            return "stub"

    orch = Orchestrator(FakeLLM(), FakeLLM(), FakeLLM(), title="T")
    d = await orch.run(ResearchInput(description="n", details="i"))
    assert d.title == "T"
    assert any(s.section == PaperSection.ABSTRACT for s in d.sections)
