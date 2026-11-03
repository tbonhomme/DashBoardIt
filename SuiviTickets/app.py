"""Suivi des tickets - interface Streamlit.

Lancement : lancer.bat   (ou : .venv\\Scripts\\python.exe -m streamlit run app.py)
"""
from __future__ import annotations

import functools
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from suivi import __version__, actions, config, db, export_excel, importer, stats
from suivi.utils import _nul, en_date, fmt_duree, fmt_hms, heures, logger

st.set_page_config(page_title="Suivi des tickets", layout="wide", initial_sidebar_state="expanded")

LIBRE = "(tâche libre, sans ticket)"
SANS_TICKET = "(sans ticket)"


# =========================================================================== utilitaires UI
def flash(msg: str, niveau: str = "success") -> None:
    st.session_state.setdefault("_flash", []).append((niveau, msg))


def afficher_flash() -> None:
    for niveau, msg in st.session_state.pop("_flash", []):
        getattr(st, niveau)(msg)


def version(nom: str) -> int:
    return st.session_state.get(f"v_{nom}", 0)


def bump(nom: str) -> None:
    st.session_state[f"v_{nom}"] = version(nom) + 1


def securise(f):
    """Callback protégé : une erreur est journalisée et affichée, sans casser l'application."""
    @functools.wraps(f)
    def enveloppe(*args, **kwargs):
        try:
            f(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            flash(f"{type(e).__name__} : {e}", "error")
            try:
                logger(args[0]).exception("Erreur dans l'action %s", f.__name__)
            except Exception:  # noqa: BLE001
                pass
    return enveloppe


def vers_affichage(serie: pd.Series, type_: str) -> pd.Series:
    if type_ == "date":
        return serie.map(en_date)
    if type_ == "nombre":
        return pd.to_numeric(serie, errors="coerce")
    if type_ == "case":
        return serie.map(lambda v: False if _nul(v) else bool(v))
    return serie.map(lambda v: None if _nul(v) else str(v))


def config_colonne(col: dict, valeurs_existantes: list[str]):
    t = col["type"]
    if t == "liste":
        opts = list(dict.fromkeys(list(col.get("valeurs", [])) + [v for v in valeurs_existantes if v]))
        return st.column_config.SelectboxColumn(col["nom"], options=opts)
    if t == "date":
        return st.column_config.DateColumn(col["nom"], format="DD/MM/YYYY")
    if t == "nombre":
        return st.column_config.NumberColumn(col["nom"])
    if t == "case":
        return st.column_config.CheckboxColumn(col["nom"])
    if t == "lien":
        return st.column_config.LinkColumn(
            col["nom"], width="small", display_text="Ouvrir",
            help="Double-cliquez pour coller ou modifier l'adresse ; cliquez sur « Ouvrir » pour l'ouvrir.")
    return st.column_config.TextColumn(col["nom"], width="medium")


def graphique(df: pd.DataFrame, x: str, y: str, titre: str, couleur: str | None = None,
              horizontal: bool = False, barmode: str = "stack") -> None:
    if df.empty:
        st.caption(f"{titre} : pas de données.")
        return
    if horizontal:
        fig = px.bar(df, x=y, y=x, color=couleur, orientation="h", text_auto=True, title=titre)
        fig.update_yaxes(autorange="reversed")
    else:
        fig = px.bar(df, x=x, y=y, color=couleur, text_auto=True, title=titre, barmode=barmode)
        fig.update_xaxes(type="category")
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), legend_title_text="")
    st.plotly_chart(fig, width="stretch")


# =========================================================================== démarrage
def traiter_resultats(resultats: list[dict]) -> None:
    for r in resultats:
        if r["statut"] == "ok":
            flash(f"Import de {r['fichier']} : {r['message']}.")
        elif r["statut"] == "erreur":
            flash(f"Import de {r['fichier']} en erreur : {r['message']}", "error")
        for a in r.get("avertissements", []):
            flash(f"{r['fichier']} : {a}", "warning")


def demarrage(cfg: dict) -> None:
    if st.session_state.get("_demarre"):
        return
    st.session_state["_demarre"] = True
    try:
        if not db.sauvegarde_du_jour_existe(cfg):
            db.sauvegarder(cfg, "quotidienne")
        if cfg.get("import_auto_au_demarrage", True):
            res = importer.importer_depot(cfg)
            traiter_resultats(res)
            if cfg.get("export_auto_apres_import") and any(r["statut"] == "ok" for r in res):
                export_excel.exporter_excel(cfg)
    except Exception as e:  # noqa: BLE001
        flash(f"Démarrage : {type(e).__name__} : {e}", "warning")


# =========================================================================== chrono (barre latérale)
@st.fragment(run_every="1s")
def bandeau_chrono_actif(cfg: dict) -> None:
    """Affiche le temps écoulé en direct (seul ce fragment est rafraîchi chaque seconde)."""
    with db.connecter(cfg) as conn:
        actif = db.chrono_actif(conn)
    if not actif:
        return
    debut = datetime.strptime(actif["debut"], "%Y-%m-%d %H:%M:%S")
    st.metric("Chrono en cours", fmt_hms((datetime.now() - debut).total_seconds()))
    st.caption(f"{actif['cle'] or 'Sans ticket'}" + (f" - {actif['libelle']}" if actif["libelle"] else ""))


