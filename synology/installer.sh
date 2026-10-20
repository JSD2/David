#!/bin/sh
# Installation du site des services ambulants sur un NAS Synology sans
# Docker, À LA PLACE de WAY2NAV.
#
# Repris de l'installeur de WAY2NAV (jsd2/paddle, synology/installer.sh),
# qui a tourné sur ce NAS (DS213j, ARM 32 bits, pas de Docker) du 24 août au
# 10 septembre 2026. Ses pièges payés sont gardés : « ps » tronqué par
# busybox, « set -e » et grep bredouille, port encore retenu, sortie Python
# tamponnée.
#
# Ce qu'il fait de WAY2NAV : il arrête son processus et met de côté son
# script de démarrage, pour qu'un redémarrage du NAS ne le relance pas sur
# le même port. Il ne touche ni à sa base ni à son code : tout reste dans
# /volume1/paddle-france, et le retour en arrière se fait en une commande
# (voir SYNOLOGY.md).
#
# Se colle dans : DSM → Planificateur de tâches → Créer → Script défini par
# l'utilisateur, utilisateur root. Réexécutable sans dommage : il met à jour
# le code sans toucher à la base.

set -e

# --------------------------------------------------------------------------
# Réglages
# --------------------------------------------------------------------------
RACINE="${AMBULANTS_RACINE:-/volume1/ambulants}"
# Le port de WAY2NAV : la règle de proxy de DSM qui pointe dessus sert
# désormais ce site-ci.
PORT="${AMBULANTS_PORT:-8000}"
BRANCHE="${AMBULANTS_BRANCHE:-develop}"
DEPOT="${AMBULANTS_DEPOT:-https://github.com/JSD2/David}"
# « test » par défaut : bandeau et noindex. Le site n'est pas encore prêt à
# être référencé (nom provisoire, pas de courriel). « production » se donne
# explicitement : AMBULANTS_ENV=production sh installer.sh
ENVIRONNEMENT="${AMBULANTS_ENV:-test}"
# Jeton GitHub en lecture seule, seulement si le dépôt devient privé.
JETON="${AMBULANTS_JETON:-}"
# Archive déposée à la main (File Station), quand le NAS ne doit rien
# télécharger : AMBULANTS_ARCHIVE=/volume1/homes/moi/david.tar.gz
ARCHIVE_LOCALE="${AMBULANTS_ARCHIVE:-}"
# Où vit WAY2NAV, qu'on arrête.
WAY2NAV="${WAY2NAV_RACINE:-/volume1/paddle-france}"
# Les motifs qui reconnaissent les processus à arrêter (voir « instances »).
# Réglables pour les essais seulement : lancée sur un poste de travail, la
# suite ne doit pas arrêter un autre programme qui porterait ces noms.
MOTIF_SITE="${AMBULANTS_MOTIF:-[a]mbulants\.cli}"
MOTIF_WAY2NAV="${WAY2NAV_MOTIF:-[p]addle_france}"

DONNEES="$RACINE/donnees"
CODE="$RACINE/code"
BASE="$DONNEES/ambulants.sqlite3"
FICHIER_JETON="$RACINE/jeton-github.txt"
JOURNAL="$RACINE/ambulants.log"
PROJET=$(echo "$DEPOT" | sed -e 's#^https\{0,1\}://github\.com/##' -e 's#\.git$##')

echo "======================================================"
echo " Installation des services ambulants"
echo "======================================================"
echo "Dossier       : $RACINE"
echo "Port          : $PORT"
echo "Branche       : $BRANCHE"
echo "Environnement : $ENVIRONNEMENT"
echo ""

# --------------------------------------------------------------------------
# 1. Python 3.8 ou plus, avec scrypt
# --------------------------------------------------------------------------
echo "--- Recherche de Python ---"
PYTHON=""
for candidat in \
    /usr/local/bin/python3 \
    /var/packages/Python3.9/target/bin/python3 \
    /var/packages/Python3/target/bin/python3 \
    /usr/bin/python3 \
    /opt/bin/python3 \
    "$(command -v python3 2>/dev/null || true)"
