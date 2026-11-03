from __future__ import annotations

import logging
import logging.handlers
from datetime import date, datetime

import pandas as pd

from . import config

FMT_ISO = "%Y-%m-%d %H:%M:%S"


def maintenant_iso() -> str:
    return datetime.now().strftime(FMT_ISO)


def _nul(v) -> bool:
    try:
        return v is None or bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def fmt_duree(secondes) -> str:
    """12 min / 1 h 05."""
    s = 0 if _nul(secondes) else int(round(float(secondes)))
    h, m = divmod(s // 60, 60)
    return f"{h} h {m:02d}" if h else f"{m} min"


def fmt_hms(secondes) -> str:
    s = max(0, int(secondes))
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def heures(secondes) -> float:
    return round(0 if _nul(secondes) else float(secondes) / 3600, 2)


def en_date(v) -> date | None:
    if _nul(v):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return pd.to_datetime(v).date()
    except (ValueError, TypeError):
        return None


def logger(cfg: dict) -> logging.Logger:
    log = logging.getLogger("suivi_tickets")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    dossier = config.chemin(cfg, "dossier_logs")
    dossier.mkdir(parents=True, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(
        dossier / "suivi_tickets.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.addHandler(h)
    return log