@securise
def cb_demarrer_chrono(cfg: dict, options: dict) -> None:
    choix = st.session_state.get("chrono_choix")
    if choix not in options:
        return
    cle, tid = options[choix]
    with db.connecter(cfg) as conn:
        db.demarrer_chrono(conn, cle, tid)
    st.session_state["chrono_choix"] = None
    bump("temps")
    bump("taches")


@securise
def cb_chrono_ticket(cfg: dict, cle: str) -> None:
    with db.connecter(cfg) as conn:
        db.demarrer_chrono(conn, cle, None)
    bump("temps")


@securise
def cb_arreter_chrono(cfg: dict) -> None:
    with db.connecter(cfg) as conn:
        db.arreter_chrono(conn)
    flash("Chrono arrêté.")
    bump("temps")


def barre_laterale(cfg: dict) -> None:
    with st.sidebar:
        st.title("Suivi des tickets")
        with db.connecter(cfg) as conn:
            actif = db.chrono_actif(conn)
            tickets = db.charger_tickets(conn, cfg)
            taches = db.charger_taches(conn)
        st.subheader("Chrono")
        if actif:
            bandeau_chrono_actif(cfg)
            st.button("Arrêter le chrono", key="btn_stop_chrono", type="primary", width="stretch",
                      on_click=cb_arreter_chrono, args=(cfg,))
        else:
            st.caption("Aucun chrono en cours.")
        options: dict[str, tuple[str | None, int | None]] = {}
        for _, t in taches[taches["statut"] != "Fait"].iterrows():
            options[f"Tâche · {t['cle'] or 'libre'} · {t['titre']}"] = (t["cle"], int(t["id"]))
        for _, t in tickets[tickets["ouvert"]].iterrows():
            options[f"Ticket · {t['cle']} · {str(t['resume'])[:60]}"] = (t["cle"], None)
        st.selectbox("Démarrer sur", list(options), index=None, placeholder="Tâche ou ticket...", key="chrono_choix")
        st.button("Démarrer le chrono", disabled=st.session_state.get("chrono_choix") is None, width="stretch",
                  on_click=cb_demarrer_chrono, args=(cfg, options))
        st.divider()
        st.caption(f"Version {__version__} · base : {config.chemin(cfg, 'base').name}")


# =========================================================================== éditeur de tâches
@securise
def cb_ajouter_taches(cfg: dict, cle_fixe: str | None, prefixe: str) -> None:
    cle = cle_fixe
    if cle_fixe is None:
        sel = st.session_state.get(f"tk_sel_{prefixe}")
        cle = None if sel in (None, LIBRE) else sel.split(" - ")[0]
    titres = (st.session_state.get(f"tk_txt_{prefixe}") or "").splitlines()
    with db.connecter(cfg) as conn:
        n = db.ajouter_taches(conn, cle, titres, st.session_state.get(f"tk_ech_{prefixe}"))
    flash(f"{n} tâche(s) ajoutée(s)." if n else "Aucune tâche saisie.", "success" if n else "warning")
    bump("taches")


def formulaire_taches(cfg: dict, cle_fixe: str | None, prefixe: str, tickets: pd.DataFrame) -> None:
    """Ajout d'une ou plusieurs tâches (une par ligne)."""
    with st.form(f"form_taches_{prefixe}", clear_on_submit=True):
        if cle_fixe is None:
            options = [LIBRE] + [f"{r.cle} - {str(r.resume)[:70]}" for r in tickets[tickets["ouvert"]].itertuples()]
            st.selectbox("Ticket", options, key=f"tk_sel_{prefixe}")
        st.text_area("Tâches à réaliser (une par ligne)", height=100, key=f"tk_txt_{prefixe}",
                     placeholder="Analyser le problème\nReproduire en recette\nCommuniquer au métier")
        st.date_input("Échéance (optionnelle)", value=None, format="DD/MM/YYYY", key=f"tk_ech_{prefixe}")
        st.form_submit_button("Ajouter", on_click=cb_ajouter_taches, args=(cfg, cle_fixe, prefixe))


@securise
def cb_enregistrer_taches(cfg: dict, ids: list[int], cle_editeur: str) -> None:
    with db.connecter(cfg) as conn:
        modifs, suppr = actions.appliquer_edition_taches(conn, ids, st.session_state.get(cle_editeur, {}))
    flash(f"{modifs} tâche(s) modifiée(s), {suppr} supprimée(s).")
    bump("taches")
    bump("temps")


def editeur_taches(cfg: dict, df: pd.DataFrame, prefixe: str) -> None:
    if df.empty:
        st.caption("Aucune tâche à afficher.")
        return
    df = df.set_index("id", drop=False)
    aff = pd.DataFrame({
        "Ticket": df["cle"].fillna("(libre)"),
        "Titre": df["titre"],
        "Statut": df["statut"],
        "Échéance": df["echeance"].map(en_date),
        "Temps passé": df["temps_s"].map(fmt_duree),
        "Supprimer": False,
    })
    cle_editeur = f"ed_taches_{prefixe}_{version('taches')}"
    st.data_editor(
        aff, key=cle_editeur, hide_index=True, width="stretch",
        disabled=["Ticket", "Temps passé"], num_rows="fixed",
        column_config={
            "Statut": st.column_config.SelectboxColumn("Statut", options=db.ETATS_TACHE, required=True),
            "Échéance": st.column_config.DateColumn("Échéance", format="DD/MM/YYYY"),
            "Titre": st.column_config.TextColumn("Titre", width="large", required=True),
            "Supprimer": st.column_config.CheckboxColumn("Supprimer"),
        })
    st.button("Enregistrer les tâches", key=f"btn_taches_{prefixe}", on_click=cb_enregistrer_taches,
              args=(cfg, [int(i) for i in aff.index], cle_editeur))


