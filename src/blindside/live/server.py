"""Replay server: streams a match on its own clock with each viewer's overlays, plus the data the app asks for.

    uv run blindside-serve --data data/league
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..contracts import ViewerProfile
from ..stats.kinematics import count_sprints
from ..stats.season import Season
from .session import TRANSPORT, Sessions
from .store import Bundle, MatchStore, frame_message, match_state, state_message
from .viewer import Viewer

RUN_TYPES = {"run_in_behind", "checking_run", "overlap_run", "forward_run"}

app = FastAPI(title="Blindside")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
store = MatchStore(Path(os.environ.get("BLINDSIDE_DATA", "data/league")))
sessions = Sessions(store)
seasons: dict[str, Season] = {}
SEASON_PLAYER = ("distance_km", "sprints", "top_speed_kmh", "decoy_runs", "pressures", "shots")


def _season(b: Bundle) -> Season:
    if b.id not in seasons:
        seasons[b.id] = Season.load(b.folder)
    return seasons[b.id]


def _bundle(match_id: str) -> Bundle:
    if match_id not in store.ids():
        raise HTTPException(404, f"no match {match_id}")
    return store.get(match_id)


def _before(item: dict, period: int, t: float, key: str = "t_end") -> bool:
    return item["period"] < period or (item["period"] == period and item[key] <= t)


@app.get("/api/matches")
def matches() -> list[dict]:
    return [store.summary(m) for m in store.ids()]


@app.get("/api/status")
def status() -> dict:
    foundry = sessions.model()
    return {"model": foundry.model if foundry else None}


@app.get("/api/matches/{match_id}")
def match(match_id: str) -> dict:
    b = _bundle(match_id)
    meta = b.md.meta
    players = [{"id": p.id, "name": p.name, "shirt": p.shirt, "position": p.position, "team": team.code}
               for team in (meta.home, meta.away) for p in team.lineup]
    return {**store.summary(match_id), "players": players,
            "periods": {str(p): list(bounds) for p, bounds in b.period_bounds.items()}}


@app.get("/api/matches/{match_id}/replay")
def replay(match_id: str, period: int, start: float, end: float, hz: int = 5) -> dict:
    b = _bundle(match_id)
    step = max(1, b.md.hz // hz)
    frames = np.flatnonzero((b.md.period == period) & (b.md.t >= start) & (b.md.t <= end))[::step]
    return {"frames": [frame_message(b, int(k)) for k in frames]}


@app.get("/api/matches/{match_id}/players/{player_id}")
def player(match_id: str, player_id: str, period: int = 2, t: float = 1e9) -> dict:
    b = _bundle(match_id)
    md = b.md
    if player_id not in md.ids:
        raise HTTPException(404, f"no player {player_id}")
    i = md.player_index(player_id)
    upto = int(b.frame(period, t)) + 1
    speed = b.kin.speed[:upto, i]
    mine = [p for p in b.patterns if p.get("actor") == player_id and _before(p, period, t)]
    dragged = [p for p in b.patterns if p["type"] == "decoy_run" and p.get("actor") == player_id
               and _before(p, period, t)]
    events = [e for e in md.events if e.get("player") == player_id and _before(e, period, t, "t")]
    passes = [e for e in events if e["type"] == "pass"]
    return {
        "id": player_id,
        "distance_km": round(float(speed.sum() / md.hz / 1000.0), 2),
        "sprints": count_sprints(speed, md.hz),
        "top_speed_kmh": round(float(speed.max(initial=0.0)) * 3.6, 1),
        "runs": {k: sum(1 for p in mine if p["type"] == k) for k in sorted(RUN_TYPES)},
        "decoy_runs": len(dragged),
        "defenders_dragged_m": round(sum(float(p["measures"].get("defender_displacement_m", 0)) for p in dragged), 1),
        "space_created": round(sum(max(0.0, float(p["measures"].get("space_value_gain", 0))) for p in dragged), 2),
        "pressures": sum(1 for e in events if e["type"] == "pressure"),
        "recovery_runs": sum(1 for p in mine if p["type"] == "recovery_run"),
        "passes": len(passes),
        "passes_complete": sum(1 for e in passes if e.get("outcome") == "complete"),
        "shots": sum(1 for e in events if e["type"] == "shot"),
        "patterns": [{"id": p["id"], "type": p["type"], "period": p["period"], "t": p["t_start"]} for p in mine][-20:],
        "season": _player_season(_season(b), player_id),
    }


def _player_season(s: Season, pid: str) -> dict | None:
    games = s.player_games(pid)
    if not games:
        return None
    return {"games": len(games),
            "avg": {m: s.player_avg(pid, m) for m in SEASON_PLAYER},
            "best": {m: s.player_best(pid, m) for m in SEASON_PLAYER},
            "totals": {m: int(s.player_total(pid, m)) for m in ("decoy_runs", "goals")},
            "rank": {m: list(s.total_rank(pid, m) or (0, 0)) for m in ("decoy_runs", "goals")}}


@app.get("/api/matches/{match_id}/talking-points")
def talking_points(match_id: str) -> list[str]:
    """Season facts for commentary, ready before kick-off."""
    b = _bundle(match_id)
    s = _season(b)
    md = b.md
    home, away = md.codes
    name = {t.code: t.name for t in (md.meta.home, md.meta.away)}
    player = {p.id: p.name for t in (md.meta.home, md.meta.away) for p in t.lineup}
    out = []
    met = s.last_meeting(home, away)
    if met:
        out.append(f"Last meeting: {name[home]} {met['score'][home]}-{met['score'][away]} {name[away]}.")
    if s.games(home) and s.games(away):
        out.append(f"Form, last five: {name[home]} {s.form(home)}, {name[away]} {s.form(away)}.")
    for code in (home, away):
        rank = s.team_rank(code, "pressures_per_min")
        if rank and rank[0] == 1:
            usual = round(s.team_avg(code, "pressures_per_min") or 0.0, 1)
            out.append(f"{name[code]} press {usual} times a minute on average, the most in the league.")
        xg = s.team_avg(code, "xg")
        if xg is not None:
            out.append(f"{name[code]} create {xg} xG a game this season.")
    on_pitch = set(md.ids)
    for metric, label in (("decoy_runs", "decoy runs"), ("goals", "goals")):
        leaders = [(pid, v) for pid, v in s.leaders(metric) if pid in on_pitch and v > 0][:2]
        if leaders:
            text = ", ".join(f"{player.get(pid, pid)} {int(v)}" for pid, v in leaders)
            table = s.leaders(metric)
            alone = table[0][0] == leaders[0][0] and (len(table) < 2 or table[0][1] > table[1][1])
            lead = f" {player.get(leaders[0][0], leaders[0][0])} leads the league." if alone else ""
            out.append(f"Most {label} this season on the pitch: {text}.{lead}")
    fastest = sorted(((s.player_best(pid, "top_speed_kmh") or 0.0, pid) for pid in on_pitch), reverse=True)[:1]
    league = s.league_best("top_speed_kmh")
    for v, pid in fastest:
        if v:
            note = " (league best)" if league and league[1] == pid else ""
            out.append(f"Fastest on the pitch: {player.get(pid, pid)}, {v} km/h this season{note}.")
    return out


@app.get("/api/matches/{match_id}/compare")
def compare(match_id: str, period: int, t: float) -> dict:
    """Each team so far against its season average, scaled to the minutes played for counting stats."""
    b = _bundle(match_id)
    s = _season(b)
    md = b.md
    p1_start, p1_end = b.period_bounds[1]
    played = (t - b.period_bounds[2][0] + (p1_end - p1_start) if period == 2 else t - p1_start) / 60.0
    played = max(played, 1.0)
    pace = min(played / 90.0, 1.0)
    bins = [x for x in b.metrics["state"] if _before(x, period, t)]
    out = {}
    for k, code in enumerate(md.codes):
        windows = [w["pressures_per_min"] for w in b.metrics["press"] if w["team"] == k and _before(w, period, t)]
        mine = [p for p in b.patterns if p.get("team") == code and _before(p, period, t)]
        shots = [x for x in b.shots if x[2] == code and (x[0] < period or (x[0] == period and x[1] <= t))]
        now = {"xg": round(sum(x[3] for x in shots), 2), "shots": len(shots),
               "pressures_per_min": round(sum(windows) / len(windows), 1) if windows else 0.0,
               "possession_pct": round(100 * sum(x["possession_share"][k] for x in bins) / len(bins)) if bins else 50,
               "decoy_runs": sum(1 for p in mine if p["type"] == "decoy_run"),
               "runs": sum(1 for p in mine if p["type"] in RUN_TYPES)}
        usual = {}
        for metric in now:
            avg = s.team_avg(code, metric)
            rate = metric in ("pressures_per_min", "possession_pct")
            usual[metric] = None if avg is None else round(avg if rate else avg * pace, 2 if metric == "xg" else 1)
        out[code] = {"now": now, "season": usual, "games": len(s.games(code)), "form": s.form(code)}
    return {"minutes": round(played), "teams": out}


@app.get("/api/matches/{match_id}/crew")
def crew(match_id: str) -> dict:
    b = _bundle(match_id)
    path = b.folder / "crew.json"
    return json.loads(path.read_text()) if path.exists() else {}


@app.get("/api/matches/{match_id}/catchup")
def catchup(match_id: str, period: int, t: float, lang: str = "en") -> dict:
    b = _bundle(match_id)
    aired = [p for p in b.packets if p["slot"] == "lower_third" and p["persona"] == "fan" and p["lang"] == lang
             and _before(p, period, t, "show_at")]
    top = sorted(aired, key=lambda p: -p["data"].get("significance", 0))[:3]
    top.sort(key=lambda p: (p["period"], p["show_at"]))
    return {"score": b.score(period, t), "xg": b.xg(period, t), "moments": [p["text"] for p in top],
            "state": match_state(b, period, t)}


@app.websocket("/ws/{match_id}")
async def stream(ws: WebSocket, match_id: str) -> None:
    await ws.accept()
    b = store.get(match_id)
    q = ws.query_params
    viewer = Viewer(ViewerProfile(viewer=q.get("viewer", "anon"), mode=q.get("mode", "fan"), lang=q.get("lang", "en"),
                                  clubs=[c for c in q.get("clubs", "").split(",") if c],
                                  players=[p for p in q.get("players", "").split(",") if p],
                                  density=q.get("density", "medium")))
    focus_insights = {p["insight"] for p in b.packets if p["persona"] == "player_focus"}
    control = {"speed": float(q.get("speed", 1.0)), "seek": None, "paused": False}
    k = b.frame(int(q.get("period", 1)), float(q.get("t", 0.0)))

    async def receive() -> None:
        while True:
            msg = await ws.receive_json()
            if msg.get("kind") == "profile":
                viewer.profile = viewer.profile.model_copy(update={k: v for k, v in msg["profile"].items()
                                                                  if k in ViewerProfile.model_fields})
                viewer.reset()
            elif msg.get("kind") == "speed":
                control["speed"] = max(0.25, min(float(msg["speed"]), 20.0))
            elif msg.get("kind") == "seek":
                control["seek"] = (int(msg["period"]), float(msg["t"]))
            elif msg.get("kind") == "pause":
                control["paused"] = bool(msg["paused"])

    receiver = asyncio.create_task(receive())
    md = b.md
    pointer = 0
    due = [(p["period"], p["show_at"]) for p in b.packets]
    try:
        await ws.send_json({"kind": "hello", "match": match_id})
        while k < len(md.t):
            if control["seek"] is not None:
                k = b.frame(*control["seek"])
                control["seek"] = None
                viewer.reset()
                pointer = 0
            period, t = int(md.period[k]), float(md.t[k])
            while pointer < len(due) and due[pointer] < (period, t - 2):
                pointer += 1
            if control["paused"]:
                await asyncio.sleep(0.1)
                continue
            await ws.send_json(frame_message(b, k))
            while pointer < len(due) and due[pointer] <= (period, t):
                packet = b.packets[pointer]
                if viewer.wants(packet, packet.get("insight") in focus_insights):
                    await ws.send_json({"kind": "packet", **packet})
                pointer += 1
            if k % (5 * md.hz) == 0:
                await ws.send_json(state_message(b, period, t))
            step = max(1, int(round(control["speed"])))
            await asyncio.sleep(0.1 * step / control["speed"])
            k += step
        await ws.send_json({"kind": "end"})
    except WebSocketDisconnect:
        pass
    finally:
        receiver.cancel()


def _profile(q, viewer_id: str = "anon") -> ViewerProfile:
    return ViewerProfile(viewer=viewer_id, mode=q.get("mode", "fan"), lang=q.get("lang", "en"),
                         clubs=[c for c in q.get("clubs", "").split(",") if c],
                         players=[p for p in q.get("players", "").split(",") if p], density=q.get("density", "medium"))


def _room(ws: WebSocket) -> str:
    room = ws.query_params.get("room", "main")
    return "".join(c for c in room if c.isalnum())[:24] or "main"


@app.websocket("/ws/live/{match_id}")
async def live_viewer(ws: WebSocket, match_id: str) -> None:
    await ws.accept()
    if match_id not in store.ids():
        await ws.close(code=4404)
        return
    session = await sessions.get(match_id, _room(ws))
    viewer = Viewer(_profile(ws.query_params))
    try:
        await ws.send_json({"kind": "hello", "match": match_id, "live": True, "playing": session.playing,
                            "speed": session.speed})
        await ws.send_json(frame_message(session.b, session.k))
        period, t = session.now
        await ws.send_json(state_message(session.b, period, t))
        await session.send_history(ws, viewer)
        session.viewers[ws] = viewer
        while True:
            msg = await ws.receive_json()
            if msg.get("kind") == "profile":
                viewer.profile = viewer.profile.model_copy(update={k: v for k, v in msg["profile"].items()
                                                                  if k in ViewerProfile.model_fields})
                viewer.reset()
                await session.send_history(ws, viewer)
            elif msg.get("kind") == "control" and msg.get("action") in TRANSPORT:
                await session.command(msg)
    except WebSocketDisconnect:
        pass
    finally:
        session.viewers.pop(ws, None)


@app.websocket("/ws/console/{match_id}")
async def console(ws: WebSocket, match_id: str) -> None:
    await ws.accept()
    if match_id not in store.ids():
        await ws.close(code=4404)
        return
    session = await sessions.get(match_id, _room(ws))
    try:
        await ws.send_json(session.snapshot())
        await ws.send_json(frame_message(session.b, session.k))
        session.consoles.add(ws)
        while True:
            await session.command(await ws.receive_json())
    except WebSocketDisconnect:
        pass
    finally:
        session.consoles.discard(ws)


def main(argv: list[str] | None = None) -> int:
    import uvicorn

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data/league"))
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--web", type=Path, default=Path("web/dist"), help="Built web app to serve, if present")
    args = ap.parse_args(argv)
    store.root = args.data
    if args.web.exists():
        app.mount("/", StaticFiles(directory=args.web, html=True), name="web")
    uvicorn.run(app, host="0.0.0.0", port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
