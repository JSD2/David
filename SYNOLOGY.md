# Installer le site sur le NAS Synology, à la place de WAY2NAV

Décision du porteur du projet, le 20 octobre 2026 : le site remplace WAY2NAV
sur le NAS. WAY2NAV reste en ligne sur son VPS (`way2nav.com`) ; le NAS en
était le **retour arrière**, il ne l'est plus après cette installation.

Le NAS est celui qu'a décrit WAY2NAV : DS213j, DSM 7.1.1, ARM 32 bits,
512 Mo, **pas de Docker**. L'installation passe donc, comme pour WAY2NAV, par
Python 3 du Centre de paquets et le Planificateur de tâches. Tout se fait
depuis l'interface web de DSM, donc depuis un téléphone par QuickConnect.

## Ce que fait l'installeur

`synology/installer.sh` :

1. trouve Python 3.8 ou plus, et **essaie scrypt** (le hachage des mots de
   passe) avec les paramètres de l'application. S'il manque, il s'arrête
   **avant d'avoir touché à WAY2NAV** ;
2. télécharge le code de la branche `develop` dans `/volume1/ambulants/code` ;
3. écrit `/volume1/ambulants/demarrer.sh` ;
4. **arrête WAY2NAV** et renomme son script de démarrage en
   `/volume1/paddle-france/demarrer.sh.arrete`, pour qu'un redémarrage du NAS
   ne le relance pas sur le même port. **Rien de WAY2NAV n'est effacé** : sa
   base et son code restent dans `/volume1/paddle-france` ;
5. démarre le site sur le **port 8000**, celui de WAY2NAV.

Le site tourne en environnement **test** : bandeau violet, pas de
référencement. Relancer l'installeur met le code à jour sans toucher à la base
(`/volume1/ambulants/donnees/ambulants.sqlite3`).

## Pas à pas

### 1. Remplacer la tâche d'installation de WAY2NAV

*Panneau de configuration → Planificateur de tâches*. Regardez les **deux**
listes : tâches planifiées et tâches déclenchées.

La tâche d'installation de WAY2NAV (« Installer paddle-france ») était
déclenchée au **Démarrage**. Laissée telle quelle, elle réinstallerait
WAY2NAV au prochain redémarrage du NAS et lui rendrait le port 8000.
**Modifiez-la** (ou supprimez-la et créez-en une neuve) :

- *Tâche* : `Installer services ambulants`
- *Utilisateur* : `root`
- *Paramètres de la tâche → Script défini par l'utilisateur* :

```sh
wget -qO /tmp/installer-ambulants.sh https://raw.githubusercontent.com/JSD2/David/develop/synology/installer.sh &&
sh /tmp/installer-ambulants.sh
```

Le `&&` n'est pas décoratif (leçon de WAY2NAV) : sans lui, un téléchargement
raté laisse un fichier vide que `sh` exécute sans rien dire, et la tâche
paraît réussie.

### 2. Lancer l'installation

Sélectionnez la tâche → **Exécuter**. Une à deux minutes plus tard,
*Action → Afficher les résultats* doit montrer, dans l'ordre :

- le Python retenu et le temps d'un hachage scrypt ;
- `code installé dans /volume1/ambulants/code` ;
- `arrêt de WAY2NAV (…)` et `démarrage de WAY2NAV mis de côté` ;
- `démarré après … s.` et l'adresse du site.

### 3. Remplacer la tâche de démarrage

La seconde tâche de WAY2NAV, déclenchée au **Démarrage**, lançait
`/volume1/paddle-france/demarrer.sh`. Ce fichier n'existe plus sous ce nom :
elle échouerait. Changez sa commande pour :

```sh
/volume1/ambulants/demarrer.sh
```

### 4. Devenir administrateur

Ouvrez le site (`http://<adresse du NAS>:8000`), créez un compte, puis
lancez une fois, en tâche planifiée `root` ou en SSH :

```sh
cd /volume1/ambulants/code &&
PYTHON=$(sed -n 's/^exec "\([^"]*\)".*/\1/p' /volume1/ambulants/demarrer.sh) &&
PYTHONPATH=/volume1/ambulants/code AMBULANTS_DB=/volume1/ambulants/donnees/ambulants.sqlite3 \
  "$PYTHON" -m ambulants.cli promouvoir "Votre nom affiché" administrateur
```

La première ligne reprend le Python retenu par l'installeur : `python3`
n'est pas toujours dans le PATH d'une tâche planifiée.

### 5. L'adresse publique

La règle de proxy inversé de DSM qui servait WAY2NAV
(`way2nav.synology.me` → `127.0.0.1:8000`) servira **ce site-ci, sous le nom
de WAY2NAV**. À vous de choisir : la garder le temps des essais, la
supprimer, ou en créer une sous un autre nom DDNS
(*Panneau de configuration → Portail de connexion → Avancé → Proxy inversé*),
toujours vers `127.0.0.1:8000`.

## Retour à WAY2NAV

Arrêter le site, rendre son nom au démarrage de WAY2NAV, le relancer :

```sh
kill $(ps w | grep "[a]mbulants\.cli" | awk '{print $1}')
mv /volume1/paddle-france/demarrer.sh.arrete /volume1/paddle-france/demarrer.sh
/volume1/paddle-france/demarrer.sh >> /volume1/paddle-france/paddle-france.log 2>&1 &
```

puis remettre les deux tâches du Planificateur comme elles étaient
(`SYNOLOGY.md` du dépôt de WAY2NAV).

## Ce qui n'a pas été vérifié sur le NAS

L'installeur est éprouvé par la suite (`tests/test_installeur.py`) sur une
machine Linux : un faux WAY2NAV arrêté, son démarrage mis de côté, sa base
intacte, le site en ligne, puis une relance qui met à jour sans perdre la
base. Ce n'est pas le NAS : le comportement de busybox, la version de Python
de DSM et le temps de scrypt sur cet ARM n'y ont pas été mesurés.
L'installeur les affiche à la première exécution.

On ne sait pas non plus, d'ici, si le proxy de DSM transmet
`X-Forwarded-For`. S'il ne le fait pas, tous les visiteurs passent pour
`127.0.0.1` et partagent le même quota de tentatives de connexion (10 par
quart d'heure).
