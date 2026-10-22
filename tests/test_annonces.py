"""Les annonces : qui publie quoi, et ce qu'on ne sait pas reste inconnu."""

import pytest

from ambulants.annonces import AnnonceRefusee
from ambulants import categories as cat
from conftest import DEMANDE, EMPLACEMENT, creer_compte


def test_un_accueillant_publie_des_son_inscription(store):
    """Décision du 22 octobre : pas d'attente de vérification."""
    a = creer_compte(store, "Lussac", "accueillant")
    f = store.annonces.publier_emplacement(a, EMPLACEMENT)
    assert f["auteur"]["verifie"] is False  # publiée, mais sans le badge
    assert [p["id"] for p in store.annonces.carte()] == [f["id"]]
    assert store.annonces.carte()[0]["verifie"] is False


def test_un_accueillant_refuse_ne_publie_plus(store):
    a = creer_compte(store, "Lussac", "accueillant")
    a = store.comptes.decider_verification(a.identifiant, "refuse", par="mod",
                                           motif="Pas la mairie")
    with pytest.raises(AnnonceRefusee, match="Pas la mairie"):
        store.annonces.publier_emplacement(a, EMPLACEMENT)


def test_un_commercant_ne_publie_pas_d_emplacement(store):
    c = creer_compte(store, "Paul")
    with pytest.raises(AnnonceRefusee, match="accueillant"):
        store.annonces.publier_emplacement(c, EMPLACEMENT)
    a = creer_compte(store, "Lussac", "accueillant", verifie=True)
    with pytest.raises(AnnonceRefusee, match="commerçant"):
        store.annonces.publier_demande(a, DEMANDE)


def test_non_renseigne_n_est_jamais_non(store):
    a = creer_compte(store, "Lussac", "accueillant", verifie=True)
    f = store.annonces.publier_emplacement(a, dict(EMPLACEMENT, eau="non"))
    assert f["electricite"] is True
    assert f["eau"] is None  # « non » en texte n'est pas une réponse
    assert f["redevance"] is None
    f = store.annonces.publier_emplacement(a, dict(EMPLACEMENT, eau=False))
    assert f["eau"] is False


def test_demande_sans_rayon_ni_surface(store):
    c = creer_compte(store, "Paul")
    f = store.annonces.publier_demande(c, dict(DEMANDE, rayon_km=None))
    assert f["rayon_km"] is None
    assert f["surface_m2"] is None
    assert f["besoin_electricite"] is None
    assert f["avertissements_activites"] == [cat.PAR_CLE["alimentaire"].avertissement]


def test_la_paire_categorie_activite_est_controlee(store):
    c = creer_compte(store, "Paul")
    with pytest.raises(AnnonceRefusee, match="catégorie"):
        store.annonces.publier_demande(c, dict(DEMANDE, activite="coiffure"))


def test_champs_propres_filtres(store):
    c = creer_compte(store, "Paul")
    f = store.annonces.publier_demande(c, dict(DEMANDE, champs_activite={
        "chaine_froid": True, "cuisson_sur_place": None, "inconnu": True, "declaration_ddpp": "oui"}))
    assert f["champs_activite"] == {"chaine_froid": True}


def test_position_obligatoire_et_valide(store):
    c = creer_compte(store, "Paul")
    with pytest.raises(AnnonceRefusee, match="Placer"):
        store.annonces.publier_demande(c, dict(DEMANDE, latitude=None))
    with pytest.raises(AnnonceRefusee, match="pas valide"):
        store.annonces.publier_demande(c, dict(DEMANDE, latitude=200))
    with pytest.raises(AnnonceRefusee, match="pas valide"):
        store.annonces.publier_demande(c, dict(DEMANDE, latitude="nan"))


def test_departements_et_jours_nettoyes(store):
    c = creer_compte(store, "Paul")
    # Sans plages horaires, les jours donnés seuls sont gardés.
    f = store.annonces.publier_demande(c, dict(DEMANDE, plages=[], departements=["23", "2a", "99", "23"],
                                               jours=["jeudi", "lundi", "férié"]))
    assert f["departements"] == ["23", "2A"]
    assert f["jours"] == ["lundi", "jeudi"]


def test_un_besoin_n_a_pas_d_adresse(store):
    a = creer_compte(store, "Lussac", "accueillant", verifie=True)
    f = store.annonces.publier_emplacement(a, dict(EMPLACEMENT, genre="besoin", adresse="1 rue X"))
    assert f["adresse"] is None
    assert f["lieu_precis"] is False


def test_carte_masquage_et_retrait(store):
    a = creer_compte(store, "Lussac", "accueillant", verifie=True)
    c = creer_compte(store, "Paul")
    e = store.annonces.publier_emplacement(a, EMPLACEMENT)
    d = store.annonces.publier_demande(c, DEMANDE)
    assert {p["id"] for p in store.annonces.carte()} == {e["id"], d["id"]}

    with pytest.raises(AnnonceRefusee, match="pourquoi"):
        store.annonces.masquer(e["id"], "")
    store.annonces.masquer(e["id"], "Doublon")
    assert {p["id"] for p in store.annonces.carte()} == {d["id"]}
    assert store.annonces.fiche(e["id"]) is None
    assert store.annonces.fiche(e["id"], lecteur_id=a.identifiant)["motif_masquage"] == "Doublon"
    store.annonces.reafficher(e["id"])

    with pytest.raises(AnnonceRefusee, match="introuvable"):
        store.annonces.retirer(a, d["id"])
    store.annonces.retirer(c, d["id"])
    assert {p["id"] for p in store.annonces.carte()} == {e["id"]}


def test_un_accueillant_refuse_apres_coup_quitte_la_carte(store):
    a = creer_compte(store, "Lussac", "accueillant", verifie=True)
    store.annonces.publier_emplacement(a, EMPLACEMENT)
    store.comptes.decider_verification(a.identifiant, "refuse", par="mod", motif="Usurpation")
    assert store.annonces.carte() == []


def test_la_fiche_ne_livre_ni_adresse_ni_siret(store):
    c = creer_compte(store, "Paul", siret="73282932000074")
    d = store.annonces.publier_demande(c, DEMANDE)
    texte = repr(store.annonces.fiche(d["id"]))
    assert "paul@exemple.fr" not in texte
    assert "73282932000074" not in texte
