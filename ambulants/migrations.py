"""Migrations de schéma versionnées.

La base contient des comptes, des annonces et, bientôt, des échanges : elle
ne doit jamais être recréée de zéro à la faveur d'une mise à jour du
programme. Chaque évolution du schéma est donc un palier numéroté, appliqué
une seule fois, suivi par `PRAGMA user_version` (repris de WAY2NAV).

**Règle des colonnes** : une valeur que personne n'a donnée reste NULL.
Électricité, eau, redevance, surface : « non renseigné » n'est ni « non »
ni zéro, et l'écran le dit tel quel.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Migration:
    version: int
    description: str
    sql: str


MIGRATIONS: Tuple[Migration, ...] = (
    Migration(
        version=1,
        description="Réglages, comptes et sessions",
        sql="""
        CREATE TABLE IF NOT EXISTS reglages (
            cle    TEXT PRIMARY KEY,
            valeur TEXT NOT NULL
        );

        -- Deux types de comptes dans une seule table : un accueillant et un
        -- commerçant se connectent de la même façon, et la modération les
        -- voit dans la même liste. Ce qui les distingue tient en quelques
        -- colonnes, nulles pour l'autre type.
        CREATE TABLE IF NOT EXISTS comptes (
            identifiant     TEXT PRIMARY KEY,
            email           TEXT NOT NULL UNIQUE,
            pseudo          TEXT NOT NULL,
            pseudo_norme    TEXT NOT NULL UNIQUE,
            empreinte       TEXT NOT NULL,
            type_compte     TEXT NOT NULL,          -- accueillant | commercant
            role            TEXT NOT NULL DEFAULT 'utilisateur',
            etat            TEXT NOT NULL DEFAULT 'actif',
            organisation    TEXT,                   -- « Mairie de … », raison sociale
            nature          TEXT,                   -- accueillant : mairie, camping…
            commune         TEXT,
            code_insee      TEXT,
            -- Accueillant : la vérification est le point sensible du site.
            -- Sans elle, n'importe qui publierait au nom d'une commune.
            verification    TEXT,                   -- en_attente | verifie | refuse
            verification_motif TEXT,
            verification_par   TEXT,
            verification_date  TEXT,
            -- Commerçant : le SIRET déclaré. Sa vérification par l'API
            -- « recherche d'entreprises » viendra ; d'ici là il est déclaré,
            -- jamais présenté comme vérifié.
            siret           TEXT,
            siret_verifie   INTEGER NOT NULL DEFAULT 0,
            categories      TEXT NOT NULL DEFAULT '[]',
            presentation    TEXT,
            date_creation   TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_comptes_type ON comptes(type_compte);
        CREATE INDEX IF NOT EXISTS idx_comptes_verif ON comptes(verification);

        -- Seul le condensat du jeton est écrit : la base volée n'ouvre aucune
        -- session.
        CREATE TABLE IF NOT EXISTS sessions (
            condensat   TEXT PRIMARY KEY,
            compte_id   TEXT NOT NULL REFERENCES comptes(identifiant) ON DELETE CASCADE,
            expire      TEXT NOT NULL,
            date_creation TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_compte ON sessions(compte_id);
        """,
    ),
    Migration(
        version=2,
        description="Emplacements proposés par les accueillants, demandes des commerçants",
        sql="""
        -- Ce qu'un accueillant offre : un lieu précis (« emplacement ») ou
        -- un besoin sans lieu fixé (« besoin » : « il nous manque un
        -- boulanger le mardi »). Le besoin est posé sur la commune.
        CREATE TABLE IF NOT EXISTS emplacements (
            identifiant     TEXT PRIMARY KEY,
            compte_id       TEXT NOT NULL REFERENCES comptes(identifiant) ON DELETE CASCADE,
            genre           TEXT NOT NULL,          -- emplacement | besoin
            titre           TEXT NOT NULL,
            description     TEXT,
            commune         TEXT NOT NULL,
            code_insee      TEXT,
            adresse         TEXT,
            latitude        REAL NOT NULL,
            longitude       REAL NOT NULL,
            lieu_precis     INTEGER NOT NULL DEFAULT 0,
            jours           TEXT NOT NULL DEFAULT '[]',
            creneaux        TEXT,
            electricite     INTEGER,                -- NULL : non renseigné
            eau             INTEGER,                -- NULL : non renseigné
            redevance       TEXT,                   -- NULL : non renseignée
            conditions      TEXT,
            activites_souhaitees TEXT NOT NULL DEFAULT '[]',
            activites_exclues    TEXT NOT NULL DEFAULT '[]',
            etat            TEXT NOT NULL DEFAULT 'publie',  -- publie | retire | masque
            motif_masquage  TEXT,
            date_creation   TEXT NOT NULL,
            date_maj        TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_empl_etat ON emplacements(etat);
        CREATE INDEX IF NOT EXISTS idx_empl_compte ON emplacements(compte_id);

        -- Ce qu'un commerçant cherche : une zone (un centre et un rayon,
        -- ou des départements), des jours libres, une activité.
        CREATE TABLE IF NOT EXISTS demandes (
            identifiant     TEXT PRIMARY KEY,
            compte_id       TEXT NOT NULL REFERENCES comptes(identifiant) ON DELETE CASCADE,
            titre           TEXT NOT NULL,
            description     TEXT,
            categorie       TEXT NOT NULL,
            activite        TEXT NOT NULL,
            commune         TEXT,
            latitude        REAL NOT NULL,
            longitude       REAL NOT NULL,
            rayon_km        REAL,                   -- NULL : non renseigné
            departements    TEXT NOT NULL DEFAULT '[]',
            jours           TEXT NOT NULL DEFAULT '[]',
            besoin_electricite INTEGER,             -- NULL : non renseigné
            besoin_eau      INTEGER,
            surface_m2      REAL,
            champs_activite TEXT NOT NULL DEFAULT '{}',
            etat            TEXT NOT NULL DEFAULT 'publie',
            motif_masquage  TEXT,
            date_creation   TEXT NOT NULL,
            date_maj        TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dem_etat ON demandes(etat);
        CREATE INDEX IF NOT EXISTS idx_dem_compte ON demandes(compte_id);
        """,
    ),
)

DERNIERE_VERSION = MIGRATIONS[-1].version


def version_actuelle(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def appliquer(conn: sqlite3.Connection) -> list:
    """Applique les paliers manquants, chacun dans sa transaction.

    Rend la liste des versions appliquées. Une base plus récente que le
    programme est refusée : la relire avec un schéma qu'on ne connaît pas
    pourrait perdre des colonnes à la première écriture.
    """
    actuelle = version_actuelle(conn)
    if actuelle > DERNIERE_VERSION:
        raise RuntimeError(
            f"La base est au palier {actuelle}, ce programme ne connaît que "
            f"le palier {DERNIERE_VERSION}. Mettre le programme à jour.")
    faites = []
    for m in MIGRATIONS:
        if m.version <= actuelle:
            continue
        # executescript valide toute transaction ouverte avant de commencer :
        # on ouvre donc la nôtre à la main, dans le script lui-même.
        conn.executescript(
            "BEGIN;\n" + m.sql + f"\nPRAGMA user_version = {m.version};\nCOMMIT;")
        faites.append(m.version)
    return faites


def etat(conn: sqlite3.Connection) -> dict:
    return {"version": version_actuelle(conn), "derniere": DERNIERE_VERSION}
