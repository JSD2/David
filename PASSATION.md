# Passation — services ambulants (nom provisoire)

Document de reprise, à donner en début de nouvelle conversation. Il dit l'état
réel du projet, les décisions prises et ce qui reste. Rien n'y est supposé.

*Dernière mise à jour : 21 octobre 2026.*

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
- [x] Hébergement : le NAS Synology, à la place de WAY2NAV (décision du
      20 octobre). Voir « Livraison 2 » et `SYNOLOGY.md`.
- [ ] Création de `main` (production). `develop` existe depuis le 20 octobre.

---

## Livraison 3 — recherches des mairies, zones d'action, notifications (21 octobre 2026)

### Ce que le porteur du projet a demandé

La mairie déclare qu'elle recherche un ou plusieurs commerces ou services
ambulants, avec les créneaux qu'elle souhaite. Le commerçant dit où il est
installé et sur quelles zones il intervient : une ville, un cercle, ou une
zone dessinée à la main ; il peut en créer plusieurs, et dit ses jours et
horaires. Les mairies qui correspondent sont prévenues ; celles qui n'ont
rien demandé ne le sont pas. Le commerçant retrouve dans son historique
chaque demande, les villes de chaque zone, et peut revoir la zone sur la
carte.

Trois choix tranchés le 21 octobre : l'historique montre **toutes** les
villes de la zone, les mairies prévenues mises en évidence ; une mairie
n'est prévenue que si **les créneaux se recoupent, quand les deux en ont
donné** ; la notification est **sur le site** (cloche), le courriel
viendra avec un prestataire d'envoi.

### Ce qui est fait

- **Référentiel des communes** (`ambulants/data/communes.json.gz`) :
  34 969 communes avec leur centre, leur département et leur population,
  pris le 21 octobre 2026 sur geo.api.gouv.fr
  (`scripts/importer_communes.py` le refait). Versé en base au démarrage,
  une seule fois (`communes.py`). Population absente : laissée absente
  (6 communes).
- **Zones** (`zones.py`, `geo.py`) : ville, cercle (1 à 300 km), dessin
  (3 à 500 points, 600 km de côté au plus). Une commune est dans une zone
  **si son centre y est** ; l'écran le dit. Les communes de chaque zone
  sont calculées une fois, à la publication, et gardées.
- **Plages horaires** (`plages.py`) : jour, début, fin, pour la mairie
  (créneaux souhaités) et pour le commerçant (disponibilités). Une liste
  vide est « non renseigné » et ne ferme rien.
- **Correspondances et notifications** (`notifications.py`) : commune de
  la recherche dans une zone du service, activité cherchée et non exclue,
  créneaux qui se recoupent. Dans les deux sens : un service publié après
  la recherche prévient la mairie, une recherche publiée après le service
  le trouve aussitôt. Une paire ne prévient qu'une fois. La correspondance
  est un événement enregistré : le premier pas de la mise en relation.
- **Le code INSEE de la recherche** décide de la commune : la recherche
  d'adresse le donne, un clic sur la carte le demande à la Base adresse
  nationale (géocodage inverse) ; à défaut, le serveur prend la commune
  dont le centre est le plus proche (approximation près des limites).
- **Écrans** : « Publier une recherche de service » (mairie),
  « Proposer mes services » (commerçant : zones, disponibilités, aperçu du
  nombre de communes pendant le réglage), « Mes demandes » (historique),
  cloche « Notifications (n) », zones dessinées sur la fiche d'un service.
- **Tableau des droits** : trois lignes neuves — chercher une commune,
  notifications, historique des demandes (commerçants).
- La fiche publique d'un service montre ses contours, **pas** la liste de
  ses villes ni les mairies prévenues (réservées à son historique).
- Ce qui disparaît des formulaires : le rayon unique et les départements
  de la demande, la case « jours » et le texte « créneaux » de la
  recherche. Les colonnes restent en base ; une annonce d'avant les montre
  encore.

### Vérifié, et comment

- 106 essais, verts sous Python 3.13 et 3.8.20 ; `tests/test_zones.py`
  couvre la géométrie, les horaires, le référentiel, les trois zones, qui
  est prévenu et qui ne l'est pas, l'historique, la fiche publique, l'API.
