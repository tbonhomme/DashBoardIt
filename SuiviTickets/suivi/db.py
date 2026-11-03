"""Accès SQLite : schéma, sauvegardes, tickets, suivi perso, tâches, temps."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from . import config
from .utils import FMT_ISO, logger, maintenant_iso

ETATS_TACHE = ["À faire", "En cours", "Fait"]
VERSION_SCHEMA = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (cle TEXT PRIMARY KEY, valeur TEXT);

CREATE TABLE IF NOT EXISTS tickets (
    cle TEXT PRIMARY KEY,
    id_jira TEXT, type TEXT, resume TEXT, assigne TEXT, rapporteur TEXT, createur TEXT,
    priorite_jira TEXT, etat TEXT, resolution TEXT,
    cree TEXT, maj TEXT, echeance TEXT, type_demande TEXT,
    bloque_par TEXT, bloque TEXT, lies TEXT,
    absent_export INTEGER NOT NULL DEFAULT 0,
    premiere_vue TEXT, derniere_vue TEXT, date_sortie TEXT
);

-- Données personnelles (JSON) : ajouter une colonne ne nécessite aucune migration.
CREATE TABLE IF NOT EXISTS suivi (
    cle TEXT PRIMARY KEY,
    donnees TEXT NOT NULL DEFAULT '{}',
    maj TEXT
);

CREATE TABLE IF NOT EXISTS taches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cle TEXT,                       -- NULL = tâche libre (sans ticket)
    titre TEXT NOT NULL,
    statut TEXT NOT NULL DEFAULT 'À faire',
    echeance TEXT,
    cree TEXT NOT NULL,
    termine TEXT
);

CREATE TABLE IF NOT EXISTS temps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tache_id INTEGER,
    cle TEXT,
    libelle TEXT,
    debut TEXT NOT NULL,
    fin TEXT,                       -- NULL = chrono en cours
    duree_s INTEGER,
    note TEXT,
    source TEXT NOT NULL DEFAULT 'chrono'
);

CREATE TABLE IF NOT EXISTS historique (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cle TEXT NOT NULL, champ TEXT NOT NULL, ancienne TEXT, nouvelle TEXT,
    date TEXT NOT NULL, import_id INTEGER
);

CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fichier TEXT, hash TEXT, date_import TEXT NOT NULL,
    statut TEXT NOT NULL, nb_total INTEGER, nb_nouveaux INTEGER, nb_maj INTEGER,
    nb_absents INTEGER, nb_reapparus INTEGER, message TEXT
);

CREATE INDEX IF NOT EXISTS ix_taches_cle ON taches(cle);
CREATE INDEX IF NOT EXISTS ix_temps_cle ON temps(cle);
CREATE INDEX IF NOT EXISTS ix_temps_tache ON temps(tache_id);
CREATE INDEX IF NOT EXISTS ix_hist_cle ON historique(cle);
CREATE INDEX IF NOT EXISTS ix_imports_hash ON imports(hash);
"""


# --------------------------------------------------------------------------- connexion
@contextmanager
def connecter(cfg: dict):
    """Connexion courte : commit si tout va bien, rollback sinon, fermeture systématique."""
    chemin = config.chemin(cfg, "base")
    chemin.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        mode = str(cfg.get("mode_journal", "DELETE")).upper()
        if mode in ("DELETE", "WAL", "TRUNCATE", "PERSIST"):
            conn.execute(f"PRAGMA journal_mode={mode}")
        conn.execute("PRAGMA busy_timeout=30000")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialiser(cfg: dict) -> None:
    with connecter(cfg) as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT OR IGNORE INTO meta(cle, valeur) VALUES ('version_schema', ?)", (str(VERSION_SCHEMA),))


