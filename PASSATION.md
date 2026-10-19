# Passation — services ambulants (nom provisoire)

Document de reprise, à donner en début de nouvelle conversation. Il dit l'état
réel du projet, les décisions prises et ce qui reste. Rien n'y est supposé.

*Dernière mise à jour : 19 octobre 2026.*

## Objet

Une carte qui met en relation ceux qui veulent **accueillir** un service
ambulant (mairies d'abord, mais aussi intercommunalités, campings, zones
d'activité, entreprises, parkings de supermarché, associations, organisateurs)
et les **services ambulants** qui cherchent un emplacement. Tous les services
ambulants, pas seulement food trucks et bureaux mobiles.

Document d'origine : « Passation — site de mise en relation accueillants et
services ambulants » (19 octobre 2026). Modèle technique : WAY2NAV (jsd2/paddle).

## Décisions déjà prises

| Sujet | Décision |
| --- | --- |
| Périmètre | Tous les services ambulants |
| Structure | Une carte, deux parties : accueillants (emplacements, besoins) et commerçants (demandes d'emplacement). Chacun peut prendre l'initiative |
| Modèle économique | Pas choisi. Le code garde les trois options ouvertes (voir plus bas) |
| Dépôt | jsd2/david, séparé de WAY2NAV |
| Socle | Celui de WAY2NAV : Python sans dépendance (3.8+), SQLite à paliers, connexion partagée verrouillée, Leaflet et fonds IGN, tableau des droits |

## Questions ouvertes

- [ ] Nom du site et nom de domaine (« Services ambulants » et le paquet
      `ambulants` sont provisoires ; l'écran l'affiche).
- [ ] Quel côté remplir en premier ? Une carte vide décourage les deux.
- [ ] Modèle économique, parmi les trois options.
- [ ] Hébergement : Coolify comme WAY2NAV, ou autre.
- [ ] Création des branches `develop` (test) et `main` (production) — voir
      « Livraison 1 ».

---

## Livraison 1 — la base (19 octobre 2026)

Branche `claude/beautiful-babbage-erahlc`. Rien n'est déployé.

### Ce qui est fait

**Serveur** (`ambulants/api.py`). `ThreadingHTTPServer`, sans dépendance. Les
routes sont un tableau (`ROUTES`) et chacune nomme sa ligne du tableau des
droits ; le contrôle est fait avant d'appeler la méthode, une route ne peut
pas l'oublier. Sept routes sans ligne (fichiers, santé, session, connexion),
listées avec leur raison. Écritures : corps JSON exigé et origine vérifiée,
en plus du cookie `SameSite=Lax`. Limiteur de connexion et d'inscription
(10 essais par quart d'heure et par adresse, en mémoire seulement).

**Environnement.** `AMBULANTS_ENV=production` seul est indexable. Toute autre
valeur, absence comprise : bandeau, `<meta name="robots" content="noindex">`,
en-tête `X-Robots-Tag`, `robots.txt` fermé. Une faute de frappe garde donc le
site hors des moteurs, et non l'inverse.

**Base** (`migrations.py`, `store.py`). Deux paliers : comptes et sessions,
puis emplacements et demandes. Connexion partagée verrouillée, reprise de
WAY2NAV avec sa leçon (deux lectures simultanées sans verrou = erreur 500 au
hasard). `secure_delete` : une adresse effacée ne reste pas lisible dans le
fichier.

**Deux types de comptes** (`comptes.py`), une seule connexion.
- *Accueillant* : nature (mairie, camping…), organisation, commune. Naît « en
  attente de vérification » et ne publie rien avant que la modération l'ait
  vérifié ; un refus exige un motif, que l'accueillant voit. Ses emplacements
  quittent la carte si la vérification est refusée après coup.
- *Commerçant* : SIRET facultatif, contrôlé (14 chiffres, clé de Luhn,
  exception La Poste) mais seulement **déclaré** : aucun badge « entreprise
  vérifiée » tant que l'API « recherche d'entreprises » n'est pas branchée.
- Mot de passe en scrypt, jeton de session en condensat, aucune adresse IP en
  base. L'adresse électronique ne sort d'aucune réponse publique (un essai
  parcourt les routes publiques pour s'en assurer). Effacer son compte
  (mot de passe redemandé) emporte ses annonces et ses sessions.

**Catégories** (`categories.py`) : alimentaire, commerce non alimentaire,
services à la personne, santé, administratif, artisanat et dépannage, culture
et loisirs ; chacune avec ses activités. Alimentaire et santé portent un
avertissement (activité réglementée, non vérifiée par le site) et des champs
propres (chaîne du froid, déclaration DDPP ; profession exercée).

**Annonces** (`annonces.py`).
- *Emplacement* (accueillant vérifié) : un lieu précis ou un besoin sans lieu
  fixé (posé sur la commune) ; jours, créneaux, électricité, eau, redevance,
  conditions, activités souhaitées et exclues.
- *Demande* (commerçant) : activité, point et rayon, départements, jours,
  besoins en électricité, eau et surface.
- Oui / non / **non renseigné** partout : seuls `true` et `false` sont une
  réponse ; le reste reste NULL et s'affiche « non renseigné ».
- Retrait par l'auteur ; masquage (motif obligatoire) et réaffichage par la
  modération.

**Tableau des droits** (`droits.py`) : cinq niveaux (sans compte, compte,
**abonné**, modérateur, administrateur), un plancher par ligne, lignes
d'administration verrouillées, désactivation par ligne, journal des
changements. Le **type de compte** exigé s'ajoute au niveau (publier un
emplacement : accueillants ; une demande : commerçants). Personne n'est
abonné : `est_abonne` est le seul endroit où l'abonnement se branchera.

**La page** (`web/`). Une carte Leaflet, fonds IGN Plan et Satellite ; filtre
« Tout / Je cherche un service / Je cherche un emplacement » et filtre par
catégorie ; recherche d'adresse par la Base adresse nationale (Géoplateforme,
appelée depuis le navigateur) ; fiche ; inscription et connexion ;
publication des deux sortes d'annonces (placement par clic sur la carte ou
par adresse, cercle du rayon) ; « Mon compte » ; console (vérification des
accueillants, tableau des droits, rôles). Les annonces arrivent **dans** la
page ; la réponse de la carte est gardée en mémoire, compressée, avec ETag.
Service worker : tuiles IGN gardées (3 000 au plus, demandées en CORS pour ne
pas peser dans le quota), page et carte en « réseau d'abord » ; rien de ce qui
regarde un compte n'est gardé.

**Outillage.** Suite pytest (76 essais), crochet `githooks/pre-push`,
workflow GitHub limité à l'entrée de `main` (comme WAY2NAV), Dockerfile avec
volume pour la base, cahier de recette (`docs/CAHIER_DE_RECETTE.md`).

### Ce qui a été vérifié, et comment

- Suite complète verte sous **Python 3.13 et Python 3.8.20** (76 essais).
- Parcours rejoués dans Chromium (Playwright), serveur local : inscription
  d'une mairie → en attente → vérification par la ligne de commande →
  publication d'un emplacement placé par adresse → fiche ; inscription d'un
  commerçant avec SIRET → demande avec champs propres → fiche ; console
  administrateur ; filtre par sens. Aucune erreur JavaScript. À 390 px de
  large, pas de défilement horizontal.
- Constaté pendant ces essais : quelques tuiles IGN refusées par le navigateur
  (`ERR_BLOCKED_BY_ORB`), en nombre semblable **avec et sans** service worker.
  Cause non établie (réponse d'erreur de la Géoplateforme, ou le mandataire
  réseau de l'environnement d'essai). À regarder sur le site de test.

### Ce qui manque, et qu'il faut savoir

- **Pas de courriel** : ni confirmation de l'adresse, ni oubli du mot de
  passe. Un compte est actif dès sa création. Il faut un prestataire d'envoi.
- **Pas de mise en relation** : candidature, invitation, messagerie, échange
  de coordonnées. La fiche le dit. C'est la livraison suivante.
- **Pas de photos** du véhicule.
- **Pas de « joueur de cahier »** (le cahier de recette rejoué par
  Playwright, comme sur WAY2NAV) : le cahier existe, il se rejoue à la main.
- **Branches** : le dépôt était vide. Seule la branche de travail existe ;
  `develop` et `main` restent à créer, avec l'accord du porteur du projet.
- **Déploiement** : rien n'est en ligne. Il faudra un service avec un volume
  pour `/data`, `AMBULANTS_ENV=test` sur le site de test et
  `AMBULANTS_DERRIERE_PROXY=1` derrière le mandataire de l'hébergeur.

### Prêt pour les trois modèles économiques

| Option | Ce qui existe déjà |
| --- | --- |
| Gratuit puis payant pour plus | Le niveau « abonné » du tableau : passer une fonction en payant est un réglage de la console |
| Paiement à la mise en relation | Rien encore : la mise en relation sera un événement enregistré (les deux acceptent d'échanger leurs coordonnées), livraison 2 |
| Commission au contrat signé | Rien de plus à prévoir ; le site ne voit pas la signature |

### Suite proposée

1. Créer `develop` et `main`, choisir l'hébergement, déployer `develop` en
   site de test.
2. **Livraison 2 — la mise en relation** : candidature du commerçant sur un
   emplacement, invitation d'un commerçant par un accueillant, messagerie sur
   le site, puis acceptation des deux côtés pour échanger les coordonnées —
   un événement enregistré, mesurable, facturable le jour venu. Chaque geste
   avec sa ligne dans le tableau des droits.
3. Ensuite : courriel (confirmation, oubli du mot de passe, avis de message),
   vérification SIRET par l'API publique, préremplissage de la vérification
   des mairies par l'Annuaire de l'administration, calendrier de tournée,
   modèles d'arrêté et de convention, communes sans commerce sur la carte
   (référentiel des communes).
