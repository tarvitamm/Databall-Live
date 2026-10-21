import numpy as np
import pytest

from databall_live.contracts import Event, TrackingFrame, Truth
from databall_live.sim import CLUBS, MatchEngine
from databall_live.sim.pitch import LENGTH, WIDTH, attack_sign, to_team_frame, xg_true


def play(seed: int = 3, scenario: str = "free", half_minutes: float = 4.0):
    frames: list[dict] = []
    engine = MatchEngine(CLUBS["HAR"], CLUBS["RED"], seed=seed, scenario=scenario, half_minutes=half_minutes)
    truth = engine.run(on_event=lambda e: None, on_frame=frames.append)
    return engine, frames, truth


@pytest.fixture(scope="module")
def short_match():
    return play()


def test_same_seed_gives_same_match():
    a, _, _ = play(seed=5, half_minutes=2.0)
    b, _, _ = play(seed=5, half_minutes=2.0)
    c, _, _ = play(seed=6, half_minutes=2.0)
    assert a.events == b.events
    assert a.events != c.events


def test_events_and_frames_match_the_contracts(short_match):
    engine, frames, truth = short_match
    for e in engine.events:
        Event.model_validate(e)
    for f in frames[:: 50]:
        TrackingFrame.model_validate(f)
    Truth.model_validate(truth.model_dump())


def test_frames_are_10_hz_and_cover_all_players(short_match):
    _, frames, _ = short_match
    first_half = [f for f in frames if f["period"] == 1]
    steps = np.diff([f["t"] for f in first_half])
    assert np.allclose(steps, 0.1)
    assert all(len(f["players"]) == 22 for f in frames[:: 100])


def test_everyone_stays_on_the_pitch(short_match):
    _, frames, _ = short_match
    xy = np.array([p for f in frames for p in f["players"].values()])
    assert xy[:, 0].min() >= -1.5 and xy[:, 0].max() <= LENGTH + 1.5
    assert xy[:, 1].min() >= -1.5 and xy[:, 1].max() <= WIDTH + 1.5
    assert min(f["ball"][2] for f in frames) >= 0.0


def test_passes_are_complete_with_a_teammate(short_match):
    engine, _, _ = short_match
    passes = [e for e in engine.events if e["type"] == "pass"]
    assert len(passes) > 20
    for e in passes:
        assert e["outcome"] in ("complete", "incomplete", "out", "offside")
        if e["outcome"] == "complete":
            assert e["recipient"].split("_")[0] == e["team"]


def test_runs_record_intent_and_marking_choice(short_match):
    _, _, truth = short_match
    assert truth.runs, "attackers should make off-ball runs"
    for r in truth.runs:
        assert r.intent in ("target", "decoy")
        assert r.t_end >= r.t_start
        assert not (r.followed_by and r.held_by)


def test_scenario_change_is_applied_and_logged():
    engine = MatchEngine(CLUBS["HAR"], CLUBS["RED"], seed=1, scenario="the_press")
    engine.period, engine.t = 2, 58 * 60.0
    before = engine.tactics[1].press_intensity
    engine._apply_scripted()
    assert engine.tactics[1].press_intensity > before
    assert engine.tactic_log[-1].team == "RED"
    assert engine.markers and engine.markers[0]["team"] == "RED"


def test_team_frame_is_its_own_inverse():
    p = np.array([[10.0, 5.0], [90.0, 60.0]])
    for sign in (1, -1):
        assert np.allclose(to_team_frame(to_team_frame(p, sign), sign), p)
    assert attack_sign(0, 1) == 1 and attack_sign(0, 2) == -1 and attack_sign(1, 1) == -1


def test_xg_is_calibrated_to_familiar_chances():
    penalty_spot = np.array([LENGTH - 11.0, WIDTH / 2])
    six_yard = np.array([LENGTH - 5.0, WIDTH / 2])
    long_range = np.array([LENGTH - 25.0, WIDTH / 2])
    assert 0.12 < xg_true(penalty_spot, 0.0) < 0.22
    assert 0.35 < xg_true(six_yard, 0.0) < 0.55
    assert xg_true(long_range, 0.0) < 0.05
    assert xg_true(penalty_spot, 1.0) < xg_true(penalty_spot, 0.0)