# --------------------------------------------------------------------------- sauvegardes
def sauvegarder(cfg: dict, motif: str = "auto") -> Path | None:
    """Copie datée de la base (API de sauvegarde SQLite, sûre même base ouverte)."""
    src = config.chemin(cfg, "base")
    if not src.exists():
        return None
    dossier = config.chemin(cfg, "dossier_sauvegardes")
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / f"{src.stem}_{datetime.now():%Y%m%d_%H%M%S}_{motif}.db"
    s = sqlite3.connect(src, timeout=30)
    d = sqlite3.connect(cible)
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()
    _purger_sauvegardes(cfg, src.stem)
    logger(cfg).info("Sauvegarde créée : %s", cible.name)
    return cible


def sauvegarde_du_jour_existe(cfg: dict) -> bool:
    src = config.chemin(cfg, "base")
    dossier = config.chemin(cfg, "dossier_sauvegardes")
    return dossier.exists() and any(dossier.glob(f"{src.stem}_{datetime.now():%Y%m%d}_*.db"))


def _purger_sauvegardes(cfg: dict, prefixe: str) -> None:
    garder = int(cfg.get("nb_sauvegardes_conservees", 20))
    fichiers = sorted(config.chemin(cfg, "dossier_sauvegardes").glob(f"{prefixe}_*.db"))
    for ancien in fichiers[:-garder] if garder > 0 else []:
        try:
            ancien.unlink()
        except OSError:
            pass


# --------------------------------------------------------------------------- suivi perso
def lire_suivi(conn, cle: str) -> dict:
    r = conn.execute("SELECT donnees FROM suivi WHERE cle=?", (cle,)).fetchone()
    return json.loads(r["donnees"]) if r and r["donnees"] else {}


def maj_suivi(conn, cle: str, valeurs: dict) -> None:
    """Fusionne `valeurs` dans le suivi du ticket. None / "" supprime la valeur."""
    actuel = lire_suivi(conn, cle)
    for k, v in valeurs.items():
        if v is None or (isinstance(v, str) and not v.strip()):
            actuel.pop(k, None)
        else:
            actuel[k] = v
    conn.execute(
        "INSERT INTO suivi(cle, donnees, maj) VALUES (?,?,?) "
        "ON CONFLICT(cle) DO UPDATE SET donnees=excluded.donnees, maj=excluded.maj",
        (cle, json.dumps(actuel, ensure_ascii=False), maintenant_iso()),
    )


# --------------------------------------------------------------------------- tâches
def ajouter_taches(conn, cle: str | None, titres: list[str], echeance: date | None = None) -> int:
    n = 0
    for t in titres:
        t = (t or "").strip()
        if not t:
            continue
        conn.execute(
            "INSERT INTO taches(cle, titre, statut, echeance, cree) VALUES (?,?,?,?,?)",
            (cle or None, t, "À faire", echeance.isoformat() if echeance else None, maintenant_iso()),
        )
        n += 1
    return n


def maj_tache(conn, tache_id: int, titre=None, statut=None, echeance=None, maj_echeance=False) -> None:
    ligne = conn.execute("SELECT * FROM taches WHERE id=?", (tache_id,)).fetchone()
    if not ligne:
        return
    nouveau_statut = statut or ligne["statut"]
    termine = ligne["termine"]
    if nouveau_statut == "Fait" and ligne["statut"] != "Fait":
        termine = maintenant_iso()
        arreter_chrono(conn, tache_id=tache_id)
    elif nouveau_statut != "Fait":
        termine = None
    conn.execute(
        "UPDATE taches SET titre=?, statut=?, echeance=?, termine=? WHERE id=?",
        (
            (titre if titre is not None else ligne["titre"]).strip() or ligne["titre"],
            nouveau_statut,
            (echeance.isoformat() if echeance else None) if maj_echeance else ligne["echeance"],
            termine,
            tache_id,
        ),
    )


def supprimer_tache(conn, tache_id: int) -> None:
    """Supprime la tâche ; le temps déjà saisi est conservé (rattaché au ticket)."""
    arreter_chrono(conn, tache_id=tache_id)
    t = conn.execute("SELECT titre FROM taches WHERE id=?", (tache_id,)).fetchone()
    if t:
        conn.execute("UPDATE temps SET libelle=COALESCE(libelle, ?), tache_id=NULL WHERE tache_id=?",
                     (t["titre"], tache_id))
    conn.execute("DELETE FROM taches WHERE id=?", (tache_id,))


