"""Calculs statistiques (fonctions pures sur DataFrames, testables sans interface)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

PERIODES = ["Cette semaine", "Ce mois", "30 derniers jours", "90 derniers jours", "Cette année", "Tout"]


def bornes_periode(periode: str, aujourdhui: date | None = None) -> tuple[date | None, date | None]:
    j = aujourdhui or date.today()
    if periode == "Cette semaine":
        return j - timedelta(days=j.weekday()), j
    if periode == "Ce mois":
        return j.replace(day=1), j
    if periode == "30 derniers jours":
        return j - timedelta(days=29), j
    if periode == "90 derniers jours":
        return j - timedelta(days=89), j
    if periode == "Cette année":
        return j.replace(month=1, day=1), j
    return None, None


def filtrer_temps(temps: pd.DataFrame, debut: date | None, fin: date | None) -> pd.DataFrame:
    if temps.empty:
        return temps
    d = temps["debut"].dt.date
    masque = pd.Series(True, index=temps.index)
    if debut:
        masque &= d >= debut
    if fin:
        masque &= d <= fin
    return temps[masque]


def ajouter_application(temps: pd.DataFrame, tickets: pd.DataFrame, colonne: str = "perso_application") -> pd.DataFrame:
    t = temps.copy()
    if colonne in tickets.columns:
        t["application"] = t["cle"].map(tickets.set_index("cle")[colonne]).fillna("Non renseignée")
    else:
        t["application"] = "Non renseignée"
    t.loc[t["cle"].isna(), "application"] = "Hors ticket"
    return t


def kpis(tickets: pd.DataFrame, taches: pd.DataFrame, temps: pd.DataFrame, cfg: dict,
         maintenant: datetime | None = None) -> dict:
    maintenant = maintenant or datetime.now()
    j = maintenant.date()
    ouverts = tickets[tickets["ouvert"]] if not tickets.empty else tickets
    ordre = cfg.get("ordre_priorite_jira") or []
    top = ordre[0].casefold() if ordre else None
    seuil = int(cfg.get("jours_sans_maj_alerte", 14))
    lundi = j - timedelta(days=j.weekday())

    def somme(debut):
        t = filtrer_temps(temps, debut, j)
        return float(t["duree_s"].sum()) if not t.empty else 0.0

    ouvertes = taches[taches["statut"] != "Fait"] if not taches.empty else taches
    return {
        "tickets_ouverts": int(len(ouverts)),
        "tickets_bloquants": int((ouverts["priorite_jira"].fillna("").str.casefold() == top).sum()) if top and len(ouverts) else 0,
        "tickets_en_retard": int(ouverts["en_retard"].sum()) if len(ouverts) else 0,
        "tickets_dormants": int((ouverts["jours_sans_maj"] > seuil).sum()) if len(ouverts) else 0,
        "age_moyen_jours": float(ouverts["age_jours"].mean()) if len(ouverts) else 0.0,
        "taches_ouvertes": int(len(ouvertes)),
        "taches_en_retard": int((ouvertes["echeance"].notna() & (ouvertes["echeance"].dt.normalize() < pd.Timestamp(j))).sum()) if len(ouvertes) else 0,
        "temps_aujourdhui_s": somme(j),
        "temps_semaine_s": somme(lundi),
        "temps_mois_s": somme(j.replace(day=1)),
    }


def repartition(df: pd.DataFrame, colonne: str, vide: str = "Non renseigné") -> pd.DataFrame:
    if df.empty or colonne not in df.columns:
        return pd.DataFrame({colonne: [], "Tickets": []})
    s = df[colonne].fillna(vide).replace("", vide).astype(str)
    r = s.value_counts().rename_axis(colonne).reset_index(name="Tickets")
    return r


def anciennete(ouverts: pd.DataFrame) -> pd.DataFrame:
    tranches = ["0-7 j", "8-30 j", "31-90 j", "> 90 j"]
    if ouverts.empty:
        return pd.DataFrame({"Ancienneté": tranches, "Tickets": [0, 0, 0, 0]})
    a = ouverts["age_jours"].fillna(0)
    cat = pd.cut(a, bins=[-1, 7, 30, 90, 10**9], labels=tranches)
    n = cat.value_counts().reindex(tranches).fillna(0).astype(int)
    return pd.DataFrame({"Ancienneté": tranches, "Tickets": n.values})


def flux_mensuel(tickets: pd.DataFrame) -> pd.DataFrame:
    """Tickets créés (date Jira) et sortis de l'export (≈ clos) par mois."""
    if tickets.empty:
        return pd.DataFrame({"Mois": [], "Type": [], "Tickets": []})
    cree = tickets["cree"].dropna().dt.to_period("M").astype(str).value_counts().rename("Créés")
    sortis = tickets["date_sortie"].dropna().dt.to_period("M").astype(str).value_counts().rename("Sortis de l'export")
    f = pd.concat([cree, sortis], axis=1).fillna(0).astype(int).sort_index()
    f.index.name = "Mois"
    return f.reset_index().melt(id_vars="Mois", var_name="Type", value_name="Tickets")


def temps_par_semaine(temps: pd.DataFrame, par: str = "application") -> pd.DataFrame:
    if temps.empty:
        return pd.DataFrame({"Semaine": [], par: [], "Heures": []})
    t = temps.copy()
    t["Semaine"] = t["debut"].dt.to_period("W-SUN").apply(lambda p: p.start_time.strftime("%d/%m/%Y"))
    t["_tri"] = t["debut"].dt.to_period("W-SUN").apply(lambda p: p.start_time)
    g = t.groupby(["_tri", "Semaine", par])["duree_s"].sum().reset_index().sort_values("_tri")
    g["Heures"] = (g["duree_s"] / 3600).round(2)
    return g[["Semaine", par, "Heures"]]


def temps_par(temps: pd.DataFrame, colonne: str, limite: int | None = None) -> pd.DataFrame:
    if temps.empty:
        return pd.DataFrame({colonne: [], "Heures": []})
    g = temps.groupby(colonne, dropna=False)["duree_s"].sum().sort_values(ascending=False)
    if limite:
        g = g.head(limite)
    out = g.rename("Heures").reset_index()
    out["Heures"] = (out["Heures"] / 3600).round(2)
    out[colonne] = out[colonne].fillna("(sans ticket)")
    return out
