"""Les comptes : deux types, vérification des accueillants, secrets."""

import pytest

from ambulants.comptes import CompteRefuse, hacher, siret_valide, verifier
from conftest import MOT_DE_PASSE, creer_compte


def test_le_mot_de_passe_n_est_jamais_en_clair(store):
    creer_compte(store, "Paul")
    ligne = store.connexion.execute("SELECT empreinte FROM comptes").fetchone()
    assert MOT_DE_PASSE not in ligne["empreinte"]
    assert ligne["empreinte"].startswith("scrypt$")


def test_empreinte_verifiee_et_illisible():
    e = hacher("abcdefghijklm")
    assert verifier("abcdefghijklm", e)
    assert not verifier("autre-chose-encore", e)
    assert not verifier("abcdefghijklm", "n'importe quoi")


def test_le_jeton_de_session_n_est_pas_en_base(store):
    c = creer_compte(store, "Paul")
    jeton = store.comptes.ouvrir_session(c.identifiant)
    lignes = [tuple(l) for l in store.connexion.execute("SELECT * FROM sessions")]
    assert jeton not in repr(lignes)
    assert store.comptes.compte_de_session(jeton).identifiant == c.identifiant
    store.comptes.fermer_session(jeton)
    assert store.comptes.compte_de_session(jeton) is None


def test_un_accueillant_nait_en_attente_de_verification(store):
    c = creer_compte(store, "Lussac", "accueillant")
    assert c.verification == "en_attente"
    assert not c.accueillant_verifie
    assert [x.identifiant for x in store.comptes.en_attente_de_verification()] == [c.identifiant]


def test_un_accueillant_doit_dire_qui_il_est(store):
    with pytest.raises(CompteRefuse, match="qui accueille"):
        store.comptes.creer("a@b.fr", "Anon", MOT_DE_PASSE, "accueillant", organisation="X")
    with pytest.raises(CompteRefuse, match="organisation"):
        store.comptes.creer("a@b.fr", "Anon", MOT_DE_PASSE, "accueillant", nature="mairie")


def test_un_commercant_n_a_pas_de_verification(store):
    c = creer_compte(store, "Pizzaiolo")
    assert c.verification is None
    assert c.public()["verifie"] is None


def test_refuser_demande_un_motif(store):
    c = creer_compte(store, "Lussac", "accueillant")
    with pytest.raises(CompteRefuse, match="pourquoi"):
        store.comptes.decider_verification(c.identifiant, "refuse", par="mod")
    c = store.comptes.decider_verification(c.identifiant, "refuse", par="mod",
                                           motif="Adresse non officielle")
    assert c.verification == "refuse"
    assert c.verification_motif == "Adresse non officielle"


def test_on_ne_verifie_pas_un_commercant(store):
    c = creer_compte(store, "Pizzaiolo")
    with pytest.raises(CompteRefuse, match="accueillant"):
        store.comptes.decider_verification(c.identifiant, "verifie", par="mod")


def test_adresse_et_nom_uniques_sans_dire_lequel(store):
    creer_compte(store, "Paul")
    with pytest.raises(CompteRefuse, match="adresse ou ce nom"):
        store.comptes.creer("PAUL@exemple.fr", "Autre", MOT_DE_PASSE, "commercant")
    with pytest.raises(CompteRefuse, match="adresse ou ce nom"):
        store.comptes.creer("autre@exemple.fr", "paul", MOT_DE_PASSE, "commercant")


def test_mot_de_passe_trop_court(store):
    with pytest.raises(CompteRefuse, match="12"):
        store.comptes.creer("a@b.fr", "Anon", "court", "commercant")


@pytest.mark.parametrize("siret,attendu", [
    ("73282932000074", True),     # SIRET public bien formé (clé de Luhn juste)
    ("73282932000075", False),    # clé fausse
    ("7328293200007", False),     # 13 chiffres
    # La Poste : somme des chiffres multiple de 5. Numéro construit pour la
    # règle, pas celui d'un établissement réel.
    ("35600000000001", True),
    ("35600000000002", False),
])
def test_siret(siret, attendu):
    assert siret_valide(siret) is attendu


def test_le_siret_est_declare_jamais_verifie(store):
    c = creer_compte(store, "Pizzaiolo", siret="732 829 320 00074")
    assert c.siret == "73282932000074"
    assert c.siret_verifie is False
    assert c.public()["entreprise_verifiee"] is False


def test_garde_fous_des_roles(store):
    admin = creer_compte(store, "Patronne", role="administrateur")
    autre = creer_compte(store, "Autre")
    with pytest.raises(CompteRefuse, match="propre rôle"):
        store.comptes.changer_role(admin.identifiant, "utilisateur", par=admin)
    store.comptes.changer_role(autre.identifiant, "administrateur", par=admin)
    store.comptes.changer_role(admin.identifiant, "utilisateur",
                               par=store.comptes.par_identifiant(autre.identifiant))
    with pytest.raises(CompteRefuse, match="dernier administrateur"):
        store.comptes.changer_role(autre.identifiant, "moderateur",
                                   par=store.comptes.par_identifiant(admin.identifiant))


def test_effacer_emporte_annonces_et_sessions(store):
    c = creer_compte(store, "Pizzaiolo")
    store.comptes.ouvrir_session(c.identifiant)
    store.annonces.publier_demande(c, {"titre": "T", "categorie": "alimentaire",
                                       "activite": "food_truck", "latitude": 46, "longitude": 1.9,
                                       "zones": [{"genre": "ville", "code_insee": "23096"}]})
    store.comptes.effacer(c.identifiant)
    for table in ("comptes", "sessions", "demandes", "zones", "zone_communes"):
        assert store.connexion.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
