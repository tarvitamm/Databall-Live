"""Formations, team tactics and scripted scenarios. Anchors are team-frame positions for a ball on the centre
spot.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace

# role per slot drives attributes and which off-ball behaviours a player may perform
ROLE = {
    "GK": "GK",
    "RB": "FB", "LB": "FB",
    "RCB": "CB", "LCB": "CB",
    "DM": "DM", "RDM": "DM", "LDM": "DM",
    "RCM": "CM", "LCM": "CM",
    "AM": "AM",
    "RM": "WM", "LM": "WM",
    "RW": "W", "LW": "W",
    "ST": "ST", "RS": "ST", "LS": "ST",
}

# slot: (in-possession anchor, out-of-possession anchor, shirt number)
FORMATIONS: dict[str, dict[str, tuple[tuple[float, float], tuple[float, float], int]]] = {
    "4-3-3": {
        "GK": ((6, 34), (5, 34), 1),
        "RB": ((46, 8), (26, 12), 2),
        "RCB": ((32, 22), (24, 27), 4),
        "LCB": ((32, 46), (24, 41), 5),
        "LB": ((46, 60), (26, 56), 3),
        "DM": ((44, 34), (34, 34), 6),
        "RCM": ((58, 24), (40, 25), 8),
        "LCM": ((58, 44), (40, 43), 10),
        "RW": ((78, 7), (50, 12), 11),
        "ST": ((84, 34), (58, 34), 9),
        "LW": ((78, 61), (50, 56), 7),
    },
    "4-4-2": {
        "GK": ((6, 34), (5, 34), 1),
        "RB": ((44, 9), (25, 12), 2),
        "RCB": ((31, 23), (23, 27), 5),
        "LCB": ((31, 45), (23, 41), 6),
        "LB": ((44, 59), (25, 56), 3),
        "RM": ((66, 8), (40, 12), 7),
        "RCM": ((52, 27), (38, 28), 4),
        "LCM": ((52, 41), (38, 40), 8),
        "LM": ((66, 60), (40, 56), 11),
        "RS": ((82, 28), (55, 30), 9),
        "LS": ((82, 40), (55, 38), 10),
    },
    "4-2-3-1": {
        "GK": ((6, 34), (5, 34), 1),
        "RB": ((47, 8), (26, 12), 2),
        "RCB": ((32, 22), (24, 27), 5),
        "LCB": ((32, 46), (24, 41), 6),
        "LB": ((47, 60), (26, 56), 3),
        "RDM": ((46, 28), (35, 29), 4),
        "LDM": ((46, 40), (35, 39), 8),
        "RW": ((76, 9), (48, 12), 7),
        "AM": ((70, 34), (50, 34), 10),
        "LW": ((76, 59), (48, 56), 11),
        "ST": ((86, 34), (60, 34), 9),
    },
}


@dataclass(frozen=True)
class Tactics:
    """Team instructions. Every value is 0..1."""

    block_height: float = 0.5      # how high the team defends out of possession
    press_intensity: float = 0.5   # how far up the pitch and how many players press
    width: float = 0.5             # how wide the team spreads in possession
    tempo: float = 0.5             # how quickly the ball carrier decides
    directness: float = 0.5        # preference for forward and long passes
    run_rate: float = 0.5          # how often attackers make off-ball runs
    decoy_share: float = 0.3       # share of runs made to drag defenders rather than to receive
    marking_follow: float = 0.5    # how often defenders follow runners instead of holding the zone

    def with_changes(self, **changes: float) -> Tactics:
        return replace(self, **changes)

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class ScriptedChange:
    """Something a scenario changes at a given time."""

    t: float
    period: int
    team: str
    tactics: dict[str, float] = field(default_factory=dict)
    player: str | None = None
    player_run_mult: float | None = None
    player_decoy_share: float | None = None
    energy_drain_mult: float | None = None
    note: str = ""


def scenario_changes(name: str, home: str, away: str) -> list[ScriptedChange]:
    """Scripted beats for each demo scenario. Codes refer to the clubs actually playing."""
    if name == "free":
        return []
    if name == "the_press":
        return [ScriptedChange(t=58 * 60, period=2, team=away,
                               tactics={"block_height": 0.85, "press_intensity": 0.9},
                               note=f"{away} switch to a high press")]
    if name == "the_decoy":
        return [ScriptedChange(t=60 * 60, period=2, team=home, player=f"{home}_7",
                               player_run_mult=3.0, player_decoy_share=0.8,
                               tactics={"run_rate": 0.7},
                               note=f"{home}_7 starts repeated decoy runs inside")]
    if name == "the_fade":
        return [ScriptedChange(t=70 * 60, period=2, team=away, energy_drain_mult=2.2,
                               tactics={"block_height": 0.3, "press_intensity": 0.25},
                               note=f"{away} tire and drop deeper")]
    raise ValueError(f"unknown scenario: {name}")


SCENARIOS = ("free", "the_press", "the_decoy", "the_fade")
