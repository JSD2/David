"""Les notifications sur le site, et les correspondances qui les font naître.

**Qui est prévenu.** Une mairie (plus largement, un accueillant) qui a
publié une recherche, quand un service ambulant y correspond : sa commune
est dans une des zones du service, l'activité est de celles qu'elle
cherche (et pas de celles qu'elle exclut), et les créneaux se recoupent —
ou l'un des deux n'en a pas donné. **Une mairie qui n'a rien demandé n'est
pas prévenue** (décision du 21 octobre).

**Dans les deux sens.** Le service publié après la recherche prévient la
mairie ; la recherche publiée après le service lui montre aussitôt les
services qui y correspondaient déjà. Une même paire ne prévient qu'une fois.

**Sur le site seulement.** Le courriel viendra avec un prestataire d'envoi ;
ce module ne s'en occupera pas, il lui passera la main.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from . import plages as pl

GENRE_CORRESPONDANCE = "service_correspondant"


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _liste(v) -> list:
    try:
        lu = json.loads(v or "[]")
    except ValueError:
        return []
    return lu if isinstance(lu, list) else []


def activite_acceptee(souhaitees: list, exclues: list, categorie: str, activite: str) -> bool:
    """Ce que la mairie cherche, face à ce que le service propose. Une
    recherche sans activité cochée les accepte toutes, sauf les exclues."""
    if categorie in exclues or activite in exclues:
        return False
    if not souhaitees:
        return True
    return categorie in souhaitees or activite in souhaitees


def correspondent(emplacement, demande) -> bool:
    """`emplacement` et `demande` : des lignes de la base."""
    return (activite_acceptee(_liste(emplacement["activites_souhaitees"]),
                              _liste(emplacement["activites_exclues"]),
                              demande["categorie"], demande["activite"])
            and pl.se_recoupent(_liste(emplacement["plages"]), _liste(demande["plages"])))


class DepotNotifications:
    def __init__(self, store):
        self._store = store

    @property
    def _conn(self):
        return self._store.connexion

    # -- faire naître les correspondances -----------------------------------

    _EMPLACEMENTS_OUVERTS = (
        "SELECT e.*, c.identifiant AS titulaire FROM emplacements e "
        "JOIN comptes c ON c.identifiant = e.compte_id "
        "WHERE e.etat = 'publie' AND c.etat = 'actif' AND c.verification = 'verifie' ")
    _DEMANDES_OUVERTES = (
        "SELECT DISTINCT d.* FROM demandes d JOIN comptes c ON c.identifiant = d.compte_id "
        "JOIN zones z ON z.demande_id = d.identifiant "
        "JOIN zone_communes zc ON zc.zone_id = z.identifiant "
        "WHERE d.etat = 'publie' AND c.etat = 'actif' ")

    def _relier(self, emplacement, demande) -> bool:
        """Enregistre la paire et prévient la mairie, une seule fois."""
        with self._store.transaction() as conn:
            r = conn.execute(
                "INSERT OR IGNORE INTO correspondances (demande_id, emplacement_id, date) "
                "VALUES (?, ?, ?)", (demande["identifiant"], emplacement["identifiant"],
                                     _maintenant()))
            if r.rowcount != 1:
                return False
            conn.execute(
                "INSERT INTO notifications (compte_id, genre, demande_id, emplacement_id, date) "
                "VALUES (?, ?, ?, ?, ?)", (emplacement["compte_id"], GENRE_CORRESPONDANCE,
                                           demande["identifiant"], emplacement["identifiant"],
                                           _maintenant()))
        return True

    def apres_demande(self, demande_id: str) -> int:
        """Une demande vient d'être publiée : les recherches de mairie des
        communes de ses zones. Rend le nombre de mairies prévenues."""
        demande = self._conn.execute("SELECT * FROM demandes WHERE identifiant = ?",
                                     (demande_id,)).fetchone()
        if demande is None or demande["etat"] != "publie":
            return 0
        emplacements = self._conn.execute(
            self._EMPLACEMENTS_OUVERTS + "AND e.code_insee IN (SELECT zc.code_insee "
            "FROM zones z JOIN zone_communes zc ON zc.zone_id = z.identifiant "
            "WHERE z.demande_id = ?)", (demande_id,)).fetchall()
        return sum(1 for e in emplacements if correspondent(e, demande) and self._relier(e, demande))

    def apres_emplacement(self, emplacement_id: str) -> int:
        """Une recherche vient d'être publiée : les services dont une zone
        couvre sa commune. Rend le nombre de services trouvés."""
        e = self._conn.execute(self._EMPLACEMENTS_OUVERTS + "AND e.identifiant = ?",
                               (emplacement_id,)).fetchone()
        if e is None or not e["code_insee"]:
            return 0
        demandes = self._conn.execute(self._DEMANDES_OUVERTES + "AND zc.code_insee = ?",
                                      (e["code_insee"],)).fetchall()
        return sum(1 for d in demandes if correspondent(e, d) and self._relier(e, d))

    # -- lire ---------------------------------------------------------------

    def du_compte(self, compte_id: str, limite: int = 50) -> dict:
        lignes = self._conn.execute(
            "SELECT n.*, d.titre AS d_titre, d.categorie, d.activite, d.plages AS d_plages, "
            "d.etat AS d_etat, e.titre AS e_titre, e.plages AS e_plages, "
            "cd.pseudo, cd.organisation "
            "FROM notifications n "
            "LEFT JOIN demandes d ON d.identifiant = n.demande_id "
            "LEFT JOIN comptes cd ON cd.identifiant = d.compte_id "
            "LEFT JOIN emplacements e ON e.identifiant = n.emplacement_id "
            "WHERE n.compte_id = ? ORDER BY n.identifiant DESC LIMIT ?",
            (compte_id, limite)).fetchall()
        non_lues = self._conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE compte_id = ? AND lue = 0",
            (compte_id,)).fetchone()[0]
        return {"non_lues": non_lues, "notifications": [
            {"identifiant": l["identifiant"], "genre": l["genre"], "lue": bool(l["lue"]),
             "date": l["date"], "demande_id": l["demande_id"],
             "emplacement_id": l["emplacement_id"],
             "service": l["organisation"] or l["pseudo"], "titre_demande": l["d_titre"],
             "demande_publiee": l["d_etat"] == "publie",
             "categorie": l["categorie"], "activite": l["activite"],
             "titre_recherche": l["e_titre"],
             "creneaux_communs": pl.communes(_liste(l["e_plages"]), _liste(l["d_plages"]))}
            for l in lignes]}

    def marquer_lues(self, compte_id: str) -> None:
        with self._store.transaction() as conn:
            conn.execute("UPDATE notifications SET lue = 1 WHERE compte_id = ? AND lue = 0",
                         (compte_id,))

    def mairies_prevenues(self, demande_id: str) -> dict:
        """code INSEE → les recherches prévenues dans cette commune."""
        sortie = {}
        for l in self._conn.execute(
                "SELECT e.code_insee, e.identifiant, e.titre, e.etat, c.organisation, k.date "
                "FROM correspondances k JOIN emplacements e ON e.identifiant = k.emplacement_id "
                "JOIN comptes c ON c.identifiant = e.compte_id WHERE k.demande_id = ?",
                (demande_id,)):
            sortie.setdefault(l["code_insee"], []).append(
                {"emplacement_id": l["identifiant"], "titre": l["titre"],
                 "organisation": l["organisation"], "date": l["date"],
                 "publiee": l["etat"] == "publie"})
        return sortie

