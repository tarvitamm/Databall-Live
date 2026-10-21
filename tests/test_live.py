import json

import pytest
from fastapi.testclient import TestClient

from blindside.insights.pipeline import run, save
from blindside.live import server
from blindside.sim.cli import simulate


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    root = tmp_path_factory.mktemp("league")
    folder = root / "m_0031"
    simulate(31, "HAR", "RED", "the_decoy", folder, half_minutes=6.0, match_id="m_0031", quiet=True)
    save(run(folder), folder)
    server.store.root = root
    server.store.cache.clear()
    return TestClient(server.app)


def test_lists_and_describes_matches(client):
    matches = client.get("/api/matches").json()
    assert [m["id"] for m in matches] == ["m_0031"]
    detail = client.get("/api/matches/m_0031").json()
    assert len(detail["players"]) == 22 and set(detail["periods"]) == {"1", "2"}
    assert client.get("/api/matches/m_9999").status_code == 404


def test_player_stats_grow_with_time(client):
    early = client.get("/api/matches/m_0031/players/HAR_7", params={"period": 1, "t": 60}).json()
    late = client.get("/api/matches/m_0031/players/HAR_7", params={"period": 2, "t": 1e9}).json()
    assert late["distance_km"] > early["distance_km"] > 0


def test_stream_sends_frames_state_and_packets(client):
    kinds: dict[str, int] = {}
    with client.websocket_connect("/ws/m_0031?speed=20&mode=analyst&lang=et&density=high") as ws:
        for _ in range(400):
            msg = ws.receive_json()
            kinds[msg["kind"]] = kinds.get(msg["kind"], 0) + 1
            if msg["kind"] == "packet":
                assert msg["lang"] == "et"
                assert msg["persona"] in ("analyst", "fan")
    assert kinds.get("frame", 0) > 100 and kinds.get("state", 0) > 0


def test_season_comparisons_and_talking_points(client):
    league = server.store.root
    summary = json.loads((league / "m_0031" / "summary.json").read_text())
    for k in range(1, 4):
        earlier = league.parent / "season" / f"m_000{k}"
        earlier.mkdir(parents=True, exist_ok=True)
        (earlier / "summary.json").write_text(json.dumps({**summary, "match": f"m_000{k}"}))
    server.seasons.clear()
    compare = client.get("/api/matches/m_0031/compare", params={"period": 1, "t": 200}).json()
    assert set(compare["teams"]) == {"HAR", "RED"}
    assert compare["teams"]["HAR"]["games"] == 3 and compare["teams"]["HAR"]["season"]["xg"] is not None
    player = client.get("/api/matches/m_0031/players/HAR_7", params={"period": 1, "t": 200}).json()
    assert player["season"]["games"] == 3
    points = client.get("/api/matches/m_0031/talking-points").json()
    assert any(p.startswith("Last meeting") for p in points)
