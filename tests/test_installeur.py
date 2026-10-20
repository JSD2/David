"""L'installeur du NAS, joué de bout en bout sur cette machine.

Un faux WAY2NAV tourne (un processus dont la ligne de commande porte
« paddle_france », ce que l'installeur cherche) avec son script de
démarrage et sa base. L'installeur doit l'arrêter, mettre son démarrage de
côté sans rien effacer, et lancer le site sur le port libéré.

Ce que cet essai ne prouve pas : le comportement de busybox et de DSM sur
le NAS lui-même. Il éprouve la logique du script, pas la machine.
"""

import io
import json
import os
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request
import uuid
from pathlib import Path

import pytest

RACINE_DEPOT = Path(__file__).resolve().parent.parent
INSTALLEUR = RACINE_DEPOT / "synology" / "installer.sh"

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"),
                                reason="l'installeur vise le Linux d'un NAS")


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _archive(cible: Path) -> None:
    """L'arbre du dépôt dans un dossier unique, comme le tarball de GitHub."""
    with tarfile.open(cible, "w:gz") as tar:
        for chemin in ("ambulants", "synology", "pyproject.toml"):
            tar.add(str(RACINE_DEPOT / chemin), arcname="JSD2-David-abc123/" + chemin,
                    filter=lambda t: None if "__pycache__" in t.name else t)


def _arreter_le_site_sur(port: int) -> None:
    """Le site lancé par l'installeur, reconnu à son port : il vit détaché
    (setsid), la fin de l'essai ne l'emporterait pas."""
    cible = f"ambulants.cli app --hote 0.0.0.0 --port {port}".encode()
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            ligne = (Path("/proc") / pid / "cmdline").read_bytes().replace(b"\0", b" ")
        except OSError:
            continue
        if cible in ligne:
            os.kill(int(pid), 15)


def test_sur_le_nas_les_motifs_sont_les_courts():
    """« ps » de busybox tronque les lignes : seuls des motifs courts y
    survivent (leçon de WAY2NAV)."""
    texte = INSTALLEUR.read_text(encoding="utf-8")
    assert 'MOTIF_SITE="${AMBULANTS_MOTIF:-[a]mbulants\\.cli}"' in texte
    assert 'MOTIF_WAY2NAV="${WAY2NAV_MOTIF:-[p]addle_france}"' in texte


def test_la_syntaxe_du_script():
    r = subprocess.run(["sh", "-n", str(INSTALLEUR)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_remplace_way2nav_et_garde_ses_donnees(tmp_path):
    w2n = tmp_path / "paddle-france"
    (w2n / "donnees").mkdir(parents=True)
    (w2n / "donnees" / "spots.sqlite3").write_bytes(b"base de WAY2NAV")
    (w2n / "demarrer.sh").write_text("#!/bin/sh\necho way2nav\n")
    # Des motifs propres à cet essai : la suite ne doit arrêter aucun autre
    # programme du poste (un WAY2NAV de développement, un serveur lancé à la
    # main). Sur le NAS, ce sont les motifs courts par défaut.
    marque = uuid.uuid4().hex[:8]
    faux = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)",
                             f"paddle_france-essai-{marque}"])

    racine = tmp_path / "ambulants"
    archive = tmp_path / "david.tar.gz"
    _archive(archive)
    port = _port_libre()
    env = dict(os.environ, AMBULANTS_RACINE=str(racine), AMBULANTS_ARCHIVE=str(archive),
               AMBULANTS_PORT=str(port), WAY2NAV_RACINE=str(w2n),
               WAY2NAV_MOTIF=f"[p]addle_france-essai-{marque}",
               AMBULANTS_MOTIF=rf"[a]mbulants\.cli app --hote 0\.0\.0\.0 --port {port}")
    env.pop("AMBULANTS_ENV", None)
    try:
        r = subprocess.run(["sh", str(INSTALLEUR)], env=env, capture_output=True,
                           text=True, timeout=180)
        sortie = r.stdout + r.stderr
        assert r.returncode == 0, sortie
        assert "arrêt de WAY2NAV" in sortie
        assert faux.wait(timeout=20) is not None  # le faux WAY2NAV est arrêté

        # Mis de côté, pas effacé ; sa base est intacte.
        assert not (w2n / "demarrer.sh").exists()
        assert (w2n / "demarrer.sh.arrete").read_text() == "#!/bin/sh\necho way2nav\n"
        assert (w2n / "donnees" / "spots.sqlite3").read_bytes() == b"base de WAY2NAV"

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/sante", timeout=5) as rep:
            assert json.load(rep)["ok"] is True
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/robots.txt", timeout=5) as rep:
            # « test » par défaut : pas de référencement.
            assert b"Disallow: /" in rep.read()
        assert (racine / "donnees" / "ambulants.sqlite3").exists()

        # Relancé, il met à jour sans toucher à la base ni se battre pour le port.
        (racine / "donnees" / "temoin").write_text("x")
        r = subprocess.run(["sh", str(INSTALLEUR)], env=env, capture_output=True,
                           text=True, timeout=180)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "arrêt de l'instance précédente" in r.stdout
        assert (racine / "donnees" / "temoin").exists()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/sante", timeout=5) as rep:
            assert json.load(rep)["ok"] is True
    finally:
        if faux.poll() is None:
            faux.kill()
        _arreter_le_site_sur(port)
        time.sleep(0.5)
