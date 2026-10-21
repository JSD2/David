"""Le référentiel des communes, et les communes d'une zone.

Le fichier livré (`data/communes.json.gz`, fabriqué par
`scripts/importer_communes.py`) est versé en base au démarrage, une fois :
tant que sa date et son nombre de communes ne changent pas, rien n'est
réécrit. La base garde ainsi l'index qui rend la recherche par boîte rapide,
et le serveur ne tient pas 35 000 communes en mémoire — le NAS n'a que
512 Mo.

**Une commune est dans une zone si son centre y est** (le point que donne
le référentiel). Une commune dont seul un bout de territoire déborde dans
le cercle n'est donc pas comptée : c'est voulu, et l'écran le dit.
"""

from __future__ import annotations

import gzip
import json
import re
import unicodedata
from pathlib import Path
from typing import List, Optional

from . import geo

FICHIER = Path(__file__).parent / "data" / "communes.json.gz"
CLE_VERSION = "communes_version"


def normaliser(nom: str) -> str:
    """Sans accent, sans casse, tirets et apostrophes en espaces :
    « st julien » doit trouver « Saint-Julien »."""
    t = unicodedata.normalize("NFKD", str(nom or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[-'’]", " ", t)
    t = re.sub(r"\bst\b", "saint", t)
    t = re.sub(r"\bste\b", "sainte", t)
    return re.sub(r"\s+", " ", t).strip()


def lire_fichier(chemin: Path) -> dict:
    with gzip.open(str(chemin), "rt", encoding="utf-8") as f:
        return json.load(f)


def charger(store, chemin: Optional[Path] = None) -> int:
    """Verse le référentiel en base s'il a changé. Rend le nombre de
    communes écrites (0 s'il n'y avait rien à faire)."""
    chemin = Path(chemin) if chemin else FICHIER
    donnees = lire_fichier(chemin)
    version = f"{donnees['prise_le']}:{donnees['nombre']}:{chemin.name}"
    if store.reglage(CLE_VERSION) == version:
        return 0
    lignes = [(c[0], c[1], normaliser(c[1]), c[2], c[3], c[4], c[5])
              for c in donnees["communes"]]
    with store.transaction() as conn:
        conn.execute("DELETE FROM communes")
        conn.executemany(
            "INSERT INTO communes (code_insee, nom, nom_norme, departement, latitude, "
            "longitude, population) VALUES (?, ?, ?, ?, ?, ?, ?)", lignes)
        conn.execute("INSERT OR REPLACE INTO reglages (cle, valeur) VALUES (?, ?)",
                     (CLE_VERSION, version))
        conn.execute("INSERT OR REPLACE INTO reglages (cle, valeur) VALUES (?, ?)",
                     ("communes_source", json.dumps(
                         {"source": donnees["source"], "prise_le": donnees["prise_le"],
                          "nombre": donnees["nombre"]})))
    return len(lignes)


def _dict(l) -> dict:
    return {"code_insee": l["code_insee"], "nom": l["nom"], "departement": l["departement"],
            "lat": l["latitude"], "lon": l["longitude"], "population": l["population"]}


class DepotCommunes:
    def __init__(self, store):
        self._store = store

    @property
    def _conn(self):
        return self._store.connexion

    def par_code(self, code: str) -> Optional[dict]:
        l = self._conn.execute("SELECT * FROM communes WHERE code_insee = ?",
                               (str(code or ""),)).fetchone()
        return _dict(l) if l else None

    def chercher(self, texte: str, limite: int = 10) -> List[dict]:
        """Par le début du nom, les plus peuplées d'abord : « saint j »
        propose les Saint-Julien les plus grands avant les hameaux. Un code
        postal n'est pas un code INSEE : un nombre de 5 chiffres est cherché
        comme code INSEE seulement."""
        t = normaliser(texte)
        if len(t) < 2:
            return []
        if re.fullmatch(r"\d[\dab]\d{3}", t):
            c = self.par_code(t.upper())
            return [c] if c else []
        return [_dict(l) for l in self._conn.execute(
            "SELECT * FROM communes WHERE nom_norme LIKE ? "
            "ORDER BY (nom_norme = ?) DESC, population IS NULL, population DESC LIMIT ?",
            (t.replace("%", "") + "%", t, limite))]

    def dans_boite(self, la0: float, la1: float, lo0: float, lo1: float) -> list:
        return list(self._conn.execute(
            "SELECT * FROM communes WHERE latitude BETWEEN ? AND ? "
            "AND longitude BETWEEN ? AND ?", (la0, la1, lo0, lo1)))

    def dans_cercle(self, lat: float, lon: float, rayon_km: float) -> List[dict]:
        return [_dict(l) for l in self.dans_boite(*geo.boite_cercle(lat, lon, rayon_km))
                if geo.distance_km(lat, lon, l["latitude"], l["longitude"]) <= rayon_km]

    def dans_polygone(self, points) -> List[dict]:
        return [_dict(l) for l in self.dans_boite(*geo.boite_polygone(points))
                if geo.dans_polygone(l["latitude"], l["longitude"], points)]

    def plus_proche(self, lat: float, lon: float) -> Optional[dict]:
        """La commune dont le centre est le plus proche : pour un point posé
        sans code INSEE. Une approximation près des limites communales, que
        la recherche d'adresse (qui donne le code) rend rarement nécessaire."""
        for rayon in (5, 20, 60):
            proches = self.dans_cercle(lat, lon, rayon)
            if proches:
                return min(proches, key=lambda c: geo.distance_km(lat, lon, c["lat"], c["lon"]))
        return None