do
    [ -n "$candidat" ] && [ -x "$candidat" ] || continue
    if "$candidat" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 8) else 1)' 2>/dev/null; then
        PYTHON="$candidat"
        break
    fi
    echo "  ignoré (trop ancien) : $candidat ($("$candidat" -V 2>&1))"
done
if [ -z "$PYTHON" ]; then
    echo ""
    echo "ECHEC : aucun Python 3.8 ou plus récent n'a été trouvé."
    echo "Centre de paquets de DSM → installer « Python 3 », puis relancer."
    exit 1
fi
echo "  retenu : $PYTHON ($("$PYTHON" -V 2>&1))"

# Les mots de passe sont hachés par scrypt, avec les paramètres exacts de
# l'application (32 Mio par calcul). WAY2NAV a quitté ce NAS avant d'avoir
# ses comptes : personne n'a encore vu ce calcul tourner ici. On le fait
# une fois, et on dit combien de temps il prend, plutôt que de découvrir à
# la première inscription qu'il manque à ce Python.
echo ""
echo "--- Hachage des mots de passe (scrypt) ---"
if ! MESURE=$("$PYTHON" - <<'FIN' 2>&1
import hashlib, time
debut = time.time()
hashlib.scrypt(b"essai", salt=b"0" * 16, n=32768, r=8, p=1,
               maxmem=64 * 1024 * 1024, dklen=32)
print("%.2f" % (time.time() - debut))
FIN
); then
    echo "ECHEC : ce Python ne sait pas calculer scrypt."
    echo "$MESURE" | tail -n 3
    echo "Les comptes ne pourraient pas être créés. Rien n'a été changé :"
    echo "WAY2NAV n'a pas été arrêté."
    exit 1
fi
echo "  un hachage prend ${MESURE} s sur ce NAS"

# --------------------------------------------------------------------------
# 2. Récupérer le code
# --------------------------------------------------------------------------
echo ""
echo "--- Téléchargement du code ---"
mkdir -p "$RACINE" "$DONNEES"
chmod 700 "$RACINE"
ARCHIVE="$RACINE/source.tar.gz"

if [ -n "$JETON" ]; then
    printf '%s\n' "$JETON" > "$FICHIER_JETON"
    chmod 600 "$FICHIER_JETON"
elif [ -f "$FICHIER_JETON" ]; then
    JETON=$(cat "$FICHIER_JETON")
    echo "  jeton GitHub repris de $FICHIER_JETON"
fi

# Le jeton passe par un fichier en 600, jamais par la ligne de commande, où
# « ps » l'exposerait.
CONFIG="$RACINE/.telechargement"
: > "$CONFIG"
chmod 600 "$CONFIG"
if command -v curl >/dev/null 2>&1; then
    OUTIL="curl"
    [ -n "$JETON" ] && printf 'header = "Authorization: Bearer %s"\n' "$JETON" > "$CONFIG"
elif command -v wget >/dev/null 2>&1; then
    OUTIL="wget"
    [ -n "$JETON" ] && printf 'header = Authorization: Bearer %s\n' "$JETON" > "$CONFIG"
else
    echo "ECHEC : ni wget ni curl sur ce NAS."
    exit 1
fi

telecharger() {
    rm -f "$2"
    if [ "$OUTIL" = "curl" ]; then
        CODE_HTTP=$(curl -sSL --config "$CONFIG" -o "$2" -w '%{http_code}' "$1" 2>/dev/null) || CODE_HTTP="000"
    elif WGETRC="$CONFIG" wget -q -O "$2" "$1" 2>/dev/null; then
        CODE_HTTP="200"
    else
        CODE_HTTP="000"
    fi
    [ "$CODE_HTTP" = "200" ] && [ -s "$2" ]
}

