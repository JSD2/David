"""Zones d'action, plages horaires, communes, et mairies prévenues."""

import gzip
import json

import pytest

from ambulants import geo, plages as pl
from ambulants.annonces import AnnonceRefusee
from ambulants.communes import FICHIER, charger, normaliser
from ambulants.notifications import activite_acceptee
from ambulants.store import Store
from conftest import (DEMANDE, EMPLACEMENT, GUERET, LIMOGES, connecter, creer_compte)

#: Un contour tracé autour de Guéret (centre 46.1585, 1.8705), qui laisse
#: Limoges (45.8567, 1.226) dehors.
AUTOUR_DE_GUERET = [[46.25, 1.75], [46.25, 2.0], [46.05, 2.0], [46.05, 1.75]]


def codes(liste):
    return {c["code_insee"] for c in liste}


# --------------------------------------------------------------------------
# Géométrie, horaires, référentiel
# --------------------------------------------------------------------------

def test_point_dans_un_polygone():
    assert geo.dans_polygone(46.1585, 1.8705, AUTOUR_DE_GUERET)
    assert not geo.dans_polygone(45.8567, 1.226, AUTOUR_DE_GUERET)


def test_distance():
    # Guéret – Limoges : environ 63 km à vol d'oiseau.
    assert 60 < geo.distance_km(46.1585, 1.8705, 45.8567, 1.226) < 66


def test_plages_refusees():
    for brut, motif in (
            ([{"jour": "mardi", "debut": "8h", "fin": "12:00"}], "08:30"),
            ([{"jour": "mardi", "debut": "14:00", "fin": "12:00"}], "fin"),
            ([{"jour": "férié", "debut": "08:00", "fin": "12:00"}], "jour"),
            ("mardi", "illisibles")):
        with pytest.raises(pl.PlageRefusee, match=motif):
            pl.valider(brut)


def test_plages_qui_se_recoupent():
    mardi_matin = [{"jour": "mardi", "debut": "08:00", "fin": "13:00"}]
    assert pl.se_recoupent(mardi_matin, [{"jour": "mardi", "debut": "12:00", "fin": "14:00"}])
    assert not pl.se_recoupent(mardi_matin, [{"jour": "mardi", "debut": "13:00", "fin": "14:00"}])
    assert not pl.se_recoupent(mardi_matin, [{"jour": "jeudi", "debut": "08:00", "fin": "13:00"}])
    # Non renseigné n'est pas « jamais ».
    assert pl.se_recoupent(mardi_matin, []) and pl.se_recoupent([], mardi_matin)
    assert pl.communes(mardi_matin, [{"jour": "mardi", "debut": "11:00", "fin": "14:00"}]) == [
        {"jour": "mardi", "debut": "11:00", "fin": "13:00"}]


def test_le_referentiel_livre(tmp_path):
    donnees = json.load(gzip.open(str(FICHIER), "rt", encoding="utf-8"))
    assert donnees["source"].startswith("https://geo.api.gouv.fr/communes")
    assert donnees["prise_le"] == "2026-10-21"
    assert donnees["nombre"] == len(donnees["communes"]) > 34000
    # Une population absente reste absente : jamais zéro inventé.
    assert all(c[5] is None or c[5] >= 0 for c in donnees["communes"])
    s = Store(tmp_path / "b.sqlite3")
    assert s.communes_versees == donnees["nombre"]
    assert charger(s) == 0  # rien à réécrire au démarrage suivant
    assert s.communes.par_code(GUERET)["nom"] == "Guéret"
    s.close()


def test_chercher_une_commune(store):
    assert normaliser("St-Junien") == "saint junien"
    assert store.communes.chercher("st junien")[0]["nom"] == "Saint-Junien"
    assert store.communes.chercher("gueret")[0]["code_insee"] == GUERET
    assert store.communes.chercher(GUERET)[0]["nom"] == "Guéret"
    assert store.communes.chercher("g") == []


# --------------------------------------------------------------------------
# Les zones
# --------------------------------------------------------------------------

def test_trois_sortes_de_zones(store):
    ville = store.zones.lire({"genre": "ville", "code_insee": GUERET})
    assert codes(ville["communes"]) == {GUERET}
    cercle = store.zones.lire({"genre": "cercle", "lat": 46.1585, "lon": 1.8705, "rayon_km": 10})
    assert GUERET in codes(cercle["communes"]) and LIMOGES not in codes(cercle["communes"])
    dessin = store.zones.lire({"genre": "polygone", "points": AUTOUR_DE_GUERET})
    assert GUERET in codes(dessin["communes"]) and LIMOGES not in codes(dessin["communes"])


