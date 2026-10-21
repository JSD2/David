"""Le serveur HTTP : la page de la carte, ses fichiers, et l'API.

Sans dépendance : `ThreadingHTTPServer` de la bibliothèque standard,
compatible Python 3.8 (repris de WAY2NAV).

**Les routes sont un tableau** (`ROUTES`), et chaque route nomme sa ligne
du tableau des droits. Le contrôle est fait ici, avant d'appeler la
méthode : une route ne peut pas l'oublier. Les quelques routes sans ligne
(fichiers, santé, connexion) sont listées à part avec leur raison, et un
essai fait échouer la suite pour toute route qui n'est ni l'un ni l'autre.

**L'environnement** (`AMBULANTS_ENV`) : seul « production » est indexable.
Tout autre valeur — « test », « local », une faute de frappe — affiche le
bandeau et refuse l'indexation. Se tromper dans ce sens-là ne coûte rien ;
dans l'autre, le site de test finirait dans les moteurs de recherche.

**Vitesse** (leçon de WAY2NAV) : la réponse de la carte est construite une
fois par état de la base, gardée en mémoire déjà compressée, et servie
avec un ETag ; la page arrive avec les annonces dedans, sans second aller
et retour.
"""

from __future__ import annotations

import gzip
import hashlib
import html
import ipaddress
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlsplit

from . import __version__, droits
from . import categories as cat
from .annonces import AVERTISSEMENT_LEGAL, JOURS, AnnonceRefusee
from .comptes import LIBELLES_NATURES, NATURES, CompteRefuse
from .store import Store
from .zones import ZoneRefusee

WEB = Path(__file__).parent / "web"
COOKIE = "amb_session"
CORPS_MAX = 64 * 1024
TYPES_FICHIERS = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".txt": "text/plain; charset=utf-8",
}

CSP = ("default-src 'self'; img-src 'self' data: https://data.geopf.fr; "
       "connect-src 'self' https://data.geopf.fr; script-src 'self'; "
       "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")


def environnement() -> str:
    return (os.environ.get("AMBULANTS_ENV") or "local").strip().lower()


def indexable() -> bool:
    return environnement() == "production"


