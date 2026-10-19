"""L'API HTTP, serveur réellement démarré sur un port éphémère."""

import gzip
import json
import urllib.request

from ambulants import droits
from conftest import DEMANDE, EMPLACEMENT, MOT_DE_PASSE, connecter, creer_compte

INSCRIPTION_ACCUEILLANT = {
    "type_compte": "accueillant", "pseudo": "Lussac", "email": "mairie@lussac.fr",
    "mot_de_passe": MOT_DE_PASSE, "nature": "mairie", "organisation": "Mairie de Lussac",
    "commune": "Lussac", "conditions_acceptees": True,
}


def test_sante(client):
    statut, corps, _ = client.get("/api/sante")
    assert statut == 200 and corps["ok"] is True


def test_parcours_accueillant_de_l_inscription_a_la_carte(client, nouveau_client, store):
    statut, corps, entetes = client.post("/api/comptes", INSCRIPTION_ACCUEILLANT)
    assert statut == 201
    assert "HttpOnly" in entetes["Set-Cookie"] and "SameSite=Lax" in entetes["Set-Cookie"]
    assert corps["compte"]["verification"] == "en_attente"

    # Pas encore vérifié : refusé, et l'écran sait dire pourquoi.
    statut, corps, _ = client.post("/api/emplacements", EMPLACEMENT)
    assert statut == 403 and "vérification" in corps["erreur"]

    modo = connecter(nouveau_client(), creer_compte(store, "Modo", role="moderateur"))
    statut, corps, _ = modo.get("/api/moderation/accueillants")
    assert [c["organisation"] for c in corps["comptes"]] == ["Mairie de Lussac"]
    assert corps["comptes"][0]["email"] == "mairie@lussac.fr"
    ident = corps["comptes"][0]["identifiant"]
    statut, _, _ = modo.post(f"/api/moderation/accueillants/{ident}", {"decision": "verifie"})
    assert statut == 200

    statut, fiche, _ = client.post("/api/emplacements", EMPLACEMENT)
    assert statut == 201 and fiche["auteur"]["verifie"] is True

    statut, carte, _ = nouveau_client().get("/api/carte")
    assert [a["id"] for a in carte["annonces"]] == [fiche["id"]]


def test_inscription_sans_conditions_refusee(client):
    statut, corps, _ = client.post("/api/comptes", dict(INSCRIPTION_ACCUEILLANT, conditions_acceptees=False))
    assert statut == 400 and "conditions" in corps["erreur"]


def test_visiteur_refuse_avec_401(client):
    statut, corps, _ = client.post("/api/demandes", DEMANDE)
    assert statut == 401 and corps["erreur"]


def test_commercant_publie_une_demande(client, store):
    connecter(client, creer_compte(store, "Paul"))
    statut, fiche, _ = client.post("/api/demandes", DEMANDE)
    assert statut == 201
    statut, corps, _ = client.post("/api/emplacements", EMPLACEMENT)
    assert statut == 403 and "accueillants" in corps["erreur"]
    statut, moi, _ = client.get("/api/moi")
    assert [a["id"] for a in moi["annonces"]] == [fiche["id"]]


def test_connexion_mauvais_mot_de_passe_puis_limiteur(client, store):
    c = creer_compte(store, "Paul")
    statut, corps, _ = client.post("/api/session", {"email": c.email, "mot_de_passe": "faux-faux-faux"})
    assert statut == 400 and "incorrect" in corps["erreur"]
    for _ in range(9):
        client.post("/api/session", {"email": c.email, "mot_de_passe": "faux-faux-faux"})
    statut, _, _ = client.post("/api/session", {"email": c.email, "mot_de_passe": MOT_DE_PASSE})
    assert statut == 429


def test_deconnexion(client, store):
    connecter(client, creer_compte(store, "Paul"))
    assert client.get("/api/session")[1]["compte"]["pseudo"] == "Paul"
    client.post("/api/session/fin")
    assert client.get("/api/session")[1]["compte"] is None


