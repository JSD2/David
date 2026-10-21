"""Ce que les essais partagent : une base neuve, un serveur réellement
démarré sur un port éphémère, et un petit client qui garde ses cookies."""

from __future__ import annotations

import http.cookiejar
import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from ambulants.api import construire_serveur
from ambulants.store import Store

os.environ.setdefault("AMBULANTS_SILENCE", "1")
MOT_DE_PASSE = "un-mot-de-passe-assez-long"


#: Un extrait réel du référentiel (Creuse et Haute-Vienne) : verser les
#: 35 000 communes à chaque essai ralentirait la suite pour rien.
COMMUNES_ESSAI = Path(__file__).parent / "donnees" / "communes-essai.json.gz"
GUERET, LIMOGES = "23096", "87085"


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "essai.sqlite3", communes=COMMUNES_ESSAI)
    yield s
    s.close()


@pytest.fixture
def serveur(store):
    srv = construire_serveur(store, "127.0.0.1", 0)
    fil = threading.Thread(target=srv.serve_forever, daemon=True)
    fil.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


class Client:
    """Un navigateur réduit : il garde ses cookies et parle JSON."""

    def __init__(self, base: str):
        self.base = base
        self.jarre = http.cookiejar.CookieJar()
        self.ouvreur = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jarre))

    def requete(self, methode: str, chemin: str, corps=None, entetes=None):
        donnees = None if corps is None else json.dumps(corps).encode("utf-8")
        e = {"Content-Type": "application/json"} if corps is not None else {}
        e.update(entetes or {})
        req = urllib.request.Request(self.base + chemin, data=donnees, method=methode, headers=e)
        try:
            with self.ouvreur.open(req, timeout=10) as r:
                brut = r.read()
                return r.status, (json.loads(brut) if brut[:1] in (b"{", b"[") else brut), r.headers
        except urllib.error.HTTPError as err:
            brut = err.read()
            try:
                lu = json.loads(brut)
            except ValueError:
                lu = brut
            return err.code, lu, err.headers

    def get(self, chemin, **kw):
        return self.requete("GET", chemin, **kw)

    def post(self, chemin, corps=None, **kw):
        return self.requete("POST", chemin, {} if corps is None else corps, **kw)


@pytest.fixture
def client(serveur):
    return Client(serveur)


@pytest.fixture
def nouveau_client(serveur):
    return lambda: Client(serveur)


def creer_compte(store, pseudo, type_compte="commercant", role="", verifie=False, **kw):
    """Un compte fabriqué en base : ces essais éprouvent l'API, le parcours
    d'inscription a les siens."""
    if type_compte == "accueillant":
        kw.setdefault("organisation", f"Mairie de {pseudo}")
        kw.setdefault("nature", "mairie")
    c = store.comptes.creer(f"{pseudo.lower()}@exemple.fr", pseudo, MOT_DE_PASSE, type_compte, **kw)
    if role:
        store.comptes.promouvoir(pseudo, role)
    if verifie:
        store.comptes.decider_verification(c.identifiant, "verifie", par="essai")
    return store.comptes.par_identifiant(c.identifiant)


def connecter(client, compte):
    statut, _, _ = client.post("/api/session", {"email": compte.email, "mot_de_passe": MOT_DE_PASSE})
    assert statut == 200
    return client


#: Une recherche de la mairie de Guéret : un lieu précis, le mardi matin.
EMPLACEMENT = {
    "genre": "emplacement", "titre": "Place du marché, le mardi", "commune": "Guéret",
    "code_insee": GUERET, "latitude": 46.1712, "longitude": 1.8715,
    "plages": [{"jour": "mardi", "debut": "08:00", "fin": "13:00"}],
    "electricite": True, "eau": None,
}
#: Un food truck installé près de Guéret, qui tourne dans 30 km.
DEMANDE = {
    "titre": "Pizzas au feu de bois", "categorie": "alimentaire", "activite": "food_truck",
    "latitude": 46.10, "longitude": 1.95,
    "zones": [{"genre": "cercle", "lat": 46.10, "lon": 1.95, "rayon_km": 30}],
    "plages": [{"jour": "mardi", "debut": "11:00", "fin": "14:00"},
               {"jour": "jeudi", "debut": "18:00", "fin": "22:00"}],
}
