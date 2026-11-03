"""Lecture / écriture de config.json (aucun chemin n'est codé en dur dans le code)."""
from __future__ import annotations

import copy
import json
import re
import unicodedata
from pathlib import Path

RACINE_DEFAUT = Path(__file__).resolve().parent.parent
CONFIG_DEFAUT = RACINE_DEFAUT / "config.json"

TYPES_COLONNE = ("texte", "liste", "date", "nombre", "case", "lien")


class ConfigError(Exception):
    pass


DEFAUT: dict = {
    "dossier_depot": "depot",
    "archiver_apres_import": True,
    "dossier_archive": "depot/traites",
    "dossier_erreurs": "depot/erreurs",
    "base": "data/suivi_tickets.db",
    # DELETE = compatible OneDrive (pas de fichiers -wal/-shm). WAL = un peu plus rapide, mais local uniquement.
    "mode_journal": "DELETE",
    "dossier_sauvegardes": "backups",
    "nb_sauvegardes_conservees": 20,
    "dossier_export": "exports",
    "nom_export": "Suivi_Tickets.xlsx",
    "export_auto_apres_import": False,
    "dossier_logs": "logs",
    "import_auto_au_demarrage": True,
    "jira_base_url": "",
    "jours_sans_maj_alerte": 14,
    # Du plus urgent au moins urgent (sert au tri et à l'indicateur "bloquants")
    "ordre_priorite_jira": ["Bloquant", "Majeur", "Mineur"],
    # États Jira considérés comme clos (en plus des tickets absents du dernier export)
    "etats_clos": ["Terminé", "Fermé", "Résolu", "Closed", "Done", "Resolved"],
    # Surcharge optionnelle des en-têtes du CSV Jira : {"etat": "Statut"}
    "mapping_jira": {},
    # Détection automatique de l'application à partir du résumé (nouveaux tickets uniquement)
    "detection_application": {
        "NAIA": ["naia"],
        "AX": ["\\bax\\b", "dynamics"],
        "EDI": ["\\bedi\\b"],
    },
    # Colonnes personnelles : ajouter une entrée ici (ou via l'onglet Paramètres) suffit, sans migration.
    "colonnes_perso": [
        {"id": "priorite_perso", "nom": "Priorité perso", "type": "liste",
         "valeurs": ["1 - Urgent", "2 - Haute", "3 - Normale", "4 - Basse"], "actif": True},
        {"id": "action_en_cours", "nom": "Action en cours", "type": "texte", "actif": True},
        {"id": "action_a_faire", "nom": "Action à faire", "type": "texte", "actif": True},
        {"id": "application", "nom": "Application", "type": "liste",
         "valeurs": ["AX", "NAIA", "EDI", "Autre"], "actif": True},
    ],
}


def slug(texte: str) -> str:
    t = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")


def charger(chemin: str | Path | None = None) -> dict:
    p = Path(chemin) if chemin else CONFIG_DEFAUT
    cfg = copy.deepcopy(DEFAUT)
    if p.exists():
        try:
            user = json.loads(p.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            raise ConfigError(f"config.json invalide (ligne {e.lineno}, colonne {e.colno}) : {e.msg}") from e
        if not isinstance(user, dict):
            raise ConfigError("config.json doit contenir un objet JSON { ... }.")
        cfg.update(user)
    else:
        sauvegarder(cfg, p)
    cfg["_racine"] = str(p.resolve().parent)
    cfg["_chemin_config"] = str(p.resolve())
    return cfg


def sauvegarder(cfg: dict, chemin: str | Path | None = None) -> None:
    p = Path(chemin) if chemin else Path(cfg.get("_chemin_config", CONFIG_DEFAUT))
    propre = {k: v for k, v in cfg.items() if not k.startswith("_")}
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(propre, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def chemin(cfg: dict, cle: str) -> Path:
    """Chemin absolu d'une clé de config (relatif => par rapport au dossier de config.json)."""
    p = Path(cfg[cle])
    if not p.is_absolute():
        p = Path(cfg.get("_racine", RACINE_DEFAUT)) / p
    return p


def colonnes_perso_actives(cfg: dict) -> list[dict]:
    return [c for c in cfg["colonnes_perso"] if c.get("actif", True)]


def ajouter_colonne(cfg: dict, nom: str, type_: str, valeurs: list[str] | None = None) -> dict:
    nom = (nom or "").strip()
    if not nom:
        raise ConfigError("Le nom de la colonne est obligatoire.")
    if type_ not in TYPES_COLONNE:
        raise ConfigError(f"Type inconnu : {type_}")
    ident = slug(nom)
    if not ident:
        raise ConfigError("Le nom doit contenir au moins une lettre ou un chiffre.")
    if any(c["id"] == ident or c["nom"].casefold() == nom.casefold() for c in cfg["colonnes_perso"]):
        raise ConfigError(f"Une colonne « {nom} » existe déjà.")
    col = {"id": ident, "nom": nom, "type": type_, "actif": True}
    if type_ == "liste":
        vals = [v.strip() for v in (valeurs or []) if v and v.strip()]
        if not vals:
            raise ConfigError("Une colonne de type liste nécessite au moins une valeur.")
        col["valeurs"] = vals
    cfg["colonnes_perso"].append(col)
    sauvegarder(cfg)
    return col


COLONNES_TICKETS_DEBUT = ["Clé", "Résumé", "Type", "État", "Priorité Jira"]
COLONNES_TICKETS_FIN = ["Échéance", "Mise à jour", "Tâches ouvertes", "Temps passé", "Présence"]


def noms_colonnes_tickets(cfg: dict) -> list[str]:
    """Noms des colonnes du tableau Tickets, dans l'ordre par défaut."""
    noms = list(COLONNES_TICKETS_DEBUT)
    for c in colonnes_perso_actives(cfg):
        noms.append(c["nom"] if c["nom"] not in noms else f"{c['nom']} (perso)")
    return noms + COLONNES_TICKETS_FIN


def ordre_colonnes(cfg: dict, colonnes: list[str]) -> list[str]:
    """Ordre d'affichage mémorisé (config.json : ordre_colonnes_tickets) adapté aux colonnes existantes.
    Une colonne absente de l'ordre mémorisé (nouvelle colonne) est ajoutée à la fin."""
    memorise = cfg.get("ordre_colonnes_tickets") or []
    ordre = [c for c in dict.fromkeys(memorise) if c in colonnes]
    return ordre + [c for c in colonnes if c not in ordre]


def deplacer_colonne(cfg: dict, nom: str, position: int) -> list[str]:
    """Place la colonne `nom` à la position `position` (1 = première) et enregistre l'ordre dans config.json."""
    colonnes = noms_colonnes_tickets(cfg)
    if nom not in colonnes:
        raise ConfigError(f"Colonne inconnue : {nom}")
    ordre = [c for c in ordre_colonnes(cfg, colonnes) if c != nom]
    position = max(1, min(int(position), len(ordre) + 1))
    ordre.insert(position - 1, nom)
    cfg["ordre_colonnes_tickets"] = ordre
    sauvegarder(cfg)
    return ordre


def reinitialiser_ordre_colonnes(cfg: dict) -> None:
    cfg.pop("ordre_colonnes_tickets", None)
    sauvegarder(cfg)


def definir_actif(cfg: dict, ident: str, actif: bool) -> None:
    for c in cfg["colonnes_perso"]:
        if c["id"] == ident:
            c["actif"] = actif
    sauvegarder(cfg)
