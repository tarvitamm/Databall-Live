import asyncio

import pytest

from blindside.insights.crew import build_crew, minute_batches, run_match
from blindside.insights.pipeline import run
from blindside.insights.storyteller import Names
from blindside.insights.verifier import verify
from blindside.sim.cli import simulate
from blindside.stats.analyse import analyse


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
