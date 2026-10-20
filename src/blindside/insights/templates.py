"""Headline and body templates per insight type, language and persona.

Placeholders are filled from an insight's facts. A missing persona falls back to "fan".
"""

from __future__ import annotations

T: dict[str, dict[str, dict[str, tuple[str, str]]]] = {
    "pressure_harder": {
        "en": {"analyst": ("{team}: pressing harder", "Pressures per min {pa} (was {pb}), line {la} m (was {lb} m). Led by {leaders}."),
               "fan": ("{team} are hunting the ball", "{team} now press high and early. {leaders} lead the charge."),
               "player_focus": ("{focus} is leading the press", "{focus} has {fn} pressures in the last 10 minutes.")},
        "es": {"analyst": ("{team}: presión más alta", "Presiones por min {pa} (antes {pb}), línea {la} m (antes {lb} m). Lideran {leaders}."),
               "fan": ("{team} salen a presionar", "{team} presionan arriba y rápido. {leaders} encabezan la presión."),
               "player_focus": ("{focus} lidera la presión", "{focus} suma {fn} presiones en los últimos 10 minutos.")},
        "et": {"analyst": ("{team}: kõrgem press", "Survestusi minutis {pa} (enne {pb}), kaitseliin {la} m (enne {lb} m). Eestvedajad: {leaders}."),
               "fan": ("{team} pressib nüüd kõrgelt", "{team} ründab palli juba vastase poolel. Eest veavad {leaders}."),
               "player_focus": ("{focus} veab pressi", "{focus}: {fn} survestust viimase 10 minutiga.")},
    },
    "pressure_softer": {
        "en": {"analyst": ("{team}: pressing less", "Pressures per min {pa} (was {pb}), line {la} m (was {lb} m)."),
               "fan": ("{team} have dropped off", "{team} are sitting deeper and letting {opp} have the ball.")},
        "es": {"analyst": ("{team}: menos presión", "Presiones por min {pa} (antes {pb}), línea {la} m (antes {lb} m)."),
               "fan": ("{team} dan un paso atrás", "{team} esperan más atrás y ceden el balón a {opp}.")},
        "et": {"analyst": ("{team}: madalam press", "Survestusi minutis {pa} (enne {pb}), kaitseliin {la} m (enne {lb} m)."),
               "fan": ("{team} taandus sügavamale", "{team} ootab nüüd tagapool ja annab palli vastasele.")},
    },
    "decoy_run": {
        "en": {"analyst": ("Decoy run: {runner}", "Dragged {defender} ({pos}) {d} m. {benef} attacked the space{served}."),
               "fan": ("{runner} made space without the ball", "The run pulled {opp}'s {pos} {d} m out of position. {benef} ran into the gap."),
               "player_focus": ("{runner}: invisible work", "No touch, but the run dragged the {pos} {d} m and opened space for {benef}.")},
        "es": {"analyst": ("Desmarque de arrastre: {runner}", "Arrastró a {defender} ({pos}) {d} m. {benef} atacó el espacio{served}."),
               "fan": ("{runner} abre espacio sin balón", "Su desmarque se llevó al {pos} de {opp} {d} m. {benef} aprovechó el hueco."),
               "player_focus": ("{runner}: trabajo invisible", "Sin tocarla, arrastró al {pos} {d} m y abrió espacio para {benef}.")},
        "et": {"analyst": ("Petteliikumine: {runner}", "{defender} ({pos}) järgnes talle {d} m. {benef} ründas vabanenud ala{served}."),
               "fan": ("{runner} lõi ruumi ilma pallita", "Vastase {pos} järgnes jooksule {d} m ja jättis ala tühjaks. {benef} jooksis sinna."),
               "player_focus": ("{runner}: nähtamatu töö", "Pallita, kuid {pos} järgnes jooksule {d} m ja ruum avanes. Kasu sai {benef}.")},
    },
    "chain_decoy": {
        "en": {"analyst": ("{outcome}: {shooter}", "xG {xg}, {passes} in {sec} s. It started off the ball: {decoy} dragged {defender}."),
               "fan": ("{outcome}: {shooter}", "{decoy} never touched it, but the run pulled {defender} away and opened the way."),
               "player_focus": ("{outcome}: {shooter}", "{decoy}'s run made this chance. {defender} followed and the space opened.")},
        "es": {"analyst": ("{outcome}: {shooter}", "xG {xg}, {passes} en {sec} s. Empezó sin balón: {decoy} arrastró a {defender}."),
               "fan": ("{outcome}: {shooter}", "{decoy} ni la tocó, pero su desmarque se llevó a {defender} y abrió el camino."),
               "player_focus": ("{outcome}: {shooter}", "El desmarque de {decoy} creó esta ocasión. {defender} le siguió y se abrió el espacio.")},
        "et": {"analyst": ("{outcome}: {shooter}", "xG {xg}, {passes} {sec} sekundiga. Algas ilma pallita: {defender} järgnes jooksjale {decoy}."),
               "fan": ("{outcome}: {shooter}", "{decoy} palli ei puudutanudki, kuid {defender} järgnes jooksule ja tee avanes."),
               "player_focus": ("{outcome}: {shooter}", "Võimaluse lõi jooks, mille tegi {decoy}. {defender} järgnes ja ruum avanes.")},
    },
    "chain": {
        "en": {"analyst": ("{outcome}: {shooter}", "xG {xg}, {passes} in {sec} s."),
               "fan": ("{outcome}: {shooter}", "{passes}, {sec} seconds, and {shooter} gets the shot away.")},
        "es": {"analyst": ("{outcome}: {shooter}", "xG {xg}, {passes} en {sec} s."),
               "fan": ("{outcome}: {shooter}", "{passes}, {sec} segundos, y {shooter} remata.")},
        "et": {"analyst": ("{outcome}: {shooter}", "xG {xg}, {passes} {sec} sekundiga."),
               "fan": ("{outcome}: {shooter}", "{passes}, {sec} sekundit ja {shooter} lööb.")},
    },
    "momentum_swing": {
        "en": {"analyst": ("Momentum: {team}", "Threat balance has swung to {team}. Drivers: {drivers}."),
               "fan": ("{team} are on top now", "The game has swung their way in the last few minutes.")},
        "es": {"analyst": ("Impulso: {team}", "El balance de amenaza favorece ahora a {team}. Factores: {drivers}."),
               "fan": ("{team} mandan ahora", "El partido ha girado a su favor en los últimos minutos.")},
        "et": {"analyst": ("Hoog: {team}", "Ohtlikkuse tasakaal on pöördunud. Peal on {team}. Põhjused: {drivers}."),
               "fan": ("{team} valitseb nüüd mängu", "Viimastel minutitel on mäng pöördunud nende kasuks.")},
    },
    "chaotic": {
        "en": {"analyst": ("Control lost: open game", "Possession changes {tpm} times a minute, {under}% of passes under pressure."),
               "fan": ("This has turned chaotic", "Nobody can keep the ball for long. Expect chances at both ends.")},
        "es": {"analyst": ("Sin control: partido abierto", "La posesión cambia {tpm} veces por minuto, {under}% de pases bajo presión."),
               "fan": ("El partido se ha vuelto loco", "Nadie retiene el balón. Habrá ocasiones en las dos áreas.")},
        "et": {"analyst": ("Kontroll kadus: avatud mäng", "Pall vahetab omanikku {tpm} korda minutis, {under}% söötudest surve all."),
               "fan": ("Mäng on läinud kaootiliseks", "Keegi ei hoia palli kaua. Oodata on võimalusi mõlemas otsas.")},
    },
    "in_control": {
        "en": {"analyst": ("{team} in control", "Control {ca} vs {cb}, possession {poss}%, territory {terr}%."),
               "fan": ("{team} are running this", "{team} have the ball and are keeping {opp} pinned back.")},
        "es": {"analyst": ("{team} tienen el control", "Control {ca} frente a {cb}, posesión {poss}%, territorio {terr}%."),
               "fan": ("{team} dominan", "{team} tienen el balón y encierran a {opp}.")},
        "et": {"analyst": ("{team} kontrollib mängu", "Kontroll {ca} vs {cb}, pallivaldamine {poss}%, territoorium {terr}%."),
               "fan": ("{team} juhib mängu", "{team} hoiab palli ja surub vastase tagasi.")},
    },
    "counter_press": {
        "en": {"analyst": ("Counter-press: {team}", "{n} players closed in, ball won back in {s} s."),
               "fan": ("{team} win it straight back", "Lost it, swarmed it, won it back in {s} seconds.")},
        "es": {"analyst": ("Contrapresión: {team}", "{n} jugadores cerraron, balón recuperado en {s} s."),
               "fan": ("{team} la recuperan al instante", "La pierden, presionan y la recuperan en {s} segundos.")},
        "et": {"analyst": ("Vastupress: {team}", "{n} mängijat sulges ruumi, pall tagasi {s} sekundiga."),
               "fan": ("{team} võitis palli kohe tagasi", "Kaotasid, ründasid kohe ja võitsid tagasi {s} sekundiga.")},
    },
    "gap_exploited": {
        "en": {"analyst": ("Gap between the lines", "{team} left {gap} m between their lines. {player} received in it."),
               "fan": ("{opp} found the gap", "{player} picked up the ball in the space between {team}'s lines.")},
        "es": {"analyst": ("Espacio entre líneas", "{team} dejaron {gap} m entre líneas. {player} recibió ahí."),
               "fan": ("{opp} encuentran el hueco", "{player} recibió en el espacio entre las líneas de {team}.")},
        "et": {"analyst": ("Ruum liinide vahel", "{team} jättis liinide vahele {gap} m. Seal sai palli {player}."),
               "fan": ("Vastane leidis augu", "{player} sai palli vabast ruumist liinide vahel.")},
    },
    "overload": {
        "en": {"analyst": ("Overload: {team}", "{a} v {d} near the ball on the {side}."),
               "fan": ("{team} have the numbers", "{a} against {d} on the {side}. Watch that side.")},
        "es": {"analyst": ("Superioridad: {team}", "{a} contra {d} cerca del balón por la {side}."),
               "fan": ("{team} tienen superioridad", "{a} contra {d} por la {side}. Atentos a esa banda.")},
        "et": {"analyst": ("Ülekaal: {team}", "Palli lähedal {a} vs {d}, {side}."),
               "fan": ("{team} on arvulises ülekaalus", "{a} {d} vastu, {side}. Jälgi seda äärt.")},
    },
    "fatigue": {
        "en": {"analyst": ("Fatigue: {player}", "High-intensity running {pct}% vs the first 15 min. Top speed {now} km/h (was {early})."),
               "fan": ("{player} is tiring", "The sprints are fading. A change could be coming."),
               "player_focus": ("{player} is tiring", "Top speed now {now} km/h, down from {early} early on.")},
        "es": {"analyst": ("Fatiga: {player}", "Carrera de alta intensidad {pct}% frente a los primeros 15 min. Velocidad máxima {now} km/h (antes {early})."),
               "fan": ("{player} acusa el cansancio", "Ya no llega a los sprints. Puede haber cambio."),
               "player_focus": ("{player} acusa el cansancio", "Velocidad máxima ahora {now} km/h, antes {early}.")},
        "et": {"analyst": ("Väsimus: {player}", "Kiire jooks {pct}% võrreldes esimese 15 minutiga. Tippkiirus {now} km/h (enne {early})."),
               "fan": ("{player} väsib", "Spurtidest on jõud otsas. Vahetus võib tulla."),
               "player_focus": ("{player} väsib", "Tippkiirus nüüd {now} km/h, alguses {early}.")},
    },
}

