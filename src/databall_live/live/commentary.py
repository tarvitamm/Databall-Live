"""Play-by-play text from the match events, the way live text feeds read, in English, Spanish and Estonian."""

from __future__ import annotations

from ..stats.match import MatchData

ASSIST_WINDOW_S = 10.0

TEXT = {
    "en": {
        "start1": "First Half begins.", "start2": "Second Half begins, {score}.",
        "end1": "First Half ends, {score}.", "end2": "Match ends, {score}.",
        "foul": "Foul by {player} ({team}).", "won": "{player} ({team}) wins a free kick {where}.",
        "defensive": "in the defensive half", "attacking": "in the attacking half",
        "left_wing": "on the left wing", "right_wing": "on the right wing",
        "goal": "Goal! {score}. {player} ({team}) {how} {zone} {target}.",
        "saved": "Attempt saved. {player} ({team}) {how} {zone} is saved {target} by {keeper} ({kteam}).",
        "off_target": "Attempt missed. {player} ({team}) {how} {zone} {target}.",
        "blocked": "Attempt blocked. {player} ({team}) {how} {zone} is blocked.",
        "assist": " Assisted by {player}.", "cross": " Assisted by {player} with a cross.",
        "corner_assist": " Assisted by {player} following a corner.",
        "corner": "Corner, {team}. Conceded by {player}.",
        "right_foot": "right footed shot", "left_foot": "left footed shot", "head": "header",
        "six": "from very close range", "box_centre": "from the centre of the box",
        "box_left": "from the left side of the box", "box_right": "from the right side of the box",
        "angle_left": "from a difficult angle on the left", "angle_right": "from a difficult angle on the right",
        "outside": "from outside the box", "long": "from long range",
        "goal_left": "to the left side of the goal", "goal_centre": "to the centre of the goal",
        "goal_right": "to the right side of the goal",
        "saved_left": "on the left side", "saved_centre": "in the centre of the goal",
        "saved_right": "on the right side",
        "miss_left": "misses to the left", "miss_right": "misses to the right", "miss_high": "is too high",
    },
    "es": {
        "start1": "Comienza la primera parte.", "start2": "Comienza la segunda parte, {score}.",
        "end1": "Final de la primera parte, {score}.", "end2": "Final del partido, {score}.",
        "foul": "Falta de {player} ({team}).", "won": "{player} ({team}) recibe una falta {where}.",
        "defensive": "en su propio campo", "attacking": "en campo rival",
        "left_wing": "en la banda izquierda", "right_wing": "en la banda derecha",
        "goal": "¡Gol! {score}. {player} ({team}), {how} {zone}, {target}.",
        "saved": "Disparo parado. {player} ({team}), {how} {zone}, lo detiene {keeper} ({kteam}) {target}.",
        "off_target": "Disparo fallado. {player} ({team}), {how} {zone}, {target}.",
        "blocked": "Disparo bloqueado. {player} ({team}), {how} {zone}.",
        "assist": " Asistencia de {player}.", "cross": " Asistencia de {player} con un centro.",
        "corner_assist": " Asistencia de {player} tras un córner.",
        "corner": "Córner, {team}. Lo concede {player}.",
        "right_foot": "disparo con la derecha", "left_foot": "disparo con la izquierda", "head": "remate de cabeza",
        "six": "desde muy cerca", "box_centre": "desde el centro del área",
        "box_left": "desde el lado izquierdo del área", "box_right": "desde el lado derecho del área",
        "angle_left": "desde un ángulo difícil por la izquierda",
        "angle_right": "desde un ángulo difícil por la derecha",
        "outside": "desde fuera del área", "long": "desde lejos",
        "goal_left": "al lado izquierdo de la portería", "goal_centre": "al centro de la portería",
        "goal_right": "al lado derecho de la portería",
        "saved_left": "por el lado izquierdo", "saved_centre": "en el centro de la portería",
        "saved_right": "por el lado derecho",
        "miss_left": "se marcha por la izquierda", "miss_right": "se marcha por la derecha", "miss_high": "se va alto",
    },
    "et": {
        "start1": "Algab esimene poolaeg.", "start2": "Algab teine poolaeg, {score}.",
        "end1": "Esimene poolaeg lõppes, {score}.", "end2": "Mäng lõppes, {score}.",
        "foul": "{player} ({team}) tegi vea.", "won": "{player} ({team}) teenib vabalöögi {where}.",
        "defensive": "omal väljapoolel", "attacking": "vastase väljapoolel",
        "left_wing": "vasakul äärel", "right_wing": "paremal äärel",
        "goal": "Värav! {score}. {player} ({team}), {how} {zone}, {target}.",
        "saved": "Löök tõrjuti. {player} ({team}), {how} {zone}, {keeper} ({kteam}) tõrjub {target}.",
        "off_target": "Löök mööda. {player} ({team}), {how} {zone}, {target}.",
        "blocked": "Löök blokeeriti. {player} ({team}), {how} {zone}.",
        "assist": " Söödu andis {player}.", "cross": " Tsenderduse andis {player}.",
        "corner_assist": " Söödu andis {player} pärast nurgalööki.",
        "corner": "Nurgalöök, {team}. Põhjustas {player}.",
        "right_foot": "parema jalaga löök", "left_foot": "vasaku jalaga löök", "head": "pealöök",
        "six": "väga lähedalt", "box_centre": "karistusala keskelt",
        "box_left": "karistusala vasakult servalt", "box_right": "karistusala paremalt servalt",
        "angle_left": "teravast nurgast vasakult", "angle_right": "teravast nurgast paremalt",
        "outside": "väljastpoolt karistusala", "long": "kaugelt",
        "goal_left": "värava vasakusse poolde", "goal_centre": "värava keskele",
        "goal_right": "värava paremasse poolde",
        "saved_left": "vasakul", "saved_centre": "värava keskel", "saved_right": "paremal",
        "miss_left": "läheb vasakult mööda", "miss_right": "läheb paremalt mööda", "miss_high": "läheb üle",
    },
    "de": {
        "start1": "Anpfiff zur ersten Halbzeit.", "start2": "Anpfiff zur zweiten Halbzeit, {score}.",
        "end1": "Halbzeit, {score}.", "end2": "Spielende, {score}.", "foul": "Foul von {player} ({team}).",
        "won": "{player} ({team}) holt einen Freistoß {where} heraus.", "defensive": "in der eigenen Hälfte",
        "attacking": "in der gegnerischen Hälfte", "left_wing": "auf dem linken Flügel",
        "right_wing": "auf dem rechten Flügel", "goal": "Tor! {score}. {player} ({team}), {how} {zone}, {target}.",
        "saved": "Schuss gehalten. {player} ({team}), {how} {zone}, {keeper} ({kteam}) hält {target}.",
        "off_target": "Schuss vorbei. {player} ({team}), {how} {zone}, {target}.",
        "blocked": "Schuss geblockt. {player} ({team}), {how} {zone}.", "assist": " Vorlage von {player}.",
        "cross": " Flanke von {player}.", "corner_assist": " Vorlage von {player} nach einer Ecke.",
        "corner": "Ecke für {team}. Verursacht von {player}.", "right_foot": "Rechtsschuss",
        "left_foot": "Linksschuss", "head": "Kopfball", "six": "aus kürzester Distanz",
        "box_centre": "aus der Mitte des Strafraums", "box_left": "von der linken Seite des Strafraums",
        "box_right": "von der rechten Seite des Strafraums", "angle_left": "aus spitzem Winkel von links",
        "angle_right": "aus spitzem Winkel von rechts", "outside": "von außerhalb des Strafraums",
        "long": "aus der Distanz", "goal_left": "in die linke Torhälfte", "goal_centre": "in die Mitte des Tores",
        "goal_right": "in die rechte Torhälfte", "saved_left": "links", "saved_centre": "in der Mitte des Tores",
        "saved_right": "rechts", "miss_left": "links vorbei", "miss_right": "rechts vorbei", "miss_high": "drüber",
    },
    "fr": {
        "start1": "Début de la première période.", "start2": "Début de la seconde période, {score}.",
        "end1": "Fin de la première période, {score}.", "end2": "Fin du match, {score}.",
        "foul": "Faute de {player} ({team}).", "won": "{player} ({team}) obtient un coup franc {where}.",
        "defensive": "dans sa moitié de terrain", "attacking": "dans la moitié adverse",
        "left_wing": "sur l’aile gauche", "right_wing": "sur l’aile droite",
        "goal": "But ! {score}. {player} ({team}), {how} {zone}, {target}.",
        "saved": "Tir arrêté. {player} ({team}), {how} {zone}, arrêté {target} par {keeper} ({kteam}).",
        "off_target": "Tir manqué. {player} ({team}), {how} {zone}, {target}.",
        "blocked": "Tir contré. {player} ({team}), {how} {zone}.", "assist": " Servi par {player}.",
        "cross": " Sur un centre de {player}.", "corner_assist": " Servi par {player} sur corner.",
        "corner": "Corner pour {team}. Concédé par {player}.", "right_foot": "frappe du droit",
        "left_foot": "frappe du gauche", "head": "tête", "six": "à bout portant",
        "box_centre": "depuis le centre de la surface", "box_left": "depuis le côté gauche de la surface",
        "box_right": "depuis le côté droit de la surface", "angle_left": "dans un angle fermé à gauche",
        "angle_right": "dans un angle fermé à droite", "outside": "de l’extérieur de la surface", "long": "de loin",
        "goal_left": "à gauche du but", "goal_centre": "au centre du but", "goal_right": "à droite du but",
        "saved_left": "côté gauche", "saved_centre": "au centre", "saved_right": "côté droit",
        "miss_left": "passe à gauche", "miss_right": "passe à droite", "miss_high": "passe au-dessus",
    },
}