# --------------------------------------------------------------------------- chrono / temps
def chrono_actif(conn):
    return conn.execute("SELECT * FROM temps WHERE fin IS NULL ORDER BY debut DESC LIMIT 1").fetchone()


def arreter_chrono(conn, tache_id: int | None = None, maintenant: datetime | None = None) -> int:
    """Arrête le(s) chrono(s) en cours (éventuellement ceux d'une tâche). Retourne le nombre arrêté."""
    fin = maintenant or datetime.now()
    sql = "SELECT * FROM temps WHERE fin IS NULL"
    params: tuple = ()
    if tache_id is not None:
        sql += " AND tache_id=?"
        params = (tache_id,)
    n = 0
    for r in conn.execute(sql, params).fetchall():
        debut = datetime.strptime(r["debut"], FMT_ISO)
        duree = max(0, int((fin - debut).total_seconds()))
        conn.execute("UPDATE temps SET fin=?, duree_s=? WHERE id=?", (fin.strftime(FMT_ISO), duree, r["id"]))
        n += 1
    return n


def demarrer_chrono(conn, cle: str | None, tache_id: int | None = None, note: str | None = None,
                    maintenant: datetime | None = None) -> int:
    """Démarre un chrono (un seul à la fois : l'éventuel chrono en cours est arrêté)."""
    debut = maintenant or datetime.now()
    arreter_chrono(conn, maintenant=debut)
    libelle = None
    if tache_id is not None:
        t = conn.execute("SELECT cle, titre, statut FROM taches WHERE id=?", (tache_id,)).fetchone()
        if t:
            libelle = t["titre"]
            cle = cle or t["cle"]
            if t["statut"] == "À faire":
                conn.execute("UPDATE taches SET statut='En cours' WHERE id=?", (tache_id,))
    cur = conn.execute(
        "INSERT INTO temps(tache_id, cle, libelle, debut, note, source) VALUES (?,?,?,?,?, 'chrono')",
        (tache_id, cle, libelle, debut.strftime(FMT_ISO), note),
    )
    return cur.lastrowid


def ajouter_temps_manuel(conn, cle: str | None, tache_id: int | None, jour: date, minutes: int,
                         note: str | None = None) -> int:
    if minutes <= 0:
        raise ValueError("La durée doit être supérieure à 0 minute.")
    debut = datetime(jour.year, jour.month, jour.day)
    fin = debut + timedelta(minutes=minutes)
    libelle = None
    if tache_id is not None:
        t = conn.execute("SELECT cle, titre FROM taches WHERE id=?", (tache_id,)).fetchone()
        if t:
            libelle = t["titre"]
            cle = cle or t["cle"]
    cur = conn.execute(
        "INSERT INTO temps(tache_id, cle, libelle, debut, fin, duree_s, note, source) VALUES (?,?,?,?,?,?,?, 'manuel')",
        (tache_id, cle, libelle, debut.strftime(FMT_ISO), fin.strftime(FMT_ISO), minutes * 60, note),
    )
    return cur.lastrowid


def maj_temps(conn, temps_id: int, minutes: int | None = None, note: str | None = None) -> None:
    r = conn.execute("SELECT * FROM temps WHERE id=?", (temps_id,)).fetchone()
    if not r or r["fin"] is None:
        return
    if minutes is not None and minutes > 0:
        debut = datetime.strptime(r["debut"], FMT_ISO)
        fin = debut + timedelta(minutes=minutes)
        conn.execute("UPDATE temps SET duree_s=?, fin=? WHERE id=?", (minutes * 60, fin.strftime(FMT_ISO), temps_id))
    if note is not None:
        conn.execute("UPDATE temps SET note=? WHERE id=?", (note.strip() or None, temps_id))


def supprimer_temps(conn, temps_id: int) -> None:
    conn.execute("DELETE FROM temps WHERE id=?", (temps_id,))


