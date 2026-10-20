"""The fictional league. Squads are seeded from the club code, so players stay the same across matches."""

from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np

from .tactics import FORMATIONS, ROLE, Tactics

FIRST_NAMES = [
    "Theo", "Sam", "Ibrahim", "Lucas", "Mateo", "Jonah", "Kofi", "Elias", "Rory", "Niko", "Tariq", "Oskar",
    "Dario", "Felix", "Emeka", "Joel", "Marek", "Callum", "Yusuf", "Bram", "Leon", "Aarav", "Iker", "Milo",
    "Soren", "Kian", "Ravi", "Tomas", "Andre", "Hugo", "Silas", "Owen", "Rafael", "Ezra", "Jalen", "Viktor",
]
LAST_NAMES = [
    "Marsh", "Okafor", "Diallo", "Brennan", "Vasquez", "Lindqvist", "Achterberg", "Mensah", "Calloway",
    "Petrescu", "Haddad", "Fairbairn", "Kowal", "Ndiaye", "Strand", "Quill", "Ferreira", "Abara", "Holt",
    "Varga", "Oyelaran", "Castell", "Rook", "Danso", "Whitlow", "Ilic", "Moreau", "Tenner", "Sallis",
    "Arnaud", "Kepler", "Ruane", "Dumont", "Okoro", "Basri", "Lenz", "Pryce", "Halloran", "Ivers", "Thorne",
]

# role: top speed m/s, acceleration m/s2, then passing, vision, first_touch, finishing, tackling, dribbling,
# work_rate (all 0..1)
ROLE_PROFILE = {
    "GK": (7.2, 3.8, 0.55, 0.50, 0.55, 0.10, 0.20, 0.20, 0.40),
    "CB": (7.9, 3.9, 0.60, 0.50, 0.60, 0.20, 0.75, 0.40, 0.65),
    "FB": (8.6, 4.4, 0.62, 0.55, 0.62, 0.30, 0.65, 0.60, 0.75),
    "DM": (8.0, 4.0, 0.72, 0.70, 0.70, 0.35, 0.70, 0.55, 0.75),
    "CM": (8.2, 4.2, 0.74, 0.72, 0.72, 0.45, 0.58, 0.65, 0.72),
    "AM": (8.4, 4.4, 0.74, 0.78, 0.78, 0.60, 0.40, 0.78, 0.62),
    "WM": (8.7, 4.6, 0.66, 0.62, 0.70, 0.50, 0.50, 0.72, 0.70),
    "W": (9.0, 4.8, 0.64, 0.64, 0.72, 0.60, 0.35, 0.80, 0.62),
    "ST": (8.8, 4.6, 0.58, 0.58, 0.70, 0.78, 0.35, 0.68, 0.62),
}

FIXED_NAMES = {("HAR", 7): "Theo Marsh", ("HAR", 3): "Sam Okafor", ("HAR", 9): "Ibrahim Diallo"}


@dataclass(frozen=True)
class Player:
    id: str
    name: str
    shirt: int
    slot: str
    role: str
    foot: str
    top_speed: float
    accel: float
    stamina: float
    passing: float
    vision: float
    first_touch: float
    finishing: float
    tackling: float
    dribbling: float
    work_rate: float


@dataclass(frozen=True)
class Club:
    code: str
    name: str
    colours: tuple[str, str]
    venue: str
    formation: str
    tactics: Tactics
    lineup: tuple[Player, ...]
    bench: tuple[Player, ...]


def _make_player(rng: np.random.Generator, code: str, shirt: int, slot: str, used: set[str]) -> Player:
    role = ROLE[slot]
    speed, accel, *skills = ROLE_PROFILE[role]
    name = FIXED_NAMES.get((code, shirt))
    while name is None or name in used:
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
    used.add(name)
    s = np.clip(np.array(skills) + rng.normal(0, 0.07, len(skills)), 0.05, 0.97)
    return Player(
        id=f"{code}_{shirt}",
        name=name,
        shirt=shirt,
        slot=slot,
        role=role,
        foot="left" if rng.random() < 0.25 or slot in ("LB", "LW") and rng.random() < 0.6 else "right",
        top_speed=float(np.clip(speed + rng.normal(0, 0.3), 6.8, 9.7)),
        accel=float(np.clip(accel + rng.normal(0, 0.25), 3.2, 5.4)),
        stamina=float(np.clip(rng.normal(0.75, 0.1), 0.5, 0.95)),
        passing=float(s[0]),
        vision=float(s[1]),
        first_touch=float(s[2]),
        finishing=float(s[3]),
        tackling=float(s[4]),
        dribbling=float(s[5]),
        work_rate=float(s[6]),
    )


def _make_club(code: str, name: str, colours: tuple[str, str], venue: str, formation: str,
               tactics: Tactics) -> Club:
    rng = np.random.default_rng(zlib.crc32(code.encode()))
    used: set[str] = set()
    lineup = tuple(_make_player(rng, code, shirt, slot, used) for slot, (_, _, shirt) in FORMATIONS[formation].items())
    # bench: a keeper, two defenders, two midfielders, two forwards
    bench_slots = ["GK", "RCB", "RB", "DM", "RCM", "RW", "ST"]
    bench = tuple(_make_player(rng, code, 12 + k, slot, used) for k, slot in enumerate(bench_slots))
    return Club(code, name, colours, venue, formation, tactics, lineup, bench)


CLUBS: dict[str, Club] = {
    c.code: c
    for c in (
        _make_club("HAR", "Harbour FC", ("#0B3D91", "#FFFFFF"), "Harbour Park", "4-3-3",
                   Tactics(block_height=0.5, press_intensity=0.5, width=0.6, tempo=0.45, directness=0.35,
                           run_rate=0.55, decoy_share=0.3, marking_follow=0.45)),
        _make_club("RED", "Redwood Athletic", ("#B22222", "#F5F5F5"), "The Redwood Ground", "4-2-3-1",
                   Tactics(block_height=0.45, press_intensity=0.4, width=0.5, tempo=0.55, directness=0.6,
                           run_rate=0.5, decoy_share=0.25, marking_follow=0.6)),
        _make_club("IRO", "Ironvale Town", ("#4A4A4A", "#F2C200"), "Ironvale Road", "4-4-2",
                   Tactics(block_height=0.3, press_intensity=0.3, width=0.45, tempo=0.5, directness=0.65,
                           run_rate=0.4, decoy_share=0.2, marking_follow=0.5)),
        _make_club("LAR", "Larkspur United", ("#6A4C93", "#FFFFFF"), "Larkspur Fields", "4-3-3",
                   Tactics(block_height=0.7, press_intensity=0.75, width=0.55, tempo=0.65, directness=0.45,
                           run_rate=0.6, decoy_share=0.35, marking_follow=0.55)),
    )
}
