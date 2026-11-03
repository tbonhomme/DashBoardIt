"""Export Excel (déposable dans OneDrive pour consultation depuis Office 365)."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config, db, stats
from .utils import heures, logger


def _tickets_export(tickets: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    cols_perso = config.colonnes_perso_actives(cfg)
    out = pd.DataFrame({
        "Clé": tickets["cle"], "Résumé": tickets["resume"], "Type": tickets["type"], "État": tickets["etat"],
        "Priorité Jira": tickets["priorite_jira"],
    })
    for c in cols_perso:
        out[c["nom"] if c["nom"] not in out.columns else f"{c['nom']} (perso)"] = tickets[f"perso_{c['id']}"]
    out["Échéance"] = tickets["echeance"].dt.date
    out["Créé le"] = tickets["cree"].dt.date
    out["Mis à jour le"] = tickets["maj"].dt.date
    out["Rapporteur"] = tickets["rapporteur"]
    out["Tâches ouvertes"] = tickets["taches_ouvertes"]
    out["Temps passé (h)"] = tickets["temps_s"].map(heures)
    out["Dans le dernier export"] = tickets["absent_export"].map({0: "Oui", 1: "Non"})
    out["Sorti de l'export le"] = tickets["date_sortie"].dt.date
    return out


def _ecrire(writer, nom: str, df: pd.DataFrame, largeurs: dict | None = None) -> None:
    df.to_excel(writer, sheet_name=nom, index=False)
    ws = writer.sheets[nom]
    wb = writer.book
    entete = wb.add_format({"bold": True, "bg_color": "#1F4E79", "font_color": "white", "border": 1})
    for i, c in enumerate(df.columns):
        ws.write(0, i, c, entete)
        mx = max([len(str(c))] + [len(str(v)) for v in df[c].head(200)]) if len(df) else len(str(c))
        ws.set_column(i, i, min(max(10, mx + 2), (largeurs or {}).get(c, 60)))
    ws.freeze_panes(1, 0)
    if len(df.columns):
        ws.autofilter(0, 0, max(len(df), 1), len(df.columns) - 1)


def exporter_excel(cfg: dict, maintenant: datetime | None = None) -> Path:
    maintenant = maintenant or datetime.now()
    dossier = config.chemin(cfg, "dossier_export")
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / cfg.get("nom_export", "Suivi_Tickets.xlsx")
    tmp = cible.with_suffix(".tmp.xlsx")

    with db.connecter(cfg) as conn:
        tickets = db.charger_tickets(conn, cfg, maintenant)
        taches = db.charger_taches(conn, maintenant)
        temps = db.charger_temps(conn, maintenant)

    t_tickets = _tickets_export(tickets, cfg)
    t_taches = pd.DataFrame({
        "Ticket": taches["cle"].fillna("(libre)"), "Résumé du ticket": taches["resume"], "Tâche": taches["titre"],
        "Statut": taches["statut"], "Échéance": taches["echeance"].dt.date, "Créée le": taches["cree"].dt.date,
        "Terminée le": taches["termine"].dt.date, "Temps passé (h)": taches["temps_s"].map(heures),
    })
    t_temps = pd.DataFrame({
        "Date": temps["debut"].dt.date, "Ticket": temps["cle"].fillna("(sans ticket)"), "Résumé": temps["resume"],
        "Tâche": temps["tache"], "Durée (h)": temps["duree_s"].map(heures),
        "Durée (min)": (temps["duree_s"] / 60).round(0), "Source": temps["source"], "Note": temps["note"],
    })

    k = stats.kpis(tickets, taches, temps, cfg, maintenant)
    t_kpi = pd.DataFrame([
        ("Généré le", maintenant.strftime("%d/%m/%Y %H:%M")),
        ("Tickets ouverts", k["tickets_ouverts"]), ("Tickets bloquants", k["tickets_bloquants"]),
        ("Tickets en retard (échéance)", k["tickets_en_retard"]),
        (f"Tickets sans mise à jour depuis > {cfg.get('jours_sans_maj_alerte', 14)} j", k["tickets_dormants"]),
        ("Ancienneté moyenne (jours)", round(k["age_moyen_jours"], 1)),
        ("Tâches ouvertes", k["taches_ouvertes"]), ("Tâches en retard", k["taches_en_retard"]),
        ("Temps aujourd'hui (h)", heures(k["temps_aujourdhui_s"])),
        ("Temps cette semaine (h)", heures(k["temps_semaine_s"])),
        ("Temps ce mois (h)", heures(k["temps_mois_s"])),
    ], columns=["Indicateur", "Valeur"])

    ouverts = tickets[tickets["ouvert"]]
    temps_app = stats.ajouter_application(temps, tickets)
    par_etat = stats.repartition(ouverts, "etat").rename(columns={"etat": "État"})
    par_type = stats.repartition(ouverts, "type").rename(columns={"type": "Type"})
    par_prio = stats.repartition(ouverts, "priorite_jira").rename(columns={"priorite_jira": "Priorité Jira"})
    par_semaine = stats.temps_par_semaine(temps_app, "application")
    par_ticket = stats.temps_par(temps, "cle", 15).rename(columns={"cle": "Ticket"})

    try:
        with pd.ExcelWriter(tmp, engine="xlsxwriter", datetime_format="dd/mm/yyyy hh:mm", date_format="dd/mm/yyyy") as w:
            _ecrire(w, "Tickets", t_tickets, {"Résumé": 70})
            _ecrire(w, "Tâches", t_taches)
            _ecrire(w, "Temps", t_temps)

            wb = w.book
            ws = wb.add_worksheet("Statistiques")
            w.sheets["Statistiques"] = ws
            gras = wb.add_format({"bold": True, "font_size": 12})
            ligne = 0
            ws.write(ligne, 0, "Indicateurs", gras)
            t_kpi.to_excel(w, sheet_name="Statistiques", startrow=ligne + 1, index=False)
            ligne += len(t_kpi) + 4
            positions = {}
            for titre, tab in (("Tickets ouverts par état", par_etat), ("Tickets ouverts par type", par_type),
                               ("Tickets ouverts par priorité Jira", par_prio), ("Temps par semaine et application (h)", par_semaine),
                               ("Top 15 tickets par temps passé (h)", par_ticket)):
                ws.write(ligne, 0, titre, gras)
                tab.to_excel(w, sheet_name="Statistiques", startrow=ligne + 1, index=False)
                positions[titre] = (ligne + 1, len(tab))
                ligne += len(tab) + 4
            ws.set_column(0, 0, 48)
            ws.set_column(1, 3, 18)

            def graphique(titre, type_, col_cat, col_val, anchor):
                if titre not in positions or positions[titre][1] == 0:
                    return
                debut, n = positions[titre]
                g = wb.add_chart({"type": type_})
                g.add_series({
                    "name": titre,
                    "categories": ["Statistiques", debut + 1, col_cat, debut + n, col_cat],
                    "values": ["Statistiques", debut + 1, col_val, debut + n, col_val],
                })
                g.set_title({"name": titre})
                g.set_legend({"none": True})
                g.set_size({"width": 480, "height": 280})
                ws.insert_chart(anchor, g)

            graphique("Tickets ouverts par état", "column", 0, 1, "F2")
            graphique("Top 15 tickets par temps passé (h)", "bar", 0, 1, "F18")
        os.replace(tmp, cible)
    except PermissionError as e:
        tmp.unlink(missing_ok=True)
        raise PermissionError(
            f"Impossible d'écrire {cible.name} : le fichier est probablement ouvert dans Excel. Fermez-le puis réessayez."
        ) from e
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    logger(cfg).info("Export Excel écrit : %s", cible)
    return cible
