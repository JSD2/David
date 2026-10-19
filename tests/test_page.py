"""La page : environnement de test non référencé, données préchargées."""

import json
import re

import pytest

from conftest import DEMANDE, connecter, creer_compte


def _page(client):
    statut, corps, entetes = client.get("/")
    assert statut == 200
    return corps.decode("utf-8"), entetes


@pytest.mark.parametrize("env", ["test", "local", "", "prod"])
def test_hors_production_bandeau_et_noindex(client, monkeypatch, env):
    """Seul « production » est indexable : une faute de frappe garde le
    site de test hors des moteurs de recherche."""
    monkeypatch.setenv("AMBULANTS_ENV", env)
    page, entetes = _page(client)
    assert 'id="bandeau-essai"' in page
    assert '<meta name="robots" content="noindex, nofollow">' in page
    assert entetes["X-Robots-Tag"] == "noindex, nofollow"
    assert b"Disallow: /" in client.get("/robots.txt")[1]


def test_en_production_ni_bandeau_ni_noindex(client, monkeypatch):
    monkeypatch.setenv("AMBULANTS_ENV", "production")
    page, entetes = _page(client)
    assert "bandeau-essai" not in page
    assert "noindex" not in page
    assert entetes.get("X-Robots-Tag") is None
    assert b"Allow: /" in client.get("/robots.txt")[1]


def test_les_annonces_arrivent_dans_la_page(client, store):
    connecter(client, creer_compte(store, "Paul"))
    client.post("/api/demandes", dict(DEMANDE, titre="</script><script>alert(1)</script>"))
    page, _ = _page(client)
    m = re.search(r'<script id="donnees" type="application/json">(.*?)</script>', page, re.S)
    donnees = json.loads(m.group(1))
    assert donnees["carte"]["annonces"][0]["titre"] == "</script><script>alert(1)</script>"
    assert {c["cle"] for c in donnees["categories"]} >= {"alimentaire", "sante", "administratif"}
    assert donnees["avertissement_legal"].startswith("Ce site aide à se trouver")


def test_l_avertissement_legal_est_au_pied_de_page(client):
    page, _ = _page(client)
    assert "il ne délivre aucune autorisation" in page


def test_entetes_de_securite(client):
    _, entetes = _page(client)
    assert "script-src 'self'" in entetes["Content-Security-Policy"]
    assert entetes["X-Content-Type-Options"] == "nosniff"


def test_les_fichiers_de_la_page_sont_servis(client):
    for chemin in ("/static/app.js", "/static/style.css", "/static/vendor/leaflet.js",
                   "/static/vendor/leaflet.css", "/static/icone.svg", "/sw.js"):
        assert client.get(chemin)[0] == 200, chemin
