"""Les comptes : deux types, un seul parcours de connexion.

**Accueillant** (mairie, intercommunalité, camping, entreprise…) : il publie
ses recherches **dès son inscription** (décision du 22 octobre : on
s'inscrit, on est connecté, on publie). La modération garde deux gestes :
**vérifier** un compte, ce qui lui donne le badge « Accueillant vérifié »,
et **refuser** un compte qui parlerait au nom d'une commune sans en avoir
le droit — ses recherches quittent alors la carte et ne préviennent plus
personne. L'Annuaire de l'administration (service-public.fr) pourra
préremplir la vérification plus tard, sans changer ce module.

**Commerçant** (service ambulant) : il publie des demandes d'emplacement.
Son SIRET est *déclaré* ; il ne devient « vérifié » que par l'API
« recherche d'entreprises », qui n'est pas encore branchée. Rien ne le
présente comme vérifié d'ici là.

**Trois secrets n'entrent jamais en base** (repris de WAY2NAV) : le mot de
passe (empreinte scrypt seulement), le jeton de session (condensat
seulement), et rien de l'adresse IP. L'adresse électronique est en clair —
il faut bien pouvoir y écrire — mais ne sort d'aucune réponse publique.

**Le rôle** (utilisateur, modérateur, administrateur) est indépendant du
type de compte. Le niveau « abonné » n'est pas un rôle : il viendra d'un
abonnement (`droits.est_abonne`), jamais d'un choix dans la console.

Ce qui manque encore, et qu'il faut savoir : la confirmation de l'adresse
par courriel et l'oubli du mot de passe. Il n'y a pas encore de prestataire
d'envoi ; un compte est actif dès sa création.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import categories as cat

# Valeurs recommandées par l'OWASP pour scrypt. `maxmem` est posé
# explicitement : OpenSSL plafonne par défaut à 32 Mio et refuserait ce
# calcul avec une erreur peu parlante. Les paramètres sont écrits DANS
# l'empreinte : les durcir plus tard ne déconnecte personne.
SCRYPT_N = 32768
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 64 * 1024 * 1024

VIE_SESSION = timedelta(days=30)
MOT_DE_PASSE_MIN = 12
PSEUDO_MIN, PSEUDO_MAX = 2, 40

TYPES = ("accueillant", "commercant")
ROLES = ("utilisateur", "moderateur", "administrateur")
ETATS = ("actif", "suspendu")
VERIFICATIONS = ("en_attente", "verifie", "refuse")

#: Qui peut accueillir. « mairie » d'abord, mais pas seulement.
NATURES = (
    ("mairie", "Mairie"),
    ("intercommunalite", "Intercommunalité"),
    ("camping", "Camping"),
    ("zone_activite", "Zone d'activité"),
    ("entreprise", "Entreprise"),
    ("supermarche", "Parking de supermarché"),
    ("association", "Association"),
    ("organisateur", "Organisateur de marché ou d'événement"),
    ("autre", "Autre"),
)
LIBELLES_NATURES = dict(NATURES)

# Volontairement large : c'est l'envoi qui dit si une adresse existe.
_ADRESSE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CompteRefuse(ValueError):
    """La demande n'est pas recevable, et le message dit pourquoi."""


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normaliser_email(brut: str) -> str:
    return str(brut or "").strip().lower()


def normaliser_pseudo(brut: str) -> str:
    """Sans accent, sans casse : « Rémi » et « Remi » sont la même personne
    pour qui lit une liste."""
    sans = unicodedata.normalize("NFKD", str(brut or "").strip())
    sans = "".join(c for c in sans if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sans).lower()


def siret_valide(siret: str) -> bool:
    """Quatorze chiffres et la clé de Luhn.

    La Poste fait exception (SIREN 356000000) : ses établissements suivent
    une autre règle, la somme des chiffres multiple de 5.
    """
    if not re.fullmatch(r"\d{14}", siret or ""):
        return False
    if siret.startswith("356000000"):
        return sum(int(c) for c in siret) % 5 == 0
    total = 0
    for i, c in enumerate(reversed(siret)):
        n = int(c)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


# --------------------------------------------------------------------------
# Le mot de passe
# --------------------------------------------------------------------------

