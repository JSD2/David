"""Le tableau des droits : qui peut se servir de quoi.

Repris de WAY2NAV, où la règle s'est imposée : **chaque fonction a sa
ligne**, et une livraison sans sa ligne n'est pas finie. Un essai fait
échouer la suite pour toute route du serveur qui ne nomme pas sa ligne.

**Cinq niveaux, cumulatifs** : sans compte, compte, abonné, modérateur,
administrateur. Chaque ligne a UN niveau minimum ; tout niveau au-dessus
l'a aussi.

**Pourquoi un niveau « abonné » dès maintenant.** Le modèle économique
n'est pas choisi. Si c'est « gratuit, puis payant pour aller plus loin »,
passer une fonction en payant doit être un réglage de la console et non un
chantier : il suffira de monter sa ligne à « abonné ». Personne n'est
abonné tant que l'abonnement n'existe pas (`est_abonne`) — sauf modération
et administration, qui ont tout ce qui est en dessous d'elles.

**Le type de compte** s'ajoute au niveau : publier un emplacement est
réservé aux accueillants, publier une demande aux commerçants. Ce n'est pas
un réglage : c'est le sens même de la fonction.

**Un plancher par ligne**, que la console ne franchit pas ; les lignes
d'administration sont verrouillées (les fermer fermerait la console à celui
qui la règle). Chaque ligne désactivable peut être coupée pour tout le
monde ; réactivée, elle retrouve son niveau.

**Où le droit est tenu.** « serveur » : la requête est refusée, quoi que
l'écran affiche. « écran » : ce qui ne passe par aucune requête à nous (la
recherche d'adresse va à la Géoplateforme) ne peut être retenu que par
l'écran, et la console le dit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

NIVEAUX = (
    ("visiteur", "Sans compte"),
    ("compte", "Compte"),
    ("abonne", "Abonné"),
    ("moderateur", "Modérateur"),
    ("administrateur", "Administrateur"),
)
RANG = {n: i for i, (n, _) in enumerate(NIVEAUX)}
LIBELLES = dict(NIVEAUX)

CLE_REGLAGE = "droits"
CLE_DESACTIVEES = "droits_desactives"
CLE_JOURNAL = "journal_des_droits"


class DroitRefuse(ValueError):
    """Un changement que le tableau n'accepte pas, avec sa raison."""


@dataclass(frozen=True)
class Fonctionnalite:
    cle: str
    famille: str
    libelle: str
    defaut: str
    plancher: str = "visiteur"
    verrouillee: bool = False
    controle: str = "serveur"  # « serveur » ou « ecran »
    #: « accueillant », « commercant » ou vide : le type de compte exigé.
    pour: str = ""
    #: Coupée, le site serait vide : la carte et la fiche restent.
    desactivable: bool = True


_F = Fonctionnalite
FONCTIONNALITES = (
    _F("carte", "Carte", "Voir la carte des emplacements et des demandes",
       "visiteur", desactivable=False),
    _F("fiche", "Carte", "Lire la fiche d'une annonce", "visiteur", desactivable=False),
    _F("filtre_sens", "Carte",
       "Filtre « je cherche un service » / « je cherche un emplacement »",
       "visiteur", controle="ecran"),
    # Les filtres du 22 octobre : tout se trie dans le navigateur, sur les
    # données de la carte — la ligne n'est tenue que par l'écran.
    _F("filtres_avances", "Carte",
       "Filtres : activité précise, jour et heure, équipements, mairies vérifiées, fraîcheur",
       "visiteur", controle="ecran"),
    _F("filtre_categories", "Carte", "Filtrer par catégorie d'activité", "visiteur",
       controle="ecran"),
    _F("communes", "Carte", "Chercher une commune du référentiel (zones d'action)",
       "visiteur"),
    _F("recherche_adresse", "Carte",
       "Chercher une commune ou une adresse (Base adresse nationale)", "visiteur",
       controle="ecran"),

    _F("inscription", "Compte", "Créer un compte (accueillant ou commerçant)",
       "visiteur", plancher="visiteur"),
    # Effacer son compte est un droit de la personne (RGPD) : verrouillée.
    _F("mon_compte", "Compte", "Mon compte : profil, mes annonces, effacer le compte",
       "compte", plancher="compte", verrouillee=True),

    # La cloche : une mairie y apprend qu'un service correspond à sa
    # recherche (21 octobre). Sur le site seulement, pas encore par courriel.
    _F("notifications", "Compte", "Notifications sur le site (services qui correspondent)",
       "compte", plancher="compte"),
    _F("historique_demandes", "Compte",
       "Historique de mes demandes : villes de chaque zone, mairies prévenues",
       "compte", plancher="compte", pour="commercant"),

    _F("publier_emplacement", "Publier",
       "Publier une recherche de service, avec ou sans lieu (accueillant)",
       "compte", plancher="compte", pour="accueillant"),
    _F("publier_demande", "Publier",
       "Publier une demande : zones d'action (ville, cercle, dessin), disponibilités",
       "compte", plancher="compte", pour="commercant"),
    _F("retirer_annonce", "Publier", "Retirer une de ses annonces", "compte",
       plancher="compte"),

    _F("mod_verifier_accueillants", "Modération",
       "Vérifier (badge) ou refuser un compte accueillant", "moderateur", plancher="moderateur"),
    _F("mod_annonces", "Modération", "Masquer ou réafficher une annonce",
       "moderateur", plancher="moderateur"),

    _F("adm_comptes", "Administration", "Comptes et rôles", "administrateur",
       plancher="administrateur", verrouillee=True),
    _F("adm_droits", "Administration", "Le tableau des droits", "administrateur",
       plancher="administrateur", verrouillee=True),
)
PAR_CLE = {f.cle: f for f in FONCTIONNALITES}