- Scénario joué dans Chromium (serveur local, référentiel complet) : la
  mairie de Guéret publie « Un food truck le mardi midi » (mardi
  11:00–14:00) ; un food truck installé à Sainte-Feyre ajoute un cercle de
  15 km (39 communes), Bourganeuf, et une zone dessinée à la souris,
  disponible mardi 10:00–15:00 → « Demande publiée : 1 mairie prévenue » ;
  la mairie voit « Notifications (1) », créneaux en commun mardi
  11:00–14:00, et la fiche du service avec ses zones. Aucune erreur
  JavaScript.
- Sur téléphone (390 px, écran tactile simulé) : le tracé au doigt ajoute
  la zone, la carte ne bouge pas pendant le geste, pas de défilement
  horizontal.

### Pas vérifié

- **Sur le NAS** : le premier démarrage verse les 35 000 communes (0,35 s
  ici ; plus long sur l'ARM, non mesuré). L'installeur attend désormais
  jusqu'à 5 minutes et le journal dit « Référentiel des communes versé ».
- Les communes à cheval sur une zone dont le centre est dehors ne sont pas
  comptées : choix assumé, à revoir si les essais réels le contestent.

---

## Livraison 2 — l'installation sur le NAS, à la place de WAY2NAV (20 octobre 2026)

Décision du porteur du projet : le site **remplace** WAY2NAV sur le NAS
Synology (DS213j, ARM 32 bits, pas de Docker). WAY2NAV reste en ligne sur
son VPS ; le NAS, qui en était le retour arrière, ne l'est plus.

### Ce qui est fait

- `synology/installer.sh`, repris de celui de WAY2NAV et de ses pièges payés
  (`ps` tronqué par busybox, `set -e` et grep bredouille, port retenu, sortie
  tamponnée). Il essaie scrypt **avant** de toucher à WAY2NAV ; arrête
  WAY2NAV ; renomme son `demarrer.sh` en `demarrer.sh.arrete` sans rien
  effacer ; installe dans `/volume1/ambulants` ; démarre sur le port 8000 en
  environnement `test`.
- `SYNOLOGY.md` : le pas à pas dans DSM (les deux tâches de WAY2NAV à
  remplacer, l'administrateur, le proxy, le retour à WAY2NAV).
- `python -m ambulants.cli` démarre enfin quelque chose : `cli.py` n'avait
  pas de point d'entrée, défaut trouvé par l'essai de l'installeur.
- Le limiteur de connexion ne croit `X-Forwarded-For` que si la connexion
  vient d'une adresse locale ou privée (le proxy de DSM), comme WAY2NAV :
  sur le NAS, le site écoute aussi sur le réseau, et un visiteur direct
  aurait pu écrire l'en-tête pour échapper au quota.

### Vérifié, et comment

- Suite verte (80 essais) sous Python 3.13 et 3.8.20.
- `tests/test_installeur.py` joue l'installeur pour de vrai sur Linux : un
  faux WAY2NAV qui tourne est arrêté, son démarrage mis de côté, sa base
  intacte ; le site répond sur le port, `robots.txt` fermé ; une relance
  arrête l'instance précédente et garde la base.

### Sur le NAS, le 20 octobre (compte rendu de l'installeur, transmis par le porteur du projet)

- Python retenu : `/usr/bin/python3`, **3.8.12**.
- Un hachage scrypt : **0,95 s**. Une connexion ou une inscription coûte
  donc environ une seconde de calcul sur ce processeur mono-cœur, et deux
  tentatives simultanées s'attendent l'une l'autre.
- WAY2NAV arrêté (un processus), son démarrage mis de côté, ses données
  conservées. Site démarré en 8 s, à `http://192.168.1.166:8000`.

### Pas vérifié

- Le site vu depuis un navigateur sur le NAS, la tâche de démarrage après
  un redémarrage, et le premier administrateur : à faire par le porteur du
  projet.
- Si le proxy de DSM transmet `X-Forwarded-For`. Sinon, tous les visiteurs
  partagent un même quota de connexion.
- `develop` a été créée le 20 octobre (accord du porteur du projet), au
  même commit que la branche de travail ; l'installeur et l'archive se
  téléchargent depuis GitHub (HTTP 200, vérifié d'ici). `main` reste à créer.

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
