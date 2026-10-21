"""Season talking points for commentary, in each language."""

from __future__ import annotations

from ..insights.text import num
from ..stats.match import MatchData
from ..stats.season import Season

TALK = {
    "last": {"en": "Last meeting: {home} {hs}-{aws} {away}.", "es": "Último duelo: {home} {hs}-{aws} {away}.",
             "et": "Eelmine kohtumine: {home} {hs}-{aws} {away}."},
    "form": {"en": "Last five: {home} {hf}; {away} {af}.", "es": "Últimos cinco: {home} {hf}; {away} {af}.",
             "et": "Viimased viis: {home} {hf}; {away} {af}."},
    "press": {"en": "{team} press {v} times a minute on average, the most in the league.",
              "es": "{team} presionan {v} veces por minuto de media, más que nadie en la liga.",
              "et": "{team} survestab keskmiselt {v} korda minutis, liigas kõige rohkem."},
    "xg": {"en": "{team} create {v} xG a game this season.", "es": "{team} generan {v} xG por partido esta temporada.",
           "et": "{team} loob sel hooajal {v} xG mängu kohta."},
    "decoys": {"en": "Most decoy runs on the pitch this season: {list}.",
               "es": "Más desmarques de arrastre en el campo esta temporada: {list}.",
               "et": "Platsil olijatest kõige rohkem petteliikumisi sel hooajal: {list}."},
    "goals": {"en": "Most goals on the pitch this season: {list}.",
              "es": "Más goles en el campo esta temporada: {list}.",
              "et": "Platsil olijatest kõige rohkem väravaid sel hooajal: {list}."},
    "leads": {"en": " {name} leads the league.", "es": " {name} lidera la liga.", "et": " {name} on liigas esimene."},
    "fastest": {"en": "Fastest on the pitch: {name}, {v} km/h this season.",
                "es": "El más rápido en el campo: {name}, {v} km/h esta temporada.",
                "et": "Platsi kiireim: {name}, sel hooajal {v} km/h."},
    "league_best": {"en": " The league's best.", "es": " La mejor marca de la liga.", "et": " Liiga parim tulemus."},
}
RESULTS = {
    "en": (("win", "wins"), ("draw", "draws"), ("loss", "losses")),
    "es": (("victoria", "victorias"), ("empate", "empates"), ("derrota", "derrotas")),
    "et": (("võit", "võitu"), ("viik", "viiki"), ("kaotus", "kaotust")),
}


def _form(form: str, lang: str) -> str:
    parts = []
    for letter, (one, many) in zip("WDL", RESULTS[lang], strict=True):
        n = form.count(letter)
        parts.append(f"{n} {one if n == 1 else many}")
    return ", ".join(parts)


def talking_points(md: MatchData, s: Season, lang: str) -> list[str]:
    t = {key: text[lang] for key, text in TALK.items()}
    home, away = md.codes
    name = {team.code: team.name for team in (md.meta.home, md.meta.away)}
    player = {p.id: p.name for team in (md.meta.home, md.meta.away) for p in team.lineup}
    out = []
    met = s.last_meeting(home, away)
    if met:
        out.append(t["last"].format(home=name[home], hs=met["score"][home], aws=met["score"][away], away=name[away]))
    if s.games(home) and s.games(away):
        out.append(t["form"].format(home=name[home], hf=_form(s.form(home), lang), away=name[away],
                                    af=_form(s.form(away), lang)))
    for code in (home, away):
        rank = s.team_rank(code, "pressures_per_min")
        if rank and rank[0] == 1:
            out.append(t["press"].format(team=name[code], v=num(s.team_avg(code, "pressures_per_min") or 0, lang, 1)))
        xg = s.team_avg(code, "xg")
        if xg is not None:
            out.append(t["xg"].format(team=name[code], v=num(xg, lang, 2)))
    on_pitch = set(md.ids)
    for metric in ("decoy_runs", "goals"):
        table = s.leaders(metric)
        mine = [(pid, v) for pid, v in table if pid in on_pitch and v > 0][:2]
        if not mine:
            continue
        text = t["decoys" if metric == "decoy_runs" else "goals"].format(
            list=", ".join(f"{player.get(pid, pid)} {int(v)}" for pid, v in mine))
        alone = table[0][0] == mine[0][0] and (len(table) < 2 or table[0][1] > table[1][1])
        out.append(text + (t["leads"].format(name=player.get(mine[0][0], mine[0][0])) if alone else ""))
    fastest = max(((s.player_best(pid, "top_speed_kmh") or 0.0, pid) for pid in on_pitch), default=(0.0, ""))
    if fastest[0]:
        league = s.league_best("top_speed_kmh")
        line = t["fastest"].format(name=player.get(fastest[1], fastest[1]), v=num(fastest[0], lang, 1))
        out.append(line + (t["league_best"] if league and league[1] == fastest[1] else ""))
    return out
