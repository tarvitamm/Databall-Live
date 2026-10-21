import asyncio
import json
from collections import defaultdict
from types import SimpleNamespace

import pytest

from databall_live.insights.cache import Cache
from databall_live.insights.crew import build_crew, run_match
from databall_live.insights.foundry import Usage
from databall_live.insights.storyteller import Names
from databall_live.insights.tools import MatchTools, ToolLog
from databall_live.insights.verifier import verify_explanation
from databall_live.sim.cli import simulate
from databall_live.stats.analyse import analyse


class FakeFoundry:
    """Stands in for Foundry: answers from the prompt itself, optionally lying or failing."""

    model = "fake-model"

    def __init__(self, lie: bool = False, fail: bool = False) -> None:
        self.lie = lie
        self.fail = fail
        self.usage = defaultdict(Usage)

    def agent(self, name, instructions, response_format, effort="minimal"):
        return SimpleNamespace(name=name, schema=response_format)

    async def run(self, agent, prompt, timeout_s, tools=None):
        self.usage[agent.name].calls += 1
        if self.fail:
            raise TimeoutError()
        if tools:
            for t in tools:
                if t.name == "match_state":
                    await t.invoke()
        if agent.name in ("tactical_analyst", "player_lens"):
            claim = next(line for line in prompt.splitlines() if line.startswith("Baseline claim:"))
            mechanism = "It happened 99 times." if self.lie else "The detectors and tools agree on the cause."
            body = {"claim": claim.split(": ", 1)[1], "mechanism": mechanism, "consequence": "Watch the next phase."}
        else:
            wanted = json.loads(prompt.split("Write these lines: ", 1)[1].splitlines()[0])
            body = {"lines": [{"lang": w["lang"], "persona": w["persona"], "headline": w["reference_headline"],
                               "body": w["reference_body"]} for w in wanted]}
            if "Analyst's explanation: " in prompt:
                why = json.loads(prompt.split("Analyst's explanation: ", 1)[1].splitlines()[0])
                langs = sorted({w["lang"] for w in wanted} - {"en"})
                body["why"] = [{"lang": lang, **why} for lang in langs]
        return SimpleNamespace(text=json.dumps(body), value=None, usage_details={})

    def report(self) -> dict:
        return {"model": self.model}


@pytest.fixture(scope="module")
def analysis(tmp_path_factory):
    folder = tmp_path_factory.mktemp("agents") / "m_0061"
    simulate(61, "HAR", "IRO", "the_decoy", folder, half_minutes=10.0, match_id="m_0061", quiet=True)
    return analyse(folder)


def crew_run(analysis, foundry, cache=None):
    crew = build_crew(analysis, foundry=foundry, cache=cache or Cache())
    result = asyncio.run(run_match(crew, analysis))
    return crew, result


def test_model_explains_and_writes_with_tools(analysis):
    crew, result = crew_run(analysis, FakeFoundry())
    drafts = crew.editor.history
    assert drafts and all(d.insight.model.analyst == "fake-model" for d in drafts)
    assert any("match_state()" in d.tools for d in drafts)
    assert {v.source for v in crew.producer.approved} == {"model"}
    assert all(d.why["es"]["source"] == "model" for d in drafts)
    assert any(p.slot == "panel" and p.data["source"] == "model" for p in result.packets)


def test_invented_numbers_are_caught_and_templates_air(analysis):
    crew, result = crew_run(analysis, FakeFoundry(lie=True))
    assert all(d.insight.model.analyst == "template" for d in crew.editor.history)
    assert any(n.kind == "rejected" and n.detail["target"] == "explanation" for n in result.notes)
    assert all("99" not in d.insight.mechanism for d in crew.editor.history)


def test_failing_model_falls_back_on_time(analysis):
    crew, result = crew_run(analysis, FakeFoundry(fail=True))
    assert crew.editor.history
    assert all(v.source == "template" for v in crew.producer.approved)
    assert any(n.kind == "fallback" and n.detail["why"] == "deadline missed" for n in result.notes)


def test_cache_answers_a_replay_without_calls(analysis, tmp_path):
    cache = Cache(tmp_path / "cache.json")
    first, _ = crew_run(analysis, FakeFoundry(), cache)
    cache.save()
    again = FakeFoundry()
    second, _ = crew_run(analysis, again, Cache(tmp_path / "cache.json"))
    assert sum(u.calls for u in again.usage.values()) == 0
    assert [v.headline for v in first.producer.approved] == [v.headline for v in second.producer.approved]


def test_tools_only_see_the_past(analysis):
    tools = MatchTools(analysis, Names(analysis.md.meta))
    early = tools.match_state((1, 60.0))
    late = tools.match_state((2, 1e9))
    assert sum(early["score"].values()) <= sum(late["score"].values())
    assert {p["minute"] for p in tools.recent_patterns((1, 60.0))} <= {"1'", "2'"}
    log = ToolLog()
    log.record("x", {}, {"a": 12.34, "b": "7 m"})
    assert {12.34, 7.0} <= log.numbers()


def test_explanations_may_round_but_not_invent(analysis):
    crew, _ = crew_run(analysis, None)
    d = next(d for d in crew.editor.history if d.insight.signals)
    d.seen = {12.345}
    d.insight.mechanism = "Pressing rose to 12.3 a minute."
    assert verify_explanation(d, crew.names) == []
    d.insight.mechanism = "Pressing rose to 45.6 a minute."
    assert any("45.6" in r for r in verify_explanation(d, crew.names))
