"""Import des exports CSV Jira déposés dans le dossier de dépôt.

Règles :
- la clé du ticket (SUP-xxxxx) est l'identifiant unique ;
- seuls les champs Jira sont mis à jour : les données personnelles (priorité perso, actions, tâches,
  temps) ne sont jamais écrasées ;
- un ticket absent du nouvel export est marqué « absent » (jamais supprimé) ;
- un même fichier (même contenu) n'est jamais importé deux fois.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config, db
from .utils import FMT_ISO, logger, maintenant_iso


class ImportErreur(Exception):
    pass


# champ interne -> en-têtes possibles dans l'export Jira (FR / EN)
CHAMPS_JIRA: dict[str, list[str]] = {
    "cle": ["Clé de ticket", "Clé", "Issue key", "Key"],
    "id_jira": ["ID de ticket", "Issue id"],
    "type": ["Type de ticket", "Issue Type", "Type"],
    "resume": ["Résumé", "Summary"],
    "assigne": ["Personne assignée", "Assignee"],
    "rapporteur": ["Rapporteur", "Reporter"],
    "createur": ["Créateur", "Creator"],
    "priorite_jira": ["Priorité", "Priority"],
    "etat": ["État", "Statut", "Status"],
    "resolution": ["Résolution", "Resolution"],
    "cree": ["Création", "Créé", "Created"],
    "maj": ["Mise à jour", "Mis à jour", "Updated"],
    "echeance": ["Date d'échéance", "Due date"],
    "type_demande": ["Champs personnalisés (Request Type)", "Custom field (Request Type)", "Request Type"],
}
CHAMPS_DATE = ("cree", "maj", "echeance")
CHAMPS_HISTORISES = ("etat", "priorite_jira", "assigne", "echeance")
CHAMPS_COMPARES = [c for c in CHAMPS_JIRA if c != "cle"] + ["bloque_par", "bloque", "lies"]
FORMATS_DATE = ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%y %H:%M", "%d/%m/%y")
RE_CLE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*-\d+$")


# --------------------------------------------------------------------------- lecture du CSV
def _norm(s: str) -> str:
    return unicodedata.normalize("NFC", str(s)).strip().casefold()


def lire_csv(chemin: Path) -> pd.DataFrame:
    raw = Path(chemin).read_bytes()
    texte = None
    for enc in ("utf-8-sig", "cp1252"):
        try:
            texte = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if texte is None or not texte.strip():
        raise ImportErreur("Fichier vide ou encodage illisible.")
    entete = texte.splitlines()[0]
    sep = max((",", ";", "\t"), key=lambda s: len(next(csv.reader([entete], delimiter=s))))
    try:
        return pd.read_csv(io.StringIO(texte), sep=sep, dtype=str, keep_default_na=False)
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as e:
        raise ImportErreur(f"CSV illisible : {e}") from e


def construire_mapping(colonnes: list[str], cfg: dict) -> dict[str, str]:
    index: dict[str, str] = {}
    for c in colonnes:
        index.setdefault(_norm(c), c)
    surcharge = cfg.get("mapping_jira", {}) or {}
    mapping = {}
    for champ, candidats in CHAMPS_JIRA.items():
        essais = ([surcharge[champ]] if champ in surcharge else []) + candidats
        for c in essais:
            if _norm(c) in index:
                mapping[champ] = index[_norm(c)]
                break
    return mapping


def extraire_liens(ligne: pd.Series, colonnes: list[str]) -> dict[str, str | None]:
    """Regroupe les colonnes de liens (souvent dupliquées par Jira : « ... (Bloquer) », « ... (Bloquer).1 »)."""
    out: dict[str, list[str]] = {"bloque_par": [], "bloque": [], "lies": []}
    for col in colonnes:
        base = _norm(re.sub(r"\.\d+$", "", col))
        if not base.startswith(("lien", "link", "inward", "outward")):
            continue
        val = str(ligne[col]).strip()
        if not val:
            continue
        entrant = "entrant" in base or "inward" in base
        if "bloqu" in base or "block" in base:
            out["bloque_par" if entrant else "bloque"].append(val)
        else:
            out["lies"].append(val)
    return {k: (", ".join(dict.fromkeys(v)) or None) for k, v in out.items()}


def parser_date(valeur: str) -> str | None:
    v = (valeur or "").strip()
    if not v:
        return None
    for fmt in FORMATS_DATE:
        try:
            return datetime.strptime(v, fmt).strftime(FMT_ISO)
        except ValueError:
            continue
    raise ValueError(valeur)


def detecter_application(resume: str, cfg: dict) -> str | None:
    for appli, motifs in (cfg.get("detection_application") or {}).items():
        if any(re.search(m, resume or "", flags=re.IGNORECASE) for m in motifs):
            return appli
    return None


def hash_fichier(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


# --------------------------------------------------------------------------- import d'un fichier
def _lignes_tickets(df: pd.DataFrame, cfg: dict, avertissements: list[str]) -> dict[str, dict]:
    mapping = construire_mapping(list(df.columns), cfg)
    if "cle" not in mapping:
        raise ImportErreur(
            "Colonne « Clé de ticket » introuvable. En-têtes lus : " + ", ".join(map(str, df.columns))
            + ". Adaptez « mapping_jira » dans config.json si l'export a changé.")
    manquants = [c for c in ("resume", "etat") if c not in mapping]
    if manquants:
        avertissements.append("Colonnes Jira non trouvées (laissées vides) : " + ", ".join(manquants))
    tickets: dict[str, dict] = {}
    for _, ligne in df.iterrows():
        cle = str(ligne[mapping["cle"]]).strip()
        if not cle:
            continue
        if not RE_CLE.match(cle):
            avertissements.append(f"Clé ignorée (format inattendu) : {cle}")
            continue
        rec: dict = {"cle": cle}
        for champ, col in mapping.items():
            if champ == "cle":
                continue
            val = str(ligne[col]).strip()
            if champ in CHAMPS_DATE:
                try:
                    val = parser_date(val)
                except ValueError:
                    avertissements.append(f"{cle} : date illisible « {val} » ({champ})")
                    val = None
            rec[champ] = val or None
        rec.update(extraire_liens(ligne, list(df.columns)))
        tickets[cle] = rec  # doublon dans le fichier : la dernière ligne l'emporte
    return tickets


def importer_fichier(conn, chemin: Path, cfg: dict) -> dict:
    """Importe un fichier CSV. Ne lève jamais : retourne un dict avec statut 'ok' ou 'erreur'."""
    chemin = Path(chemin)
    res = {"fichier": chemin.name, "statut": "ok", "total": 0, "nouveaux": 0, "mises_a_jour": 0,
           "inchanges": 0, "absents": 0, "reapparus": 0, "avertissements": [], "message": ""}
    log = logger(cfg)
    empreinte = None
    try:
        empreinte = hash_fichier(chemin)
        deja = conn.execute("SELECT date_import FROM imports WHERE hash=? AND statut='ok'", (empreinte,)).fetchone()
        if deja:
            res.update(statut="ignore", message=f"Déjà importé le {deja['date_import']}.")
            return res
        df = lire_csv(chemin)
        tickets = _lignes_tickets(df, cfg, res["avertissements"])
        if not tickets:
            raise ImportErreur("Aucun ticket exploitable dans le fichier : import annulé (rien n'est modifié).")
        res["total"] = len(tickets)
        _appliquer(conn, tickets, cfg, res, chemin.name, empreinte)
        conn.commit()
        log.info("Import OK %s : %s tickets, %s nouveaux, %s maj, %s absents", chemin.name, res["total"],
                 res["nouveaux"], res["mises_a_jour"], res["absents"])
    except Exception as e:  # noqa: BLE001 - on journalise puis on remonte une erreur lisible
        conn.rollback()
        res.update(statut="erreur", message=str(e) if isinstance(e, ImportErreur) else f"{type(e).__name__} : {e}")
        log.error("Import en erreur %s : %s", chemin.name, res["message"], exc_info=not isinstance(e, ImportErreur))
        conn.execute(
            "INSERT INTO imports(fichier, hash, date_import, statut, message) VALUES (?,?,?,?,?)",
            (chemin.name, empreinte, maintenant_iso(), "erreur", res["message"]))
        conn.commit()
    return res


def _appliquer(conn, tickets: dict[str, dict], cfg: dict, res: dict, nom: str, empreinte: str) -> None:
    now = maintenant_iso()
    existants = {r["cle"]: dict(r) for r in conn.execute("SELECT * FROM tickets")}
    cur = conn.execute(
        "INSERT INTO imports(fichier, hash, date_import, statut) VALUES (?,?,?, 'en_cours')", (nom, empreinte, now))
    import_id = cur.lastrowid
    a_detecter = any(c["id"] == "application" for c in cfg["colonnes_perso"])

    for cle, rec in tickets.items():
        ancien = existants.get(cle)
        if ancien is None:
            champs = ["cle"] + CHAMPS_COMPARES + ["absent_export", "premiere_vue", "derniere_vue"]
            vals = [cle] + [rec.get(c) for c in CHAMPS_COMPARES] + [0, now, now]
            conn.execute(f"INSERT INTO tickets({','.join(champs)}) VALUES ({','.join('?' * len(champs))})", vals)
            if a_detecter:
                appli = detecter_application(rec.get("resume") or "", cfg)
                if appli:
                    db.maj_suivi(conn, cle, {"application": appli})
            res["nouveaux"] += 1
            continue

        diffs = {}
        for champ in CHAMPS_COMPARES:
            nouveau = rec.get(champ)
            if (nouveau or None) != (ancien.get(champ) or None):
                diffs[champ] = nouveau
        reapparu = bool(ancien["absent_export"])
        for champ in CHAMPS_HISTORISES:
            if champ in diffs:
                conn.execute(
                    "INSERT INTO historique(cle, champ, ancienne, nouvelle, date, import_id) VALUES (?,?,?,?,?,?)",
                    (cle, champ, ancien.get(champ), diffs[champ], now, import_id))
        if reapparu:
            conn.execute(
                "INSERT INTO historique(cle, champ, ancienne, nouvelle, date, import_id) VALUES (?,?,?,?,?,?)",
                (cle, "présence", "absent de l'export", "présent", now, import_id))
            res["reapparus"] += 1
        sets = ["derniere_vue=?", "absent_export=0", "date_sortie=NULL"]
        params: list = [now]
        for champ, val in diffs.items():
            sets.append(f"{champ}=?")
            params.append(val)
        conn.execute(f"UPDATE tickets SET {', '.join(sets)} WHERE cle=?", params + [cle])
        if diffs:
            res["mises_a_jour"] += 1
        else:
            res["inchanges"] += 1

    # tickets connus mais absents de ce fichier : marqués, jamais supprimés
    nouveaux_absents = [c for c, r in existants.items() if not r["absent_export"] and c not in tickets]
    for cle in nouveaux_absents:
        conn.execute("UPDATE tickets SET absent_export=1, date_sortie=? WHERE cle=?", (now, cle))
        conn.execute(
            "INSERT INTO historique(cle, champ, ancienne, nouvelle, date, import_id) VALUES (?,?,?,?,?,?)",
            (cle, "présence", "présent", "absent de l'export", now, import_id))
    res["absents"] = len(nouveaux_absents)
    actifs_avant = sum(1 for r in existants.values() if not r["absent_export"])
    if actifs_avant >= 10 and len(nouveaux_absents) / actifs_avant > 0.5:
        res["avertissements"].append(
            f"{len(nouveaux_absents)} tickets sur {actifs_avant} sont absents de ce fichier : "
            "vérifiez que le filtre de l'export Jira n'a pas changé (les tickets restent conservés).")

    msg = f"{res['nouveaux']} nouveaux, {res['mises_a_jour']} mis à jour, {res['inchanges']} inchangés, " \
          f"{res['absents']} absents, {res['reapparus']} réapparus"
    res["message"] = msg
    conn.execute(
        "UPDATE imports SET statut='ok', nb_total=?, nb_nouveaux=?, nb_maj=?, nb_absents=?, nb_reapparus=?, message=? "
        "WHERE id=?",
        (res["total"], res["nouveaux"], res["mises_a_jour"], res["absents"], res["reapparus"],
         "; ".join([msg] + res["avertissements"]), import_id))


# --------------------------------------------------------------------------- dossier de dépôt
def fichiers_en_attente(cfg: dict) -> list[Path]:
    dossier = config.chemin(cfg, "dossier_depot")
    if not dossier.exists():
        return []
    return sorted(
        (p for p in dossier.glob("*.csv") if p.is_file() and not p.name.startswith(("~$", "."))),
        key=lambda p: (p.stat().st_mtime, p.name))


def _deplacer(fichier: Path, dossier: Path) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / f"{datetime.now():%Y%m%d_%H%M%S}_{fichier.name}"
    shutil.move(str(fichier), str(cible))


def importer_depot(cfg: dict) -> list[dict]:
    """Importe, du plus ancien au plus récent, les CSV du dossier de dépôt. Sauvegarde la base avant."""
    fichiers = fichiers_en_attente(cfg)
    if not fichiers:
        return []
    with db.connecter(cfg) as conn:
        connus = {r["hash"] for r in conn.execute("SELECT hash FROM imports WHERE statut='ok'")}
    try:
        nouveaux = any(hash_fichier(f) not in connus for f in fichiers)
    except OSError:
        nouveaux = True
    if nouveaux:  # pas de sauvegarde inutile si tous les fichiers sont des doublons
        db.sauvegarder(cfg, "avant-import")
    resultats = []
    for f in fichiers:
        try:
            with db.connecter(cfg) as conn:
                res = importer_fichier(conn, f, cfg)
        except Exception as e:  # noqa: BLE001
            res = {"fichier": f.name, "statut": "erreur", "message": f"{type(e).__name__} : {e}",
                   "avertissements": [], "total": 0}
            logger(cfg).error("Import impossible %s : %s", f.name, e, exc_info=True)
        try:
            if res["statut"] == "erreur":
                _deplacer(f, config.chemin(cfg, "dossier_erreurs"))
            elif cfg.get("archiver_apres_import", True):
                _deplacer(f, config.chemin(cfg, "dossier_archive"))
        except OSError as e:
            res["avertissements"].append(f"Fichier non déplacé ({e}).")
        resultats.append(res)
    return resultats
