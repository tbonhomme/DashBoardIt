"""Tests sans interface : import, fusion, conservation des données perso, temps, sauvegarde, export."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from suivi import config, db, export_excel, importer, stats

ENTETE = ("Type de ticket,Clé de ticket,ID de ticket,Résumé,Personne assignée,Rapporteur,Priorité,État,Résolution,"
          "Création,Mise à jour,Date d'échéance,Champs personnalisés (Request Type),"
          "Lien du ticket entrant (Bloquer),Lien du ticket entrant (Bloquer),Lien de ticket sortant (Lier),Créateur\n")


def ligne(cle, resume="Export BL AX", etat="En cours", prio="Majeur", maj="02/11/2026 16:55",
          ech="", bloque1="", bloque2="", lie=""):
    return (f"Incident,{cle},1{cle[-4:]},{resume},Thomas,Marie,{prio},{etat},,01/10/2026 10:00,{maj},{ech},"
            f"Signaler,{bloque1},{bloque2},{lie},Marie\n")


@pytest.fixture
def cfg(tmp_path):
    c = config.charger(tmp_path / "config.json")
    db.initialiser(c)
    return c


def deposer(cfg, nom, *lignes, entete=ENTETE, encoding="utf-8-sig"):
    d = config.chemin(cfg, "dossier_depot")
    d.mkdir(parents=True, exist_ok=True)
    p = d / nom
    p.write_text(entete + "".join(lignes), encoding=encoding)
    return p


def test_import_initial_et_colonnes(cfg):
    deposer(cfg, "a.csv",
            ligne("SUP-1001", "Export BL AX", bloque1="SUP-1", bloque2="SUP-2", lie="SUP-3", ech="31/12/2026 00:00"),
            ligne("SUP-1002", "NAIA - Décompte", etat="En attente", prio="Mineur"))
    res = importer.importer_depot(cfg)
    assert [r["statut"] for r in res] == ["ok"] and res[0]["nouveaux"] == 2
    with db.connecter(cfg) as conn:
        t = {r["cle"]: dict(r) for r in conn.execute("SELECT * FROM tickets")}
        assert t["SUP-1001"]["bloque_par"] == "SUP-1, SUP-2"       # colonnes dupliquées fusionnées
        assert t["SUP-1001"]["lies"] == "SUP-3"
        assert t["SUP-1001"]["echeance"] == "2026-12-31 00:00:00"  # jj/mm/aaaa -> ISO
        assert db.lire_suivi(conn, "SUP-1001")["application"] == "AX"      # détection auto
        assert db.lire_suivi(conn, "SUP-1002")["application"] == "NAIA"


def test_merge_conserve_donnees_perso_et_historise(cfg):
    deposer(cfg, "a.csv", ligne("SUP-1001"), ligne("SUP-1002"))
    importer.importer_depot(cfg)
    with db.connecter(cfg) as conn:
        db.maj_suivi(conn, "SUP-1001", {"priorite_perso": "1 - Urgent", "action_a_faire": "Appeler le métier"})
        db.ajouter_taches(conn, "SUP-1001", ["Analyser", "Tester"])
        db.ajouter_temps_manuel(conn, "SUP-1001", None, date.today(), 90)
    deposer(cfg, "b.csv", ligne("SUP-1001", etat="Travaux Externes en cours", maj="03/11/2026 09:00"),
            ligne("SUP-1003", "Nouveau"))
    res = importer.importer_depot(cfg)[0]
    assert (res["nouveaux"], res["mises_a_jour"], res["absents"]) == (1, 1, 1)
    with db.connecter(cfg) as conn:
        assert db.lire_suivi(conn, "SUP-1001")["priorite_perso"] == "1 - Urgent"
        assert conn.execute("SELECT COUNT(*) FROM taches WHERE cle='SUP-1001'").fetchone()[0] == 2
        assert conn.execute("SELECT SUM(duree_s) FROM temps WHERE cle='SUP-1001'").fetchone()[0] == 5400
        r = conn.execute("SELECT absent_export, date_sortie FROM tickets WHERE cle='SUP-1002'").fetchone()
        assert r["absent_export"] == 1 and r["date_sortie"]
        h = db.charger_historique(conn, "SUP-1001")
        assert ("etat", "En cours", "Travaux Externes en cours") in set(map(tuple, h[["champ", "ancienne", "nouvelle"]].values))
    # un ticket absent qui revient est de nouveau actif
    deposer(cfg, "c.csv", ligne("SUP-1002"), ligne("SUP-1001"), ligne("SUP-1003"))
    res = importer.importer_depot(cfg)[0]
    assert res["reapparus"] == 1
    with db.connecter(cfg) as conn:
        assert conn.execute("SELECT absent_export FROM tickets WHERE cle='SUP-1002'").fetchone()[0] == 0


def test_meme_fichier_non_reimporte_et_archivage(cfg):
    p = deposer(cfg, "a.csv", ligne("SUP-1001"))
    assert importer.importer_depot(cfg)[0]["statut"] == "ok"
    assert not p.exists() and any(config.chemin(cfg, "dossier_archive").glob("*_a.csv"))
    deposer(cfg, "a_copie.csv", ligne("SUP-1001"))                # contenu identique
    assert importer.importer_depot(cfg)[0]["statut"] == "ignore"


def test_fichier_invalide_deplace_et_base_intacte(cfg):
    deposer(cfg, "ok.csv", ligne("SUP-1001"))
    importer.importer_depot(cfg)
    deposer(cfg, "mauvais.csv", entete="Colonne A,Colonne B\n", ) .write_text("Colonne A,Colonne B\n1,2\n", encoding="utf-8")
    res = importer.importer_depot(cfg)[0]
    assert res["statut"] == "erreur" and "Clé de ticket" in res["message"]
    assert any(config.chemin(cfg, "dossier_erreurs").glob("*mauvais.csv"))
    with db.connecter(cfg) as conn:
        assert conn.execute("SELECT absent_export FROM tickets WHERE cle='SUP-1001'").fetchone()[0] == 0


def test_cp1252_et_point_virgule(cfg):
    entete = ENTETE.replace(",", ";")
    corps = ligne("SUP-1001", "Résumé accentué éàù").replace(",", ";")
    deposer(cfg, "x.csv", corps, entete=entete, encoding="cp1252")
    assert importer.importer_depot(cfg)[0]["statut"] == "ok"
    with db.connecter(cfg) as conn:
        assert "accentué" in conn.execute("SELECT resume FROM tickets").fetchone()[0]


def test_chrono_un_seul_actif_et_duree(cfg):
    deposer(cfg, "a.csv", ligne("SUP-1001"))
    importer.importer_depot(cfg)
    t0 = datetime(2026, 11, 3, 9, 0, 0)
    with db.connecter(cfg) as conn:
        db.ajouter_taches(conn, "SUP-1001", ["Analyser"])
        tid = conn.execute("SELECT id FROM taches").fetchone()[0]
        db.demarrer_chrono(conn, "SUP-1001", tid, maintenant=t0)
        assert conn.execute("SELECT statut FROM taches WHERE id=?", (tid,)).fetchone()[0] == "En cours"
        db.demarrer_chrono(conn, "SUP-1001", None, maintenant=t0 + timedelta(minutes=30))   # arrête le précédent
        assert conn.execute("SELECT COUNT(*) FROM temps WHERE fin IS NULL").fetchone()[0] == 1
        assert conn.execute("SELECT duree_s FROM temps WHERE tache_id=?", (tid,)).fetchone()[0] == 1800
        db.arreter_chrono(conn, maintenant=t0 + timedelta(minutes=45))
        tickets = db.charger_tickets(conn, cfg, t0 + timedelta(hours=1))
        assert tickets.loc[tickets.cle == "SUP-1001", "temps_s"].iloc[0] == 2700
        db.maj_tache(conn, tid, statut="Fait")
        assert conn.execute("SELECT termine FROM taches WHERE id=?", (tid,)).fetchone()[0]
        db.supprimer_tache(conn, tid)       # le temps reste, rattaché au ticket
        assert conn.execute("SELECT SUM(duree_s) FROM temps WHERE cle='SUP-1001'").fetchone()[0] == 2700


def test_sauvegarde_et_purge(cfg):
    cfg["nb_sauvegardes_conservees"] = 2
    for i in range(4):
        db.sauvegarder(cfg, f"t{i}")
    assert len(list(config.chemin(cfg, "dossier_sauvegardes").glob("*.db"))) == 2
    assert db.sauvegarde_du_jour_existe(cfg)


def test_colonne_perso_evolutive(cfg):
    config.ajouter_colonne(cfg, "Commentaire", "texte")
    config.ajouter_colonne(cfg, "Complexité", "liste", ["Faible", "Forte"])
    with pytest.raises(config.ConfigError):
        config.ajouter_colonne(cfg, "commentaire", "texte")
    cfg2 = config.charger(cfg["_chemin_config"])
    assert [c["id"] for c in cfg2["colonnes_perso"]][-2:] == ["commentaire", "complexite"]
    deposer(cfg2, "a.csv", ligne("SUP-1001"))
    importer.importer_depot(cfg2)
    with db.connecter(cfg2) as conn:
        db.maj_suivi(conn, "SUP-1001", {"commentaire": "ok"})      # aucune migration SQL nécessaire
        df = db.charger_tickets(conn, cfg2)
    assert df["perso_commentaire"].iloc[0] == "ok"


def test_stats_et_export(cfg, tmp_path):
    deposer(cfg, "a.csv", ligne("SUP-1001", ech="01/10/2026 00:00"), ligne("SUP-1002", "NAIA x", prio="Bloquant"))
    importer.importer_depot(cfg)
    with db.connecter(cfg) as conn:
        db.ajouter_temps_manuel(conn, "SUP-1001", None, date.today(), 60)
        db.ajouter_temps_manuel(conn, "SUP-1002", None, date.today(), 30)
        db.ajouter_taches(conn, None, ["Tâche libre"])
        tickets, taches, temps = db.charger_tickets(conn, cfg), db.charger_taches(conn), db.charger_temps(conn)
    k = stats.kpis(tickets, taches, temps, cfg)
    assert k["tickets_ouverts"] == 2 and k["tickets_bloquants"] == 1 and k["tickets_en_retard"] == 1
    assert k["temps_aujourdhui_s"] == 5400 and k["taches_ouvertes"] == 1
    assert stats.temps_par(temps, "cle")["Heures"].tolist() == [1.0, 0.5]
    chemin = export_excel.exporter_excel(cfg)
    assert chemin.exists()
    x = pd.read_excel(chemin, sheet_name=None)
    assert set(x) == {"Tickets", "Tâches", "Temps", "Statistiques"}
    assert "Priorité perso" in x["Tickets"].columns and len(x["Tickets"]) == 2


def test_actions_edition_tableaux(cfg):
    from suivi import actions
    deposer(cfg, "a.csv", ligne("SUP-1001"), ligne("SUP-1002"))
    importer.importer_depot(cfg)
    colonnes = {c["nom"]: c for c in cfg["colonnes_perso"]}
    with db.connecter(cfg) as conn:
        n = actions.appliquer_edition_tickets(
            conn, ["SUP-1001", "SUP-1002"],
            {"edited_rows": {1: {"Priorité perso": "2 - Haute", "Action à faire": "  Relancer  "}, 0: {"Action en cours": None}}},
            colonnes)
        assert n == 2
        assert db.lire_suivi(conn, "SUP-1002") == {"application": "AX", "priorite_perso": "2 - Haute", "action_a_faire": "Relancer"} \
            or db.lire_suivi(conn, "SUP-1002")["action_a_faire"] == "Relancer"
        db.ajouter_taches(conn, "SUP-1001", ["T1", "T2"])
        ids = [r[0] for r in conn.execute("SELECT id FROM taches ORDER BY id DESC")]   # même ordre que charger_taches
        m, s = actions.appliquer_edition_taches(conn, ids, {"edited_rows": {0: {"Statut": "Fait"}, 1: {"Supprimer": True}}})
        assert (m, s) == (1, 1)
        assert [r[0] for r in conn.execute("SELECT statut FROM taches")] == ["Fait"]
        db.ajouter_temps_manuel(conn, "SUP-1001", None, date.today(), 30)
        tid = conn.execute("SELECT id FROM temps").fetchone()[0]
        actions.appliquer_edition_temps(conn, [tid], {"edited_rows": {0: {"Durée (min)": 45, "Note": "x"}}})
        assert conn.execute("SELECT duree_s, note FROM temps").fetchone()[:] == (2700, "x")
