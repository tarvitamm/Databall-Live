import asyncio

import pytest

from databall_live.contracts import ViewerProfile
from databall_live.insights.pipeline import run, save
from databall_live.live.commentary import commentary
from databall_live.live.fantasy import fantasy
from databall_live.live.maps import maps
from databall_live.live.predictions import POLLS, Predictor
from databall_live.live.session import LiveSession
from databall_live.live.store import MatchStore
from databall_live.live.viewer import Viewer
from databall_live.sim.cli import simulate
from databall_live.stats.analyse import analyse


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


def test_polls_score_everyone_in_the_room(match):
    session, viewer, _ = session_with_audience(match)
    voted: set[str] = set()

    async def run() -> None:
        end = len(session.b.md.t) - 1
        while session.k < end:
            await session._predictions()
            for m in viewer.out:
                if m["kind"] == "prediction" and m["id"] not in voted:
                    voted.add(m["id"])
                    session.vote({"fan": "me", "name": "Me", "id": m["id"], "option": m["options"][0]["id"]})
            session.k += 25

    asyncio.run(run())
    questions = {q["en"] for _, q in POLLS.values()}
    assert any(m["question"]["en"] in questions for m in viewer.out if m["kind"] == "prediction")
    board = [m for m in viewer.out if m["kind"] == "leaderboard"][-1]
    me = next(r for r in board["rows"] if r["fan"] == "me")
    settled = {m["id"] for m in viewer.out if m["kind"] == "prediction_result"}
    assert me["played"] == len(voted & settled) > 0
    assert len(board["rows"]) > 1 and board["rows"] == sorted(board["rows"], key=lambda r: -r["points"])
    session.vote({"fan": "crowd_0", "name": "x", "id": "pr_1", "option": "yes"})


def test_fantasy_points_follow_the_match(match):
    bundle, _ = match
    starts = {p: start for p, (start, _) in bundle.period_bounds.items()}
    period, t, _, scorer = bundle.goals[0]
    before = {r["id"]: r for r in fantasy(bundle.md, bundle.goals, bundle.patterns, period, t - 1, starts)}
    after = fantasy(bundle.md, bundle.goals, bundle.patterns, period, t, starts)
    row = next(r for r in after if r["id"] == scorer)
    assert any(k == "goals" and n == 1 for k, n, _ in row["items"])
    assert row["points"] > before[scorer]["points"]
    assert [r["points"] for r in after] == sorted((r["points"] for r in after), reverse=True)
    assert sum(1 for r in after if any(k == "bonus" for k, _, _ in r["items"])) == 3


def test_live_text_follows_the_events(match):
    bundle, _ = match
    md = bundle.md
    lines = commentary(md, "en")
    assert lines[0]["text"] == "First Half begins." and lines[-1]["text"].startswith("Match ends")
    assert lines == sorted(lines, key=lambda x: (x["period"], x["t"]))
    goals = [x for x in lines if x["kind"] == "goal"]
    assert len(goals) == len(bundle.goals)
    final = bundle.score(*max((g[0], g[1]) for g in bundle.goals)) if bundle.goals else dict.fromkeys(md.codes, 0)
    home, away = md.meta.home, md.meta.away
    assert f"{home.name} {final[home.code]}, {away.name} {final[away.code]}" in lines[-1]["text"]
    fouls = sum(1 for e in md.events if e["type"] == "foul")
    assert sum(1 for x in lines if x["kind"] == "foul") == fouls
    assert len(commentary(md, "es")) == len(commentary(md, "et")) == len(lines)


def test_maps_face_the_goal_each_team_attacks(match):
    bundle, _ = match
    period, (_, end) = max(bundle.period_bounds.items())
    out = maps(bundle.md, bundle.patterns, {}, period, end)
    for code, m in out.items():
        assert len(m["shots"]) == sum(1 for e in bundle.md.events if e["type"] == "shot" and e.get("team") == code)
        assert all(x > 52.5 for x, *_ in m["shots"])
        assert all(0 <= v <= 105 for row in m["passes"] for v in row[:4:2])


def test_events_stream_with_pass_quality_and_possession(match):
    session, viewer, _ = session_with_audience(match)

    async def run() -> None:
        while session.k < 3000:
            await session._ingest()
            session.k += 10

    asyncio.run(run())
    items = [i for m in viewer.out if m["kind"] == "events" for i in m["items"]]
    passes = [i for i in items if i["type"] == "pass" and "difficulty" in i]
    assert passes and all(0 <= p["difficulty"] <= 10 for p in passes)
    assert any(i["type"] == "possession" for i in items)


def test_a_followed_metric_gets_past_the_density_limit():
    tag = {"lang": "en", "slot": "player_tag", "persona": "fan", "priority": 5, "period": 1, "show_at": 10.0,
           "data": {"type": "speed_tag", "kind": "tag", "players": ["HAR_7"], "teams": ["HAR"]}}
    quiet = Viewer(ViewerProfile(viewer="a", mode="fan", lang="en", density="low"))
    keen = Viewer(ViewerProfile(viewer="b", mode="fan", lang="en", density="low", metric="speed"))
    assert not quiet.wants(tag) and keen.wants(tag)
