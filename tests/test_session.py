import asyncio

import pytest

from blindside.contracts import ViewerProfile
from blindside.insights.pipeline import run, save
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
