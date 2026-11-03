"""Lanceur « discret » : l'application tourne en arrière-plan avec une icône à côté de l'horloge.

Lancement sans fenêtre noire :   .venv\\Scripts\\pythonw.exe tray.py     (ou lancer_tray.bat / raccourci)
Clic gauche sur l'icône : ouvre l'application. Clic droit : menu (importer, arrêter le chrono, quitter...).
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

from suivi import config, db, serveur  # noqa: E402
from suivi.utils import logger  # noqa: E402

PORT_VERROU = 8599          # verrou « une seule icône » (port local, jamais exposé)


def message(titre: str, texte: str, style: int = 0x40) -> int:
    """Boîte de dialogue Windows (0x40 info, 0x30 avertissement, 0x10 erreur, 0x23 oui/non/annuler)."""
    if sys.platform != "win32":
        print(f"{titre} : {texte}")
        return 6
    import ctypes
    return ctypes.windll.user32.MessageBoxW(None, texte, titre, style | 0x10000)


def ouvrir(chemin: Path) -> None:
    if chemin.suffix == "":
        chemin.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(chemin))  # noqa: S606
    else:
        webbrowser.open(chemin.as_uri())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8501)
    ap.add_argument("--sans-navigateur", action="store_true", help="n'ouvre pas le navigateur au démarrage")
    ap.add_argument("--script", default="app.py", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    try:
        cfg = config.charger()
    except config.ConfigError as e:
        message("Suivi des tickets", f"Configuration invalide :\n{e}", 0x10)
        return 1
    log = logger(cfg)
    db.initialiser(cfg)

    verrou = socket.socket()
    try:
        verrou.bind(("127.0.0.1", PORT_VERROU))
    except OSError:
        webbrowser.open(f"http://localhost:{args.port}")      # déjà lancé : on ouvre simplement la page
        return 0
    if serveur.port_ouvert(args.port):
        message("Suivi des tickets",
                f"Le port {args.port} est déjà utilisé (application lancée avec lancer.bat ?).\n"
                "Fermez l'autre fenêtre puis relancez.", 0x30)
        verrou.close()
        return 1

    try:
        import pystray
        from suivi.icone import creer_icone
    except Exception as e:  # noqa: BLE001
        message("Suivi des tickets", f"Composants d'icône manquants ({e}).\n"
                "Exécutez : .venv\\Scripts\\python.exe -m pip install -r requirements.txt", 0x10)
        verrou.close()
        return 1

    srv = serveur.ServeurStreamlit(cfg, args.port, RACINE, args.script)
    srv.demarrer()
    arret = threading.Event()
    etat = {"chrono": None, "redemarrages": 0}

    def ouvrir_app(icon=None, item=None):
        webbrowser.open(srv.url)

    def maj_chrono():
        etat["chrono"] = serveur.etat_chrono(cfg)
        return etat["chrono"]

    def texte_chrono(item):
        c = etat["chrono"]
        return f"Chrono : {c['texte']}" if c else "Aucun chrono en cours"

    def rafraichir(icon):
        c = maj_chrono()
        icon.icon = creer_icone(bool(c))
        icon.title = ("Suivi des tickets - chrono : " + c["texte"])[:120] if c else "Suivi des tickets"
        icon.update_menu()

    def arreter_chrono(icon, item):
        try:
            with db.connecter(cfg) as conn:
                db.arreter_chrono(conn)
            icon.notify("Chrono arrêté. Actualisez la page (F5) si elle est ouverte.", "Suivi des tickets")
        except Exception as e:  # noqa: BLE001
            log.exception("Arrêt du chrono impossible")
            icon.notify(f"Erreur : {e}", "Suivi des tickets")
        rafraichir(icon)

    def importer_depot(icon, item):
        def travail():
            try:
                from suivi import importer
                res = importer.importer_depot(cfg)
                if not res:
                    icon.notify("Aucun fichier CSV dans le dépôt.", "Import")
                for r in res:
                    icon.notify(f"{r['fichier']} : {r.get('message', '')}", "Import " + r["statut"])
                if any(r["statut"] == "ok" for r in res) and cfg.get("export_auto_apres_import"):
                    from suivi import export_excel
                    export_excel.exporter_excel(cfg)
            except Exception as e:  # noqa: BLE001
                log.exception("Import depuis l'icône")
                icon.notify(f"Erreur : {e}", "Import")
        threading.Thread(target=travail, daemon=True).start()

    def quitter(icon, item):
        c = maj_chrono()
        if c:
            rep = message("Suivi des tickets",
                          f"Un chrono est en cours :\n{c['texte']}\n\nOui = l'arrêter puis quitter\n"
                          "Non = quitter en le laissant tourner (il restera enregistré)\nAnnuler = ne pas quitter", 0x23)
            if rep == 2:        # annuler
                return
            if rep == 6:        # oui
                with db.connecter(cfg) as conn:
                    db.arreter_chrono(conn)
        arret.set()
        srv.arreter()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Ouvrir le suivi des tickets", ouvrir_app, default=True),
        pystray.MenuItem(texte_chrono, None, enabled=False),
        pystray.MenuItem("Arrêter le chrono", arreter_chrono, visible=lambda item: etat["chrono"] is not None),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Importer le dépôt maintenant", importer_depot),
        pystray.MenuItem("Ouvrir le dossier de dépôt", lambda i, it: ouvrir(config.chemin(cfg, "dossier_depot"))),
        pystray.MenuItem("Ouvrir le dossier de l'application", lambda i, it: ouvrir(RACINE)),
        pystray.MenuItem("Ouvrir le journal", lambda i, it: ouvrir(config.chemin(cfg, "dossier_logs") / "suivi_tickets.log")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quitter", quitter),
    )
    icon = pystray.Icon("suivi_tickets", creer_icone(False), "Suivi des tickets - démarrage...", menu)

    def surveillance():
        pret = srv.attendre(90)
        if arret.is_set():
            return
        if pret:
            icon.title = "Suivi des tickets"
            if not args.sans_navigateur:
                ouvrir_app()
        else:
            icon.notify("Le serveur n'a pas démarré. Consultez logs\\streamlit.log.", "Suivi des tickets")
        while not arret.wait(15):
            try:
                rafraichir(icon)
                if not srv.vivant():                                  # serveur arrêté : redémarrage limité
                    if etat["redemarrages"] < 3:
                        etat["redemarrages"] += 1
                        log.error("Serveur Streamlit arrêté : redémarrage %s/3", etat["redemarrages"])
                        icon.notify("Le serveur s'est arrêté : redémarrage...", "Suivi des tickets")
                        srv.demarrer()
                    else:
                        icon.notify("Le serveur ne redémarre pas. Voir logs\\streamlit.log.", "Suivi des tickets")
                        arret.set()
                        icon.stop()
            except Exception:  # noqa: BLE001
                log.exception("Surveillance de l'icône")

    def preparer(icon):
        icon.visible = True
        threading.Thread(target=surveillance, daemon=True).start()

    log.info("Icône démarrée (port %s)", args.port)
    try:
        icon.run(setup=preparer)
    finally:
        arret.set()
        srv.arreter()
        verrou.close()
        log.info("Icône arrêtée")
    return 0


if __name__ == "__main__":
    sys.exit(main())