if [ -n "$ARCHIVE_LOCALE" ]; then
    echo "  archive locale : $ARCHIVE_LOCALE"
    if [ ! -f "$ARCHIVE_LOCALE" ]; then
        echo "ECHEC : $ARCHIVE_LOCALE est introuvable."
        rm -f "$CONFIG"
        exit 1
    fi
    cp "$ARCHIVE_LOCALE" "$ARCHIVE"
else
    # L'API accepte les noms de branche à barres obliques, et les dépôts
    # privés quand un jeton est fourni.
    URL="https://api.github.com/repos/$PROJET/tarball/$BRANCHE"
    echo "  source : $URL"
    if ! telecharger "$URL" "$ARCHIVE"; then
        rm -f "$CONFIG" "$ARCHIVE"
        echo ""
        echo "ECHEC : le code n'a pas pu être téléchargé (HTTP $CODE_HTTP)."
        if [ "$CODE_HTTP" = "404" ]; then
            echo "La branche « $BRANCHE » n'existe pas dans $PROJET, ou le"
            echo "dépôt est devenu privé (fournir alors AMBULANTS_JETON)."
        elif [ "$CODE_HTTP" = "401" ] || [ "$CODE_HTTP" = "403" ]; then
            echo "Le jeton est refusé ou expiré. Effacez $FICHIER_JETON"
            echo "pour en fournir un autre."
        elif [ "$CODE_HTTP" = "000" ]; then
            echo "Le NAS n'a pas joint GitHub : réseau, DNS, ou horloge du NAS"
            echo "fausse (un certificat TLS se refuse alors)."
        fi
        echo "WAY2NAV n'a pas été arrêté."
        exit 1
    fi
fi
rm -f "$CONFIG"

# On remplace le code, jamais les données.
rm -rf "$CODE.nouveau"
mkdir -p "$CODE.nouveau"
if ! tar xzf "$ARCHIVE" -C "$CODE.nouveau" --strip-components=1 2>/dev/null; then
    # La forme « Code → Download ZIP », quand l'archive est déposée à la main.
    if ! "$PYTHON" - "$ARCHIVE" "$CODE.nouveau" <<'FIN' 2>/dev/null
import os, shutil, sys, zipfile
archive, cible = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(archive) as z:
    z.extractall(cible)
entrees = os.listdir(cible)
if len(entrees) == 1 and os.path.isdir(os.path.join(cible, entrees[0])):
    racine = os.path.join(cible, entrees[0])
    for nom in os.listdir(racine):
        shutil.move(os.path.join(racine, nom), os.path.join(cible, nom))
    os.rmdir(racine)
FIN
    then
        echo "ECHEC : l'archive est illisible (ni tar.gz, ni zip)."
        rm -rf "$CODE.nouveau"
        rm -f "$ARCHIVE"
        exit 1
    fi
fi
rm -f "$ARCHIVE"
if [ ! -d "$CODE.nouveau/ambulants" ]; then
    echo "ECHEC : l'archive ne contient pas le paquet « ambulants »."
    rm -rf "$CODE.nouveau"
    exit 1
fi
rm -rf "$CODE"
mv "$CODE.nouveau" "$CODE"
echo "  code installé dans $CODE"

