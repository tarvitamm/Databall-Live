"""Live predictions for the fan app: opened by what the crew finds, settled by the match itself.

Answers come from the match events, but a result is only sent once the match clock reaches the moment it is decided.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ..insights.text import minute
from ..stats.match import MatchData

WINDOW_S = 300.0
GAP_S = 240.0
NEXT_CLOSE_S = 60.0
VOTE_S = 60.0
POLL_EVERY_S = (150.0, 300.0)
MAX_FANS = 500
PERIODIC_MIN = (6, 19, 32)
TRIGGERS = {"pressure_shift", "momentum_swing", "between_lines_gap", "overload", "counter_press"}

REASON = {
    "pressure_shift": {"en": "{team} are pressing harder.", "es": "{team} aprietan más arriba.",
                       "et": "{team} pressib nüüd kõvemini.",
                       "de": "{team} presst jetzt härter.", "fr": "{team} presse plus fort."},
    "momentum_swing": {"en": "{team} have the momentum.", "es": "{team} tienen el impulso.",
                       "et": "{team} on hoo sisse saanud.",
                       "de": "{team} hat das Momentum.", "fr": "{team} a pris l’ascendant."},
    "between_lines_gap": {"en": "{team} are finding space between the lines.",
                          "es": "{team} encuentran espacio entre líneas.", "et": "{team} leiab liinide vahelt ruumi.",
                          "de": "{team} findet Raum zwischen den Ketten.",
                          "fr": "{team} trouve de l’espace entre les lignes."},
    "overload": {"en": "{team} have numbers around the ball.", "es": "{team} tienen superioridad cerca del balón.",
                 "et": "{team} on palli ümber ülekaalus.",
                 "de": "{team} hat Überzahl am Ball.", "fr": "{team} est en surnombre autour du ballon."},
    "counter_press": {"en": "{team} are winning it back high.", "es": "{team} recuperan arriba.",
                      "et": "{team} võidab palli kõrgel tagasi.",
                      "de": "{team} erobert den Ball weit vorne zurück.", "fr": "{team} récupère le ballon haut."},
}
ASK_SHOT = {"en": "Shot in the next 5 minutes?", "es": "¿Remate en los próximos 5 minutos?",
            "et": "Kas löök tuleb järgmise 5 minuti jooksul?",
            "de": "Schuss in den nächsten 5 Minuten?", "fr": "Un tir dans les 5 prochaines minutes ?"}
ASK_NEXT = {"en": "Who has the next shot?", "es": "¿Quién remata primero?", "et": "Kes lööb järgmisena?",
            "de": "Wer schießt als Nächstes?", "fr": "Qui tirera le prochain ?"}
YES = {"en": "Yes", "es": "Sí", "et": "Jah", "de": "Ja", "fr": "Oui"}
NO = {"en": "No", "es": "No", "et": "Ei", "de": "Nein", "fr": "Non"}
SHOT_AT = {"en": "{team} shot at {minute}.", "es": "{team} remató en el {minute}.", "et": "{team}: löök {minute}.",
           "de": "{team}: Schuss, {minute}.", "fr": "{team} : tir, {minute}."}
NO_SHOT = {"en": "No {team} shot in the 5 minutes.", "es": "{team} no remató en esos 5 minutos.",
           "et": "{team} ei löönud 5 minuti jooksul.",
           "de": "Kein Schuss von {team} in den 5 Minuten.", "fr": "Aucun tir de {team} en 5 minutes."}
POLLS = {
    "goal": (600.0, {"en": "Goal in the next 10 minutes?", "es": "¿Gol en los próximos 10 minutos?",
                     "et": "Kas järgmise 10 minuti jooksul tuleb värav?",
                     "de": "Tor in den nächsten 10 Minuten?", "fr": "Un but dans les 10 prochaines minutes ?"}),
    "foul": (180.0, {"en": "Foul in the next 3 minutes?", "es": "¿Falta en los próximos 3 minutos?",
                     "et": "Kas järgmise 3 minuti jooksul tuleb vabalöök?",
                     "de": "Foul in den nächsten 3 Minuten?", "fr": "Une faute dans les 3 prochaines minutes ?"}),
    "corner": (300.0, {"en": "Corner in the next 5 minutes?", "es": "¿Córner en los próximos 5 minutos?",
                       "et": "Kas järgmise 5 minuti jooksul tuleb nurgalöök?",
                       "de": "Ecke in den nächsten 5 Minuten?", "fr": "Un corner dans les 5 prochaines minutes ?"}),
    "on_target": (300.0, {"en": "Shot on target in the next 5 minutes?",
                          "es": "¿Remate a puerta en los próximos 5 minutos?",
                          "et": "Kas järgmise 5 minuti jooksul tuleb löök väravale?",
                          "de": "Schuss aufs Tor in den nächsten 5 Minuten?",
                          "fr": "Un tir cadré dans les 5 prochaines minutes ?"}),
}
HAPPENED = {
    "goal": {"en": "Goal at {minute}.", "es": "Gol en el {minute}.", "et": "Värav {minute}.",
             "de": "Tor, {minute}.", "fr": "But, {minute}."},
    "foul": {"en": "Foul at {minute}.", "es": "Falta en el {minute}.", "et": "Vabalöök {minute}.",
             "de": "Foul, {minute}.", "fr": "Faute, {minute}."},
    "corner": {"en": "Corner at {minute}.", "es": "Córner en el {minute}.", "et": "Nurgalöök {minute}.",
               "de": "Ecke, {minute}.", "fr": "Corner, {minute}."},
    "on_target": {"en": "On target at {minute}.", "es": "A puerta en el {minute}.", "et": "Löök väravale {minute}.",
                  "de": "Aufs Tor, {minute}.", "fr": "Cadré, {minute}."},
}
MISSED = {"en": "It did not happen this time.", "es": "Esta vez no pasó.", "et": "Seekord ei juhtunud.",
          "de": "Diesmal ist es nicht passiert.", "fr": "Cette fois, ça ne s’est pas produit."}
CROWD = ("Kai", "Maris", "Jonas", "Lea", "Rasmus", "Mia", "Oskar", "Sofia", "Tom", "Grete", "Leo", "Nora", "Hugo",
         "Ella", "Ivan", "Zara")


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
        events = md.events
        self.moments = {
            "goal": [(e["period"], e["t"]) for e in events if e["type"] == "shot" and e.get("outcome") == "goal"],
            "foul": [(e["period"], e["t"]) for e in events if e["type"] == "foul"],
            "corner": [(e["period"], e["t"]) for e in events
                       if e["type"] == "out_of_play" and e.get("outcome") == "corner"],
            "on_target": [(e["period"], e["t"]) for e in events
                          if e["type"] == "shot" and e.get("outcome") in ("goal", "saved")],
        }
        self.rng = random.Random(md.meta.seed)
        self.next_poll: dict[int, float] = {}

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
            return self._make("shot_window", period, t, t + VOTE_S, shot[0], "yes", question, options, detail)
        detail = {lang: NO_SHOT[lang].format(team=name) for lang in NO_SHOT}
        return self._make("shot_window", period, t, t + VOTE_S, end, "no", question, options, detail)

    def poll(self, period: int, t: float, start: float) -> Prediction | None:
        """Now and then, a random yes or no question the match itself will answer."""
        due = self.next_poll.setdefault(period, start + 180.0)
        if t < due or not self._free(period, t):
            return None
        self.next_poll[period] = t + self.rng.uniform(*POLL_EVERY_S)
        kind = self.rng.choice(sorted(POLLS))
        window, question = POLLS[kind]
        end = t + window
        if end > self.period_end[period]:
            return None
        options = [{"id": "yes", "label": YES}, {"id": "no", "label": NO}]
        hit = next((mt for p, mt in self.moments[kind] if p == period and t < mt <= end), None)
        if hit is not None:
            detail = {lang: HAPPENED[kind][lang].format(minute=minute(hit)) for lang in MISSED}
            return self._make(kind, period, t, t + VOTE_S, hit, "yes", question, options, detail)
        return self._make(kind, period, t, t + VOTE_S, end, "no", question, options, MISSED)

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


@dataclass
class Fan:
    name: str
    skill: float = 0.0
    points: int = 0
    streak: int = 0
    best: int = 0
    called: int = 0
    played: int = 0
    gained: int = 0


class Board:
    """Everyone's calls in one room, scored alike, with a simulated crowd so a lone viewer still has rivals."""

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.fans = {f"crowd_{i}": Fan(name, skill=self.rng.uniform(0.35, 0.7)) for i, name in enumerate(CROWD)}
        self.votes: dict[str, dict[str, str]] = {}
        self.open: dict[str, Prediction] = {}

    def opened(self, p: Prediction) -> None:
        self.open[p.id] = p
        picks = self.votes.setdefault(p.id, {})
        wrong = [o["id"] for o in p.prompt["options"] if o["id"] != p.answer]
        for fan_id, fan in self.fans.items():
            if fan.skill and self.rng.random() < 0.85:
                picks[fan_id] = p.answer if self.rng.random() < fan.skill else self.rng.choice(wrong)

    def vote(self, fan: str, name: str, pid: str, option: str, now: tuple[int, float]) -> bool:
        p = self.open.get(pid)
        if p is None or now > (p.period, p.closes) or fan in self.votes[pid]:
            return False
        full = fan not in self.fans and len(self.fans) >= MAX_FANS
        if full or option not in [o["id"] for o in p.prompt["options"]]:
            return False
        self.fans.setdefault(fan, Fan(name)).name = name
        self.votes[pid][fan] = option
        return True

    def settle(self, pid: str) -> dict:
        p = self.open.pop(pid, None)
        votes = self.votes.pop(pid, {})
        for fan in self.fans.values():
            fan.gained = 0
        for fan_id, option in votes.items():
            fan = self.fans[fan_id]
            won = option == p.answer
            fan.streak = fan.streak + 1 if won else 0
            fan.gained = 10 + 5 * (fan.streak - 1) if won else 0
            fan.points += fan.gained
            fan.best = max(fan.best, fan.streak)
            fan.called += won
            fan.played += 1
        return self.message(pid)

    def message(self, settled: str | None = None) -> dict:
        ranked = sorted(self.fans.items(), key=lambda kv: (-kv[1].points, -kv[1].called, kv[1].name))
        rows = [{"fan": fan_id, "name": f.name, "points": f.points, "streak": f.streak, "best": f.best,
                 "called": f.called, "played": f.played, "gained": f.gained} for fan_id, f in ranked]
        return {"kind": "leaderboard", "settled": settled, "rows": rows}
