import asyncio

import pytest

from blindside.contracts import ViewerProfile
from blindside.insights.pipeline import run, save
from blindside.live.predictions import Predictor
from blindside.live.session import LiveSession
from blindside.live.store import MatchStore
from blindside.live.viewer import Viewer
from blindside.sim.cli import simulate
from blindside.stats.analyse import analyse


class Socket:
    def __init__(self) -> None:
        self.out: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.out.append(message)

    def packets(self, slot: str | None = None) -> list[dict]:
        return [m for m in self.out if m["kind"] == "packet" and (slot is None or m["slot"] == slot)]


@pytest.fixture(scope="module")
def match(tmp_path_factory):
    root = tmp_path_factory.mktemp("league")
    folder = root / "m_0071"
    simulate(71, "LAR", "HAR", "the_decoy", folder, half_minutes=12.0, match_id="m_0071", quiet=True)
    save(run(folder), folder)
    store = MatchStore(root)
    return store.get("m_0071"), analyse(folder)


def session_with_audience(match):
    bundle, analysis = match
    session = LiveSession(bundle, analysis)
    viewer, console = Socket(), Socket()
    session.viewers[viewer] = Viewer(ViewerProfile(viewer="v", mode="fan", lang="en", density="high"))
    session.consoles.add(console)
    return session, viewer, console


async def play(session: LiveSession, seconds: float, approve: bool = False) -> None:
    step = 5
    end = min(session.k + int(seconds * session.b.md.hz), len(session.b.md.t) - 1)
    while session.k < end:
        await session._run_crew(session.now)
        await session._release()
        if approve:
            for insight, status in list(session.statuses.items()):
                if status == "awaiting_approval":
                    await session.command({"action": "approve", "insight": insight})
        session.k += step


def test_automatic_mode_airs_lower_thirds(match):
    session, viewer, console = session_with_audience(match)
    asyncio.run(play(session, 900))
    assert viewer.packets("lower_third")
    assert any(m["kind"] == "insight" for m in console.out)


def test_supervised_mode_holds_until_approved(match):
    session, viewer, _ = session_with_audience(match)
    asyncio.run(session.command({"action": "mode", "value": "supervised"}))
    asyncio.run(play(session, 900))
    assert not viewer.packets("lower_third")
    assert "awaiting_approval" in session.statuses.values() or "expired" in session.statuses.values()

    session, viewer, _ = session_with_audience(match)
    asyncio.run(session.command({"action": "mode", "value": "supervised"}))
    asyncio.run(play(session, 900, approve=True))
    assert viewer.packets("lower_third")


def test_kill_switch_and_type_switches(match):
    session, viewer, _ = session_with_audience(match)
    asyncio.run(session.command({"action": "kill", "value": True}))
    asyncio.run(play(session, 900))
    assert not viewer.packets()
    assert any(m["kind"] == "clear" for m in viewer.out)

    session, viewer, _ = session_with_audience(match)
    asyncio.run(session.command({"action": "type", "value": "speed_tag", "on": False}))
    asyncio.run(play(session, 900))
    assert not [p for p in viewer.packets() if p["data"].get("type") == "speed_tag"]


def test_injected_errors_are_rejected_live(match):
    session, _, console = session_with_audience(match)
    asyncio.run(session.command({"action": "unreliable", "value": 0.6}))
    asyncio.run(play(session, 1200))
    assert session.rejections > 0
    assert any(m["kind"] == "note" and m["note"] == "rejected" for m in console.out)


def test_switching_view_replays_what_already_aired(match):
    session, viewer, _ = session_with_audience(match)
    asyncio.run(play(session, 900))
    late = Socket()
    analyst = Viewer(ViewerProfile(viewer="late", mode="analyst", lang="es", density="high"))
    asyncio.run(session.send_history(late, analyst))
    history = [m for m in late.out if m["kind"] == "history"][0]["packets"]
    assert history
    assert all(p["persona"] == "analyst" and p["lang"] == "es" for p in history)


def test_seeking_fills_the_feed_with_everything_before(match):
    session, viewer, _ = session_with_audience(match)
    asyncio.run(session.seek(2, session.b.period_bounds[2][0] + 300))
    history = [m for m in viewer.out if m["kind"] == "history"][-1]["packets"]
    assert len(history) >= 3
    assert any(p["period"] == 1 for p in history)
    assert all(p["persona"] == "fan" and p["lang"] == "en" for p in history)


def test_predictions_are_settled_by_the_match(match):
    bundle, analysis = match
    ends = {p: end for p, (_, end) in bundle.period_bounds.items()}
    names = {code: code.title() for code in bundle.md.codes}
    shots = [(e["period"], e["t"], e["team"]) for e in bundle.md.events if e["type"] == "shot"]
    period, t, team = next((p, st, c) for p, st, c in shots
                           if st - 60.0 > bundle.period_bounds[p][0] and ends[p] - st > 300.0)
    predictor = Predictor(bundle.md, names, ends)
    call = predictor.after_insight("pressure_shift", team, period, t - 60.0)
    assert call is not None and call.answer == "yes" and call.settled == t
    assert predictor.after_insight("pressure_shift", team, period, t - 30.0) is None
    assert call.prompt["question"]["et"] and call.result["detail"]["es"]


def test_viewers_get_prompts_before_results(match):
    session, viewer, _ = session_with_audience(match)

    async def run() -> None:
        end = len(session.b.md.t) - 1
        while session.k < end:
            await session._predictions()
            session.k += 25

    asyncio.run(run())
    kinds = [(m["kind"], m["id"]) for m in viewer.out if m["kind"].startswith("prediction")]
    assert kinds
    for kind, pid in kinds:
        if kind == "prediction_result":
            assert ("prediction", pid) in kinds[:kinds.index((kind, pid))]
