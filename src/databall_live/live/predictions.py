"""Live predictions for the fan app: opened by what the crew finds, settled by the match itself.

Answers come from the match events, but a result is only sent once the match clock reaches the moment it is decided.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..insights.text import minute
from ..stats.match import MatchData

WINDOW_S = 300.0
GAP_S = 240.0
NEXT_CLOSE_S = 60.0
PERIODIC_MIN = (6, 19, 32)
TRIGGERS = {"pressure_shift", "momentum_swing", "between_lines_gap", "overload", "counter_press"}

REASON = {
    "pressure_shift": {"en": "{team} are pressing harder.", "es": "{team} aprietan más arriba.",
                       "et": "{team} pressib nüüd kõvemini."},
    "momentum_swing": {"en": "{team} have the momentum.", "es": "{team} tienen el impulso.",
                       "et": "{team} on hoo sisse saanud."},
    "between_lines_gap": {"en": "{team} are finding space between the lines.",
                          "es": "{team} encuentran espacio entre líneas.", "et": "{team} leiab liinide vahelt ruumi."},
    "overload": {"en": "{team} have numbers around the ball.", "es": "{team} tienen superioridad cerca del balón.",
                 "et": "{team} on palli ümber ülekaalus."},
    "counter_press": {"en": "{team} are winning it back high.", "es": "{team} recuperan arriba.",
                      "et": "{team} võidab palli kõrgel tagasi."},
}
ASK_SHOT = {"en": "Shot in the next 5 minutes?", "es": "¿Remate en los próximos 5 minutos?",
            "et": "Kas löök tuleb järgmise 5 minuti jooksul?"}
ASK_NEXT = {"en": "Who has the next shot?", "es": "¿Quién remata primero?", "et": "Kes lööb järgmisena?"}
YES = {"en": "Yes", "es": "Sí", "et": "Jah"}
NO = {"en": "No", "es": "No", "et": "Ei"}
SHOT_AT = {"en": "{team} shot at {minute}.", "es": "{team} remató en el {minute}.", "et": "{team}: löök {minute}."}
NO_SHOT = {"en": "No {team} shot in the 5 minutes.", "es": "{team} no remató en esos 5 minutos.",
           "et": "{team} ei löönud 5 minuti jooksul."}


@dataclass
class Prediction:
    id: str
    kind: str
    period: int
    opens: float
    closes: float
    settled: float
    answer: str
    prompt: dict
    result: dict


class Predictor:
    def __init__(self, md: MatchData, team_names: dict[str, str], period_end: dict[int, float]) -> None:
        self.names = team_names
        self.period_end = period_end
        self.shots = sorted((e["period"], e["t"], e["team"]) for e in md.events if e["type"] == "shot")
        self.n = 0
        self.busy_until: tuple[int, float] = (0, -1e9)
        self.asked: set[tuple[int, int]] = set()

    def _free(self, period: int, t: float) -> bool:
        return (period, t) >= self.busy_until

    def _next_shot(self, period: int, t: float, end: float, team: str | None = None) -> tuple[float, str] | None:
        for p, st, code in self.shots:
            if p == period and t < st <= end and (team is None or code == team):
                return st, code
        return None

    def _make(self, kind: str, period: int, t: float, closes: float, settled: float, answer: str,
              question: dict, options: list[dict], detail: dict) -> Prediction:
        self.n += 1
        pid = f"pr_{self.n}"
        self.busy_until = (period, max(settled, closes) + GAP_S / 4)
        prompt = {"kind": "prediction", "id": pid, "period": period, "opens": round(t, 1),
                  "closes": round(closes, 1), "question": question, "options": options}
        result = {"kind": "prediction_result", "id": pid, "period": period, "t": round(settled, 1),
                  "answer": answer, "detail": detail}
        return Prediction(pid, kind, period, t, closes, settled, answer, prompt, result)

    def after_insight(self, kind: str, team: str, period: int, t: float) -> Prediction | None:
        """Ask whether the team that just got on top turns it into a shot."""
        if kind not in TRIGGERS or not team or not self._free(period, t):
            return None
        end = min(t + WINDOW_S, self.period_end[period])
        if end - t < 120:
            return None
        name = self.names.get(team, team)
        shot = self._next_shot(period, t, end, team)
        question = {lang: f"{REASON[kind][lang].format(team=name)} {ASK_SHOT[lang]}" for lang in ASK_SHOT}
        options = [{"id": "yes", "label": YES}, {"id": "no", "label": NO}]
        if shot:
            detail = {lang: SHOT_AT[lang].format(team=name, minute=minute(shot[0])) for lang in SHOT_AT}
            return self._make("shot_window", period, t, end, shot[0], "yes", question, options, detail)
        detail = {lang: NO_SHOT[lang].format(team=name) for lang in NO_SHOT}
        return self._make("shot_window", period, t, end, end, "no", question, options, detail)

    def periodic(self, period: int, t: float, start: float) -> Prediction | None:
        """Every so often, ask who has the next shot."""
        due = [m for m in PERIODIC_MIN if (period, m) not in self.asked and t - start >= m * 60]
        if not due:
            return None
        self.asked.update((period, m) for m in due)
        if not self._free(period, t):
            return None
        end = self.period_end[period]
        shot = self._next_shot(period, t + NEXT_CLOSE_S, end)
        if shot is None or shot[0] - t > 900:
            return None
        options = [{"id": code, "label": {lang: name for lang in ASK_NEXT}} for code, name in self.names.items()]
        detail = {lang: SHOT_AT[lang].format(team=self.names[shot[1]], minute=minute(shot[0])) for lang in SHOT_AT}
        return self._make("next_shot", period, t, t + NEXT_CLOSE_S, shot[0], shot[1], ASK_NEXT, options, detail)