# =========================================================================== temps
@securise
def cb_ajouter_temps(cfg: dict, cle_fixe: str | None, prefixe: str, options_t: dict) -> None:
    if cle_fixe is not None:
        cle = cle_fixe
    else:
        sel = st.session_state.get(f"tps_tk_{prefixe}")
        cle = None if sel in (None, SANS_TICKET) else sel.split(" - ")[0]
    minutes = int(st.session_state.get(f"tps_m_{prefixe}", 30))
    with db.connecter(cfg) as conn:
        db.ajouter_temps_manuel(conn, cle, options_t.get(st.session_state.get(f"tps_ta_{prefixe}")),
                                st.session_state.get(f"tps_j_{prefixe}") or date.today(), minutes,
                                st.session_state.get(f"tps_n_{prefixe}") or None)
    flash(f"{minutes} min ajoutées.")
    bump("temps")


def formulaire_temps(cfg: dict, tickets: pd.DataFrame, taches: pd.DataFrame, cle_fixe: str | None,
                     prefixe: str) -> None:
    st.markdown("**Ajouter du temps manuellement**")
    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
    if cle_fixe is None:
        options = [SANS_TICKET] + [f"{r.cle} - {str(r.resume)[:60]}" for r in tickets[tickets["ouvert"]].itertuples()]
        choix = c1.selectbox("Ticket", options, key=f"tps_tk_{prefixe}")
        cle = None if choix == SANS_TICKET else choix.split(" - ")[0]
    else:
        cle = cle_fixe
        c1.text_input("Ticket", cle, disabled=True, key=f"tps_tk_{prefixe}")
    t = taches[(taches["cle"] == cle) & (taches["statut"] != "Fait")] if cle else taches[taches["cle"].isna()]
    options_t = {"(aucune tâche)": None} | {f"{r.titre}": int(r.id) for r in t.itertuples()}
    c2.selectbox("Tâche", list(options_t), key=f"tps_ta_{prefixe}")
    c3.date_input("Date", value=date.today(), format="DD/MM/YYYY", key=f"tps_j_{prefixe}")
    c4.number_input("Minutes", min_value=1, max_value=1440, value=30, step=5, key=f"tps_m_{prefixe}")
    st.text_input("Note (optionnelle)", key=f"tps_n_{prefixe}")
    st.button("Ajouter le temps", key=f"tps_b_{prefixe}", on_click=cb_ajouter_temps,
              args=(cfg, cle_fixe, prefixe, options_t))


@securise
def cb_enregistrer_temps(cfg: dict, ids: list[int], cle_editeur: str) -> None:
    with db.connecter(cfg) as conn:
        modifs, suppr = actions.appliquer_edition_temps(conn, ids, st.session_state.get(cle_editeur, {}))
    flash(f"{modifs} saisie(s) modifiée(s), {suppr} supprimée(s).")
    bump("temps")


def editeur_temps(cfg: dict, temps: pd.DataFrame, prefixe: str) -> None:
    if temps.empty:
        st.caption("Aucune saisie de temps sur cette sélection.")
        return
    t = temps.set_index("id", drop=False)
    aff = pd.DataFrame({
        "Date": t["debut"].dt.date,
        "Ticket": t["cle"].fillna(SANS_TICKET),
        "Tâche": t["tache"].fillna(""),
        "Durée (min)": (t["duree_s"] / 60).round().astype(int),
        "Source": t["source"].where(~t["en_cours"], "chrono (en cours)"),
        "Note": t["note"].fillna(""),
        "Supprimer": False,
    })
    cle_editeur = f"ed_temps_{prefixe}_{version('temps')}"
    st.data_editor(
        aff, key=cle_editeur, hide_index=True, width="stretch",
        disabled=["Date", "Ticket", "Tâche", "Source"],
        column_config={"Durée (min)": st.column_config.NumberColumn(min_value=1, step=1),
                       "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY")})
    st.button("Enregistrer les temps", key=f"btn_temps_{prefixe}", on_click=cb_enregistrer_temps,
              args=(cfg, [int(i) for i in aff.index], cle_editeur))


# =========================================================================== onglet Tickets
@securise
def cb_enregistrer_tickets(cfg: dict, cles: list[str], colonnes_par_nom: dict, cle_editeur: str) -> None:
    with db.connecter(cfg) as conn:
        n = actions.appliquer_edition_tickets(conn, cles, st.session_state.get(cle_editeur, {}), colonnes_par_nom)
    flash(f"{n} ticket(s) mis à jour." if n else "Aucune modification à enregistrer.", "success" if n else "info")
    bump("tickets")