# --------------------------------------------------------------------------
# 3. Script de démarrage
# --------------------------------------------------------------------------
echo ""
echo "--- Script de démarrage ---"
DEMARRAGE="$RACINE/demarrer.sh"
cat > "$DEMARRAGE" <<FIN
#!/bin/sh
# Lance le site. À déclencher au démarrage du NAS depuis le Planificateur
# de tâches. Généré par installer.sh, ne pas éditer : relancer l'installeur.
#
# Le paquet n'est pas installé dans Python, il est lu depuis ce dossier :
# sans « cd » ni PYTHONPATH, le démarrage du NAS (qui part d'un répertoire
# quelconque) échouerait sur « No module named 'ambulants' » (leçon de
# WAY2NAV). PYTHONUNBUFFERED : sans lui, le journal resterait vide des
# minutes et l'installeur croirait à un échec.
#
# AMBULANTS_DERRIERE_PROXY : le proxy inversé de DSM joint le site par
# 127.0.0.1 ; sans lire X-Forwarded-For, tous les visiteurs auraient la
# même adresse et partageraient le même quota de tentatives de connexion.
cd "$CODE" || exit 1
PYTHONUNBUFFERED=1 \\
PYTHONPATH="$CODE" \\
AMBULANTS_DB="$BASE" \\
AMBULANTS_ENV="$ENVIRONNEMENT" \\
AMBULANTS_DERRIERE_PROXY=1 \\
TZ=Europe/Paris \\
exec "$PYTHON" -m ambulants.cli app --hote 0.0.0.0 --port $PORT
FIN
chmod +x "$DEMARRAGE"
echo "  écrit dans $DEMARRAGE"

# --------------------------------------------------------------------------
# 4. Arrêter ce qui tourne : l'instance précédente du site, et WAY2NAV
# --------------------------------------------------------------------------
# « ps » de busybox tronque la ligne de commande quand il n'a pas de
# terminal — c'est le cas du Planificateur. On l'interroge sous toutes ses
# formes et l'on cherche un motif court qui survit à la troncature : le nom
# du module Python. Le PID est le premier champ numérique. Ce script et son
# parent sont écartés, au cas où leur ligne contiendrait le motif.
instances() {
    {
        ps -w 2>/dev/null
        ps w 2>/dev/null
        ps aux 2>/dev/null
        ps 2>/dev/null
    } | grep -e "$1" \
      | awk '{for (i = 1; i <= NF; i++) if ($i ~ /^[0-9]+$/) { print $i; break }}' \
      | sort -u \
      | grep -v -x -e "$$" -e "${PPID:-0}" \
      || true
    # « || true » : ne rien trouver est le cas normal, mais grep sort alors
    # en 1, et « set -e » emporterait le script sans un mot.
}

arreter() {
    _motif="$1"
    _nom="$2"
    _pids=$(instances "$_motif")
    [ -n "$_pids" ] || return 0
    echo "  arrêt de $_nom ($(echo $_pids | tr '\n' ' '))"
    kill $_pids 2>/dev/null || true
    # SIGTERM d'abord : la base se ferme proprement. Ce NAS n'est pas rapide.
    _i=0
    while [ $_i -lt 15 ] && [ -n "$(instances "$_motif")" ]; do
        sleep 1
        _i=$((_i + 1))
    done
    _restants=$(instances "$_motif")
    if [ -n "$_restants" ]; then
        echo "  $_nom ne répond pas : arrêt forcé"
        kill -9 $_restants 2>/dev/null || true
        sleep 2
    fi
}

echo ""
echo "--- Arrêt de ce qui tourne ---"
# « ambulants.cli » : le point ne figure ni dans le nom du dossier
# d'installation ni dans celui de l'installeur.
arreter "$MOTIF_SITE" "l'instance précédente"
# « paddle_france » s'écrit avec un tiret bas, le dossier de WAY2NAV avec
# un trait d'union : seul le module correspond.
arreter "$MOTIF_WAY2NAV" "WAY2NAV"

# Mettre de côté le démarrage de WAY2NAV : sa tâche déclenchée au
# démarrage du NAS le relancerait sur le même port, avant ou après ce
# site — l'un des deux tomberait sur « Address already in use ». Renommé et
# non effacé : le retour en arrière consiste à lui rendre son nom.
if [ -f "$WAY2NAV/demarrer.sh" ]; then
    mv "$WAY2NAV/demarrer.sh" "$WAY2NAV/demarrer.sh.arrete"
    echo "  démarrage de WAY2NAV mis de côté : $WAY2NAV/demarrer.sh.arrete"
fi
if [ -d "$WAY2NAV" ]; then
    echo "  données de WAY2NAV conservées, intactes : $WAY2NAV"