def test_l_adresse_ne_sort_d_aucune_reponse_publique(client, nouveau_client, store):
    c = creer_compte(store, "Paul", siret="73282932000074")
    connecter(client, c)
    _, fiche, _ = client.post("/api/demandes", DEMANDE)
    visiteur = nouveau_client()
    for chemin in ("/api/carte", f"/api/annonces/{fiche['id']}", "/api/session", "/"):
        _, corps, _ = visiteur.get(chemin)
        texte = corps.decode("utf-8") if isinstance(corps, bytes) else json.dumps(corps)
        assert "paul@exemple.fr" not in texte, chemin
        assert "73282932000074" not in texte, chemin


def test_ecriture_exige_json_et_meme_origine(client, store):
    connecter(client, creer_compte(store, "Paul"))
    statut, _, _ = client.requete("POST", "/api/demandes", None,
                                  {"Content-Type": "application/x-www-form-urlencoded"})
    assert statut == 415
    statut, _, _ = client.post("/api/demandes", DEMANDE, entetes={"Origin": "https://ailleurs.example"})
    assert statut == 403


def test_carte_compressee_et_etag(serveur, client, store):
    connecter(client, creer_compte(store, "Paul"))
    for i in range(20):
        client.post("/api/demandes", dict(DEMANDE, titre=f"Demande {i}"))
    req = urllib.request.Request(serveur + "/api/carte", headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req) as r:
        assert r.headers["Content-Encoding"] == "gzip"
        etag = r.headers["ETag"]
        assert len(json.loads(gzip.decompress(r.read()))["annonces"]) == 20
    statut, _, _ = client.get("/api/carte", entetes={"If-None-Match": etag})
    assert statut == 304


def test_fonction_desactivee_fermee(client, store):
    droits.activer(store, "inscription", False)
    statut, corps, _ = client.post("/api/comptes", INSCRIPTION_ACCUEILLANT)
    assert statut == 403 and "fermée" in corps["erreur"]


def test_console_des_droits(client, nouveau_client, store):
    connecter(client, creer_compte(store, "Patronne", role="administrateur"))
    statut, tableau, _ = client.get("/api/admin/droits")
    assert statut == 200 and len(tableau["fonctionnalites"]) == len(droits.FONCTIONNALITES)
    statut, tableau, _ = client.post("/api/admin/droits", {"cle": "publier_demande", "niveau": "abonne"})
    assert statut == 200 and tableau["journal"][-1]["apres"] == "abonne"
    statut, corps, _ = client.post("/api/admin/droits", {"cle": "adm_droits", "niveau": "compte"})
    assert statut == 400

    paul = connecter(nouveau_client(), creer_compte(store, "Paul"))
    assert paul.get("/api/admin/droits")[0] == 403
    assert paul.post("/api/demandes", DEMANDE)[0] == 403


def test_moderation_masque_une_annonce(client, nouveau_client, store):
    paul = connecter(nouveau_client(), creer_compte(store, "Paul"))
    _, fiche, _ = paul.post("/api/demandes", DEMANDE)
    connecter(client, creer_compte(store, "Modo", role="moderateur"))
    statut, _, _ = client.post(f"/api/moderation/annonces/{fiche['id']}", {"action": "masquer"})
    assert statut == 400
    client.post(f"/api/moderation/annonces/{fiche['id']}", {"action": "masquer", "motif": "Doublon"})
    assert nouveau_client().get(f"/api/annonces/{fiche['id']}")[0] == 404
    assert client.get(f"/api/annonces/{fiche['id']}")[1]["etat"] == "masque"
    assert paul.get(f"/api/annonces/{fiche['id']}")[1]["motif_masquage"] == "Doublon"


def test_effacer_son_compte_redemande_le_mot_de_passe(client, store):
    connecter(client, creer_compte(store, "Paul"))
    assert client.post("/api/moi/effacer", {"mot_de_passe": "faux-faux-faux"})[0] == 400
    assert client.post("/api/moi/effacer", {"mot_de_passe": MOT_DE_PASSE})[0] == 200
    assert store.comptes.tous() == []


def test_inconnu_et_methode(client):
    assert client.get("/api/rien")[0] == 404
    assert client.get("/api/demandes")[0] == 405
    assert client.get("/static/../store.py")[0] == 404