def onglet_tickets(cfg: dict) -> None:
    with db.connecter(cfg) as conn:
        df = db.charger_tickets(conn, cfg)
        taches = db.charger_taches(conn)
        temps = db.charger_temps(conn)
    if df.empty:
        st.info(f"Aucun ticket pour l'instant. Déposez un export CSV Jira dans « {config.chemin(cfg, 'dossier_depot')} » "
                "puis ouvrez l'onglet Import / Export.")
        return

    cols_perso = config.colonnes_perso_actives(cfg)
    ordre = {p.casefold(): i for i, p in enumerate(cfg.get("ordre_priorite_jira", []))}

    f1, f2, f3, f4 = st.columns([2, 2, 2, 3])
    etats = f1.multiselect("État", sorted(df["etat"].dropna().unique()))
    types = f2.multiselect("Type", sorted(df["type"].dropna().unique()))
    prios = f3.multiselect("Priorité Jira", sorted(df["priorite_jira"].dropna().unique(),
                                                   key=lambda p: ordre.get(p.casefold(), 99)))
    recherche = f4.text_input("Recherche (clé, résumé, actions)")
    with st.expander("Plus de filtres"):
        g1, g2 = st.columns(2)
        filtres_perso = {}
        for i, c in enumerate(x for x in cols_perso if x["type"] == "liste"):
            vals = list(dict.fromkeys(c.get("valeurs", []) + [v for v in df[f"perso_{c['id']}"].dropna().unique()]))
            filtres_perso[c["id"]] = (g1 if i % 2 == 0 else g2).multiselect(c["nom"], vals, key=f"flt_{c['id']}")
        h1, h2, h3 = st.columns(3)
        inclure_absents = h1.checkbox("Inclure les tickets absents du dernier export / clos")
        seulement_retard = h2.checkbox("Échéance dépassée uniquement")
        seulement_dormants = h3.checkbox(f"Sans mise à jour depuis plus de {cfg.get('jours_sans_maj_alerte', 14)} j")

    d = df.copy()
    if not inclure_absents:
        d = d[d["ouvert"]]
    if etats:
        d = d[d["etat"].isin(etats)]
    if types:
        d = d[d["type"].isin(types)]
    if prios:
        d = d[d["priorite_jira"].isin(prios)]
    for cid, vals in filtres_perso.items():
        if vals:
            d = d[d[f"perso_{cid}"].isin(vals)]
    if seulement_retard:
        d = d[d["en_retard"]]
    if seulement_dormants:
        d = d[d["jours_sans_maj"] > int(cfg.get("jours_sans_maj_alerte", 14))]
    if recherche.strip():
        masque = d["cle"].str.contains(recherche, case=False, na=False) | d["resume"].str.contains(recherche, case=False, na=False)
        for c in cols_perso:
            if c["type"] == "texte":
                masque |= d[f"perso_{c['id']}"].fillna("").astype(str).str.contains(recherche, case=False, na=False)
        d = d[masque]

    d = d.assign(_p=d["priorite_jira"].fillna("").str.casefold().map(lambda p: ordre.get(p, 99)))
    d = d.sort_values(["_p", "echeance", "cle"], na_position="last").set_index("cle", drop=False)

    st.caption(f"{len(d)} ticket(s) affiché(s) sur {len(df)} en base. Les colonnes personnelles se modifient directement dans le tableau.")
    aff = pd.DataFrame({
        "Clé": d["cle"], "Résumé": d["resume"], "Type": d["type"], "État": d["etat"],
        "Priorité Jira": d["priorite_jira"],
    })
    noms_perso = []
    for c in cols_perso:
        nom = c["nom"] if c["nom"] not in aff.columns else f"{c['nom']} (perso)"
        aff[nom] = vers_affichage(d[f"perso_{c['id']}"], c["type"])
        noms_perso.append((c, nom))
    aff["Échéance"] = d["echeance"].map(en_date)
    aff["Mise à jour"] = d["maj"]
    aff["Tâches ouvertes"] = d["taches_ouvertes"]
    aff["Temps passé"] = d["temps_s"].map(fmt_duree)
    aff["Présence"] = d.apply(
        lambda r: "Actif" if r["ouvert"] else ("Clos" if not r["absent_export"] else
                                               f"Absent depuis le {r['date_sortie']:%d/%m/%Y}" if pd.notna(r["date_sortie"]) else "Absent"),
        axis=1)

    config_cols = {nom: config_colonne(c, [str(v) for v in d[f"perso_{c['id']}"].dropna().unique()]) for c, nom in noms_perso}
    config_cols.update({
        "Résumé": st.column_config.TextColumn("Résumé", width="large"),
        "Échéance": st.column_config.DateColumn("Échéance", format="DD/MM/YYYY"),
        "Mise à jour": st.column_config.DatetimeColumn("Mise à jour", format="DD/MM/YYYY HH:mm"),
    })
    cle_editeur = f"ed_tickets_{version('tickets')}"
    st.data_editor(
        aff, key=cle_editeur, hide_index=True, width="stretch", height=480,
        column_order=config.ordre_colonnes(cfg, list(aff.columns)),
        disabled=[c for c in aff.columns if c not in [n for _, n in noms_perso]], column_config=config_cols)
    st.button("Enregistrer les modifications", type="primary", key="btn_save_tickets", on_click=cb_enregistrer_tickets,
              args=(cfg, list(aff.index), {nom: c for c, nom in noms_perso}, cle_editeur))

    st.divider()
    resumes = dict(zip(d["cle"], d["resume"]))
    cle = st.selectbox("Ouvrir le détail d'un ticket", list(d["cle"]), index=None, key="detail_cle",
                       format_func=lambda c: f"{c} - {str(resumes[c])[:90]}", placeholder="Choisir un ticket...")
    if cle:
        detail_ticket(cfg, df, taches, temps, cle)