# --------------------------------------------------------------------------- chargement DataFrames
def charger_temps(conn, maintenant: datetime | None = None) -> pd.DataFrame:
    df = pd.read_sql_query(
        """SELECT t.id, t.tache_id, t.cle, COALESCE(ta.titre, t.libelle) AS tache, COALESCE(k.resume, '') AS resume,
                  t.debut, t.fin, t.duree_s, t.note, t.source
           FROM temps t
           LEFT JOIN tickets k ON k.cle = t.cle
           LEFT JOIN taches ta ON ta.id = t.tache_id
           ORDER BY t.debut DESC, t.id DESC""",
        conn,
    )
    df["debut"] = pd.to_datetime(df["debut"], errors="coerce")
    df["fin"] = pd.to_datetime(df["fin"], errors="coerce")
    df["en_cours"] = df["fin"].isna()
    maintenant = maintenant or datetime.now()
    df["duree_s"] = pd.to_numeric(df["duree_s"], errors="coerce").astype(float)
    if df["en_cours"].any():
        ecoule = (pd.Timestamp(maintenant) - df.loc[df["en_cours"], "debut"]).dt.total_seconds().clip(lower=0)
        df.loc[df["en_cours"], "duree_s"] = ecoule
    df["duree_s"] = df["duree_s"].fillna(0.0)
    return df


def charger_taches(conn, maintenant: datetime | None = None) -> pd.DataFrame:
    df = pd.read_sql_query(
        """SELECT ta.id, ta.cle, COALESCE(k.resume, '') AS resume, ta.titre, ta.statut, ta.echeance, ta.cree, ta.termine
           FROM taches ta LEFT JOIN tickets k ON k.cle = ta.cle
           ORDER BY ta.id DESC""",
        conn,
    )
    for c in ("echeance", "cree", "termine"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    tps = charger_temps(conn, maintenant)
    par_tache = tps.dropna(subset=["tache_id"]).groupby("tache_id")["duree_s"].sum()
    df["temps_s"] = df["id"].map(par_tache).fillna(0.0)
    return df


def charger_tickets(conn, cfg: dict, maintenant: datetime | None = None) -> pd.DataFrame:
    maintenant = maintenant or datetime.now()
    df = pd.read_sql_query("SELECT * FROM tickets", conn)
    suivi = {r["cle"]: json.loads(r["donnees"] or "{}") for r in conn.execute("SELECT cle, donnees FROM suivi")}
    for col in cfg["colonnes_perso"]:
        df[f"perso_{col['id']}"] = [suivi.get(c, {}).get(col["id"]) for c in df["cle"]]
    for c in ("cree", "maj", "echeance", "premiere_vue", "derniere_vue", "date_sortie"):
        df[c] = pd.to_datetime(df[c], errors="coerce")

    clos = {e.casefold() for e in cfg.get("etats_clos", [])}
    df["ouvert"] = (df["absent_export"] == 0) & ~df["etat"].fillna("").str.casefold().isin(clos)
    now = pd.Timestamp(maintenant)
    df["age_jours"] = (now - df["cree"]).dt.days
    df["jours_sans_maj"] = (now - df["maj"]).dt.days
    df["en_retard"] = df["ouvert"] & df["echeance"].notna() & (df["echeance"].dt.normalize() < now.normalize())

    tps = charger_temps(conn, maintenant)
    df["temps_s"] = df["cle"].map(tps.groupby("cle")["duree_s"].sum()).fillna(0.0)
    tch = charger_taches(conn, maintenant)
    df["taches_ouvertes"] = df["cle"].map(tch[tch["statut"] != "Fait"].groupby("cle").size()).fillna(0).astype(int)
    df["taches_total"] = df["cle"].map(tch.groupby("cle").size()).fillna(0).astype(int)
    return df


def charger_historique(conn, cle: str) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT date, champ, ancienne, nouvelle FROM historique WHERE cle=? ORDER BY date DESC, id DESC",
        conn, params=(cle,))


def charger_imports(conn, limite: int = 50) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM imports ORDER BY id DESC LIMIT ?", conn, params=(limite,))
