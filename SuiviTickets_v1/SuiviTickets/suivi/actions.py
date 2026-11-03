"""Application des modifications faites dans les tableaux éditables (fonctions pures, testables).

Streamlit fournit pour chaque tableau un « delta » : {"edited_rows": {position: {colonne: valeur}}, ...}
où `position` est la position de la ligne dans le tableau d'origine.
"""
from __future__ import annotations

from . import db
from .utils import en_date


def norm(v, type_: str):
    """Valeur normalisée d'une cellule de colonne perso (stockage JSON)."""
    from .utils import _nul
    if _nul(v):
        return None
    if type_ == "case":
        return True if v else None
    if type_ == "date":
        d = en_date(v)
        return d.isoformat() if d else None
    if type_ == "nombre":
        return float(v)
    s = str(v).strip()
    return s or None


def appliquer_edition_tickets(conn, cles: list[str], delta: dict, colonnes_par_nom: dict[str, dict]) -> int:
    """cles : clés des tickets dans l'ordre du tableau ; colonnes_par_nom : nom affiché -> définition de colonne perso."""
    n = 0
    for pos, changes in (delta or {}).get("edited_rows", {}).items():
        cle = cles[int(pos)]
        valeurs = {colonnes_par_nom[nom]["id"]: norm(val, colonnes_par_nom[nom]["type"])
                   for nom, val in changes.items() if nom in colonnes_par_nom}
        if valeurs:
            db.maj_suivi(conn, cle, valeurs)
            n += 1
    return n


def appliquer_edition_taches(conn, ids: list[int], delta: dict) -> tuple[int, int]:
    modifs = suppr = 0
    for pos, changes in (delta or {}).get("edited_rows", {}).items():
        tid = int(ids[int(pos)])
        if changes.get("Supprimer"):
            db.supprimer_tache(conn, tid)
            suppr += 1
            continue
        kw = {}
        if "Titre" in changes:
            kw["titre"] = changes["Titre"]
        if "Statut" in changes:
            kw["statut"] = changes["Statut"]
        if "Échéance" in changes:
            kw["echeance"] = en_date(changes["Échéance"])
            kw["maj_echeance"] = True
        if kw:
            db.maj_tache(conn, tid, **kw)
            modifs += 1
    return modifs, suppr


def appliquer_edition_temps(conn, ids: list[int], delta: dict) -> tuple[int, int]:
    modifs = suppr = 0
    for pos, changes in (delta or {}).get("edited_rows", {}).items():
        tid = int(ids[int(pos)])
        if changes.get("Supprimer"):
            db.supprimer_temps(conn, tid)
            suppr += 1
            continue
        minutes = changes.get("Durée (min)")
        note = changes.get("Note")
        if minutes is not None or note is not None:
            db.maj_temps(conn, tid, minutes=int(minutes) if minutes else None, note=note)
            modifs += 1
    return modifs, suppr
