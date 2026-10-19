"""Les essais JavaScript, lancés par Node.

**Node est un outil d'essai, pas une dépendance du programme** : le service
tourne sur Python seul. Sans Node, ces essais se sautent avec un message ;
`AMBULANTS_EXIGE_NODE=1` (posé par le workflow) change le saut en échec,
pour qu'un coureur sans Node ne rende pas une suite verte qui n'a rien
éprouvé.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent


def test_les_essais_js_passent():
    node = shutil.which("node")
    if node is None:
        if os.environ.get("AMBULANTS_EXIGE_NODE") == "1":
            pytest.fail("Node est exigé ici et n'est pas installé.")
        pytest.skip("Node absent : essais JavaScript non lancés.")
    fichiers = sorted(str(p) for p in (RACINE / "tests" / "js").glob("*.test.mjs"))
    assert fichiers
    r = subprocess.run([node, "--test", *fichiers], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr


def test_app_js_se_lit_sans_erreur_de_syntaxe():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node absent.")
    for f in ("app.js", "sw.js"):
        r = subprocess.run([node, "--check", str(RACINE / "ambulants" / "web" / f)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