@pytest.mark.parametrize("zone,motif", [
    ({"genre": "ville", "code_insee": "99999"}, "référentiel"),
    ({"genre": "cercle", "lat": 46, "lon": 1.9, "rayon_km": 400}, "rayon"),
    ({"genre": "cercle", "lat": 46, "lon": 1.9, "rayon_km": 0}, "rayon"),
    ({"genre": "polygone", "points": [[46, 1], [46.1, 1.1]]}, "trois points"),
    ({"genre": "polygone", "points": [[42, -4], [51, -4], [51, 8]]}, "600"),
    ({"genre": "département"}, "ville, un cercle ou un dessin"),
])
def test_zones_refusees(store, zone, motif):
    with pytest.raises(ValueError, match=motif):
        store.zones.lire(zone)


def test_une_demande_sans_zone_est_refusee(store):
    c = creer_compte(store, "Paul")
    with pytest.raises(AnnonceRefusee, match="au moins une zone"):
        store.annonces.publier_demande(c, dict(DEMANDE, zones=[]))


# --------------------------------------------------------------------------
# Qui est prévenu
# --------------------------------------------------------------------------

def _mairie(store, nom="Gueret", **recherche):
    m = creer_compte(store, nom, "accueillant", verifie=True)
    return m, store.annonces.publier_emplacement(m, dict(EMPLACEMENT, **recherche))


def _non_lues(store, compte):
    return store.notifications.du_compte(compte.identifiant)["non_lues"]


def test_la_mairie_qui_cherche_est_prevenue(store):
    mairie, _ = _mairie(store)
    f = store.annonces.publier_demande(creer_compte(store, "Paul"), DEMANDE)
    assert f["mairies_prevenues"] == 1
    n = store.notifications.du_compte(mairie.identifiant)
    assert n["non_lues"] == 1
    assert n["notifications"][0]["titre_demande"] == "Pizzas au feu de bois"
    assert n["notifications"][0]["creneaux_communs"] == [
        {"jour": "mardi", "debut": "11:00", "fin": "13:00"}]


def test_une_mairie_qui_n_a_rien_demande_n_est_pas_prevenue(store):
    silencieuse = creer_compte(store, "Silence", "accueillant", verifie=True,
                               commune="Guéret", code_insee=GUERET)
    store.annonces.publier_demande(creer_compte(store, "Paul"), DEMANDE)
    assert _non_lues(store, silencieuse) == 0


def test_hors_zone_pas_prevenue(store):
    mairie, _ = _mairie(store)
    store.annonces.publier_demande(creer_compte(store, "Paul"), dict(
        DEMANDE, zones=[{"genre": "ville", "code_insee": LIMOGES}]))
    assert _non_lues(store, mairie) == 0


def test_activite_exclue_ou_non_cherchee(store):
    assert activite_acceptee([], [], "alimentaire", "food_truck")
    assert activite_acceptee(["alimentaire"], [], "alimentaire", "food_truck")
    assert activite_acceptee(["food_truck"], [], "alimentaire", "food_truck")
    assert not activite_acceptee(["sante"], [], "alimentaire", "food_truck")
    assert not activite_acceptee([], ["food_truck"], "alimentaire", "food_truck")

    mairie, _ = _mairie(store, activites_souhaitees=["sante"])
    store.annonces.publier_demande(creer_compte(store, "Paul"), DEMANDE)
    assert _non_lues(store, mairie) == 0


def test_creneaux_disjoints_pas_prevenue_mais_inconnus_si(store):
    mairie, _ = _mairie(store, plages=[{"jour": "lundi", "debut": "08:00", "fin": "12:00"}])
    store.annonces.publier_demande(creer_compte(store, "Paul"), DEMANDE)
    assert _non_lues(store, mairie) == 0
    # Sans créneaux : prévenue du service déjà là, puis du suivant.
    autre, recherche = _mairie(store, "Gueret2", plages=[])
    assert recherche["services_trouves"] == 1
    store.annonces.publier_demande(creer_compte(store, "Pierre"), DEMANDE)
    assert _non_lues(store, autre) == 2


def test_la_recherche_publiee_apres_trouve_les_services_deja_la(store):
    store.annonces.publier_demande(creer_compte(store, "Paul"), DEMANDE)
    mairie, recherche = _mairie(store)
    assert recherche["services_trouves"] == 1
    assert _non_lues(store, mairie) == 1


