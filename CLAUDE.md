# Règles de travail

Reprises de WAY2NAV (jsd2/paddle), qui sert de modèle technique. Elles valent
pour toute conversation qui reprend ce dépôt.

## Branches et mise en ligne

- `develop` est la branche de test déployée ; `main` est la production.
- **Jamais de mise en production sans accord explicite**, donné sur le moment,
  pour cette fois-là. Un accord passé ne vaut pas pour la suivante.
- **Une poussée Git n'est pas une preuve de déploiement** : vérifier en ligne
  (`/api/sante` donne la version servie) avant de dire qu'une chose est en
  ligne.
- Le site de test n'est pas référencé : `AMBULANTS_ENV=test` (bandeau,
  `noindex`, `robots.txt` fermé). Seul `production` est indexable.

## Écrire le code

- Code, commentaires, messages et documentation **en français**. Les
  commentaires expliquent **pourquoi**, pas ce que le code fait déjà voir.
- Serveur Python **sans dépendance** (bibliothèque standard), compatible
  **Python 3.8**. La suite tourne sur 3.8 et sur un récent.
- **Chaque fonction a sa ligne dans le tableau des droits**
  (`ambulants/droits.py`), et chaque route du serveur nomme sa ligne
  (`ambulants/api.py`, `ROUTES`). Un essai fait échouer la suite sinon. Une
  livraison sans sa ligne n'est pas finie.
- **Aucune valeur inconnue ne devient zéro ni « non »** : une case non
  renseignée reste NULL en base et « non renseigné » à l'écran.
- **Ne rien inventer** : ni source, ni date, ni historique, ni chiffre.
  **Mesurer avant d'affirmer.**
- **Ne pas changer ce qui n'a pas été demandé.**
- Tout ce qui vient d'un utilisateur s'affiche en texte (`textContent`), jamais
  en HTML.

## Livrer

- La suite passe avant chaque poussée (`git config core.hooksPath githooks`).
- Le cahier de recette (`docs/CAHIER_DE_RECETTE.md`) suit les écrans livrés.
- Le journal de passation (`PASSATION.md`) est tenu **à chaque livraison** :
  ce qui a été fait, ce qui a été vérifié et comment, ce qui reste.
