from dataclasses import replace

import pytest

from blindside.contracts import OverlayPacket
from blindside.insights.pipeline import run
from blindside.insights.storyteller import Names, render
from blindside.insights.text import LANGS
from blindside.insights.verifier import verify
from blindside.sim.cli import simulate


@pytest.fixture(scope="module")
def output(tmp_path_factory):
    folder = tmp_path_factory.mktemp("match") / "m_0077"
    simulate(77, "LAR", "HAR", "the_decoy", folder, half_minutes=12.0, match_id="m_0077", quiet=True)
    return run(folder)


def test_every_line_passes_verification(output):
    assert output.drafts, "a match should produce insights"
    assert not output.rejected


def test_packets_follow_the_contract(output):
    for p in output.packets:
        OverlayPacket.model_validate(p.model_dump())
        assert p.expires_at > p.show_at
    langs = {p.lang for p in output.packets}
    assert langs == set(LANGS)
    recaps = [p for p in output.packets if p.data.get("type") == "recap"]
    assert {p.data["kind"] for p in recaps} == {"half_time", "full_time"}


def test_lower_thirds_never_overlap_within_a_lane(output):
    lanes: dict = {}
    for p in output.packets:
        if p.slot == "lower_third":
            lanes.setdefault((p.persona, p.lang, p.period), []).append(p)
    for packets in lanes.values():
        packets.sort(key=lambda p: p.show_at)
        for a, b in zip(packets, packets[1:], strict=False):
            assert b.show_at >= a.expires_at


def test_verifier_catches_wrong_numbers_and_names(output):
    names = Names(output.analysis.md.meta)
    draft = output.drafts[0]
    good = render(draft, "fan", "en", names)
    assert verify(draft, good, names) == []
    wrong_number = replace(good, body=good.body + " 97 times.")
    assert any("97" in r for r in verify(draft, wrong_number, names))
    outsider = next(pid for pid in names.player if pid not in draft.insight.entities.get("players", [])
                    and names.player[pid] not in f"{good.headline} {good.body}")
    wrong_name = replace(good, body=f"{good.body} {names.player[outsider]} watched.")
    assert verify(draft, wrong_name, names)
