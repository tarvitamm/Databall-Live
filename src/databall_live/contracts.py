"""Data contracts shared by every component.

Coordinates are metres in a fixed stadium frame, (0, 0) bottom-left to (105, 68). `t` is the match clock in
seconds; period 2 starts at 2700, so `period` disambiguates stoppage time.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["sim", "provider", "cv"]
Point = tuple[float, float]
Point3 = tuple[float, float, float]

EventType = Literal[
    "kick_off",
    "pass",
    "carry",
    "shot",
    "goal",
    "tackle",
    "interception",
    "ball_recovery",
    "clearance",
    "pressure",
    "foul",
    "out_of_play",
    "half_start",
    "half_end",
    "substitution",
    "card",
]


class Event(BaseModel):
    """One on-ball or match event, as a data provider would send it."""

    id: str
    match: str
    t: float
    period: int
    source: Source = "sim"
    type: EventType
    team: str | None = None
    player: str | None = None
    start: Point | None = None
    end: Point | None = None
    recipient: str | None = None
    opponent: str | None = Field(default=None, description="Player tackled, pressed or fouled")
    outcome: str | None = None
    height: Literal["ground", "high"] | None = None
    body_part: Literal["right_foot", "left_foot", "head", "other"] | None = None
    set_piece: Literal["kick_off", "throw_in", "corner", "goal_kick", "free_kick"] | None = None
    duration: float | None = Field(default=None, description="Seconds, for carries")


class TrackingFrame(BaseModel):
    """Positions of the ball and every player on the pitch at one instant."""

    match: str
    t: float
    period: int
    source: Source = "sim"
    ball: Point3
    players: dict[str, Point]


class PlayerInfo(BaseModel):
    id: str
    name: str
    shirt: int
    position: str
    foot: Literal["right", "left"]


class TeamInfo(BaseModel):
    code: str
    name: str
    colours: tuple[str, str]
    formation: str
    lineup: list[PlayerInfo]
    bench: list[PlayerInfo]


class MatchMetadata(BaseModel):
    match: str
    seed: int
    scenario: str
    sim_version: str
    home: TeamInfo
    away: TeamInfo
    venue: str
    kick_off: str
    weather: str
    referee: str
    pitch: Point = (105.0, 68.0)
    hz: int = 10


class TacticState(BaseModel):
    block_height: float
    press_intensity: float
    width: float
    tempo: float
    directness: float
    run_rate: float
    decoy_share: float
    marking_follow: float


class TacticChange(BaseModel):
    t: float
    period: int
    team: str
    tactics: TacticState
    note: str = ""


class RunTruth(BaseModel):
    id: str
    player: str
    team: str
    type: Literal["in_behind", "checking", "overlap"]
    intent: Literal["target", "decoy"]
    t_start: float
    t_end: float
    period: int
    followed_by: str | None = None
    held_by: str | None = Field(default=None, description="Nearest defender who chose to hold the zone")
    linked_to: str | None = Field(default=None, description="The decoy run whose vacated space this run attacks")


class Truth(BaseModel):
    """Hidden ground truth. Never ingested by the pipeline; used only for grading."""

    match: str
    seed: int
    scenario: str
    tactics: list[TacticChange]
    runs: list[RunTruth]
    fatigue: dict[str, list[float]] = Field(description="Energy per player at the end of each minute")
    markers: list[dict] = Field(default_factory=list, description="Scripted scenario beats")


class Evidence(BaseModel):
    events: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    window: tuple[float, float] | None = None


class Pattern(BaseModel):
    """A tactical pattern detected by the stats engine."""

    id: str
    match: str
    type: str
    period: int
    t_start: float
    t_end: float
    actor: str | None = None
    team: str | None = None
    affected: list[str] = Field(default_factory=list)
    measures: dict[str, float | str] = Field(default_factory=dict)
    evidence: Evidence = Field(default_factory=Evidence)
    significance: float = 0.0


class ModelInfo(BaseModel):
    analyst: str | None = None
    storyteller: str | None = None
    prompt_version: str | None = None


class Insight(BaseModel):
    """An explained, verified claim about the match."""

    id: str
    match: str
    t: float
    period: int
    type: str
    status: Literal["draft", "verified", "scheduled", "aired", "rejected", "expired"] = "draft"
    claim: str
    signals: dict[str, list[float] | float]
    mechanism: str
    consequence: str
    evidence: Evidence
    entities: dict[str, list[str]] = Field(default_factory=dict)
    confidence: float
    significance: float
    model: ModelInfo = Field(default_factory=ModelInfo)


Persona = Literal["analyst", "fan", "player_focus", "catch_up", "audio"]


class OverlayPacket(BaseModel):
    """A timed, render-ready graphic for one persona and language."""

    packet: str
    match: str
    insight: str | None = None
    persona: Persona
    lang: str
    slot: Literal["lower_third", "player_tag", "pass_card", "shot_card", "panel", "ticker"]
    priority: int = 2
    show_at: float
    expires_at: float
    period: int
    text: dict[str, str] = Field(default_factory=dict)
    data: dict = Field(default_factory=dict)
    viz: dict | None = None
    audio: dict | None = None
    fallback: bool = False


class ViewerProfile(BaseModel):
    viewer: str
    mode: Persona = "fan"
    lang: str = "en"
    clubs: list[str] = Field(default_factory=list)
    players: list[str] = Field(default_factory=list)
    metric: str | None = None
    detail: Literal["low", "medium", "high"] = "medium"
    density: Literal["low", "medium", "high"] = "medium"
    audio: bool = False