def attacking(md: MatchData, code: str, period: int, xy: list[float]) -> tuple[float, float]:
    """The point as seen by `code` attacking towards x = 105, so left is +y."""
    x, y = xy
    return (x, y) if md.sign(md.team_index(code), period) > 0 else (105.0 - x, 68.0 - y)


def _zone(x: float, y: float) -> str:
    depth, off = 105.0 - x, y - 34.0
    side = "left" if off > 0 else "right"
    if depth <= 5.5 and abs(off) <= 9.2:
        return "six"
    if depth <= 16.5 and abs(off) <= 20.2:
        if abs(off) > 12 and depth < 8:
            return f"angle_{side}"
        return "box_centre" if abs(off) <= 7 else f"box_{side}"
    return "long" if depth > 30 else "outside"


def _target(outcome: str, y: float) -> str:
    off = y - 34.0
    if outcome == "off_target":
        return "miss_high" if abs(off) <= 3.66 else f"miss_{'left' if off > 0 else 'right'}"
    place = "centre" if abs(off) <= 1.2 else "left" if off > 0 else "right"
    return f"{'goal' if outcome == 'goal' else 'saved'}_{place}"


def commentary(md: MatchData, lang: str) -> list[dict]:
    """Every line of the match in order, each with the period and clock it belongs to."""
    t = TEXT[lang]
    meta = md.meta
    names = {p.id: p.name for team in (meta.home, meta.away) for p in team.lineup}
    clubs = {meta.home.code: meta.home.name, meta.away.code: meta.away.name}
    keeper = {code: md.ids[md.keeper(i)] for i, code in enumerate(md.codes)}
    score = dict.fromkeys(md.codes, 0)
    passes: list[dict] = []
    lines: list[dict] = []

    def say(e: dict, kind: str, text: str, team: str | None = None) -> None:
        lines.append({"period": e["period"], "t": round(e["t"], 1), "kind": kind, "team": team, "text": text})

    def board() -> str:
        return f"{meta.home.name} {score[meta.home.code]}, {meta.away.name} {score[meta.away.code]}"

    for e in sorted(md.events, key=lambda e: (e["period"], e["t"])):
        kind, period, team = e["type"], e["period"], e.get("team")
        if kind == "half_start":
            say(e, "half", t["start1"] if period == 1 else t["start2"].format(score=board()))
        elif kind == "half_end":
            say(e, "half", t[f"end{min(period, 2)}"].format(score=board()))
        elif kind == "pass" and e.get("outcome") == "complete":
            passes.append(e)
        elif kind == "foul" and team:
            say(e, "foul", t["foul"].format(player=names.get(e["player"], ""), team=clubs[team]), team)
            victim = e.get("opponent")
            if victim:
                other = next(c for c in md.codes if c != team)
                x, y = attacking(md, other, period, e["start"])
                where = (f"{'left' if y > 34 else 'right'}_wing" if abs(y - 34) > 22
                         else "attacking" if x > 52.5 else "defensive")
                say(e, "free_kick", t["won"].format(player=names.get(victim, ""), team=clubs[other], where=t[where]),
                    other)
        elif kind == "out_of_play" and e.get("outcome") == "corner" and team:
            other = next(c for c in md.codes if c != team)
            say(e, "corner", t["corner"].format(team=clubs[other], player=names.get(e["player"], "")), other)
        elif kind == "shot" and team:
            outcome = e.get("outcome", "off_target")
            if outcome == "goal":
                score[team] += 1
            x, y = attacking(md, team, period, e["start"])
            ex, ey = attacking(md, team, period, e.get("end", [105.0, 34.0]))
            other = next(c for c in md.codes if c != team)
            text = t[outcome if outcome in t else "off_target"].format(
                score=board(), player=names.get(e["player"], ""), team=clubs[team],
                how=t.get(e.get("body_part", ""), t["right_foot"]), zone=t[_zone(x, y)], target=t[_target(outcome, ey)],
                keeper=names.get(keeper[other], ""), kteam=clubs[other])
            helper = next((p for p in reversed(passes) if p.get("recipient") == e["player"] and p["team"] == team
                           and p["period"] == period and e["t"] - p["t"] <= ASSIST_WINDOW_S), None)
            if helper:
                _, hy = attacking(md, team, period, helper["start"])
                key = ("corner_assist" if helper.get("set_piece") == "corner"
                       else "cross" if helper.get("height") == "high" and abs(hy - 34) > 20 else "assist")
                text += t[key].format(player=names.get(helper["player"], ""))
            say(e, "goal" if outcome == "goal" else "shot", text, team)
    return lines
