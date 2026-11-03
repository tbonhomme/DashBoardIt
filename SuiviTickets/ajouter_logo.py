"""Affiche le logo Cérèsia centré en haut de l'application (au-dessus des onglets).

Usage (depuis le dossier de l'application) :
    .venv\\Scripts\\python.exe ajouter_logo.py             # applique la modification
    .venv\\Scripts\\python.exe ajouter_logo.py --verifier  # simule, ne modifie rien

Le logo est lu dans assets\\logo.png : pour le changer plus tard, remplacez simplement ce fichier
(si le fichier est absent, rien n'est affiché et l'application fonctionne normalement).

Sécurité :
- tout est vérifié AVANT d'écrire : si app.py ne correspond pas à la version attendue, rien n'est modifié ;
- app.py est sauvegardé à côté sous le nom app.py.avant_logo ;
- le fichier est recompilé après modification ; en cas d'erreur, l'original est restauré ;
- le script peut être relancé sans risque (une modification déjà présente est ignorée).
Vos données (base SQLite, config.json) ne sont ni lues ni modifiées.
"""
from __future__ import annotations

import argparse
import py_compile
import shutil
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent
SUFFIXE = ".avant_logo"

MODIFICATIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("app.py", [
        ('''# =========================================================================== main
def main() -> None:''',
         '''# =========================================================================== logo
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
def main() -> None:'''),
        ('''    barre_laterale(cfg)
    afficher_flash()
''',
         '''    barre_laterale(cfg)
    afficher_logo()
    afficher_flash()
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

    if not (RACINE / "assets" / "logo.png").exists():
        print("ATTENTION : assets\\logo.png est introuvable. Le code sera installé, mais aucun logo ne s'affichera "
              "tant que ce fichier n'existe pas.\n")

    resultats: dict[Path, tuple[str, str]] = {}
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
        print("\nRien à faire : le logo est déjà installé.")
        return 0
    if args.verifier:
        print("\nVérification OK : la modification peut être appliquée (rien n'a été écrit).")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        for chemin, (nouveau, bom) in resultats.items():
            essai = Path(tmp) / chemin.name
            essai.write_bytes((bom + nouveau).encode("utf-8"))
            try:
                py_compile.compile(str(essai), cfile=str(essai) + "c", doraise=True)
            except py_compile.PyCompileError as e:
                print(f"\nERREUR - le résultat pour {chemin.name} n'est pas valide, rien n'a été modifié.\n{e}")
                return 1

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
        print(f"\nERREUR d'écriture ({e}) : restauration du fichier d'origine.")
        for chemin in ecrits:
            sauvegarde = chemin.with_name(chemin.name + SUFFIXE)
            if sauvegarde.exists():
                shutil.copy2(sauvegarde, chemin)
        return 1

    print("\nTerminé. Relancez l'application (fermez puis rouvrez l'icône ou la fenêtre noire), puis Ctrl + F5.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
