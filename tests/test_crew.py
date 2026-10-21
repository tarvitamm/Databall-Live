import asyncio
import json

import pytest

from databall_live.insights.crew import build_crew, minute_batches, run_match
from databall_live.insights.pipeline import run
from databall_live.insights.storyteller import Names
from databall_live.insights.verifier import verify
from databall_live.sim.cli import simulate
from databall_live.stats.analyse import analyse
from databall_live.stats.season import Season, summarize


@pytest.fixture(scope="module")
def folder(tmp_path_factory):
    path = tmp_path_factory.mktemp("match") / "m_0055"
    simulate(55, "RED", "HAR", "the_decoy", path, half_minutes=10.0, match_id="m_0055", quiet=True)
    return path


def test_batches_cover_every_pattern_once(folder):
    a = analyse(folder)
    batches = minute_batches(a)
    ids = [p.id for b in batches for p in b.patterns]
    assert sorted(ids) == sorted(p.id for p in a.patterns)
    assert [b.close_period for b in batches].count(True) == 2


def test_unreliable_storyteller_is_caught_and_nothing_wrong_airs(folder):
    out = run(folder, unreliable=0.5)
    assert out.report["rejections"] > 0
    names = Names(out.analysis.md.meta)
    drafts = {d.insight.id: d for d in out.drafts}
    for v in out.variants:
        assert verify(drafts[v.insight], v, names) == []
    reliable = run(folder)
    assert reliable.report["rejections"] == 0
    assert len(out.packets) == len(reliable.packets)


def test_every_executor_takes_part(folder):
    out = run(folder)
    assert set(out.report["executors"]) == {"moment_router", "tactical_analyst", "player_lens", "editor",
                                            "storyteller", "verifier", "recapper", "producer"}


def test_checkpoints_are_written(folder, tmp_path):
    a = analyse(folder)
    crew = build_crew(a, checkpoints=tmp_path)
    asyncio.run(run_match(crew, a))
    assert any(tmp_path.iterdir())


def test_season_context_adds_previews_records_and_totals(folder):
    a = analyse(folder)
    base = summarize(a)
    history = []
    for k in range(4):
        game = json.loads(json.dumps(base))
        game["match"] = f"m_000{k}"
        for player in game["players"].values():
            player["top_speed_kmh"] = 20.0
            player["decoy_runs"] = 2
        history.append(game)
    crew = build_crew(a, season=Season(history))
    asyncio.run(run_match(crew, a))
    keys = {d.key for d in crew.editor.history}
    assert "preview_h2h" in keys
    assert any(k.startswith("record_speed") for k in keys)
    assert all(not verify(d, v, crew.names) for d in crew.editor.history for v in crew.producer.approved
               if v.insight == d.insight.id and v.source != "fallback")
