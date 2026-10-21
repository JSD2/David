"""Fabrique ambulants/data/communes.json.gz depuis le référentiel officiel.

    python3 scripts/importer_communes.py            # télécharge
    python3 scripts/importer_communes.py fichier.json --date AAAA-MM-JJ

Source : l'API Découpage administratif (geo.api.gouv.fr), communes actuelles,
avec leur centre, leur département et leur population. Le fichier livré dit
d'où il vient et quand il a été pris : on ne date pas une donnée de mémoire.

Le centre d'une commune est celui que donne l'API (un point dans la commune,
pas son contour). C'est lui qui décide si une commune est « dans » une zone.
"""

from __future__ import annotations

import argparse
import gzip
import json
import urllib.request
from datetime import date
from pathlib import Path

URL = ("https://geo.api.gouv.fr/communes?fields=nom,code,centre,codeDepartement,"
       "population&format=json")
CIBLE = Path(__file__).resolve().parent.parent / "ambulants" / "data" / "communes.json.gz"


def convertir(brutes: list, prise_le: str) -> dict:
    communes = []
    for c in brutes:
        centre = (c.get("centre") or {}).get("coordinates")
        if not centre or not c.get("code") or not c.get("nom"):
            continue
        lon, lat = centre
        # [code INSEE, nom, département, latitude, longitude, population]
        # La population absente reste absente (None), jamais zéro.
        communes.append([c["code"], c["nom"], c.get("codeDepartement"),
                         round(lat, 5), round(lon, 5), c.get("population")])
    communes.sort()
    return {"source": URL, "prise_le": prise_le, "nombre": len(communes),
            "champs": ["code_insee", "nom", "departement", "latitude", "longitude",
                       "population"],
            "communes": communes}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("fichier", nargs="?", help="réponse de l'API déjà téléchargée")
    p.add_argument("--date", help="date de la prise, si le fichier a été téléchargé avant")
    args = p.parse_args()
    if args.fichier:
        brutes = json.loads(Path(args.fichier).read_text(encoding="utf-8"))
        prise_le = args.date or date.today().isoformat()
    else:
        with urllib.request.urlopen(URL, timeout=300) as r:
            brutes = json.load(r)
        prise_le = date.today().isoformat()
    donnees = convertir(brutes, prise_le)
    CIBLE.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(CIBLE, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(donnees, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{donnees['nombre']} communes → {CIBLE} ({CIBLE.stat().st_size} octets)")


if __name__ == "__main__":
    main()