fi

port_occupe() {
    "$PYTHON" - "$PORT" <<'FIN' 2>/dev/null
import socket, sys
prise = socket.socket()
prise.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    prise.bind(("0.0.0.0", int(sys.argv[1])))
except OSError:
    sys.exit(0)   # occupé
finally:
    prise.close()
sys.exit(1)       # libre
FIN
}

# Le port peut rester retenu un instant après la fin du processus.
i=0
while port_occupe && [ $i -lt 15 ]; do
    sleep 1
    i=$((i + 1))
done
if port_occupe; then
    echo "  ECHEC : le port $PORT est occupé par un autre programme."
    echo "  Pour savoir par qui :  netstat -lnp | grep :$PORT"
    echo "  Ou un autre port :     AMBULANTS_PORT=8001 sh \"\$0\""
    exit 1
fi

# --------------------------------------------------------------------------
# 5. Démarrage
# --------------------------------------------------------------------------
echo ""
echo "--- Démarrage ---"
DEBUT_JOURNAL=0
[ -f "$JOURNAL" ] && DEBUT_JOURNAL=$(wc -l < "$JOURNAL")
# setsid détache le site de la tâche du Planificateur, qui sinon emporte
# ses enfants en se terminant.
if command -v setsid >/dev/null 2>&1; then
    setsid "$DEMARRAGE" >> "$JOURNAL" 2>&1 &
else
    nohup "$DEMARRAGE" >> "$JOURNAL" 2>&1 &
fi
# Seules les lignes écrites par ce démarrage-ci comptent : le journal garde
# celles des installations précédentes.
CONFIRME=""
ATTENTE=0
while [ $ATTENTE -lt 120 ]; do
    if tail -n +"$((DEBUT_JOURNAL + 1))" "$JOURNAL" 2>/dev/null | grep -q "^Serveur sur "; then
        CONFIRME="oui"
        break
    fi
    if [ $ATTENTE -gt 0 ] && [ -z "$(instances "$MOTIF_SITE")" ]; then
        echo "  ECHEC : le processus s'est arrêté. Fin du journal :"
        tail -n 20 "$JOURNAL" 2>/dev/null || echo "  (journal vide)"
        echo ""
        echo "  Pour revenir à WAY2NAV :"
        echo "    mv $WAY2NAV/demarrer.sh.arrete $WAY2NAV/demarrer.sh && $WAY2NAV/demarrer.sh &"
        exit 1
    fi
    sleep 2
    ATTENTE=$((ATTENTE + 2))
done
if [ -n "$CONFIRME" ]; then
    echo "  démarré après ${ATTENTE} s."
else
    echo "  Le processus tourne mais ne s'est pas annoncé après ${ATTENTE} s."
    echo "  Journal : cat $JOURNAL"
fi

# --------------------------------------------------------------------------
# Récapitulatif
# --------------------------------------------------------------------------
ADRESSE=$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+\.' | grep -v '^127\.' | head -1)
[ -n "$ADRESSE" ] || ADRESSE=$(ip -4 route get 1 2>/dev/null | sed -n 's/.*src \([0-9.]*\).*/\1/p' | head -1)
[ -n "$ADRESSE" ] || ADRESSE="adresse-du-nas"

echo ""
echo "======================================================"
echo " Terminé"
echo "======================================================"
echo "Site            : http://$ADRESSE:$PORT"
echo "Base de données : $BASE"
echo "Journal         : $JOURNAL"
echo ""
echo "Premier administrateur : créez un compte sur le site, puis ici même :"
echo "    cd $CODE && PYTHONPATH=$CODE AMBULANTS_DB=$BASE \\"
echo "        $PYTHON -m ambulants.cli promouvoir \"<nom affiché>\" administrateur"
echo ""
echo "Au démarrage du NAS, la tâche déclenchée doit lancer :"
echo "    $DEMARRAGE"
echo "(et non plus $WAY2NAV/demarrer.sh)."
echo ""
