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
from .session import TRANSPORT, Sessions
from .store import Bundle, MatchStore, frame_message, match_state, state_message
from .viewer import Viewer

RUN_TYPES = {"run_in_behind", "checking_run", "overlap_run", "forward_run"}

app = FastAPI(title="Blindside")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
store = MatchStore(Path(os.environ.get("BLINDSIDE_DATA", "data/league")))
sessions = Sessions(store)


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
    }


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
        session.viewers[ws] = viewer
        while True:
            msg = await ws.receive_json()
            if msg.get("kind") == "profile":
                viewer.profile = viewer.profile.model_copy(update={k: v for k, v in msg["profile"].items()
                                                                  if k in ViewerProfile.model_fields})
                viewer.reset()
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
