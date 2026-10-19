"""Le tableau des droits, et la règle qui le tient à jour : chaque route
du serveur nomme sa ligne, ou figure dans la courte liste des routes sans
ligne, avec sa raison."""

import re

import pytest

from ambulants import api, droits
from conftest import creer_compte

#: Les routes sans ligne. En ajouter une demande de l'écrire ici ET de dire
#: pourquoi dans `api.ROUTES` : c'est voulu.
ROUTES_SANS_LIGNE = {
    ("GET", "fichier"), ("GET", "service_worker"), ("GET", "robots"), ("GET", "api_sante"),
    ("GET", "api_session"), ("POST", "api_connexion"), ("POST", "api_deconnexion"),
}


def test_chaque_route_nomme_une_ligne_du_tableau():
    for r in api.ROUTES:
        if r.droit is None:
            assert (r.methode, r.action) in ROUTES_SANS_LIGNE, (
                f"{r.methode} {r.motif} n'a pas de ligne dans le tableau des droits")
        else:
            assert r.droit in droits.PAR_CLE, f"{r.motif} nomme une ligne inconnue : {r.droit}"


def test_chaque_route_a_sa_methode():
    for r in api.ROUTES:
        assert callable(getattr(api.Gestionnaire, r.action, None)), r.action


def test_chaque_ligne_serveur_sert_a_une_route():
    """Une ligne « serveur » qu'aucune route ne porte ne protège rien."""
    portees = {r.droit for r in api.ROUTES if r.droit}
    for f in droits.FONCTIONNALITES:
        if f.controle == "serveur":
            assert f.cle in portees, f"La ligne « {f.cle} » n'est tenue par aucune route"


def test_les_motifs_ne_se_chevauchent_pas():
    vus = set()
    for r in api.ROUTES:
        cle = (r.methode, r.motif)
        assert cle not in vus, cle
        vus.add(cle)
        re.compile(r.motif)


def test_cinq_niveaux_dont_abonne():
    assert [n for n, _ in droits.NIVEAUX] == [
        "visiteur", "compte", "abonne", "moderateur", "administrateur"]


def test_personne_n_est_abonne_tant_que_l_abonnement_n_existe_pas(store):
    c = creer_compte(store, "Paul")
    assert droits.rang_de(c) == droits.RANG["compte"]
    assert droits.rang_de(None) == droits.RANG["visiteur"]


def test_monter_une_ligne_a_abonne_la_ferme_aux_comptes(store):
    """Le modèle « gratuit puis payant » : un réglage, pas un chantier."""
    c = creer_compte(store, "Paul")
    assert droits.permis(store, "publier_demande", c)
    droits.definir(store, "publier_demande", "abonne", par="essai")
    assert not droits.permis(store, "publier_demande", c)
    mod = creer_compte(store, "Modo", role="moderateur")
    assert droits.permis(store, "publier_demande", mod)


def test_le_type_de_compte_s_ajoute_au_niveau(store):
    commercant = creer_compte(store, "Paul", role="administrateur")
    accueillant = creer_compte(store, "Lussac", "accueillant", verifie=True)
    assert droits.permis(store, "publier_demande", commercant)
    assert not droits.permis(store, "publier_emplacement", commercant)
    assert droits.permis(store, "publier_emplacement", accueillant)
    assert not droits.permis(store, "publier_demande", accueillant)


def test_plancher_et_verrou(store):
    with pytest.raises(droits.DroitRefuse, match="ne descend pas"):
        droits.definir(store, "publier_demande", "visiteur")
    with pytest.raises(droits.DroitRefuse, match="verrouillée"):
        droits.definir(store, "adm_droits", "moderateur")
    with pytest.raises(droits.DroitRefuse, match="ne se désactive pas"):
        droits.activer(store, "carte", False)
    with pytest.raises(droits.DroitRefuse, match="ne se désactive pas"):
        droits.activer(store, "mon_compte", False)


def test_une_valeur_posee_a_la_main_sous_le_plancher_est_ramenee(store):
    store.definir_reglage(droits.CLE_REGLAGE, '{"publier_demande": "visiteur", "adm_droits": "visiteur"}')
    n = droits.niveaux(store)
    assert n["publier_demande"] == "compte"
    assert n["adm_droits"] == "administrateur"


def test_desactiver_puis_reactiver_rend_le_niveau(store):
    c = creer_compte(store, "Paul")
    droits.definir(store, "publier_demande", "abonne")
    droits.activer(store, "publier_demande", False)
    assert not droits.permis(store, "publier_demande", c)
    droits.activer(store, "publier_demande", True)
    assert droits.niveaux(store)["publier_demande"] == "abonne"


def test_chaque_changement_est_consigne(store):
    droits.definir(store, "publier_demande", "abonne", par="Patronne")
    droits.activer(store, "inscription", False, par="Patronne")
    j = droits.journal(store)
    assert [(e["cle"], e["avant"], e["apres"], e["par"]) for e in j] == [
        ("publier_demande", "compte", "abonne", "Patronne"),
        ("inscription", "active", "désactivée", "Patronne")]


def test_un_compte_suspendu_est_un_visiteur(store):
    c = creer_compte(store, "Paul")
    store.connexion.execute("UPDATE comptes SET etat = 'suspendu'")
    store.connexion.commit()
    assert droits.rang_de(store.comptes.par_identifiant(c.identifiant)) == droits.RANG["visiteur"]