TAGS: dict[str, dict[str, str]] = {
    "speed_tag": {"en": "{player} {v} km/h", "es": "{player} {v} km/h", "et": "{player} {v} km/h"},
    "match_top_speed": {"en": "Fastest today: {player} {v} km/h", "es": "Más rápido hoy: {player} {v} km/h",
                        "et": "Päeva kiireim: {player} {v} km/h"},
    "distance_milestone": {"en": "{player}: {km} km covered", "es": "{player}: {km} km recorridos",
                           "et": "{player}: {km} km läbitud"},
    "shot_speed": {"en": "{player}: shot at {v} km/h", "es": "{player}: disparo a {v} km/h",
                   "et": "{player}: löök {v} km/h"},
    "difficult_pass": {"en": "{player}: pass difficulty {diff}/10, {m} m", "es": "{player}: pase de dificultad {diff}/10, {m} m",
                       "et": "{player}: söödu raskus {diff}/10, {m} m"},
    "line_breaking_pass": {"en": "{player} breaks {n} lines", "es": "{player} rompe {n} líneas",
                           "et": "{player} lõhub {n} liini"},
    "recovery_run": {"en": "{player}: {m} m sprint back", "es": "{player}: {m} m de repliegue",
                     "et": "{player}: {m} m tagasijooks"},
}

