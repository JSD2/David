"""La base SQLite : une connexion partagée, verrouillée, et les dépôts.

Repris de WAY2NAV, avec la leçon qui l'accompagne : le serveur sert chaque
requête dans son fil, et deux lectures simultanées sur une connexion SQLite
sans verrou suffisent à rendre une erreur 500 au hasard. La connexion est
donc enveloppée (`ConnexionVerrouillee`) : une instruction à la fois, ses
lignes lues en entier sous le verrou.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Union

from . import migrations

#: Variable d'environnement qui désigne le fichier de la base.
VARIABLE_BASE = "AMBULANTS_DB"


def chemin_defaut() -> Path:
    brut = os.environ.get(VARIABLE_BASE, "").strip()
    return Path(brut) if brut else Path.cwd() / "ambulants.sqlite3"


class _Resultat:
    """Les lignes d'une requête, lues en entier sous le verrou."""

    __slots__ = ("_lignes", "rowcount", "lastrowid", "description")

    def __init__(self, curseur: sqlite3.Cursor):
        self.description = curseur.description
        self._lignes = curseur.fetchall() if curseur.description else []
        self.rowcount = curseur.rowcount
        self.lastrowid = curseur.lastrowid

    def fetchone(self):
        return self._lignes.pop(0) if self._lignes else None

    def fetchall(self):
        lignes, self._lignes = self._lignes, []
        return lignes

    def __iter__(self):
        return iter(self.fetchall())


class ConnexionVerrouillee:
    """La connexion SQLite, partagée par tous les fils du serveur, un seul
    à la fois. Le verrou est réentrant : une instruction dans un bloc
    `with connexion:` ne s'attend pas elle-même."""

    def __init__(self, connexion: sqlite3.Connection):
        object.__setattr__(self, "_c", connexion)
        object.__setattr__(self, "_verrou", threading.RLock())

    def execute(self, *args):
        with self._verrou:
            return _Resultat(self._c.execute(*args))

    def executemany(self, *args):
        with self._verrou:
            return _Resultat(self._c.executemany(*args))

    def commit(self):
        with self._verrou:
            self._c.commit()

    def close(self):
        with self._verrou:
            self._c.close()

    def __enter__(self):
        self._verrou.acquire()
        try:
            self._c.__enter__()
        except BaseException:
            self._verrou.release()
            raise
        return self

    def __exit__(self, *exc):
        try:
            return self._c.__exit__(*exc)
        finally:
            self._verrou.release()

    def __getattr__(self, nom):
        with self._verrou:
            return getattr(self._c, nom)


class Store:
    """Accès à la base."""

    def __init__(self, chemin: Optional[Union[Path, str]] = None,
                 communes: Optional[Union[Path, str]] = None):
        """`communes` : le fichier du référentiel à verser, si ce n'est pas
        celui livré (les essais en passent un de quelques communes)."""
        self.chemin = Path(chemin) if chemin else chemin_defaut()
        if str(self.chemin) != ":memory:":
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
        brute = sqlite3.connect(str(self.chemin), check_same_thread=False)
        brute.row_factory = sqlite3.Row
        # Distingue deux exécutions du programme dans `empreinte` : les
        # compteurs repartent de zéro à chaque ouverture.
        self._sel = secrets.token_hex(6)
        brute.execute("PRAGMA foreign_keys = ON")
        # Un DELETE ordinaire laisse l'ancien contenu lisible dans les pages
        # libres du fichier. La base porte des adresses électroniques : une
        # adresse effacée ne doit pas y rester lisible.
        brute.execute("PRAGMA secure_delete = ON")
        self.migrations_appliquees = migrations.appliquer(brute)
        self._conn = ConnexionVerrouillee(brute)

        from .annonces import DepotAnnonces
        from .communes import DepotCommunes, charger
        from .comptes import DepotComptes
        from .notifications import DepotNotifications
        from .zones import DepotZones
        self.comptes = DepotComptes(self)
        self.communes = DepotCommunes(self)
        self.zones = DepotZones(self)
        self.notifications = DepotNotifications(self)
        self.annonces = DepotAnnonces(self)
        # Long la première fois sur le NAS (35 000 lignes), instantané
        # ensuite : rien n'est réécrit tant que le fichier ne change pas.
        self.communes_versees = charger(self, communes)

    @property
    def connexion(self) -> ConnexionVerrouillee:
        return self._conn

    def empreinte(self) -> str:
        """Change dès que la base change, et jamais autrement.

        Sert à garder la réponse de la carte en mémoire tant que rien n'a
        bougé. `total_changes` voit les écritures de l'application,
        `data_version` celles d'une autre connexion (la ligne de commande
        pendant que le serveur tourne).
        """
        version = self._conn.execute("PRAGMA data_version").fetchone()[0]
        return f"{self._sel}.{self._conn.total_changes}.{version}"

    def etat_schema(self) -> dict:
        return migrations.etat(self._conn)

    def reglage(self, cle: str) -> str:
        """Ce que l'application retient d'un démarrage à l'autre."""
        ligne = self._conn.execute(
            "SELECT valeur FROM reglages WHERE cle = ?", (cle,)).fetchone()
        return ligne["valeur"] if ligne else ""

    def definir_reglage(self, cle: str, valeur: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO reglages (cle, valeur) VALUES (?, ?)",
                (cle, valeur))

    @contextmanager
    def transaction(self) -> Iterator[ConnexionVerrouillee]:
        """Un bloc validé en entier ou annulé en entier, verrou tenu."""
        with self._conn as conn:
            yield conn

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
