"""Tests du type de colonne « lien ». Données fictives dans un dossier temporaire : votre base n'est pas touchée."""
from __future__ import annotations

import pytest

from suivi import actions, config, db, export_excel


@pytest.fixture
def cfg(tmp_path):
    c = config.charger(tmp_path / "config.json")
    db.initialiser(c)
    return c


def ajouter_ticket(cfg, cle, resume="Ticket de test"):
    with db.connecter(cfg) as conn:
        conn.execute(
            "INSERT INTO tickets(cle, resume, type, etat, priorite_jira, cree, maj, absent_export) "
            "VALUES (?,?,?,?,?,?,?,0)",
            (cle, resume, "Incident", "En cours", "Majeur", "2026-10-01 10:00:00", "2026-11-02 10:00:00"))


def test_type_lien_disponible_et_ajout_de_colonne(cfg):
    assert "lien" in config.TYPES_COLONNE
    col = config.ajouter_colonne(cfg, "Lien SharePoint", "lien")
    assert col == {"id": "lien_sharepoint", "nom": "Lien SharePoint", "type": "lien", "actif": True}
    relu = config.charger(cfg["_chemin_config"])
    assert any(c["id"] == "lien_sharepoint" and c["type"] == "lien" for c in relu["colonnes_perso"])


@pytest.mark.parametrize("saisie, attendu", [
    ("https://jira.exemple.fr/browse/SUP-1", "https://jira.exemple.fr/browse/SUP-1"),
    ("  http://intranet/page  ", "http://intranet/page"),
    ("www.exemple.fr/page", "https://www.exemple.fr/page"),
    ("jira.societe.com/browse/SUP-36233", "https://jira.societe.com/browse/SUP-36233"),
    ("mailto:a@b.fr", "mailto:a@b.fr"),
    ("\\\\serveur\\partage\\doc.docx", "\\\\serveur\\partage\\doc.docx"),
    ("C:\\Users\\moi\\doc.docx", "C:\\Users\\moi\\doc.docx"),
    ("rapport.final.docx", "rapport.final.docx"),            # pas d'adresse web : conservé tel quel
    ("   ", None),
    ("", None),
    (None, None),
])
def test_normaliser_lien(saisie, attendu):
    assert actions.normaliser_lien(saisie) == attendu
    assert actions.norm(saisie, "lien") == attendu


def test_les_autres_types_ne_changent_pas():
    assert actions.norm("  texte  ", "texte") == "texte"
    assert actions.norm("www.exemple.fr", "texte") == "www.exemple.fr"      # pas de https:// sur un texte
    assert actions.norm(True, "case") is True


def test_edition_tableau_enregistre_le_lien(cfg):
    config.ajouter_colonne(cfg, "Lien", "lien")
    ajouter_ticket(cfg, "SUP-1")
    colonnes = {"Lien": next(c for c in cfg["colonnes_perso"] if c["id"] == "lien")}
    with db.connecter(cfg) as conn:
        n = actions.appliquer_edition_tickets(conn, ["SUP-1"], {"edited_rows": {0: {"Lien": "www.exemple.fr/doc"}}}, colonnes)
        assert n == 1 and db.lire_suivi(conn, "SUP-1")["lien"] == "https://www.exemple.fr/doc"
        actions.appliquer_edition_tickets(conn, ["SUP-1"], {"edited_rows": {0: {"Lien": None}}}, colonnes)
        assert "lien" not in db.lire_suivi(conn, "SUP-1")                   # vider la cellule supprime le lien


def test_une_colonne_texte_existante_peut_devenir_un_lien(cfg):
    """Changer "type" dans config.json suffit : les données déjà saisies sont conservées."""
    ajouter_ticket(cfg, "SUP-1")
    with db.connecter(cfg) as conn:
        db.maj_suivi(conn, "SUP-1", {"action_en_cours": "https://exemple.fr/a"})
    for c in cfg["colonnes_perso"]:
        if c["id"] == "action_en_cours":
            c["type"] = "lien"
    with db.connecter(cfg) as conn:
        df = db.charger_tickets(conn, cfg)
    assert df.loc[0, "perso_action_en_cours"] == "https://exemple.fr/a"


def test_export_excel_hyperliens(cfg):
    import openpyxl
    config.ajouter_colonne(cfg, "Lien", "lien")
    for i in range(1, 6):
        ajouter_ticket(cfg, f"SUP-{i}")
    valeurs = {"SUP-1": "https://exemple.fr/a?x=1&y=2", "SUP-2": "\\\\serveur\\partage\\doc.docx",
               "SUP-3": "mailto:a@b.fr", "SUP-4": "juste du texte", "SUP-5": None}
    with db.connecter(cfg) as conn:
        for cle, v in valeurs.items():
            db.maj_suivi(conn, cle, {"lien": v})
    chemin = export_excel.exporter_excel(cfg)

    ws = openpyxl.load_workbook(chemin)["Tickets"]
    entetes = [c.value for c in ws[1]]
    col = entetes.index("Lien") + 1
    par_cle = {ws.cell(r, 1).value: ws.cell(r, col) for r in range(2, ws.max_row + 1)}
    assert par_cle["SUP-1"].hyperlink is not None and par_cle["SUP-1"].hyperlink.target == "https://exemple.fr/a?x=1&y=2"
    assert par_cle["SUP-1"].value == "https://exemple.fr/a?x=1&y=2"          # le texte affiché reste l'adresse
    assert par_cle["SUP-2"].hyperlink is not None                            # chemin réseau cliquable dans Excel
    assert par_cle["SUP-3"].hyperlink is not None
    assert par_cle["SUP-4"].hyperlink is None and par_cle["SUP-4"].value == "juste du texte"
    assert par_cle["SUP-5"].value is None


def test_export_sans_colonne_lien_inchange(cfg):
    """Régression : l'export fonctionne toujours quand aucune colonne de type lien n'existe."""
    ajouter_ticket(cfg, "SUP-1")
    assert export_excel.exporter_excel(cfg).exists()
