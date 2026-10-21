"""Les plages horaires : un jour de la semaine, une heure de début, une
heure de fin.

La mairie dit les créneaux qu'elle souhaite ; le commerçant, ceux où il est
disponible. Deux listes se recoupent si un même jour leurs heures se
chevauchent. **Une liste vide est « non renseigné »**, pas « jamais » : elle
ne ferme rien (décision du 21 octobre : on prévient quand même).
"""

from __future__ import annotations

import re
from typing import List

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
PLAGES_MAX = 21
_HEURE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class PlageRefusee(ValueError):
    """Une plage illisible, avec la raison."""


def _minutes(heure: str) -> int:
    m = _HEURE.match(heure)
    return int(m.group(1)) * 60 + int(m.group(2))


def valider(brut) -> List[dict]:
    """Les plages reçues, nettoyées et triées ; refus si l'une est fausse.

    Une plage mal formée est refusée plutôt qu'écartée en silence : ce sont
    les heures où quelqu'un compte être là."""
    if brut is None:
        return []
    if not isinstance(brut, list):
        raise PlageRefusee("Les horaires sont illisibles.")
    if len(brut) > PLAGES_MAX:
        raise PlageRefusee(f"Au plus {PLAGES_MAX} plages horaires.")
    plages = []
    for p in brut:
        if not isinstance(p, dict) or p.get("jour") not in JOURS:
            raise PlageRefusee("Chaque plage horaire demande un jour de la semaine.")
        debut, fin = str(p.get("debut") or ""), str(p.get("fin") or "")
        if not (_HEURE.match(debut) and _HEURE.match(fin)):
            raise PlageRefusee(f"{p['jour']} : heures attendues sous la forme 08:30.")
        if _minutes(debut) >= _minutes(fin):
            raise PlageRefusee(f"{p['jour']} : l'heure de fin doit suivre l'heure de début.")
        plage = {"jour": p["jour"], "debut": debut, "fin": fin}
        if plage not in plages:
            plages.append(plage)
    return sorted(plages, key=lambda x: (JOURS.index(x["jour"]), x["debut"]))


def jours_de(plages: List[dict]) -> List[str]:
    return [j for j in JOURS if any(p["jour"] == j for p in plages)]


def se_recoupent(a: List[dict], b: List[dict]) -> bool:
    """Vrai si un même jour, les heures se chevauchent — ou si l'un des deux
    n'a rien indiqué (inconnu n'est pas « non »)."""
    if not a or not b:
        return True
    for x in a:
        for y in b:
            if (x["jour"] == y["jour"]
                    and max(_minutes(x["debut"]), _minutes(y["debut"]))
                    < min(_minutes(x["fin"]), _minutes(y["fin"]))):
                return True
    return False


def communes(a: List[dict], b: List[dict]) -> List[dict]:
    """Les créneaux communs, pour dire à la mairie quand le service peut
    venir. Vide si l'un des deux n'a rien indiqué."""
    sortie = []
    for x in a:
        for y in b:
            if x["jour"] != y["jour"]:
                continue
            d = max(_minutes(x["debut"]), _minutes(y["debut"]))
            f = min(_minutes(x["fin"]), _minutes(y["fin"]))
            if d < f:
                sortie.append({"jour": x["jour"], "debut": f"{d // 60:02d}:{d % 60:02d}",
                               "fin": f"{f // 60:02d}:{f % 60:02d}"})
    return sorted(sortie, key=lambda p: (JOURS.index(p["jour"]), p["debut"]))