class Refus(Exception):
    """Une réponse d'erreur, avec son code et son message pour l'écran."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Route:
    methode: str
    motif: str
    droit: Optional[str]
    action: str


ROUTES = (
    Route("GET", r"/", "carte", "page"),
    Route("GET", r"/api/carte", "carte", "api_carte"),
    Route("GET", r"/api/categories", "carte", "api_categories"),
    Route("GET", r"/api/annonces/(?P<id>[ed]-[0-9a-f]{12})", "fiche", "api_fiche"),
    Route("POST", r"/api/comptes", "inscription", "api_inscription"),
    Route("GET", r"/api/moi", "mon_compte", "api_moi"),
    Route("POST", r"/api/moi/effacer", "mon_compte", "api_effacer"),
    Route("POST", r"/api/emplacements", "publier_emplacement", "api_publier_emplacement"),
    Route("POST", r"/api/demandes", "publier_demande", "api_publier_demande"),
    Route("POST", r"/api/zones/apercu", "publier_demande", "api_apercu_zone"),
    Route("GET", r"/api/communes", "communes", "api_communes"),
    Route("GET", r"/api/moi/historique", "historique_demandes", "api_historique"),
    Route("GET", r"/api/notifications", "notifications", "api_notifications"),
    Route("POST", r"/api/notifications/lues", "notifications", "api_notifications_lues"),
    Route("POST", r"/api/annonces/(?P<id>[ed]-[0-9a-f]{12})/retirer", "retirer_annonce",
          "api_retirer"),
    Route("GET", r"/api/moderation/accueillants", "mod_verifier_accueillants",
          "api_accueillants_a_verifier"),
    Route("POST", r"/api/moderation/accueillants/(?P<id>[0-9a-f]{16})",
          "mod_verifier_accueillants", "api_decider_verification"),
    Route("POST", r"/api/moderation/annonces/(?P<id>[ed]-[0-9a-f]{12})", "mod_annonces",
          "api_moderer_annonce"),
    Route("GET", r"/api/admin/comptes", "adm_comptes", "api_comptes"),
    Route("POST", r"/api/admin/comptes/(?P<id>[0-9a-f]{16})/role", "adm_comptes",
          "api_changer_role"),
    Route("GET", r"/api/admin/droits", "adm_droits", "api_tableau_droits"),
    Route("POST", r"/api/admin/droits", "adm_droits", "api_regler_droit"),

    # Sans ligne, et pourquoi :
    # - les fichiers de la page et le service worker : sans eux, rien ne
    #   s'affiche, pas même un refus ;
    Route("GET", r"/static/(?P<fichier>[\w.-]+(?:/[\w.-]+)?)", None, "fichier"),
    Route("GET", r"/sw\.js", None, "service_worker"),
    Route("GET", r"/robots\.txt", None, "robots"),
    # - la santé : l'hébergeur la lit pour savoir si le service vit ;
    Route("GET", r"/api/sante", None, "api_sante"),
    # - la session et les droits : c'est ce qui dit à la page ce qui est
    #   permis — les refuser rendrait le refus illisible ;
    Route("GET", r"/api/session", None, "api_session"),
    # - se connecter et se déconnecter : fermer la connexion fermerait la
    #   console à l'administrateur lui-même.
    Route("POST", r"/api/session", None, "api_connexion"),
    Route("POST", r"/api/session/fin", None, "api_deconnexion"),
)
_COMPILEES = [(r, re.compile("^" + r.motif + "$")) for r in ROUTES]


class Limiteur:
    """Compte les tentatives de connexion par adresse, sur une fenêtre
    glissante. L'adresse n'est gardée qu'en mémoire, et seulement le temps
    de la fenêtre."""

    def __init__(self, maximum: int = 10, fenetre_s: float = 15 * 60):
        self.maximum = maximum
        self.fenetre_s = fenetre_s
        self._essais = {}
        self._verrou = threading.Lock()

    def autorise(self, cle: str) -> bool:
        maintenant = time.monotonic()
        with self._verrou:
            recents = [t for t in self._essais.get(cle, []) if maintenant - t < self.fenetre_s]
            if len(recents) >= self.maximum:
                self._essais[cle] = recents
                return False
            recents.append(maintenant)
            self._essais[cle] = recents
            return True


class Application:
    """Ce que les requêtes partagent : la base, la carte gardée, le
    limiteur."""

    def __init__(self, store: Store):
        self.store = store
        self.limiteur = Limiteur()
        self._verrou_carte = threading.Lock()
        self._carte = None  # (empreinte, corps, corps gzip, etag)

    def carte(self):
        """La réponse de la carte, reconstruite seulement si la base a bougé."""
        empreinte = self.store.empreinte()
        with self._verrou_carte:
            if self._carte is None or self._carte[0] != empreinte:
                corps = json.dumps({"annonces": self.store.annonces.carte()},
                                   ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                etag = '"' + hashlib.sha256(corps).hexdigest()[:20] + '"'
                self._carte = (empreinte, corps, gzip.compress(corps, 9), etag)
            return self._carte


def _pair_de_confiance(adresse: str) -> bool:
    try:
        ip = ipaddress.ip_address(adresse)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def _bandeau() -> str:
    if indexable():
        return ""
    libelle = "ENVIRONNEMENT DE TEST" if environnement() == "test" else "ENVIRONNEMENT LOCAL"
    return (f'<div id="bandeau-essai" role="status">{libelle} — les annonces '
            'sont fictives, rien n\'est engagé.</div>')


class Gestionnaire(BaseHTTPRequestHandler):
    app: Application  # posé par `construire_serveur`
    server_version = "ambulants"
    sys_version = ""

    # -- journal ------------------------------------------------------------

    def log_message(self, format, *args):  # noqa: A002 - signature imposée
        # Pas d'adresse IP dans les journaux : la méthode, le chemin, le code.
        if os.environ.get("AMBULANTS_SILENCE"):
            return
        print(f"{self.command} {urlsplit(self.path).path} {args[1] if len(args) > 1 else ''}")

    # -- aiguillage ---------------------------------------------------------

    def do_GET(self) -> None:
        self._traiter("GET")

    def do_HEAD(self) -> None:
        self._traiter("GET")

    def do_POST(self) -> None:
        self._traiter("POST")

    def _traiter(self, methode: str) -> None:
        chemin = urlsplit(self.path).path
        self._compte_lu = False
        try:
            trouvee = None
            methode_ailleurs = False
            for route, motif in _COMPILEES:
                m = motif.match(chemin)
                if m:
                    if route.methode == methode:
                        trouvee = (route, m.groupdict())
                        break
                    methode_ailleurs = True
            if trouvee is None:
                raise Refus(405 if methode_ailleurs else 404,
                            "Méthode non permise." if methode_ailleurs else "Introuvable.")
            route, params = trouvee
            if methode == "POST":
                self._verifier_origine()
            if route.droit and not droits.permis(self.app.store, route.droit, self.compte):
                self._refus_droit(route.droit)
            getattr(self, route.action)(**params)
        except Refus as r:
            self._json({"erreur": r.message}, r.code)
        except (CompteRefuse, AnnonceRefusee, droits.DroitRefuse) as e:
            self._json({"erreur": str(e)}, 400)

    def _refus_droit(self, cle: str) -> None:
        f = droits.PAR_CLE[cle]
        if cle in droits.desactivees(self.app.store):
            raise Refus(403, "Cette fonction est fermée pour le moment.")
        if self.compte is None:
            raise Refus(401, "Il faut un compte pour cela.")
        if f.pour and self.compte.type_compte != f.pour:
            qui = "accueillants" if f.pour == "accueillant" else "commerçants"
            raise Refus(403, f"Cette fonction est réservée aux comptes {qui}.")
        raise Refus(403, "Votre compte n'a pas accès à cette fonction.")

    def _verifier_origine(self) -> None:
        """Une écriture ne vient que de nos propres pages.

        Le cookie est déjà `SameSite=Lax` ; on exige en plus un corps JSON
        (un formulaire d'un autre site ne sait pas l'envoyer sans requête
        préalable) et, quand le navigateur dit d'où il vient, que ce soit
        d'ici.
        """
        type_contenu = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        if type_contenu != "application/json":
            raise Refus(415, "Corps JSON attendu.")
        origine = self.headers.get("Origin")
        if origine and urlsplit(origine).netloc != (self.headers.get("Host") or ""):
            raise Refus(403, "Origine refusée.")

    # -- outils -------------------------------------------------------------

    @property
    def compte(self):
        if not self._compte_lu:
            self._compte = self.app.store.comptes.compte_de_session(self._jeton())
            self._compte_lu = True
        return self._compte

    def _jeton(self) -> str:
        for morceau in (self.headers.get("Cookie") or "").split(";"):
            nom, _, valeur = morceau.strip().partition("=")
            if nom == COOKIE:
                return valeur
        return ""

    def _corps(self) -> dict:
        try:
            longueur = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise Refus(400, "Longueur illisible.")
        if longueur > CORPS_MAX:
            raise Refus(413, "Envoi trop lourd.")
        brut = self.rfile.read(longueur) if longueur else b"{}"
        try:
            donnees = json.loads(brut.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise Refus(400, "JSON illisible.")
        if not isinstance(donnees, dict):
            raise Refus(400, "Un objet JSON est attendu.")
        return donnees

    def _entetes_communs(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", CSP)
        if not indexable():
            self.send_header("X-Robots-Tag", "noindex, nofollow")

    def _accepte_gzip(self) -> bool:
        return "gzip" in (self.headers.get("Accept-Encoding") or "").lower()

    def _envoyer(self, corps: bytes, type_contenu: str, code: int = 200, *,
                 cache: str = "no-store", etag: str = "", gzip_pret: Optional[bytes] = None,
                 cookies=()) -> None:
        if etag and self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache)
            self._entetes_communs()
            self.end_headers()
            return
        encodage = ""
        if self._accepte_gzip() and len(corps) > 1024 and type_contenu.split(";")[0] in (
                "application/json", "text/html", "text/javascript", "text/css"):
            corps = gzip_pret if gzip_pret is not None else gzip.compress(corps, 6)
            encodage = "gzip"
        self.send_response(code)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", cache)
        self.send_header("Vary", "Accept-Encoding, Cookie")
        if encodage:
            self.send_header("Content-Encoding", encodage)
        if etag:
            self.send_header("ETag", etag)
        for c in cookies:
            self.send_header("Set-Cookie", c)
        self._entetes_communs()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corps)

    def _json(self, donnees, code: int = 200, **kw) -> None:
        corps = json.dumps(donnees, ensure_ascii=False).encode("utf-8")
        self._envoyer(corps, "application/json; charset=utf-8", code, **kw)

    def _cookie(self, jeton: str, max_age: int) -> str:
        securise = "; Secure" if environnement() in ("production", "test") else ""
        return (f"{COOKIE}={jeton}; Path=/; HttpOnly; SameSite=Lax; "
                f"Max-Age={max_age}{securise}")

    def _adresse(self) -> str:
        """L'adresse du client, pour le limiteur seulement.

        Derrière un proxy inversé (Coolify, ou celui de DSM sur le NAS),
        c'est le dernier saut d'`X-Forwarded-For` qui compte, celui que le
        proxy a posé. L'en-tête n'est cru que si on l'a dit
        (`AMBULANTS_DERRIERE_PROXY=1`) ET si la connexion vient d'une
        adresse locale ou privée, là où vit le proxy : sur le NAS, le site
        écoute aussi sur le réseau, et un visiteur qui le joindrait
        directement pourrait sinon écrire l'en-tête lui-même pour échapper
        au limiteur (repris de WAY2NAV, `pair_de_confiance`).
        """
        pair = self.client_address[0]
        if os.environ.get("AMBULANTS_DERRIERE_PROXY") == "1" and _pair_de_confiance(pair):
            transmis = (self.headers.get("X-Forwarded-For") or "").split(",")[-1].strip()
            if transmis:
                return transmis
        return pair

    # -- la page et ses fichiers -------------------------------------------

    def page(self) -> None:
        """La page de la carte, avec les annonces et les listes dedans."""
        _, corps_carte, _, _ = self.app.carte()
        prechargees = {
            "carte": json.loads(corps_carte.decode("utf-8")),
            "categories": cat.pour_le_navigateur(),
            "natures": [{"cle": c, "libelle": l} for c, l in NATURES],
            "jours": list(JOURS),
            "avertissement_legal": AVERTISSEMENT_LEGAL,
            "version": __version__,
            "environnement": environnement(),
        }
        # « </ » échappé : un titre d'annonce ne doit pas pouvoir fermer la
        # balise <script> qui porte les données.
        donnees = json.dumps(prechargees, ensure_ascii=False).replace("</", "<\\/")
        gabarit = (WEB / "index.html").read_text(encoding="utf-8")
        robots = "" if indexable() else '<meta name="robots" content="noindex, nofollow">'
        page = (gabarit.replace("<!--ROBOTS-->", robots)
                .replace("<!--BANDEAU-->", _bandeau())
                .replace("<!--DONNEES-->", donnees)
                .replace("{{VERSION}}", html.escape(__version__)))
        self._envoyer(page.encode("utf-8"), "text/html; charset=utf-8", cache="no-cache")

    def fichier(self, fichier: str) -> None:
        chemin = (WEB / fichier).resolve()
        if WEB.resolve() not in chemin.parents or not chemin.is_file():
            raise Refus(404, "Introuvable.")
        type_contenu = TYPES_FICHIERS.get(chemin.suffix)
        if type_contenu is None:
            raise Refus(404, "Introuvable.")
        corps = chemin.read_bytes()
        etag = '"' + hashlib.sha256(corps).hexdigest()[:20] + '"'
        self._envoyer(corps, type_contenu, cache="no-cache", etag=etag)

    def service_worker(self) -> None:
        # Servi depuis la racine : un service worker ne contrôle que ce qui
        # est sous son propre chemin.
        corps = (WEB / "sw.js").read_bytes()
        self._envoyer(corps, "text/javascript; charset=utf-8", cache="no-cache")

    def robots(self) -> None:
        texte = "User-agent: *\n" + ("Allow: /\n" if indexable() else "Disallow: /\n")
        self._envoyer(texte.encode("utf-8"), "text/plain; charset=utf-8", cache="no-cache")

    # -- lecture publique ---------------------------------------------------

    def api_sante(self) -> None:
        self._json({"ok": True, "version": __version__,
                    "schema": self.app.store.etat_schema()})

    def api_carte(self) -> None:
        _, corps, serre, etag = self.app.carte()
        self._envoyer(corps, "application/json; charset=utf-8", cache="no-cache",
                      etag=etag, gzip_pret=serre)

    def api_categories(self) -> None:
        self._json({"categories": cat.pour_le_navigateur()}, cache="public, max-age=3600")

    def api_fiche(self, id: str) -> None:  # noqa: A002 - nom du groupe de la route
        moderateur = droits.permis(self.app.store, "mod_annonces", self.compte)
        fiche = self.app.store.annonces.fiche(
            id, voir_masquee=moderateur,
            lecteur_id=self.compte.identifiant if self.compte else "")
        if fiche is None:
            raise Refus(404, "Cette annonce n'existe pas ou n'est plus publiée.")
        self._json(fiche)

    # -- session et compte --------------------------------------------------

    def api_session(self) -> None:
        self._json({"compte": self.compte.prive() if self.compte else None,
                    "droits": droits.pour_le_navigateur(self.app.store, self.compte)})

    def api_connexion(self) -> None:
        if not self.app.limiteur.autorise(self._adresse()):
            raise Refus(429, "Trop de tentatives. Réessayer dans un quart d'heure.")
        d = self._corps()
        compte = self.app.store.comptes.connecter(d.get("email", ""), d.get("mot_de_passe", ""))
        jeton = self.app.store.comptes.ouvrir_session(compte.identifiant)
        self._compte, self._compte_lu = compte, True
        self._json({"compte": compte.prive(),
                    "droits": droits.pour_le_navigateur(self.app.store, compte)},
                   cookies=[self._cookie(jeton, 30 * 24 * 3600)])

    def api_deconnexion(self) -> None:
        jeton = self._jeton()
        if jeton:
            self.app.store.comptes.fermer_session(jeton)
        self._json({"ok": True}, cookies=[self._cookie("", 0)])

    def api_inscription(self) -> None:
        if not self.app.limiteur.autorise("inscription:" + self._adresse()):
            raise Refus(429, "Trop de tentatives. Réessayer dans un quart d'heure.")
        d = self._corps()
        if d.get("conditions_acceptees") is not True:
            raise Refus(400, "Il faut accepter les conditions d'utilisation.")
        cats = d.get("categories") if isinstance(d.get("categories"), list) else []
        compte = self.app.store.comptes.creer(
            d.get("email", ""), d.get("pseudo", ""), d.get("mot_de_passe", ""),
            d.get("type_compte", ""), organisation=d.get("organisation") or "",
            nature=d.get("nature") or "", commune=d.get("commune") or "",
            code_insee=d.get("code_insee") or "", siret=d.get("siret") or "",
            categories=cats, presentation=d.get("presentation") or "")
        jeton = self.app.store.comptes.ouvrir_session(compte.identifiant)
        self._compte, self._compte_lu = compte, True
        self._json({"compte": compte.prive(),
                    "droits": droits.pour_le_navigateur(self.app.store, compte)}, 201,
                   cookies=[self._cookie(jeton, 30 * 24 * 3600)])

    def api_moi(self) -> None:
        self._json({"compte": self.compte.prive(),
                    "annonces": self.app.store.annonces.du_compte(self.compte.identifiant)})

    def api_effacer(self) -> None:
        d = self._corps()
        # Le mot de passe redemandé : une session oubliée ouverte ne doit
        # pas suffire à effacer un compte.
        self.app.store.comptes.connecter(self.compte.email, d.get("mot_de_passe", ""))
        self.app.store.comptes.effacer(self.compte.identifiant)
        self._json({"ok": True}, cookies=[self._cookie("", 0)])

    # -- publier ------------------------------------------------------------

    def api_publier_emplacement(self) -> None:
        if not self.compte.accueillant_verifie:
            # Le tableau dit que la fonction est ouverte aux accueillants ;
            # la vérification, elle, est propre au compte.
            raise Refus(403, "Votre compte attend sa vérification par la modération : "
                             "vous pourrez publier dès qu'il sera vérifié.")
        self._json(self.app.store.annonces.publier_emplacement(self.compte, self._corps()), 201)

    def api_publier_demande(self) -> None:
        self._json(self.app.store.annonces.publier_demande(self.compte, self._corps()), 201)

    def api_apercu_zone(self) -> None:
        """Les communes d'une zone avant publication : le commerçant voit ce
        que son cercle ou son dessin couvre pendant qu'il le règle."""
        try:
            zone = self.app.store.zones.lire(self._corps().get("zone"))
        except ZoneRefusee as exc:
            raise Refus(400, str(exc))
        communes = sorted(zone["communes"], key=lambda c: c["nom"])
        self._json({"libelle": zone["libelle"], "nombre": len(communes),
                    "communes": [{"code_insee": c["code_insee"], "nom": c["nom"],
                                  "departement": c["departement"]} for c in communes[:200]]})

    def api_communes(self) -> None:
        texte = parse_qs(urlsplit(self.path).query).get("q", [""])[0]
        self._json({"communes": self.app.store.communes.chercher(texte[:80])},
                   cache="public, max-age=3600")

    def api_historique(self) -> None:
        self._json({"demandes": self.app.store.annonces.historique(self.compte.identifiant)})

    def api_notifications(self) -> None:
        self._json(self.app.store.notifications.du_compte(self.compte.identifiant))

    def api_notifications_lues(self) -> None:
        self.app.store.notifications.marquer_lues(self.compte.identifiant)
        self._json({"ok": True})

    def api_retirer(self, id: str) -> None:  # noqa: A002
        self.app.store.annonces.retirer(self.compte, id)
        self._json({"ok": True})

    # -- modération ---------------------------------------------------------

    def api_accueillants_a_verifier(self) -> None:
        # La modération voit l'adresse électronique : c'est souvent elle qui
        # dit qu'un compte parle bien au nom d'une commune (un domaine en
        # « mairie-… » ou une adresse publiée dans l'Annuaire).
        self._json({"comptes": [dict(c.public(), email=c.email,
                                     nature_libelle=LIBELLES_NATURES.get(c.nature or ""),
                                     date_creation=c.date_creation)
                                for c in self.app.store.comptes.en_attente_de_verification()]})

    def api_decider_verification(self, id: str) -> None:  # noqa: A002
        d = self._corps()
        compte = self.app.store.comptes.decider_verification(
            id, d.get("decision", ""), par=self.compte.pseudo, motif=d.get("motif") or "")
        self._json({"compte": compte.public()})

    def api_moderer_annonce(self, id: str) -> None:  # noqa: A002
        d = self._corps()
        if d.get("action") == "masquer":
            self.app.store.annonces.masquer(id, d.get("motif") or "")
        elif d.get("action") == "reafficher":
            self.app.store.annonces.reafficher(id)
        else:
            raise Refus(400, "Action inconnue : « masquer » ou « reafficher ».")
        self._json({"ok": True})

    # -- administration -----------------------------------------------------

    def api_comptes(self) -> None:
        self._json({"comptes": [c.prive() for c in self.app.store.comptes.tous()]})

    def api_changer_role(self, id: str) -> None:  # noqa: A002
        d = self._corps()
        compte = self.app.store.comptes.changer_role(id, d.get("role", ""), par=self.compte)
        self._json({"compte": compte.prive()})

    def api_tableau_droits(self) -> None:
        tableau = droits.pour_le_navigateur(self.app.store, self.compte)
        tableau["journal"] = droits.journal(self.app.store)[-50:]
        self._json(tableau)

    def api_regler_droit(self) -> None:
        d = self._corps()
        cle = d.get("cle", "")
        if "niveau" in d:
            droits.definir(self.app.store, cle, d.get("niveau", ""), par=self.compte.pseudo)
        if "active" in d:
            if not isinstance(d["active"], bool):
                raise Refus(400, "« active » doit valoir vrai ou faux.")
            droits.activer(self.app.store, cle, d["active"], par=self.compte.pseudo)
        tableau = droits.pour_le_navigateur(self.app.store, self.compte)
        tableau["journal"] = droits.journal(self.app.store)[-50:]
        self._json(tableau)


def construire_serveur(store: Store, hote: str = "127.0.0.1",
                       port: int = 8000) -> ThreadingHTTPServer:
    app = Application(store)
    gestionnaire = type("GestionnaireLie", (Gestionnaire,), {"app": app})
    ThreadingHTTPServer.allow_reuse_address = True
    serveur = ThreadingHTTPServer((hote, port), gestionnaire)
    serveur.daemon_threads = True
    return serveur
