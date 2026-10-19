"""Les annonces : les emplacements des accueillants, les demandes des
commerçants. Les deux vont sur la même carte.

**Deux sens, une carte.** Un emplacement dit « venez chez nous » ; une
demande dit « je cherche où m'installer ». Le filtre de la carte (« je
cherche un service » / « je cherche un emplacement ») choisit lequel des
deux on regarde ; chacun peut prendre l'initiative.

**Qui publie quoi** est tenu ici *et* par le tableau des droits : le
tableau dit si la fonction est ouverte et à quel niveau ; ce module refuse
qu'un commerçant publie un emplacement, ou qu'un accueillant non vérifié
publie quoi que ce soit au nom de son organisation.

**Ce qu'on ne sait pas reste inconnu.** Électricité, eau, redevance,
surface, rayon : une case non cochée n'est pas « non ». Les trois états
(oui, non, non renseigné) arrivent comme `true`, `false` ou `null`.
"""

from __future__ import annotations

import json
import math
import re
import secrets
from datetime import datetime, timezone
from typing import Optional

from . import categories as cat

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
GENRES = ("emplacement", "besoin")
_DEPARTEMENT = re.compile(r"^(0[1-9]|[1-8]\d|9[0-5]|2A|2B|97[1-6])$")

#: Ce que l'écran doit dire partout où l'on décide. Une seule rédaction,
#: pour qu'elle ne diverge pas d'un écran à l'autre.
AVERTISSEMENT_LEGAL = (
    "Ce site aide à se trouver ; il ne délivre aucune autorisation. "
    "S'installer sur le domaine public demande une autorisation de la mairie "
    "(arrêté ou convention), souvent avec une redevance. Les activités "
    "réglementées (alimentaire, santé…) ont des obligations que le site ne "
    "vérifie pas.")


class AnnonceRefusee(ValueError):
    """L'annonce n'est pas recevable, et le message dit pourquoi."""


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _texte(valeur, maximum: int) -> Optional[str]:
    if valeur is None:
        return None
    t = str(valeur).strip()
    return t[:maximum] if t else None


def _obligatoire(valeur, maximum: int, nom: str) -> str:
    t = _texte(valeur, maximum)
    if not t:
        raise AnnonceRefusee(f"{nom} est demandé.")
    return t


def _tri_etat(valeur) -> Optional[int]:
    """oui / non / non renseigné. Seuls `true` et `false` sont une réponse ;
    tout le reste — absent, `null`, une chaîne — reste « non renseigné »."""
    if valeur is True:
        return 1
    if valeur is False:
        return 0
    return None


