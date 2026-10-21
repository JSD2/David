"""Les zones d'action d'un service ambulant, et les communes qu'elles
couvrent.

Trois façons de dire où l'on va : **une ville** (une commune du
référentiel), **un cercle** (un centre et un rayon), **un dessin à main
levée** (un contour tracé sur la carte). Une demande en porte une ou
plusieurs.

Les communes de chaque zone sont calculées **une fois, à la publication**,
et gardées (`zone_communes`) : c'est la liste que le commerçant retrouve
dans son historique, et celle qui décide quelles mairies sont prévenues.
"""

from __future__ import annotations

import json
import math
import secrets
from datetime import datetime, timezone
from typing import List

from . import geo

GENRES = ("ville", "cercle", "polygone")
ZONES_MAX = 10


class ZoneRefusee(ValueError):
    """Une zone illisible, avec la raison."""


def _nombre(v, nom: str) -> float:
    try:
        n = float(v)
    except (TypeError, ValueError):
        raise ZoneRefusee(f"{nom} : un nombre est attendu.")
    if not math.isfinite(n):
        raise ZoneRefusee(f"{nom} : un nombre est attendu.")
    return n


class DepotZones:
    def __init__(self, store):
        self._store = store

    @property
    def _conn(self):
        return self._store.connexion

    def lire(self, brut) -> dict:
        """Une zone reçue, validée, avec ses communes. Sert à l'aperçu
        (avant publication) comme à l'enregistrement."""
        if not isinstance(brut, dict) or brut.get("genre") not in GENRES:
            raise ZoneRefusee("Une zone est une ville, un cercle ou un dessin.")
        genre = brut["genre"]
        if genre == "ville":
            commune = self._store.communes.par_code(brut.get("code_insee"))
            if commune is None:
                raise ZoneRefusee("Cette ville n'est pas dans le référentiel des communes.")
            return {"genre": "ville", "code_insee": commune["code_insee"],
                    "lat": commune["lat"], "lon": commune["lon"], "rayon_km": None,
                    "polygone": None, "libelle": commune["nom"], "communes": [commune]}
        if genre == "cercle":
            lat = _nombre(brut.get("lat"), "Le centre")
            lon = _nombre(brut.get("lon"), "Le centre")
            rayon = _nombre(brut.get("rayon_km"), "Le rayon")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ZoneRefusee("Le centre du cercle est hors de la carte.")
            if not 0 < rayon <= geo.RAYON_MAX_KM:
                raise ZoneRefusee(f"Le rayon va de 1 à {geo.RAYON_MAX_KM:g} km.")
            return {"genre": "cercle", "code_insee": None, "lat": round(lat, 6),
                    "lon": round(lon, 6), "rayon_km": round(rayon, 1), "polygone": None,
                    "libelle": f"Cercle de {rayon:g} km",
                    "communes": self._store.communes.dans_cercle(lat, lon, rayon)}
        try:
            points = geo.valider_polygone(brut.get("points"))
        except ValueError as exc:
            raise ZoneRefusee(str(exc))
        return {"genre": "polygone", "code_insee": None, "lat": None, "lon": None,
                "rayon_km": None, "polygone": points, "libelle": "Zone dessinée",
                "communes": self._store.communes.dans_polygone(points)}

    def lire_toutes(self, brutes) -> List[dict]:
        if not isinstance(brutes, list) or not brutes:
            raise ZoneRefusee("Indiquer au moins une zone : une ville, un cercle ou un dessin.")
        if len(brutes) > ZONES_MAX:
            raise ZoneRefusee(f"Au plus {ZONES_MAX} zones par demande.")
        return [self.lire(b) for b in brutes]

    def enregistrer(self, conn, demande_id: str, zones: List[dict]) -> None:
        """Dans la transaction de la demande : tout ou rien."""
        maintenant = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for rang, z in enumerate(zones):
            zid = "z-" + secrets.token_hex(6)
            conn.execute(
                "INSERT INTO zones (identifiant, demande_id, rang, genre, code_insee, latitude, "
                "longitude, rayon_km, polygone, date_creation) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (zid, demande_id, rang, z["genre"], z["code_insee"], z["lat"], z["lon"],
                 z["rayon_km"], json.dumps(z["polygone"]) if z["polygone"] else None,
                 maintenant))
            conn.executemany("INSERT OR IGNORE INTO zone_communes (zone_id, code_insee) "
                             "VALUES (?, ?)", [(zid, c["code_insee"]) for c in z["communes"]])

    def de_la_demande(self, demande_id: str, *, avec_communes: bool = False) -> List[dict]:
        """Les zones d'une demande, dans l'ordre où elles ont été données.
        Les communes ne sont jointes que pour l'historique du titulaire."""
        zones = []
        for l in self._conn.execute("SELECT * FROM zones WHERE demande_id = ? ORDER BY rang",
                                    (demande_id,)):
            z = {"identifiant": l["identifiant"], "genre": l["genre"],
                 "code_insee": l["code_insee"], "lat": l["latitude"], "lon": l["longitude"],
                 "rayon_km": l["rayon_km"],
                 "polygone": json.loads(l["polygone"]) if l["polygone"] else None}
            if l["genre"] == "ville":
                c = self._store.communes.par_code(l["code_insee"])
                z["libelle"] = c["nom"] if c else l["code_insee"]
            elif l["genre"] == "cercle":
                z["libelle"] = f"Cercle de {l['rayon_km']:g} km"
            else:
                z["libelle"] = "Zone dessinée"
            z["nombre_communes"] = self._conn.execute(
                "SELECT COUNT(*) FROM zone_communes WHERE zone_id = ?",
                (l["identifiant"],)).fetchone()[0]
            if avec_communes:
                z["communes"] = [
                    {"code_insee": c["code_insee"], "nom": c["nom"],
                     "departement": c["departement"]}
                    for c in self._conn.execute(
                        "SELECT c.code_insee, c.nom, c.departement FROM zone_communes zc "
                        "JOIN communes c ON c.code_insee = zc.code_insee "
                        "WHERE zc.zone_id = ? ORDER BY c.nom_norme", (l["identifiant"],))]
            zones.append(z)
        return zones