# --------------------------------------------------------------------------
# Qui est l'appelant
# --------------------------------------------------------------------------

def est_abonne(compte) -> bool:
    """Le compte a-t-il un abonnement en cours ?

    Toujours non : l'abonnement n'existe pas. C'est ICI qu'il se branchera,
    et nulle part ailleurs — la console ne le choisit pas.
    """
    return False


def rang_de(compte) -> int:
    if compte is None or not getattr(compte, "actif", False):
        return RANG["visiteur"]
    role = getattr(compte, "role", "")
    if role in ("moderateur", "administrateur"):
        return RANG[role]
    return RANG["abonne"] if est_abonne(compte) else RANG["compte"]


# --------------------------------------------------------------------------
# Ce que le tableau dit
# --------------------------------------------------------------------------

def _lu(store, cle: str, defaut):
    try:
        lu = json.loads(store.reglage(cle) or "null")
    except ValueError:
        return defaut
    return lu if isinstance(lu, type(defaut)) else defaut


def _borne(f: Fonctionnalite, niveau: str) -> str:
    """Un niveau ramené dans ce que la ligne permet : une valeur posée à la
    main en base ne doit pas ouvrir sous le plancher."""
    if f.verrouillee or niveau not in RANG:
        return f.defaut
    return niveau if RANG[niveau] >= RANG[f.plancher] else f.plancher


def niveaux(store) -> dict:
    poses = _lu(store, CLE_REGLAGE, {})
    return {f.cle: _borne(f, poses.get(f.cle) or f.defaut) for f in FONCTIONNALITES}


def desactivees(store) -> set:
    return {c for c in _lu(store, CLE_DESACTIVEES, [])
            if c in PAR_CLE and PAR_CLE[c].desactivable and not PAR_CLE[c].verrouillee}


def permis(store, cle: str, compte, tous: Optional[dict] = None,
           inactives: Optional[set] = None) -> bool:
    """La fonction est-elle ouverte à cet appelant ? Le type de compte
    exigé s'ajoute au niveau ; la modération n'en est pas dispensée — un
    modérateur commerçant ne publie pas d'emplacement."""
    f = PAR_CLE[cle]
    tous = niveaux(store) if tous is None else tous
    inactives = desactivees(store) if inactives is None else inactives
    if cle in inactives:
        return False
    if rang_de(compte) < RANG[tous[cle]]:
        return False
    if f.pour and getattr(compte, "type_compte", "") != f.pour:
        return False
    return True


def _consigner(store, entree: dict) -> dict:
    journal = _lu(store, CLE_JOURNAL, [])
    journal.append(entree)
    # Les 500 derniers : assez pour retrouver qui a fermé quoi.
    store.definir_reglage(CLE_JOURNAL, json.dumps(journal[-500:], ensure_ascii=False))
    return entree


def definir(store, cle: str, niveau: str, *, par: str = "") -> dict:
    f = PAR_CLE.get(cle)
    if f is None:
        raise DroitRefuse(f"Fonctionnalité inconnue : {cle}")
    if niveau not in RANG:
        raise DroitRefuse(f"Niveau inconnu : {niveau}")
    if f.verrouillee:
        raise DroitRefuse(f"« {f.libelle} » est verrouillée : elle ne se règle pas.")
    if RANG[niveau] < RANG[f.plancher]:
        raise DroitRefuse(f"« {f.libelle} » ne descend pas sous « {LIBELLES[f.plancher]} ».")
    avant = niveaux(store)[cle]
    poses = _lu(store, CLE_REGLAGE, {})
    poses[cle] = niveau
    store.definir_reglage(CLE_REGLAGE, json.dumps(poses, ensure_ascii=False))
    return _consigner(store, {"date": _maintenant(), "par": par, "cle": cle,
                             "avant": avant, "apres": niveau})


def activer(store, cle: str, active: bool, *, par: str = "") -> dict:
    f = PAR_CLE.get(cle)
    if f is None:
        raise DroitRefuse(f"Fonctionnalité inconnue : {cle}")
    if f.verrouillee or not f.desactivable:
        raise DroitRefuse(f"« {f.libelle} » ne se désactive pas.")
    inactives = desactivees(store)
    avant = "désactivée" if cle in inactives else "active"
    (inactives.discard if active else inactives.add)(cle)
    store.definir_reglage(CLE_DESACTIVEES, json.dumps(sorted(inactives)))
    return _consigner(store, {"date": _maintenant(), "par": par, "cle": cle,
                             "avant": avant, "apres": "active" if active else "désactivée"})


def journal(store) -> list:
    return _lu(store, CLE_JOURNAL, [])


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pour_le_navigateur(store, compte) -> dict:
    """Ce que la page doit savoir pour montrer, cacher ou inviter."""
    tous = niveaux(store)
    inactives = desactivees(store)
    return {
        "rang": rang_de(compte),
        "niveaux": [{"valeur": n, "libelle": l} for n, l in NIVEAUX],
        "fonctionnalites": [
            {"cle": f.cle, "famille": f.famille, "libelle": f.libelle,
             "niveau": tous[f.cle], "plancher": f.plancher, "pour": f.pour,
             "permis": permis(store, f.cle, compte, tous, inactives),
             "active": f.cle not in inactives,
             "desactivable": f.desactivable and not f.verrouillee,
             "verrouillee": f.verrouillee, "controle": f.controle}
            for f in FONCTIONNALITES
        ],
    }
