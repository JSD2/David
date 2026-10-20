"""La ligne de commande : lancer le serveur, poser le premier administrateur.

    python -m ambulants app [--hote 0.0.0.0] [--port 8000]
    python -m ambulants promouvoir <nom affiché> <rôle>
    python -m ambulants verifier <nom affiché>
    python -m ambulants schema

Le premier administrateur ne peut naître que d'ici : la console ne donne un
rôle qu'à qui en a déjà un.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from .comptes import ROLES, CompteRefuse
from .store import Store


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="ambulants")
    p.add_argument("--base", help="fichier SQLite (sinon $AMBULANTS_DB, sinon ./ambulants.sqlite3)")
    sous = p.add_subparsers(dest="commande", required=True)

    app = sous.add_parser("app", help="lancer le serveur")
    app.add_argument("--hote", default="127.0.0.1")
    app.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))

    pr = sous.add_parser("promouvoir", help="donner un rôle à un compte")
    pr.add_argument("pseudo")
    pr.add_argument("role", choices=ROLES)

    ve = sous.add_parser("verifier", help="vérifier un compte accueillant")
    ve.add_argument("pseudo")

    sous.add_parser("schema", help="dire le palier de la base")

    args = p.parse_args(argv)
    store = Store(args.base) if args.base else Store()
    try:
        if args.commande == "app":
            from .api import construire_serveur, environnement, indexable
            serveur = construire_serveur(store, args.hote, args.port)
            print(f"Serveur sur http://{args.hote}:{args.port}/ — base {store.chemin}")
            print(f"Environnement : {environnement()}"
                  + ("" if indexable() else " (bandeau affiché, indexation refusée)"))
            try:
                serveur.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                serveur.server_close()
            return 0
        if args.commande == "promouvoir":
            c = store.comptes.promouvoir(args.pseudo, args.role)
            print(f"{c.pseudo} : {c.role}")
            return 0
        if args.commande == "verifier":
            c = store.comptes.par_pseudo(args.pseudo)
            if c is None:
                raise CompteRefuse(f"Aucun compte « {args.pseudo} ».")
            c = store.comptes.decider_verification(c.identifiant, "verifie", par="ligne de commande")
            print(f"{c.pseudo} ({c.organisation}) : vérifié")
            return 0
        if args.commande == "schema":
            e = store.etat_schema()
            print(f"palier {e['version']} sur {e['derniere']}")
            return 0
    except CompteRefuse as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        store.close()
    return 2


# « python -m ambulants.cli » : la forme qu'emploie le démarrage du NAS, parce
# que « ambulants.cli » est un motif que « ps » retrouve sans le confondre avec
# le dossier d'installation.
if __name__ == "__main__":
    raise SystemExit(main())
