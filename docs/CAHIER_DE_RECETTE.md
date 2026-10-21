# Cahier de recette

À rejouer sur le site de test avant toute demande de mise en production.
Chaque ligne : ce qu'on fait, ce qu'on doit voir. Une ligne qui échoue
bloque la mise en production.

Préparation : une base de test, un compte administrateur posé par
`python3 -m ambulants promouvoir "<nom>" administrateur`.

## 1. Environnement

| # | Geste | Attendu |
| --- | --- | --- |
| 1.1 | Ouvrir la page d'accueil du site de test | Bandeau violet « ENVIRONNEMENT DE TEST » en haut |
| 1.2 | Ouvrir `/robots.txt` | `Disallow: /` |
| 1.3 | Ouvrir `/api/sante` | `ok: true`, la version attendue, le palier de schéma |

## 2. Carte

| # | Geste | Attendu |
| --- | --- | --- |
| 2.1 | Ouvrir la page sans compte | Carte de France, fond Plan IGN, légende avec le nombre d'annonces |
| 2.2 | Cliquer « Satellite » puis « Plan » | Le fond change, sans erreur |
| 2.3 | « Je cherche un service » | Seuls les ronds orange (services ambulants) restent |
| 2.4 | « Je cherche un emplacement » | Seuls les carrés bleus et losanges violets restent |
| 2.5 | Choisir la catégorie « Santé » | Seules les annonces qui concernent la santé restent ; un emplacement sans activité souhaitée reste (il accepte tout) |
| 2.6 | Chercher « Guéret » | Liste de résultats ; un clic centre la carte |
| 2.7 | Cliquer un repère | La fiche s'ouvre ; les valeurs absentes disent « non renseigné » ; l'avertissement légal est là |
| 2.8 | Sur téléphone (≈ 390 px) | Pas de défilement horizontal ; la fiche monte du bas, au-dessus des contrôles de la carte |

## 3. Comptes

| # | Geste | Attendu |
| --- | --- | --- |
| 3.1 | Créer un compte accueillant (mairie) | Compte créé, connecté, « En attente de vérification » |
| 3.2 | Avec ce compte, cliquer « Publier » | Message : le compte attend sa vérification |
| 3.3 | Créer un compte commerçant avec un SIRET faux (14 chiffres, clé fausse) | Refus : SIRET non valide |
| 3.4 | Le même avec un SIRET valide | Compte créé ; le SIRET est « déclaré », aucun badge « entreprise vérifiée » |
| 3.5 | Se déconnecter, se reconnecter avec un mauvais mot de passe | « Adresse ou mot de passe incorrect » |
| 3.6 | Effacer son compte avec un mauvais mot de passe, puis le bon | Refus, puis compte et annonces effacés |

## 4. Publier

| # | Geste | Attendu |
| --- | --- | --- |
| 4.1 | Administrateur : Console → « Accueillants à vérifier » → « Vérifié » | Le compte disparaît de la liste |
| 4.2 | Accueillant vérifié : publier un lieu précis, placé par recherche d'adresse | La fiche s'ouvre ; badge « Accueillant vérifié » ; le repère est sur la carte |
| 4.3 | Publier un « besoin sans lieu fixé » | Losange violet ; pas d'adresse sur la fiche |
| 4.4 | Commerçant : publier une demande « Alimentaire / Food truck », rayon 40 km | Cercle de 40 km pendant la saisie ; fiche avec l'avertissement alimentaire |
| 4.5 | Laisser électricité et eau sur « Non renseigné » | La fiche dit « non renseigné », jamais « Non » |
| 4.6 | « Retirer mon annonce » | Le repère disparaît ; l'annonce reste dans « Mes annonces », « retirée » |

## 5. Modération et droits

| # | Geste | Attendu |
| --- | --- | --- |
| 5.1 | Modérateur : masquer une annonce sans motif | Refus : motif obligatoire |
| 5.2 | Masquer avec un motif | Le repère disparaît pour un visiteur ; l'auteur voit le motif sur sa fiche |
| 5.3 | Réafficher | Le repère revient |
| 5.4 | Administrateur : Console → Tableau des droits, « Publier une demande » à « Abonné » | Un commerçant ordinaire ne peut plus publier ; le modérateur le peut |
| 5.5 | Décocher « Créer un compte » | L'onglet « Créer un compte » disparaît ; l'API refuse (fonction fermée) |
| 5.6 | Essayer de régler « Le tableau des droits » | Impossible : ligne verrouillée |

## 6. Recherches des mairies, zones des services, notifications

| # | Geste | Attendu |
| --- | --- | --- |
| 6.1 | Mairie vérifiée : « Publier » → recherche « Alimentaire », créneau mardi 11:00–14:00, commune placée par la recherche d'adresse | Fiche publiée ; message « vous serez prévenu… » (ou le nombre de services déjà là) |
| 6.2 | Commerçant : « Publier » → position, puis « + Un cercle » de 15 km | Cercle en pointillé pendant le réglage ; le nombre de communes s'affiche ; « Ajouter ce cercle » l'ajoute à la liste |
| 6.3 | « + Une ville » → « Bourganeuf » | La ville s'ajoute : 1 commune |
| 6.4 | « + Dessiner une zone » → tracer un contour sans lever le doigt | La carte ne bouge pas pendant le tracé ; la zone s'ajoute avec son nombre de communes |
| 6.5 | Sur téléphone, même tracé | Le panneau se replie pendant le tracé ; le doigt trace sans faire défiler la carte |
| 6.6 | Disponibilité mardi 10:00–15:00, publier | « Mon compte » s'ouvre : « Demande publiée : 1 mairie prévenue » |
| 6.7 | Dans « Mes demandes », chaque zone | Nombre de villes, « Voir la zone » la cadre sur la carte, la liste des villes s'ouvre ; la ville de la mairie prévenue est en vert avec son lien |
| 6.8 | Mairie : recharger la page | « Notifications (1) » ; la notification dit le service, l'activité et les créneaux en commun |
| 6.9 | « Voir le service et sa zone » | La fiche du service ; ses zones dessinées sur la carte |
| 6.10 | Une mairie de la zone qui n'a rien publié | Aucune notification |
| 6.11 | Créneaux sans jour commun (mairie lundi, service mardi) | Pas de notification |
| 6.12 | Fiche publique d'un service, vue sans compte | Les zones sont visibles ; ni la liste des villes ni les mairies prévenues |

