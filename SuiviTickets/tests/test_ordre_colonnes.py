"""Tests de l'ordre mémorisé des colonnes du tableau Tickets (données fictives, votre base n'est pas touchée)."""
from __future__ import annotations

import json

import pytest

from suivi import config

DEFAUT = ["Clé", "Résumé", "Type", "État", "Priorité Jira", "Priorité perso", "Action en cours", "Action à faire",
          "Application", "Échéance", "Mise à jour", "Tâches ouvertes", "Temps passé", "Présence"]


@pytest.fixture
def cfg(tmp_path):
    return config.charger(tmp_path / "config.json")


def test_ordre_par_defaut(cfg):
    assert config.noms_colonnes_tickets(cfg) == DEFAUT
    assert config.ordre_colonnes(cfg, DEFAUT) == DEFAUT


def test_nom_en_double_recoit_le_suffixe_perso(cfg):
    config.ajouter_colonne(cfg, "Type", "texte")
    noms = config.noms_colonnes_tickets(cfg)
    assert "Type (perso)" in noms and noms.count("Type") == 1


def test_deplacer_en_deuxieme_position_est_memorise(cfg):
    config.ajouter_colonne(cfg, "Lien ticket", "lien")
    ordre = config.deplacer_colonne(cfg, "Lien ticket", 2)
    assert ordre[:3] == ["Clé", "Lien ticket", "Résumé"] and len(ordre) == len(DEFAUT) + 1
    relu = config.charger(cfg["_chemin_config"])                      # rechargement = nouvelle session
    assert relu["ordre_colonnes_tickets"] == ordre
    assert config.ordre_colonnes(relu, config.noms_colonnes_tickets(relu)) == ordre
    assert json.loads(open(cfg["_chemin_config"], encoding="utf-8").read())["ordre_colonnes_tickets"] == ordre


def test_positions_limites(cfg):
    assert config.deplacer_colonne(cfg, "Présence", 0)[0] == "Présence"           # 0 ou négatif => première
    assert config.deplacer_colonne(cfg, "Clé", 99)[-1] == "Clé"                    # trop grand => dernière
    assert sorted(config.ordre_colonnes(cfg, DEFAUT)) == sorted(DEFAUT)            # rien n'est perdu ni dupliqué


def test_colonne_inconnue(cfg):
    with pytest.raises(config.ConfigError):
        config.deplacer_colonne(cfg, "N'existe pas", 2)


def test_nouvelle_colonne_ajoutee_a_la_fin_puis_deplacable(cfg):
    config.deplacer_colonne(cfg, "Application", 2)
    config.ajouter_colonne(cfg, "Commentaire", "texte")
    ordre = config.ordre_colonnes(cfg, config.noms_colonnes_tickets(cfg))
    assert ordre[1] == "Application" and ordre[-1] == "Commentaire"
    assert config.deplacer_colonne(cfg, "Commentaire", 3)[2] == "Commentaire"


def test_colonne_masquee_ou_renommee_ne_casse_rien(cfg):
    config.deplacer_colonne(cfg, "Action à faire", 2)
    config.definir_actif(cfg, "action_a_faire", False)                             # colonne masquée
    ordre = config.ordre_colonnes(cfg, config.noms_colonnes_tickets(cfg))
    assert "Action à faire" not in ordre and ordre[0] == "Clé"
    cfg["ordre_colonnes_tickets"] = ["Colonne disparue", "Présence"] + ["Présence"]  # doublon + inconnue
    ordre = config.ordre_colonnes(cfg, DEFAUT)
    assert ordre[0] == "Présence" and len(ordre) == len(DEFAUT) and len(set(ordre)) == len(ordre)


def test_reinitialiser(cfg):
    config.deplacer_colonne(cfg, "Présence", 1)
    config.reinitialiser_ordre_colonnes(cfg)
    relu = config.charger(cfg["_chemin_config"])
    assert "ordre_colonnes_tickets" not in relu
    assert config.ordre_colonnes(relu, DEFAUT) == DEFAUT