def hacher(mot_de_passe: str) -> str:
    sel = secrets.token_bytes(16)
    cle = hashlib.scrypt(mot_de_passe.encode("utf-8"), salt=sel, n=SCRYPT_N,
                         r=SCRYPT_R, p=SCRYPT_P, maxmem=SCRYPT_MAXMEM, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${sel.hex()}${cle.hex()}"


def verifier(mot_de_passe: str, empreinte: str) -> bool:
    """Comparaison à temps constant ; une empreinte illisible rend faux
    plutôt que de faire tomber la connexion."""
    try:
        marque, n, r, p, sel_hex, cle_hex = empreinte.split("$")
        if marque != "scrypt":
            return False
        calcul = hashlib.scrypt(mot_de_passe.encode("utf-8"), salt=bytes.fromhex(sel_hex),
                                n=int(n), r=int(r), p=int(p), maxmem=SCRYPT_MAXMEM,
                                dklen=len(bytes.fromhex(cle_hex)))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(calcul, bytes.fromhex(cle_hex))


def _condensat(jeton: str) -> str:
    return hashlib.sha256(jeton.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Le compte
# --------------------------------------------------------------------------

@dataclass
class Compte:
    identifiant: str
    email: str
    pseudo: str
    type_compte: str
    role: str
    etat: str
    organisation: Optional[str]
    nature: Optional[str]
    commune: Optional[str]
    code_insee: Optional[str]
    verification: Optional[str]
    verification_motif: Optional[str]
    siret: Optional[str]
    siret_verifie: bool
    categories: list
    presentation: Optional[str]
    date_creation: str

    @property
    def actif(self) -> bool:
        return self.etat == "actif"

    @property
    def est_accueillant(self) -> bool:
        return self.type_compte == "accueillant"

    @property
    def est_commercant(self) -> bool:
        return self.type_compte == "commercant"

    @property
    def accueillant_verifie(self) -> bool:
        """Le badge : posé par la modération, il ne conditionne rien."""
        return self.est_accueillant and self.verification == "verifie"

    @property
    def accueillant_refuse(self) -> bool:
        return self.est_accueillant and self.verification == "refuse"

    def public(self) -> dict:
        """Ce que n'importe qui peut lire : jamais l'adresse électronique,
        jamais le SIRET (il viendra avec la mise en relation)."""
        return {
            "identifiant": self.identifiant,
            "pseudo": self.pseudo,
            "type_compte": self.type_compte,
            "organisation": self.organisation,
            "nature": self.nature,
            "nature_libelle": LIBELLES_NATURES.get(self.nature or "", None),
            "commune": self.commune,
            "verifie": self.accueillant_verifie if self.est_accueillant else None,
            "entreprise_verifiee": bool(self.siret_verifie) if self.est_commercant else None,
            "categories": self.categories,
            "presentation": self.presentation,
        }

    def prive(self) -> dict:
        """Ce que le titulaire voit de son propre compte."""
        d = self.public()
        d.update({"email": self.email, "role": self.role, "etat": self.etat,
                  "verification": self.verification,
                  "verification_motif": self.verification_motif,
                  "siret": self.siret, "code_insee": self.code_insee})
        return d


def _compte(ligne) -> Compte:
    try:
        categories = json.loads(ligne["categories"] or "[]")
    except ValueError:
        categories = []
    role = ligne["role"] if ligne["role"] in ROLES else "utilisateur"
    return Compte(
        identifiant=ligne["identifiant"], email=ligne["email"], pseudo=ligne["pseudo"],
        type_compte=ligne["type_compte"], role=role, etat=ligne["etat"],
        organisation=ligne["organisation"], nature=ligne["nature"],
        commune=ligne["commune"], code_insee=ligne["code_insee"],
        verification=ligne["verification"], verification_motif=ligne["verification_motif"],
        siret=ligne["siret"], siret_verifie=bool(ligne["siret_verifie"]),
        categories=categories if isinstance(categories, list) else [],
        presentation=ligne["presentation"], date_creation=ligne["date_creation"])


def _texte(valeur, maximum: int) -> Optional[str]:
    """Un texte nettoyé, ou None s'il est vide : un champ laissé vide n'est
    pas une chaîne vide en base."""
    if valeur is None:
        return None
    t = str(valeur).strip()
    return t[:maximum] if t else None


class DepotComptes:
    def __init__(self, store):
        self._store = store

    @property
    def _conn(self):
        return self._store.connexion

    # -- création -----------------------------------------------------------

    def creer(self, email: str, pseudo: str, mot_de_passe: str, type_compte: str, *,
              organisation: str = "", nature: str = "", commune: str = "",
              code_insee: str = "", siret: str = "", categories=None,
              presentation: str = "") -> Compte:
        email_n = normaliser_email(email)
        if not _ADRESSE.match(email_n):
            raise CompteRefuse("L'adresse électronique n'a pas la bonne forme.")
        pseudo = re.sub(r"\s+", " ", str(pseudo or "").strip())
        if not PSEUDO_MIN <= len(pseudo) <= PSEUDO_MAX:
            raise CompteRefuse(
                f"Le nom affiché doit faire entre {PSEUDO_MIN} et {PSEUDO_MAX} caractères.")
        if len(mot_de_passe or "") < MOT_DE_PASSE_MIN:
            raise CompteRefuse(
                f"Le mot de passe doit faire au moins {MOT_DE_PASSE_MIN} caractères.")
        if type_compte not in TYPES:
            raise CompteRefuse("Choisir : accueillant ou commerçant.")

        verification = None
        if type_compte == "accueillant":
            if nature not in LIBELLES_NATURES:
                raise CompteRefuse("Dire qui accueille : mairie, camping, entreprise…")
            if not _texte(organisation, 120):
                raise CompteRefuse("Le nom de l'organisation est demandé "
                                   "(par exemple « Mairie de Saint-Julien »).")
            verification = "en_attente"
            siret = ""
        siret = re.sub(r"\s+", "", siret or "")
        if siret and not siret_valide(siret):
            raise CompteRefuse("Ce SIRET n'est pas valide (14 chiffres, clé de contrôle).")
        cats = [c for c in (categories or []) if c in cat.PAR_CLE]

        identifiant = secrets.token_hex(8)
        try:
            with self._store.transaction() as conn:
                conn.execute(
                    """INSERT INTO comptes (identifiant, email, pseudo, pseudo_norme,
                       empreinte, type_compte, organisation, nature, commune, code_insee,
                       verification, siret, categories, presentation, date_creation)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (identifiant, email_n, pseudo, normaliser_pseudo(pseudo),
                     hacher(mot_de_passe), type_compte, _texte(organisation, 120),
                     nature or None, _texte(commune, 120), _texte(code_insee, 5),
                     verification, siret or None, json.dumps(cats),
                     _texte(presentation, 2000), _maintenant()))
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc):
                # Le même message pour l'adresse et le nom : ne pas dire à un
                # inconnu quelle adresse a déjà un compte.
                raise CompteRefuse("Cette adresse ou ce nom affiché est déjà pris.") from exc
            raise
        return self.par_identifiant(identifiant)

    # -- lecture ------------------------------------------------------------

    def par_identifiant(self, identifiant: str) -> Optional[Compte]:
        l = self._conn.execute("SELECT * FROM comptes WHERE identifiant = ?",
                               (identifiant,)).fetchone()
        return _compte(l) if l else None

    def par_pseudo(self, pseudo: str) -> Optional[Compte]:
        l = self._conn.execute("SELECT * FROM comptes WHERE pseudo_norme = ?",
                               (normaliser_pseudo(pseudo),)).fetchone()
        return _compte(l) if l else None

    def en_attente_de_verification(self) -> list:
        return [_compte(l) for l in self._conn.execute(
            "SELECT * FROM comptes WHERE type_compte = 'accueillant' "
            "AND verification = 'en_attente' ORDER BY date_creation")]

    def tous(self) -> list:
        return [_compte(l) for l in self._conn.execute(
            "SELECT * FROM comptes ORDER BY date_creation")]

    # -- connexion ----------------------------------------------------------

    def connecter(self, email: str, mot_de_passe: str) -> Compte:
        l = self._conn.execute("SELECT * FROM comptes WHERE email = ?",
                               (normaliser_email(email),)).fetchone()
        # Le calcul est fait même sans compte : le temps de réponse ne doit
        # pas dire si l'adresse existe.
        empreinte = l["empreinte"] if l else hacher("leurre-pour-le-temps")
        bon = verifier(mot_de_passe or "", empreinte)
        if not l or not bon:
            raise CompteRefuse("Adresse ou mot de passe incorrect.")
        compte = _compte(l)
        if not compte.actif:
            raise CompteRefuse("Ce compte est suspendu.")
        return compte

    def ouvrir_session(self, compte_id: str) -> str:
        jeton = secrets.token_urlsafe(32)
        expire = (datetime.now(timezone.utc) + VIE_SESSION).isoformat(timespec="seconds")
        with self._store.transaction() as conn:
            conn.execute("INSERT INTO sessions (condensat, compte_id, expire, date_creation) "
                         "VALUES (?, ?, ?, ?)", (_condensat(jeton), compte_id, expire,
                                                 _maintenant()))
        return jeton

    def compte_de_session(self, jeton: str) -> Optional[Compte]:
        if not jeton:
            return None
        l = self._conn.execute(
            "SELECT c.*, s.expire AS s_expire FROM sessions s "
            "JOIN comptes c ON c.identifiant = s.compte_id WHERE s.condensat = ?",
            (_condensat(jeton),)).fetchone()
        if not l:
            return None
        if l["s_expire"] < _maintenant():
            self.fermer_session(jeton)
            return None
        compte = _compte(l)
        return compte if compte.actif else None

    def fermer_session(self, jeton: str) -> None:
        with self._store.transaction() as conn:
            conn.execute("DELETE FROM sessions WHERE condensat = ?", (_condensat(jeton),))

    # -- rôles et vérification ---------------------------------------------

    def promouvoir(self, pseudo: str, role: str) -> Compte:
        """La porte de la ligne de commande : pose le premier administrateur."""
        if role not in ROLES:
            raise CompteRefuse(f"Rôle inconnu : {role}")
        compte = self.par_pseudo(pseudo)
        if compte is None:
            raise CompteRefuse(f"Aucun compte « {pseudo} ».")
        with self._store.transaction() as conn:
            conn.execute("UPDATE comptes SET role = ? WHERE identifiant = ?",
                         (role, compte.identifiant))
        return self.par_identifiant(compte.identifiant)

    def changer_role(self, compte_id: str, role: str, *, par: Compte) -> Compte:
        """La porte de la console, avec ses garde-fous : on ne change pas
        son propre rôle, et on ne retire pas le dernier administrateur."""
        if role not in ROLES:
            raise CompteRefuse(f"Rôle inconnu : {role}")
        cible = self.par_identifiant(compte_id)
        if cible is None:
            raise CompteRefuse("Compte introuvable.")
        if cible.identifiant == par.identifiant:
            raise CompteRefuse("On ne change pas son propre rôle.")
        if cible.role == "administrateur" and role != "administrateur":
            n = self._conn.execute(
                "SELECT COUNT(*) FROM comptes WHERE role = 'administrateur' "
                "AND etat = 'actif'").fetchone()[0]
            if n <= 1:
                raise CompteRefuse("C'est le dernier administrateur actif.")
        with self._store.transaction() as conn:
            conn.execute("UPDATE comptes SET role = ? WHERE identifiant = ?",
                         (role, compte_id))
        return self.par_identifiant(compte_id)

    def decider_verification(self, compte_id: str, decision: str, *, par: str,
                             motif: str = "") -> Compte:
        """Vérifie ou refuse un accueillant. Le motif d'un refus est
        obligatoire : l'accueillant doit savoir quoi corriger."""
        if decision not in ("verifie", "refuse"):
            raise CompteRefuse("Décision inconnue.")
        cible = self.par_identifiant(compte_id)
        if cible is None or not cible.est_accueillant:
            raise CompteRefuse("Ce compte n'est pas un compte accueillant.")
        motif_t = _texte(motif, 500)
        if decision == "refuse" and not motif_t:
            raise CompteRefuse("Dire pourquoi la vérification est refusée.")
        with self._store.transaction() as conn:
            conn.execute(
                "UPDATE comptes SET verification = ?, verification_motif = ?, "
                "verification_par = ?, verification_date = ? WHERE identifiant = ?",
                (decision, motif_t, par, _maintenant(), compte_id))
        return self.par_identifiant(compte_id)

    def effacer(self, compte_id: str) -> None:
        """Effacer son compte est un droit de la personne (RGPD). Ses
        annonces et ses sessions partent avec lui (ON DELETE CASCADE)."""
        with self._store.transaction() as conn:
            conn.execute("DELETE FROM comptes WHERE identifiant = ?", (compte_id,))