def detail_ticket(cfg: dict, df: pd.DataFrame, taches: pd.DataFrame, temps: pd.DataFrame, cle: str) -> None:
    t = df[df["cle"] == cle].iloc[0]
    st.subheader(f"{cle} - {t['resume']}")
    base = (cfg.get("jira_base_url") or "").strip()
    if base:
        st.markdown(f"[Ouvrir dans Jira]({base.rstrip('/')}/{cle})")
    m = st.columns(5)
    m[0].metric("État", t["etat"] or "-")
    m[1].metric("Priorité Jira", t["priorite_jira"] or "-")
    m[2].metric("Échéance", f"{t['echeance']:%d/%m/%Y}" if pd.notna(t["echeance"]) else "-")
    m[3].metric("Dernière mise à jour", f"{t['maj']:%d/%m/%Y}" if pd.notna(t["maj"]) else "-")
    m[4].metric("Temps passé", fmt_duree(t["temps_s"]))
    liens = [f"{lib} : {t[col]}" for lib, col in (("Bloqué par", "bloque_par"), ("Bloque", "bloque"), ("Lié à", "lies")) if t[col]]
    if liens:
        st.caption(" · ".join(liens))
    for col_lien in config.colonnes_perso_actives(cfg):          # colonnes de type « lien » : boutons cliquables
        if col_lien["type"] != "lien":
            continue
        url = t.get(f"perso_{col_lien['id']}")
        if _nul(url) or not str(url).strip():
            continue
        url = str(url).strip()
        if url.lower().startswith(("http://", "https://", "mailto:")):
            st.link_button(f"{col_lien['nom']} : ouvrir", url)
        else:
            st.caption(f"{col_lien['nom']} : {url}")

    sous = st.tabs(["Tâches du ticket", "Temps", "Historique Jira"])
    with sous[0]:
        editeur_taches(cfg, taches[taches["cle"] == cle], f"det_{cle}")
        formulaire_taches(cfg, cle, f"det_{cle}", df)
    with sous[1]:
        st.button("Démarrer un chrono sur ce ticket", key=f"chrono_{cle}", on_click=cb_chrono_ticket, args=(cfg, cle))
        formulaire_temps(cfg, df, taches, cle, f"det_{cle}")
        editeur_temps(cfg, temps[temps["cle"] == cle], f"det_{cle}")
    with sous[2]:
        with db.connecter(cfg) as conn:
            h = db.charger_historique(conn, cle)
        if h.empty:
            st.caption("Aucun changement enregistré depuis le premier import.")
        else:
            st.dataframe(h.rename(columns={"date": "Date", "champ": "Champ", "ancienne": "Avant", "nouvelle": "Après"}),
                         hide_index=True, width="stretch")


# =========================================================================== onglet To-do list
def onglet_todo(cfg: dict) -> None:
    with db.connecter(cfg) as conn:
        tickets = db.charger_tickets(conn, cfg)
        taches = db.charger_taches(conn)
    with st.expander("Ajouter des tâches", expanded=taches.empty):
        formulaire_taches(cfg, None, "todo", tickets)

    c1, c2, c3 = st.columns([2, 2, 3])
    statuts = c1.multiselect("Statut", db.ETATS_TACHE, default=["À faire", "En cours"])
    echeance = c2.selectbox("Échéance", ["Toutes", "En retard", "Aujourd'hui", "7 prochains jours", "Sans échéance"])
    cles = sorted(taches["cle"].dropna().unique())
    filtre_ticket = c3.selectbox("Ticket", ["(tous)", "(tâches libres)"] + cles)

    d = taches.copy()
    if statuts:
        d = d[d["statut"].isin(statuts)]
    j = pd.Timestamp(date.today())
    if echeance == "En retard":
        d = d[d["echeance"].notna() & (d["echeance"] < j) & (d["statut"] != "Fait")]
    elif echeance == "Aujourd'hui":
        d = d[d["echeance"] == j]
    elif echeance == "7 prochains jours":
        d = d[d["echeance"].between(j, j + pd.Timedelta(days=7))]
    elif echeance == "Sans échéance":
        d = d[d["echeance"].isna()]
    if filtre_ticket == "(tâches libres)":
        d = d[d["cle"].isna()]
    elif filtre_ticket != "(tous)":
        d = d[d["cle"] == filtre_ticket]
    d = d.sort_values(["echeance", "id"], na_position="last")

    ouvertes = taches[taches["statut"] != "Fait"]
    m = st.columns(4)
    m[0].metric("À faire / en cours", len(ouvertes))
    m[1].metric("En retard", int((ouvertes["echeance"].notna() & (ouvertes["echeance"] < j)).sum()))
    m[2].metric("Terminées", int((taches["statut"] == "Fait").sum()))
    m[3].metric("Temps sur les tâches affichées", fmt_duree(d["temps_s"].sum()))
    editeur_taches(cfg, d, "todo")


