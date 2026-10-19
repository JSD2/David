"""La base : paliers de schéma et connexion partagée."""

import sqlite3
import threading

import pytest

from ambulants import migrations
from ambulants.store import Store


def test_une_base_neuve_monte_au_dernier_palier(tmp_path):
    s = Store(tmp_path / "b.sqlite3")
    assert s.etat_schema() == {"version": migrations.DERNIERE_VERSION,
                               "derniere": migrations.DERNIERE_VERSION}
    assert s.migrations_appliquees == [m.version for m in migrations.MIGRATIONS]
    s.close()


def test_une_base_existante_n_est_pas_remigree(tmp_path):
    Store(tmp_path / "b.sqlite3").close()
    s = Store(tmp_path / "b.sqlite3")
    assert s.migrations_appliquees == []
    s.close()


def test_les_paliers_sont_numerotes_sans_trou():
    assert [m.version for m in migrations.MIGRATIONS] == list(
        range(1, len(migrations.MIGRATIONS) + 1))


def test_une_base_plus_recente_que_le_programme_est_refusee(tmp_path):
    chemin = tmp_path / "b.sqlite3"
    c = sqlite3.connect(str(chemin))
    c.execute(f"PRAGMA user_version = {migrations.DERNIERE_VERSION + 1}")
    c.close()
    with pytest.raises(RuntimeError, match="Mettre le programme à jour"):
        Store(chemin)


def test_les_reglages_survivent_a_la_reouverture(tmp_path):
    s = Store(tmp_path / "b.sqlite3")
    s.definir_reglage("cle", "valeur")
    s.close()
    s = Store(tmp_path / "b.sqlite3")
    assert s.reglage("cle") == "valeur"
    assert s.reglage("absente") == ""
    s.close()


def test_l_empreinte_change_a_l_ecriture_seulement(store):
    avant = store.empreinte()
    store.reglage("rien")
    assert store.empreinte() == avant
    store.definir_reglage("x", "1")
    assert store.empreinte() != avant


def test_la_connexion_partagee_tient_sous_les_fils(store):
    """La leçon de WAY2NAV : sans verrou, deux lectures simultanées sur la
    même connexion rendaient « bad parameter or other API misuse »."""
    store.definir_reglage("k", "v")
    erreurs = []

    def lire():
        try:
            for _ in range(300):
                assert store.reglage("k") == "v"
                store.empreinte()
        except Exception as exc:  # pragma: no cover - c'est l'échec qu'on guette
            erreurs.append(exc)

    fils = [threading.Thread(target=lire) for _ in range(8)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()
    assert erreurs == []
