from pathlib import Path

import numpy as np
import pytest

from blindside.contracts import Pattern
from blindside.sim.cli import simulate
from blindside.sim.pitch import attack_sign
from blindside.stats.analyse import analyse
from blindside.stats.pressing import PressWindow, _call


@pytest.fixture(scope="module")
def analysis(tmp_path_factory):
    folder: Path = tmp_path_factory.mktemp("match") / "m_0042"
    simulate(42, "HAR", "RED", "free", folder, half_minutes=8.0, match_id="m_0042", quiet=True)
    return analyse(folder)


def test_playing_directions_are_inferred_from_kick_off(analysis):
    md = analysis.md
    for team in (0, 1):
        for period in (1, 2):
            assert md.sign(team, period) == attack_sign(team, period)


def test_speeds_are_human(analysis):
    top = analysis.kin.speed.max()
    assert 7.0 < top < 11.0, f"top speed {top:.1f} m/s"


def test_possession_is_tracked(analysis):
    poss = analysis.poss
    share = poss.in_play.mean()
    assert 0.4 < share < 0.95
    assert (poss.team[poss.in_play] >= 0).mean() > 0.9
    assert len(poss.spells) > 10


def test_shape_is_sensible(analysis):
    gap = analysis.shape.gap[analysis.poss.in_play]
    assert np.all(analysis.shape.def_line >= 0) and np.all(analysis.shape.def_line <= 105)
    assert 0 < np.median(gap) < 40


def test_runs_become_valid_patterns(analysis):
    assert analysis.runs, "a match should contain off-ball runs"
    kinds = {r.kind for r in analysis.runs}
    assert kinds <= {"in_behind", "checking", "overlap", "forward"}
    for p in analysis.patterns:
        Pattern.model_validate(p.model_dump())
        assert p.t_end >= p.t_start
    for r in analysis.runs:
        if r.decoy:
            assert r.dragging and r.follower is not None and not r.received


def _w(pressures: float, line: float, regains: float = 0.0) -> PressWindow:
    return PressWindow(team=0, period=2, t_end=0.0, minutes=10, opp_possession_min=5.0, pressures_per_min=pressures,
                       ppda=10.0, def_actions=0, line_height_m=line, high_regains_per_10=regains)


def test_pressure_shift_needs_two_families():
    assert _call(_w(5.0, 30.0), _w(8.0, 38.0))[0] == 1          # intensity and position agree: harder
    assert _call(_w(8.0, 38.0), _w(5.0, 30.0))[0] == -1         # both drop: softer
    assert _call(_w(5.0, 30.0), _w(8.0, 30.0)) is None          # intensity alone is not enough