# =========================================================================== onglet Temps
def onglet_temps(cfg: dict) -> None:
    with db.connecter(cfg) as conn:
        tickets = db.charger_tickets(conn, cfg)
        taches = db.charger_taches(conn)
        temps = db.charger_temps(conn)
    k = stats.kpis(tickets, taches, temps, cfg)
    m = st.columns(3)
    m[0].metric("Aujourd'hui", fmt_duree(k["temps_aujourdhui_s"]))
    m[1].metric("Cette semaine", fmt_duree(k["temps_semaine_s"]))
    m[2].metric("Ce mois", fmt_duree(k["temps_mois_s"]))

    with st.expander("Ajouter du temps manuellement", expanded=False):
        formulaire_temps(cfg, tickets, taches, None, "global")

    c1, c2 = st.columns([2, 3])
    periode = c1.selectbox("Période", stats.PERIODES, index=2, key="tps_periode")
    cles = sorted(temps["cle"].dropna().unique())
    ticket = c2.selectbox("Ticket", ["(tous)"] + cles, key="tps_ticket")
    debut, fin = stats.bornes_periode(periode)
    t = stats.filtrer_temps(temps, debut, fin)
    if ticket != "(tous)":
        t = t[t["cle"] == ticket]
    st.caption(f"Total sur la sélection : {fmt_duree(t['duree_s'].sum())}")

    a, b = st.columns(2)
    with a:
        st.markdown("**Par ticket**")
        par_ticket = t.groupby(t["cle"].fillna(SANS_TICKET)).agg(Résumé=("resume", "first"), duree=("duree_s", "sum")) \
            .sort_values("duree", ascending=False)
        par_ticket["Temps"] = par_ticket["duree"].map(fmt_duree)
        par_ticket["Heures"] = par_ticket["duree"].map(heures)
        st.dataframe(par_ticket[["Résumé", "Temps", "Heures"]], width="stretch")
    with b:
        st.markdown("**Par tâche**")
        par_tache = t.groupby([t["cle"].fillna(SANS_TICKET), t["tache"].fillna("(sans tâche)")])["duree_s"].sum() \
            .sort_values(ascending=False).reset_index()
        par_tache.columns = ["Ticket", "Tâche", "duree"]
        par_tache["Temps"] = par_tache["duree"].map(fmt_duree)
        par_tache["Heures"] = par_tache["duree"].map(heures)
        st.dataframe(par_tache[["Ticket", "Tâche", "Temps", "Heures"]], hide_index=True, width="stretch")

    st.markdown("**Saisies détaillées**")
    editeur_temps(cfg, t, "global")


# =========================================================================== onglet Statistiques
def onglet_stats(cfg: dict) -> None:
    with db.connecter(cfg) as conn:
        tickets = db.charger_tickets(conn, cfg)
        taches = db.charger_taches(conn)
        temps = db.charger_temps(conn)
    if tickets.empty:
        st.info("Les statistiques apparaîtront après le premier import.")
        return
    k = stats.kpis(tickets, taches, temps, cfg)
    ouverts = tickets[tickets["ouvert"]]
    seuil = int(cfg.get("jours_sans_maj_alerte", 14))

    r1 = st.columns(5)
    r1[0].metric("Tickets ouverts", k["tickets_ouverts"])
    r1[1].metric("Bloquants", k["tickets_bloquants"])
    r1[2].metric("Échéance dépassée", k["tickets_en_retard"])
    r1[3].metric(f"Sans MAJ > {seuil} j", k["tickets_dormants"])
    r1[4].metric("Ancienneté moyenne", f"{k['age_moyen_jours']:.0f} j")
    r2 = st.columns(5)
    r2[0].metric("Tâches ouvertes", k["taches_ouvertes"])
    r2[1].metric("Tâches en retard", k["taches_en_retard"])
    r2[2].metric("Temps aujourd'hui", fmt_duree(k["temps_aujourdhui_s"]))
    r2[3].metric("Temps cette semaine", fmt_duree(k["temps_semaine_s"]))
    r2[4].metric("Temps ce mois", fmt_duree(k["temps_mois_s"]))

    st.subheader("Tickets ouverts")
    a, b, c = st.columns(3)
    with a:
        graphique(stats.repartition(ouverts, "etat"), "etat", "Tickets", "Par état", horizontal=True)
    with b:
        ordre = {p.casefold(): i for i, p in enumerate(cfg.get("ordre_priorite_jira", []))}
        rp = stats.repartition(ouverts, "priorite_jira")
        rp = rp.assign(_o=rp["priorite_jira"].str.casefold().map(lambda p: ordre.get(p, 99))).sort_values("_o")
        graphique(rp, "priorite_jira", "Tickets", "Par priorité Jira")
    with c:
        graphique(stats.repartition(ouverts, "type"), "type", "Tickets", "Par type", horizontal=True)

    d, e, f = st.columns(3)
    with d:
        listes = [x for x in config.colonnes_perso_actives(cfg) if x["type"] == "liste"]
        if listes:
            choix = st.selectbox("Répartition par colonne perso", [x["nom"] for x in listes], key="stat_perso")
            col = next(x for x in listes if x["nom"] == choix)
            graphique(stats.repartition(ouverts, f"perso_{col['id']}"), f"perso_{col['id']}", "Tickets", f"Par {choix}")
    with e:
        graphique(stats.anciennete(ouverts), "Ancienneté", "Tickets", "Ancienneté des tickets ouverts")
    with f:
        graphique(stats.repartition(ouverts, "rapporteur").head(10), "rapporteur", "Tickets", "Top 10 demandeurs", horizontal=True)

    graphique(stats.flux_mensuel(tickets), "Mois", "Tickets", "Tickets créés / sortis de l'export par mois",
              couleur="Type", barmode="group")

    st.subheader("Temps passé")
    periode = st.selectbox("Période", stats.PERIODES, index=2, key="stat_periode")
    debut, fin = stats.bornes_periode(periode)
    t = stats.ajouter_application(stats.filtrer_temps(temps, debut, fin), tickets)
    st.caption(f"Total sur la période : {fmt_duree(t['duree_s'].sum())}")
    g, h = st.columns(2)
    with g:
        graphique(stats.temps_par_semaine(t, "application"), "Semaine", "Heures", "Heures par semaine", couleur="application")
    with h:
        graphique(stats.temps_par(t, "application"), "application", "Heures", "Heures par application")
    i, j = st.columns(2)
    with i:
        graphique(stats.temps_par(t, "cle", 10), "cle", "Heures", "Top 10 tickets par temps passé", horizontal=True)
    with j:
        graphique(stats.temps_par(t, "tache", 10), "tache", "Heures", "Top 10 tâches par temps passé", horizontal=True)

    st.subheader("Points d'attention")
    x, y = st.columns(2)
    with x:
        st.markdown("**Échéance dépassée**")
        r = ouverts[ouverts["en_retard"]][["cle", "resume", "echeance", "priorite_jira"]].sort_values("echeance")
        st.dataframe(r.rename(columns={"cle": "Clé", "resume": "Résumé", "echeance": "Échéance", "priorite_jira": "Priorité Jira"}),
                     hide_index=True, width="stretch", column_config={"Échéance": st.column_config.DateColumn(format="DD/MM/YYYY")})
    with y:
        st.markdown(f"**Sans mise à jour depuis plus de {seuil} jours**")
        r = ouverts[ouverts["jours_sans_maj"] > seuil][["cle", "resume", "jours_sans_maj", "etat"]].sort_values("jours_sans_maj", ascending=False)
        st.dataframe(r.rename(columns={"cle": "Clé", "resume": "Résumé", "jours_sans_maj": "Jours", "etat": "État"}),
                     hide_index=True, width="stretch")


