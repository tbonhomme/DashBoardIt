"""Ajoute l'ordre des colonnes MÉMORISÉ du tableau « Tickets » (Paramètres > Ordre des colonnes).

Pourquoi : faire glisser une colonne avec la souris ne change que l'affichage du navigateur ; l'ordre est perdu
à chaque enregistrement ou rechargement de la page. Ce correctif enregistre l'ordre dans config.json.

Usage (depuis le dossier de l'application) :
    .venv\\Scripts\\python.exe ajouter_ordre_colonnes.py             # applique la modification
    .venv\\Scripts\\python.exe ajouter_ordre_colonnes.py --verifier  # simule, ne modifie rien

Sécurité :
- tout est vérifié AVANT d'écrire : si un fichier ne correspond pas à la version attendue, rien n'est modifié ;
- chaque fichier modifié est sauvegardé à côté sous le nom <fichier>.avant_ordre ;
- les fichiers sont recompilés après modification ; en cas d'erreur, les originaux sont restaurés ;
- le script peut être relancé sans risque (une modification déjà présente est ignorée).
Vos données (base SQLite, config.json) ne sont ni lues ni modifiées par ce script.
"""
from __future__ import annotations

import argparse
import py_compile
import shutil
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent
SUFFIXE = ".avant_ordre"

# (fichier, [(extrait à remplacer, remplacement)]) - l'extrait doit exister EXACTEMENT une fois.
MODIFICATIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("suivi/config.py", [
        ('''def definir_actif(cfg: dict, ident: str, actif: bool) -> None:''',
         '''COLONNES_TICKETS_DEBUT = ["Clé", "Résumé", "Type", "État", "Priorité Jira"]
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


def definir_actif(cfg: dict, ident: str, actif: bool) -> None:'''),
    ]),
    ("app.py", [
        ('''aff, key=cle_editeur, hide_index=True, width="stretch", height=480,''',
         '''aff, key=cle_editeur, hide_index=True, width="stretch", height=480,
        column_order=config.ordre_colonnes(cfg, list(aff.columns)),'''),
        ('''def onglet_params(cfg: dict) -> None:''',
         '''@securise
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


def onglet_params(cfg: dict) -> None:'''),
        ('''    st.subheader("Sauvegardes")
''',
         '''    section_ordre_colonnes(cfg)
    st.divider()
    st.subheader("Sauvegardes")
'''),
    ]),
]


def lire(chemin: Path) -> tuple[str, str]:
    brut = chemin.read_bytes()
    bom = "\ufeff" if brut.startswith(b"\xef\xbb\xbf") else ""
    return brut.decode("utf-8-sig"), bom


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verifier", action="store_true", help="simule sans rien modifier")
    args = ap.parse_args()

    # 1. Préparation en mémoire : aucune écriture tant que tout n'est pas validé
    resultats: dict[Path, tuple[str, str]] = {}      # chemin -> (nouveau texte, bom)
    erreurs: list[str] = []
    for nom, edits in MODIFICATIONS:
        chemin = RACINE / nom
        if not chemin.exists():
            erreurs.append(f"{nom} : fichier introuvable (lancez le script depuis le dossier de l'application).")
            continue
        original, bom = lire(chemin)
        crlf = "\r\n" in original
        texte = original.replace("\r\n", "\n")
        modifie = False
        for i, (ancre, nouveau) in enumerate(edits, start=1):
            if nouveau in texte:
                print(f"  = {nom} (modification {i}) : déjà appliquée")
                continue
            n = texte.count(ancre)
            if n != 1:
                erreurs.append(f"{nom} (modification {i}) : {n} occurrence(s) de l'extrait attendu au lieu de 1. "
                               "Ce fichier a probablement été modifié à la main.")
                continue
            texte = texte.replace(ancre, nouveau, 1)
            modifie = True
            print(f"  + {nom} (modification {i}) : à appliquer")
        if modifie:
            resultats[chemin] = (texte.replace("\n", "\r\n") if crlf else texte, bom)

    if erreurs:
        print("\nERREUR - aucune modification n'a été faite :")
        for e in erreurs:
            print("  -", e)
        return 1
    if not resultats:
        print("\nRien à faire : l'ordre des colonnes mémorisé est déjà installé.")
        return 0
    if args.verifier:
        print("\nVérification OK : la modification peut être appliquée (rien n'a été écrit).")
        return 0

    # 2. Vérification de syntaxe sur des copies temporaires
    with tempfile.TemporaryDirectory() as tmp:
        for chemin, (nouveau, bom) in resultats.items():
            essai = Path(tmp) / chemin.name
            essai.write_bytes((bom + nouveau).encode("utf-8"))
            try:
                py_compile.compile(str(essai), cfile=str(essai) + "c", doraise=True)
            except py_compile.PyCompileError as e:
                print(f"\nERREUR - le résultat pour {chemin.name} n'est pas valide, rien n'a été modifié.\n{e}")
                return 1

    # 3. Écriture avec sauvegarde, restauration automatique en cas d'incident
    ecrits: list[Path] = []
    try:
        for chemin, (nouveau, bom) in resultats.items():
            sauvegarde = chemin.with_name(chemin.name + SUFFIXE)
            if not sauvegarde.exists():
                shutil.copy2(chemin, sauvegarde)
            chemin.write_bytes((bom + nouveau).encode("utf-8"))
            ecrits.append(chemin)
            print(f"  OK {chemin.relative_to(RACINE)} (sauvegarde : {sauvegarde.name})")
    except OSError as e:
        print(f"\nERREUR d'écriture ({e}) : restauration des fichiers d'origine.")
        for chemin in ecrits:
            sauvegarde = chemin.with_name(chemin.name + SUFFIXE)
            if sauvegarde.exists():
                shutil.copy2(sauvegarde, chemin)
        return 1

    print("\nTerminé. Relancez l'application (fermez puis rouvrez l'icône ou la fenêtre noire).")
    print("Réglage : onglet Paramètres > Ordre des colonnes du tableau Tickets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
