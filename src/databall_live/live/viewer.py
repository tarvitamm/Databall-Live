"""Which packets reach a viewer, given their mode, language, clubs, players and preferred density."""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import ViewerProfile

DENSITY_GAP_S = {"low": 180.0, "medium": 75.0, "high": 30.0}
METRIC_TYPES = {
    "speed": {"speed_tag", "match_top_speed", "record", "distance_milestone", "shot_speed"},
    "offball": {"decoy_run", "between_lines_gap", "overload", "standout"},
    "pressing": {"pressure_shift", "counter_press", "match_state"},
    "chances": {"chain", "shot_speed", "momentum_swing"},
    "passing": {"difficult_pass", "line_breaking_pass", "between_lines_gap"},
}


def absolute(period: int, t: float) -> float:
    return t + (10_000.0 if period == 2 else 0.0)


@dataclass
class Viewer:
    profile: ViewerProfile
    last_lower_third: float = -1e9

    def reset(self) -> None:
        self.last_lower_third = -1e9

    def fits(self, packet: dict, has_focus_line: bool = False) -> bool:
        """Whether a packet suits this viewer's mode, language, clubs and players, ignoring density."""
        prof = self.profile
        if packet["lang"] != prof.lang:
            return False
        data = packet.get("data", {})
        players = set(data.get("players", []))
        teams = set(data.get("teams", []))
        followed = bool(players & set(prof.players)) or data.get("type") in METRIC_TYPES.get(prof.metric or "", set())
        if data.get("kind") == "tag":
            return followed or prof.density != "low" or prof.mode == "analyst"
        if packet["slot"] == "panel":
            return packet["persona"] == ("analyst" if prof.mode == "analyst" else "fan")
        persona = packet["persona"]
        if prof.mode == "analyst":
            ok = persona == "analyst"
        elif prof.mode == "player_focus":
            if persona == "player_focus":
                ok = followed
            else:
                ok = persona == "fan" and ((followed and not has_focus_line) or packet["priority"] == 1)
        else:
            ok = persona == "fan"
        if not ok:
            return False
        return not (prof.mode == "fan" and prof.clubs and not teams & set(prof.clubs)
                    and data.get("significance", 0) < 0.6)

    def wants(self, packet: dict, has_focus_line: bool = False) -> bool:
        if not self.fits(packet, has_focus_line):
            return False
        data = packet.get("data", {})
        if data.get("kind") == "tag" or packet["slot"] == "panel":
            return True
        followed = bool(set(data.get("players", [])) & set(self.profile.players))
        followed = followed or data.get("type") in METRIC_TYPES.get(self.profile.metric or "", set())
        now = absolute(packet["period"], packet["show_at"])
        gap = DENSITY_GAP_S[self.profile.density]
        if packet["priority"] > 1 and not followed and now - self.last_lower_third < gap:
            return False
        self.last_lower_third = now
        return True