# =========================================================================== onglet Import / Export
@securise
def cb_importer(cfg: dict) -> None:
    res = importer.importer_depot(cfg)
    traiter_resultats(res)
    if cfg.get("export_auto_apres_import") and any(r["statut"] == "ok" for r in res):
        try:
            export_excel.exporter_excel(cfg)
        except Exception as e:  # noqa: BLE001
            flash(f"Export Excel : {e}", "error")
    bump("tickets")


@securise
def cb_charger_csv(cfg: dict) -> None:
    envoi = st.session_state.get(f"upload_{version('upload')}")
    if envoi is None:
        return
    depot = config.chemin(cfg, "dossier_depot")
    depot.mkdir(parents=True, exist_ok=True)
    (depot / Path(envoi.name).name).write_bytes(envoi.getvalue())
    cb_importer(cfg)
    bump("upload")


@securise
def cb_exporter(cfg: dict) -> None:
    try:
        flash(f"Export écrit : {export_excel.exporter_excel(cfg)}")
    except Exception as e:  # noqa: BLE001
        flash(str(e), "error")


def onglet_import(cfg: dict) -> None:
    depot = config.chemin(cfg, "dossier_depot")
    en_attente = importer.fichiers_en_attente(cfg)
    st.markdown(f"**Dossier de dépôt :** `{depot}`")
    st.caption("Déposez ici l'export CSV Jira : il est importé au lancement de l'application, ou avec le bouton ci-dessous. "
               "Vos priorités, actions, tâches et temps ne sont jamais écrasés.")
    st.write(f"{len(en_attente)} fichier(s) en attente : " + (", ".join(p.name for p in en_attente) if en_attente else "aucun"))

    c1, c2 = st.columns(2)
    c1.button("Importer maintenant", type="primary", disabled=not en_attente, on_click=cb_importer, args=(cfg,))
    c2.file_uploader("Ou charger un export CSV ici", type=["csv"], key=f"upload_{version('upload')}",
                     on_change=cb_charger_csv, args=(cfg,))

    st.divider()
    st.subheader("Export Excel (pour OneDrive / Office 365)")
    cible = config.chemin(cfg, "dossier_export") / cfg.get("nom_export", "Suivi_Tickets.xlsx")
    st.caption(f"Fichier généré : `{cible}`. Pour le consulter depuis Office 365, placez le dossier d'export dans "
               "OneDrive (clé « dossier_export » de config.json).")
    st.button("Générer l'export Excel", on_click=cb_exporter, args=(cfg,))
    if cible.exists():
        st.download_button("Télécharger le dernier export", cible.read_bytes(), file_name=cible.name,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.divider()
    st.subheader("Historique des imports")
    with db.connecter(cfg) as conn:
        h = db.charger_imports(conn)
    if h.empty:
        st.caption("Aucun import pour l'instant.")
    else:
        st.dataframe(h[["date_import", "fichier", "statut", "nb_total", "nb_nouveaux", "nb_maj", "nb_absents", "message"]]
                     .rename(columns={"date_import": "Date", "fichier": "Fichier", "statut": "Statut", "nb_total": "Tickets",
                                      "nb_nouveaux": "Nouveaux", "nb_maj": "Mis à jour", "nb_absents": "Absents",
                                      "message": "Détail"}), hide_index=True, width="stretch")


# =========================================================================== onglet Paramètres
@securise
def cb_actif_colonne(cfg: dict, ident: str) -> None:
    config.definir_actif(cfg, ident, bool(st.session_state.get(f"actif_{ident}")))
    bump("tickets")


@securise
def cb_ajouter_colonne(cfg: dict) -> None:
    nom = st.session_state.get("col_nom", "")
    try:
        config.ajouter_colonne(cfg, nom, st.session_state.get("col_type", "texte"),
                               (st.session_state.get("col_vals") or "").split(";"))
        flash(f"Colonne « {nom.strip()} » ajoutée.")
        bump("tickets")
    except config.ConfigError as e:
        flash(str(e), "error")


@securise
def cb_sauvegarde(cfg: dict) -> None:
    p = db.sauvegarder(cfg, "manuelle")
    flash(f"Sauvegarde créée : {p.name}" if p else "Aucune base à sauvegarder.")


@securise
def cb_deplacer_colonne(cfg: dict) -> None:
    nom = st.session_state.get("ord_col")
    position = int(st.session_state.get("ord_pos") or 1)
    try:
        config.deplacer_colonne(cfg, nom, position)
        flash(f"Colonne « {nom} » placée en position {position}.")
        bump("tickets")
    except config.ConfigError as e:
        flash(str(e), "error")


@securise
def cb_reinitialiser_ordre(cfg: dict) -> None:
    config.reinitialiser_ordre_colonnes(cfg)
    flash("Ordre des colonnes remis par défaut.")
    bump("tickets")


def section_ordre_colonnes(cfg: dict) -> None:
    st.subheader("Ordre des colonnes du tableau Tickets")
    ordre = config.ordre_colonnes(cfg, config.noms_colonnes_tickets(cfg))
    st.caption("Ordre actuel : " + " | ".join(f"{i}. {n}" for i, n in enumerate(ordre, start=1)))
    if st.session_state.get("ord_col") not in ordre:
        st.session_state.pop("ord_col", None)
    if st.session_state.get("ord_pos", 1) > len(ordre):
        st.session_state["ord_pos"] = len(ordre)
    c1, c2, c3 = st.columns([3, 1, 2])
    c1.selectbox("Colonne à déplacer", ordre, key="ord_col")
    c2.number_input("Position", min_value=1, max_value=len(ordre), value=min(2, len(ordre)), step=1, key="ord_pos")
    c3.button("Déplacer la colonne", on_click=cb_deplacer_colonne, args=(cfg,))
    st.button("Remettre l'ordre par défaut", on_click=cb_reinitialiser_ordre, args=(cfg,))


def onglet_params(cfg: dict) -> None:
    st.subheader("Colonnes personnelles")
    st.caption("Ajoutez une colonne ici : elle apparaît aussitôt dans le tableau des tickets, l'export Excel et les filtres. "
               "Une colonne masquée conserve ses données.")
    for col in cfg["colonnes_perso"]:
        libelle = f"{col['nom']} ({col['type']})" + (f" : {', '.join(col.get('valeurs', []))}" if col["type"] == "liste" else "")
        st.checkbox(libelle, value=col.get("actif", True), key=f"actif_{col['id']}",
                    on_change=cb_actif_colonne, args=(cfg, col["id"]))
    with st.form("form_colonne", clear_on_submit=True):
        c1, c2 = st.columns(2)
        c1.text_input("Nom de la nouvelle colonne", key="col_nom")
        c2.selectbox("Type", config.TYPES_COLONNE, key="col_type", help="texte, liste (choix), date, nombre, case à cocher, lien (adresse web)")
        st.text_input("Valeurs possibles (type liste, séparées par des points-virgules)", key="col_vals")
        st.form_submit_button("Ajouter la colonne", on_click=cb_ajouter_colonne, args=(cfg,))

    st.divider()
    section_ordre_colonnes(cfg)
    st.divider()
    st.subheader("Sauvegardes")
    st.caption(f"Une sauvegarde est faite chaque jour au premier lancement et avant chaque import "
               f"({cfg['nb_sauvegardes_conservees']} conservées) dans `{config.chemin(cfg, 'dossier_sauvegardes')}`.")
    st.button("Créer une sauvegarde maintenant", on_click=cb_sauvegarde, args=(cfg,))
    dossier = config.chemin(cfg, "dossier_sauvegardes")
    recentes = sorted(dossier.glob("*.db"), reverse=True)[:5] if dossier.exists() else []
    for p in recentes:
        st.write(f"- {p.name} ({p.stat().st_size / 1024:.0f} Ko)")

    st.divider()
    st.subheader("Emplacements")
    st.write({k: str(config.chemin(cfg, k)) for k in ("base", "dossier_depot", "dossier_archive", "dossier_export",
                                                      "dossier_sauvegardes", "dossier_logs")})
    st.caption(f"Configuration : `{cfg['_chemin_config']}` (modifiable avec un éditeur de texte, puis rechargez la page).")


# =========================================================================== logo
def afficher_logo() -> None:
    """Logo centré en haut de la page (assets/logo.png). Rien n'est affiché si le fichier est absent."""
    chemin = Path(__file__).resolve().parent / "assets" / "logo.png"
    if not chemin.exists():
        return
    try:
        _, milieu, _ = st.columns([2, 1, 2])          # colonne centrale = logo centré
        try:
            milieu.image(str(chemin), width="stretch")
        except TypeError:                              # anciennes versions de Streamlit
            milieu.image(str(chemin), use_container_width=True)
    except Exception:  # noqa: BLE001 - un souci d'image ne doit jamais bloquer l'application
        pass


# =========================================================================== main
def main() -> None:
    try:
        cfg = config.charger()
    except config.ConfigError as e:
        st.error(str(e))
        st.stop()
    db.initialiser(cfg)
    demarrage(cfg)
    barre_laterale(cfg)
    afficher_logo()
    afficher_flash()

    tabs = st.tabs(["Tickets", "To-do list", "Temps", "Statistiques", "Import / Export", "Paramètres"])
    for tab, fonction in zip(tabs, (onglet_tickets, onglet_todo, onglet_temps, onglet_stats, onglet_import, onglet_params)):
        with tab:
            try:
                fonction(cfg)
            except Exception as e:  # noqa: BLE001
                st.error(f"Erreur dans cet onglet : {type(e).__name__} : {e}")
                logger(cfg).exception("Erreur d'onglet %s", fonction.__name__)


main()