def test_une_paire_ne_previent_qu_une_fois(store):
    mairie, recherche = _mairie(store)
    f = store.annonces.publier_demande(creer_compte(store, "Paul"), dict(
        DEMANDE, zones=[{"genre": "ville", "code_insee": GUERET},
                        {"genre": "cercle", "lat": 46.1585, "lon": 1.8705, "rayon_km": 5}]))
    assert f["mairies_prevenues"] == 1
    assert store.notifications.apres_emplacement(recherche["id"]) == 0
    assert _non_lues(store, mairie) == 1
    store.notifications.marquer_lues(mairie.identifiant)
    assert _non_lues(store, mairie) == 0


def test_point_pose_sans_code_insee(store):
    """Un point posé à la main : la commune la plus proche."""
    _, recherche = _mairie(store, code_insee=None)
    assert store.connexion.execute("SELECT code_insee FROM emplacements WHERE identifiant = ?",
                                   (recherche["id"],)).fetchone()[0] == GUERET


def test_historique_villes_et_mairies_prevenues(store):
    mairie, recherche = _mairie(store)
    paul = creer_compte(store, "Paul")
    store.annonces.publier_demande(paul, dict(DEMANDE, zones=[
        {"genre": "ville", "code_insee": GUERET},
        {"genre": "polygone", "points": AUTOUR_DE_GUERET}]))
    (h,) = store.annonces.historique(paul.identifiant)
    ville, dessin = h["zones"]
    assert ville["libelle"] == "Guéret" and [c["nom"] for c in ville["communes"]] == ["Guéret"]
    assert ville["communes"][0]["prevenues"][0]["emplacement_id"] == recherche["id"]
    assert dessin["nombre_communes"] == len(dessin["communes"]) > 1
    assert dessin["polygone"] == AUTOUR_DE_GUERET
    assert h["nombre_mairies_prevenues"] == 1


def test_la_fiche_publique_ne_livre_que_les_contours(store):
    _mairie(store)
    f = store.annonces.publier_demande(creer_compte(store, "Paul"), DEMANDE)
    publique = store.annonces.fiche(f["id"])
    assert publique["zones"][0]["genre"] == "cercle"
    assert "communes" not in publique["zones"][0]
    assert "prevenues" not in json.dumps(publique)


# --------------------------------------------------------------------------
# Par l'API
# --------------------------------------------------------------------------

def test_api_apercu_communes_historique_notifications(client, nouveau_client, store):
    mairie = connecter(nouveau_client(), creer_compte(store, "Gueret", "accueillant", verifie=True))
    assert mairie.post("/api/emplacements", EMPLACEMENT)[0] == 201

    connecter(client, creer_compte(store, "Paul"))
    statut, apercu, _ = client.post("/api/zones/apercu", {"zone": {"genre": "polygone",
                                                                   "points": AUTOUR_DE_GUERET}})
    assert statut == 200 and "Guéret" in [c["nom"] for c in apercu["communes"]]
    assert client.post("/api/zones/apercu", {"zone": {"genre": "cercle"}})[0] == 400

    statut, trouvees, _ = nouveau_client().get("/api/communes?q=gu%C3%A9ret")
    assert statut == 200 and trouvees["communes"][0]["code_insee"] == GUERET

    statut, fiche, _ = client.post("/api/demandes", DEMANDE)
    assert statut == 201 and fiche["mairies_prevenues"] == 1
    statut, h, _ = client.get("/api/moi/historique")
    assert statut == 200 and h["demandes"][0]["nombre_mairies_prevenues"] == 1

    # L'historique des demandes est celui des commerçants.
    assert mairie.get("/api/moi/historique")[0] == 403
    statut, n, _ = mairie.get("/api/notifications")
    assert statut == 200 and n["non_lues"] == 1
    assert n["notifications"][0]["demande_id"] == fiche["id"]
    mairie.post("/api/notifications/lues")
    assert mairie.get("/api/notifications")[1]["non_lues"] == 0
    assert nouveau_client().get("/api/notifications")[0] == 401


def test_api_horaires_faux_refuses(client, store):
    connecter(client, creer_compte(store, "Paul"))
    statut, corps, _ = client.post("/api/demandes", dict(
        DEMANDE, plages=[{"jour": "mardi", "debut": "14:00", "fin": "09:00"}]))
    assert statut == 400 and "fin" in corps["erreur"]