OUTCOME = {"en": {"goal": "GOAL", "saved": "Saved", "blocked": "Blocked", "off_target": "Wide"},
           "es": {"goal": "GOL", "saved": "Parada", "blocked": "Bloqueado", "off_target": "Fuera"},
           "et": {"goal": "VÄRAV", "saved": "Tõrje", "blocked": "Blokeeritud", "off_target": "Mööda"}}

PASSES = {"en": ("{n} pass", "{n} passes"), "es": ("{n} pase", "{n} pases"), "et": ("{n} sööt", "{n} söötu")}

SERVED = {"en": " and got the ball", "es": " y recibió el balón", "et": " ja sai palli"}

DRIVER = {
    "en": {"pressure_shift": "pressing", "decoy_run": "decoy runs", "overload": "overloads", "counter_press": "counter-pressing",
           "line_breaking_pass": "line-breaking passes", "between_lines_gap": "space between the lines", "fatigue": "tired legs",
           "chain": "dangerous attacks"},
    "es": {"pressure_shift": "presión", "decoy_run": "desmarques de arrastre", "overload": "superioridades",
           "counter_press": "contrapresión", "line_breaking_pass": "pases entre líneas", "between_lines_gap": "espacio entre líneas",
           "fatigue": "cansancio", "chain": "ataques peligrosos"},
    "et": {"pressure_shift": "press", "decoy_run": "petteliikumised", "overload": "ülekaal", "counter_press": "vastupress",
           "line_breaking_pass": "liine lõhkuvad söödud", "between_lines_gap": "ruum liinide vahel", "fatigue": "väsimus",
           "chain": "ohtlikud rünnakud"},
}

RECAP = {
    "en": {"half_time": "Half-time", "full_time": "Full-time", "catch_up": "Catch-up",
           "body": "{home} {hs}-{as_} {away}. xG {hx}-{ax}. Key moments: {moments}."},
    "es": {"half_time": "Descanso", "full_time": "Final", "catch_up": "Resumen",
           "body": "{home} {hs}-{as_} {away}. xG {hx}-{ax}. Momentos clave: {moments}."},
    "et": {"half_time": "Poolaeg", "full_time": "Lõpuvile", "catch_up": "Kokkuvõte",
           "body": "{home} {hs}-{as_} {away}. xG {hx}-{ax}. Võtmehetked: {moments}."},
}