def _position(donnees: dict):
    try:
        lat = float(donnees.get("latitude"))
        lon = float(donnees.get("longitude"))
    except (TypeError, ValueError):
        raise AnnonceRefusee("Placer l'annonce sur la carte (latitude, longitude).")
    if not (math.isfinite(lat) and math.isfinite(lon)
            and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise AnnonceRefusee("La position n'est pas valide.")
    return round(lat, 6), round(lon, 6)


def _jours(valeur) -> list:
    if not isinstance(valeur, list):
        return []
    return [j for j in JOURS if j in valeur]


def _nombre(valeur, minimum: float, maximum: float, nom: str) -> Optional[float]:
    if valeur is None or valeur == "":
        return None
    try:
        n = float(valeur)
    except (TypeError, ValueError):
        raise AnnonceRefusee(f"{nom} doit être un nombre.")
    if not (math.isfinite(n) and minimum < n <= maximum):
        raise AnnonceRefusee(f"{nom} doit être compris entre {minimum:g} et {maximum:g}.")
    return n


def _activites(valeur) -> list:
    """Une liste de catégories ou d'activités connues, dans l'ordre reçu."""
    if not isinstance(valeur, list):
        return []
    connues = set(cat.PAR_CLE) | set(cat.CATEGORIE_DE)
    vues = []
    for v in valeur:
        if v in connues and v not in vues:
            vues.append(v)
    return vues


def _json(valeur, defaut):
    try:
        lu = json.loads(valeur) if valeur else defaut
    except ValueError:
        return defaut
    return lu if isinstance(lu, type(defaut)) else defaut


def _oui_non(valeur) -> Optional[bool]:
    return None if valeur is None else bool(valeur)


class DepotAnnonces:
    def __init__(self, store):
        self._store = store

    @property
    def _conn(self):
        return self._store.connexion

    # -- publier ------------------------------------------------------------

    def publier_emplacement(self, compte, donnees: dict) -> dict:
        if not compte.est_accueillant:
            raise AnnonceRefusee("Seul un compte accueillant publie un emplacement.")
        if not compte.accueillant_verifie:
            raise AnnonceRefusee(
                "Votre compte attend sa vérification par la modération : "
                "vous pourrez publier dès qu'il sera vérifié.")
        genre = donnees.get("genre")
        if genre not in GENRES:
            raise AnnonceRefusee("Dire s'il s'agit d'un lieu précis ou d'un besoin sans lieu fixé.")
        lat, lon = _position(donnees)
        souhaitees = _activites(donnees.get("activites_souhaitees"))
        exclues = [a for a in _activites(donnees.get("activites_exclues")) if a not in souhaitees]
        identifiant = "e-" + secrets.token_hex(6)
        maintenant = _maintenant()
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO emplacements (identifiant, compte_id, genre, titre,
                   description, commune, code_insee, adresse, latitude, longitude,
                   lieu_precis, jours, creneaux, electricite, eau, redevance,
                   conditions, activites_souhaitees, activites_exclues,
                   date_creation, date_maj)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (identifiant, compte.identifiant, genre,
                 _obligatoire(donnees.get("titre"), 120, "Un titre"),
                 _texte(donnees.get("description"), 3000),
                 _obligatoire(donnees.get("commune"), 120, "La commune"),
                 _texte(donnees.get("code_insee"), 5),
                 _texte(donnees.get("adresse"), 200) if genre == "emplacement" else None,
                 lat, lon, 1 if genre == "emplacement" else 0,
                 json.dumps(_jours(donnees.get("jours"))),
                 _texte(donnees.get("creneaux"), 300),
                 _tri_etat(donnees.get("electricite")), _tri_etat(donnees.get("eau")),
                 _texte(donnees.get("redevance"), 200),
                 _texte(donnees.get("conditions"), 2000),
                 json.dumps(souhaitees), json.dumps(exclues), maintenant, maintenant))
        return self.fiche(identifiant)

    def publier_demande(self, compte, donnees: dict) -> dict:
        if not compte.est_commercant:
            raise AnnonceRefusee("Seul un compte commerçant publie une demande d'emplacement.")
        categorie = donnees.get("categorie")
        activite = donnees.get("activite")
        if not cat.valider_paire(categorie, activite):
            raise AnnonceRefusee("Choisir une catégorie et une activité de la liste.")
        lat, lon = _position(donnees)
        departements = []
        for d in donnees.get("departements") or []:
            d = str(d).strip().upper()
            if _DEPARTEMENT.match(d) and d not in departements:
                departements.append(d)
        identifiant = "d-" + secrets.token_hex(6)
        maintenant = _maintenant()
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO demandes (identifiant, compte_id, titre, description,
                   categorie, activite, commune, latitude, longitude, rayon_km,
                   departements, jours, besoin_electricite, besoin_eau, surface_m2,
                   champs_activite, date_creation, date_maj)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (identifiant, compte.identifiant,
                 _obligatoire(donnees.get("titre"), 120, "Un titre"),
                 _texte(donnees.get("description"), 3000), categorie, activite,
                 _texte(donnees.get("commune"), 120), lat, lon,
                 _nombre(donnees.get("rayon_km"), 0, 300, "Le rayon"),
                 json.dumps(departements), json.dumps(_jours(donnees.get("jours"))),
                 _tri_etat(donnees.get("besoin_electricite")),
                 _tri_etat(donnees.get("besoin_eau")),
                 _nombre(donnees.get("surface_m2"), 0, 500, "La surface"),
                 json.dumps(cat.valider_champs(categorie, donnees.get("champs_activite") or {})),
                 maintenant, maintenant))
        return self.fiche(identifiant)

    # -- changer d'état -----------------------------------------------------

    def _table(self, identifiant: str) -> str:
        if identifiant.startswith("e-"):
            return "emplacements"
        if identifiant.startswith("d-"):
            return "demandes"
        raise AnnonceRefusee("Annonce introuvable.")

    def _proprietaire(self, identifiant: str) -> Optional[str]:
        l = self._conn.execute(
            f"SELECT compte_id FROM {self._table(identifiant)} WHERE identifiant = ?",
            (identifiant,)).fetchone()
        return l["compte_id"] if l else None

    def retirer(self, compte, identifiant: str) -> None:
        """Le titulaire retire son annonce. Elle reste en base : une
        mise en relation future pourra y renvoyer."""
        if self._proprietaire(identifiant) != compte.identifiant:
            raise AnnonceRefusee("Annonce introuvable.")
        self._poser_etat(identifiant, "retire", None)

    def masquer(self, identifiant: str, motif: str) -> None:
        if self._proprietaire(identifiant) is None:
            raise AnnonceRefusee("Annonce introuvable.")
        motif_t = _texte(motif, 500)
        if not motif_t:
            raise AnnonceRefusee("Dire pourquoi l'annonce est masquée.")
        self._poser_etat(identifiant, "masque", motif_t)

    def reafficher(self, identifiant: str) -> None:
        if self._proprietaire(identifiant) is None:
            raise AnnonceRefusee("Annonce introuvable.")
        self._poser_etat(identifiant, "publie", None)

    def _poser_etat(self, identifiant: str, etat: str, motif: Optional[str]) -> None:
        with self._store.transaction() as conn:
            conn.execute(
                f"UPDATE {self._table(identifiant)} SET etat = ?, motif_masquage = ?, "
                "date_maj = ? WHERE identifiant = ?",
                (etat, motif, _maintenant(), identifiant))

    # -- lire ---------------------------------------------------------------

    def carte(self) -> list:
        """Les annonces publiées, réduites à ce que la carte dessine.

        Légère exprès : la fiche complète se lit au clic. Le nom de
        l'organisation y est, et le badge « vérifié », parce que c'est ce
        qui fait qu'on clique.
        """
        points = []
        for l in self._conn.execute(
                "SELECT e.identifiant, e.genre, e.titre, e.commune, e.latitude, "
                "e.longitude, e.jours, e.activites_souhaitees, c.organisation, "
                "c.verification FROM emplacements e JOIN comptes c "
                "ON c.identifiant = e.compte_id WHERE e.etat = 'publie' "
                "AND c.etat = 'actif' AND c.verification = 'verifie' ORDER BY e.date_creation DESC"):
            points.append({
                "id": l["identifiant"], "sens": "emplacement", "genre": l["genre"],
                "titre": l["titre"], "commune": l["commune"],
                "lat": l["latitude"], "lon": l["longitude"],
                "jours": _json(l["jours"], []),
                "activites": _json(l["activites_souhaitees"], []),
                "organisation": l["organisation"],
                "verifie": l["verification"] == "verifie"})
        for l in self._conn.execute(
                "SELECT d.identifiant, d.titre, d.commune, d.latitude, d.longitude, "
                "d.jours, d.categorie, d.activite, d.rayon_km, c.pseudo, c.organisation, "
                "c.siret_verifie FROM demandes d JOIN comptes c "
                "ON c.identifiant = d.compte_id WHERE d.etat = 'publie' "
                "AND c.etat = 'actif' ORDER BY d.date_creation DESC"):
            points.append({
                "id": l["identifiant"], "sens": "demande",
                "titre": l["titre"], "commune": l["commune"],
                "lat": l["latitude"], "lon": l["longitude"],
                "jours": _json(l["jours"], []), "categorie": l["categorie"],
                "activite": l["activite"], "rayon_km": l["rayon_km"],
                "organisation": l["organisation"] or l["pseudo"],
                "entreprise_verifiee": bool(l["siret_verifie"])})
        return points

    def fiche(self, identifiant: str, *, voir_masquee: bool = False,
              lecteur_id: str = "") -> Optional[dict]:
        """La fiche complète. Une annonce retirée ou masquée ne se lit que
        par son titulaire et par la modération."""
        try:
            table = self._table(identifiant)
        except AnnonceRefusee:
            return None
        l = self._conn.execute(f"SELECT * FROM {table} WHERE identifiant = ?",
                               (identifiant,)).fetchone()
        if not l:
            return None
        if l["etat"] != "publie" and not voir_masquee and l["compte_id"] != lecteur_id:
            return None
        auteur = self._store.comptes.par_identifiant(l["compte_id"])
        commun = {
            "id": l["identifiant"], "titre": l["titre"], "description": l["description"],
            "commune": l["commune"], "lat": l["latitude"], "lon": l["longitude"],
            "jours": _json(l["jours"], []), "etat": l["etat"],
            "motif_masquage": l["motif_masquage"] if l["etat"] == "masque" else None,
            "date_creation": l["date_creation"], "date_maj": l["date_maj"],
            "auteur": auteur.public() if auteur else None,
            "avertissement_legal": AVERTISSEMENT_LEGAL,
        }
        if table == "emplacements":
            commun.update({
                "sens": "emplacement", "genre": l["genre"], "adresse": l["adresse"],
                "lieu_precis": bool(l["lieu_precis"]), "creneaux": l["creneaux"],
                "electricite": _oui_non(l["electricite"]), "eau": _oui_non(l["eau"]),
                "redevance": l["redevance"], "conditions": l["conditions"],
                "activites_souhaitees": _json(l["activites_souhaitees"], []),
                "activites_exclues": _json(l["activites_exclues"], []),
                "avertissements_activites": [],
            })
        else:
            c = cat.PAR_CLE.get(l["categorie"])
            commun.update({
                "sens": "demande", "categorie": l["categorie"], "activite": l["activite"],
                "rayon_km": l["rayon_km"], "departements": _json(l["departements"], []),
                "besoin_electricite": _oui_non(l["besoin_electricite"]),
                "besoin_eau": _oui_non(l["besoin_eau"]), "surface_m2": l["surface_m2"],
                "champs_activite": _json(l["champs_activite"], {}),
                "avertissements_activites": [c.avertissement] if c and c.avertissement else [],
            })
        return commun

    def du_compte(self, compte_id: str) -> list:
        """Les annonces d'un compte, tous états confondus."""
        ids = [l["identifiant"] for l in self._conn.execute(
            "SELECT identifiant, date_creation FROM emplacements WHERE compte_id = ? "
            "UNION ALL SELECT identifiant, date_creation FROM demandes WHERE compte_id = ? "
            "ORDER BY date_creation DESC", (compte_id, compte_id))]
        return [self.fiche(i, voir_masquee=True) for i in ids]
