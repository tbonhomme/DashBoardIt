"""Tests de l'icône / du serveur en arrière-plan. Données fictives dans un dossier temporaire (votre base n'est pas touchée)."""
from __future__ import annotations

import socket
import sys
import types
from datetime import datetime, timedelta

import pytest

from suivi import config, db, serveur


def port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def cfg(tmp_path):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    c = config.charger(tmp_path / "config.json")
    db.initialiser(c)
    (tmp_path / "mini_app.py").write_text("import streamlit as st\nst.write('ok')\n", encoding="utf-8")
    return c


def test_python_console_remplace_pythonw(tmp_path):
    (tmp_path / "pythonw.exe").write_text("")
    (tmp_path / "python.exe").write_text("")
    assert serveur.python_console(str(tmp_path / "pythonw.exe")) == str(tmp_path / "python.exe")
    assert serveur.python_console(str(tmp_path / "python.exe")) == str(tmp_path / "python.exe")


def test_port_ouvert():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        assert serveur.port_ouvert(s.getsockname()[1])
    assert not serveur.port_ouvert(port_libre())


def test_etat_chrono(cfg):
    assert serveur.etat_chrono(cfg) is None
    with db.connecter(cfg) as conn:
        db.demarrer_chrono(conn, "SUP-1001", None, maintenant=datetime.now() - timedelta(minutes=12))
    c = serveur.etat_chrono(cfg)
    assert c["cle"] == "SUP-1001" and "12 min" in c["texte"]
    with db.connecter(cfg) as conn:
        db.arreter_chrono(conn)
    assert serveur.etat_chrono(cfg) is None


def test_demarrer_attendre_arreter(cfg):
    port = port_libre()
    srv = serveur.ServeurStreamlit(cfg, port, script="mini_app.py")
    srv.demarrer()
    try:
        assert srv.attendre(60), "le serveur doit répondre sur /_stcore/health"
        assert srv.vivant() and serveur.port_ouvert(port)
    finally:
        srv.arreter()
    assert not srv.vivant()
    assert not serveur.port_ouvert(port)
    assert (config.chemin(cfg, "dossier_logs") / "streamlit.log").exists()


def test_serveur_qui_plante_est_detecte(cfg):
    srv = serveur.ServeurStreamlit(cfg, port_libre(), script="inexistant.py")
    srv.demarrer()
    try:
        assert srv.attendre(30) is False          # le processus se termine : attendre() rend la main sans attendre 30 s
    finally:
        srv.arreter()


def test_tray_cycle_complet_avec_icone_simulee(cfg, tmp_path, monkeypatch):
    """Démarre tray.main() avec une fausse icône : serveur lancé, menu construit, chrono arrêté via le menu, arrêt propre."""
    import threading
    import tray

    evenements = {"notifs": [], "menu": None, "titres": []}

    class FauxItem:
        def __init__(self, text, action=None, default=False, enabled=True, visible=True):
            self.text, self.action, self.default, self.enabled, self.visible = text, action, default, enabled, visible

    class FauxMenu(list):
        SEPARATOR = "---"

        def __init__(self, *items):
            super().__init__(items)

    class FausseIcone:
        def __init__(self, nom, image, titre, menu):
            self.icon, self.title, self.menu, self.visible = image, titre, menu, False
            self.fini = threading.Event()
            evenements["menu"] = menu

        def notify(self, msg, titre=None):
            evenements["notifs"].append(msg)

        def update_menu(self):
            pass

        def stop(self):
            self.fini.set()

        def run(self, setup=None):
            setup(self)
            self.fini.wait(90)

    faux = types.SimpleNamespace(Icon=FausseIcone, Menu=FauxMenu, MenuItem=FauxItem)
    monkeypatch.setitem(sys.modules, "pystray", faux)
    monkeypatch.setattr(tray.config, "charger", lambda *a, **k: cfg)
    monkeypatch.setattr(tray, "RACINE", tmp_path)
    monkeypatch.setattr(tray, "PORT_VERROU", port_libre())
    monkeypatch.setattr(tray.webbrowser, "open", lambda url: evenements.setdefault("urls", []).append(url))
    port = port_libre()

    with db.connecter(cfg) as conn:
        db.demarrer_chrono(conn, "SUP-2002", None)

    def pilote():
        """Joue le rôle de l'utilisateur : attend le serveur, clique « Arrêter le chrono » puis « Quitter »."""
        assert serveur.port_ouvert(port) or evenements.setdefault("attente", True)
        for _ in range(120):
            if serveur.serveur_pret(port):
                break
            threading.Event().wait(0.5)
        items = [i for i in evenements["menu"] if isinstance(i, FauxItem)]
        libelles = [i.text if isinstance(i.text, str) else "(dynamique)" for i in items]
        evenements["libelles"] = libelles
        icone = evenements["icone"]
        arreter = next(i for i in items if i.text == "Arrêter le chrono")
        arreter.action(icone, arreter)
        evenements["chrono_apres"] = serveur.etat_chrono(cfg)
        quitter = next(i for i in items if i.text == "Quitter")
        quitter.action(icone, quitter)

    orig_init = FausseIcone.__init__

    def init_capture(self, *a):
        orig_init(self, *a)
        evenements["icone"] = self
        threading.Thread(target=pilote, daemon=True).start()

    monkeypatch.setattr(FausseIcone, "__init__", init_capture)
    code = tray.main(["--port", str(port), "--script", "mini_app.py", "--sans-navigateur"])
    assert code == 0
    assert evenements["libelles"][0] == "Ouvrir le suivi des tickets"
    assert "Quitter" in evenements["libelles"] and "Importer le dépôt maintenant" in evenements["libelles"]
    assert evenements["chrono_apres"] is None
    assert any("Chrono arrêté" in n for n in evenements["notifs"])
    assert not serveur.port_ouvert(port)                      # le serveur est bien arrêté à la sortie
