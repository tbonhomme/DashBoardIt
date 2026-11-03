"""Gestion du serveur Streamlit en arrière-plan (sans fenêtre) et état du chrono, pour l'icône de la barre des tâches."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from . import config, db
from .utils import fmt_duree

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def port_ouvert(port: int, hote: str = "127.0.0.1", delai: float = 0.5) -> bool:
    try:
        with socket.create_connection((hote, port), timeout=delai):
            return True
    except OSError:
        return False


def serveur_pret(port: int, delai: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=delai) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def python_console(exe: str | None = None) -> str:
    """python.exe (et non pythonw.exe) : Streamlit a besoin de flux de sortie valides."""
    p = Path(exe or sys.executable)
    if p.name.lower() == "pythonw.exe" and (p.parent / "python.exe").exists():
        return str(p.parent / "python.exe")
    return str(p)


class ServeurStreamlit:
    def __init__(self, cfg: dict, port: int = 8501, racine: Path | None = None, script: str = "app.py"):
        self.cfg = cfg
        self.port = port
        self.racine = Path(racine or cfg.get("_racine", "."))
        self.script = script
        self.proc: subprocess.Popen | None = None
        self._journal = None

    @property
    def url(self) -> str:
        return f"http://localhost:{self.port}"

    def vivant(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def demarrer(self) -> None:
        if self.vivant():
            return
        dossier_logs = config.chemin(self.cfg, "dossier_logs")
        dossier_logs.mkdir(parents=True, exist_ok=True)
        self._journal = open(dossier_logs / "streamlit.log", "ab")
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        cmd = [python_console(), "-m", "streamlit", "run", self.script,
               "--server.port", str(self.port), "--server.address", "127.0.0.1",
               "--server.headless", "true", "--browser.gatherUsageStats", "false"]
        self.proc = subprocess.Popen(
            cmd, cwd=str(self.racine), stdin=subprocess.DEVNULL, stdout=self._journal, stderr=subprocess.STDOUT,
            env=env, creationflags=CREATE_NO_WINDOW)

    def attendre(self, delai_max: float = 60.0) -> bool:
        fin = time.time() + delai_max
        while time.time() < fin:
            if self.proc is not None and self.proc.poll() is not None:
                return False
            if serveur_pret(self.port):
                return True
            time.sleep(0.5)
        return False

    def arreter(self) -> None:
        p = self.proc
        if p is not None and p.poll() is None:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True,
                               creationflags=CREATE_NO_WINDOW)
            else:
                p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        self.proc = None
        if self._journal:
            self._journal.close()
            self._journal = None


def etat_chrono(cfg: dict) -> dict | None:
    """None si aucun chrono ; sinon {'cle', 'libelle', 'secondes', 'texte'}."""
    try:
        with db.connecter(cfg) as conn:
            r = db.chrono_actif(conn)
    except Exception:  # noqa: BLE001 - base momentanément verrouillée : on réessaiera
        return None
    if not r:
        return None
    debut = datetime.strptime(r["debut"], "%Y-%m-%d %H:%M:%S")
    sec = max(0.0, (datetime.now() - debut).total_seconds())
    nom = r["cle"] or "Sans ticket"
    if r["libelle"]:
        nom += f" - {r['libelle']}"
    return {"cle": r["cle"], "libelle": r["libelle"], "secondes": sec, "texte": f"{nom} ({fmt_duree(sec)})"}
