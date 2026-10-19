# Services ambulants (nom provisoire)

Un site, autour d'une carte, qui met en relation ceux qui veulent **accueillir**
un service ambulant (mairies, intercommunalités, campings, entreprises, parkings
de supermarché, associations, organisateurs de marchés) et les **services
ambulants** qui cherchent un emplacement (food trucks, épiceries, boulangers,
coiffeurs, bureaux mobiles, soins itinérants, garagistes, artisans).

Le site aide à se trouver ; **il ne délivre aucune autorisation**.

État, décisions et suite : [PASSATION.md](PASSATION.md). Règles de travail :
[CLAUDE.md](CLAUDE.md).

## Lancer

Python 3.8 ou plus récent, sans aucune dépendance.

```bash
python3 -m ambulants app                    # http://127.0.0.1:8000/
python3 -m ambulants promouvoir "Nom affiché" administrateur
python3 -m ambulants verifier "Nom affiché"  # vérifie un compte accueillant
```

La base est `./ambulants.sqlite3`, ou le fichier désigné par `AMBULANTS_DB`
(ou `--base`). Ses paliers de schéma s'appliquent seuls au démarrage.

| Variable | Rôle |
| --- | --- |
| `AMBULANTS_ENV` | `production` seul rend le site indexable. `test` (et toute autre valeur) : bandeau « environnement de test » et `noindex`. |
| `AMBULANTS_DB` | Fichier de la base. |
| `AMBULANTS_DERRIERE_PROXY` | `1` derrière le mandataire de l'hébergeur : le limiteur de connexion lit alors `X-Forwarded-For`. |
| `PORT` | Port d'écoute (8000 par défaut). |

## Essais

```bash
python3 -m pip install "pytest<8" pytest-xdist
python3 -m pytest -q -n auto
git config core.hooksPath githooks          # une fois par clone : la suite avant chaque poussée
```

Node (facultatif) fait tourner les essais du service worker ; sans lui, ils se
sautent avec un message. Le cahier de recette est dans
[docs/CAHIER_DE_RECETTE.md](docs/CAHIER_DE_RECETTE.md).

## Organisation du code

```
ambulants/
  api.py          serveur HTTP ; tableau des routes, chacune avec sa ligne de droits
  droits.py       tableau des droits (cinq niveaux, dont « abonné »)
  comptes.py      comptes accueillant et commerçant, sessions, vérification
  annonces.py     emplacements (accueillants) et demandes (commerçants)
  categories.py   catégories d'activité, avertissements, champs propres
  migrations.py   paliers de schéma SQLite
  store.py        connexion partagée verrouillée
  web/            la page : carte Leaflet, fonds IGN, service worker
tests/            suite pytest (+ tests/js pour Node)
```

Fonds de carte © IGN — Géoplateforme (Licence Ouverte Etalab 2.0). Recherche
d'adresse : Base adresse nationale, via la Géoplateforme. Leaflet 1.9.4
(licence BSD-2, `ambulants/web/vendor/`).
