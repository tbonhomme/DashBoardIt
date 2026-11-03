"""Ajoute le type de colonne « lien » (adresse web cliquable) au Suivi des tickets V1.

Usage (depuis le dossier de l'application) :
    .venv\\Scripts\\python.exe ajouter_type_lien.py            # applique la modification
    .venv\\Scripts\\python.exe ajouter_type_lien.py --verifier # simule, ne modifie rien

Sécurité :
- tout est vérifié AVANT d'écrire : si un seul fichier ne correspond pas à la version attendue, rien n'est modifié ;
- chaque fichier modifié est sauvegardé à côté sous le nom <fichier>.avant_lien ;
- les fichiers sont recompilés après modification ; en cas d'erreur, les originaux sont restaurés ;
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

# (fichier, [(ancre à remplacer, remplacement)]) - une ancre doit exister EXACTEMENT une fois.
MODIFICATIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("suivi/config.py", [
        ('TYPES_COLONNE = ("texte", "liste", "date", "nombre", "case")',
         'TYPES_COLONNE = ("texte", "liste", "date", "nombre", "case", "lien")'),
    ]),
    ("suivi/actions.py", [
        ('from . import db\nfrom .utils import en_date\n\n\ndef norm(v, type_: str):',
         'import re\n\nfrom . import db\nfrom .utils import en_date\n\n'
         '_RE_SCHEMA = re.compile(r"^[A-Za-z][A-Za-z0-9+.\\-]+://")\n'
         '_RE_CHEMIN = re.compile(r"^([A-Za-z]:[\\\\/]|\\\\\\\\)")\n'
         '_RE_DOMAINE = re.compile(r"^[\\w\\-]+(\\.[\\w\\-]+)+(:\\d+)?/")\n\n\n'
         'def normaliser_lien(valeur) -> str | None:\n'
         '    """Nettoie une adresse saisie. Ajoute https:// si elle commence par www. ou ressemble à\n'
         '    « site.societe.fr/page ». Les chemins (C:\\\\..., \\\\\\\\serveur\\\\...), mailto: et les liens déjà complets sont conservés."""\n'
         '    s = str(valeur or "").strip()\n'
         '    if not s:\n'
         '        return None\n'
         '    if _RE_SCHEMA.match(s) or s.lower().startswith(("mailto:", "file:")) or _RE_CHEMIN.match(s):\n'
         '        return s\n'
         '    if s.lower().startswith("www.") or _RE_DOMAINE.match(s):\n'
         '        return "https://" + s\n'
         '    return s\n\n\n'
         'def norm(v, type_: str):'),
        ('        return float(v)\n    s = str(v).strip()\n    return s or None\n',
         '        return float(v)\n    if type_ == "lien":\n        return normaliser_lien(v)\n'
         '    s = str(v).strip()\n    return s or None\n'),
    ]),
    ("suivi/export_excel.py", [
        ('def _ecrire(writer, nom: str, df: pd.DataFrame, largeurs: dict | None = None) -> None:',
         'def _url_excel(url: str) -> str | None:\n'
         '    """Adresse utilisable par Excel (web, mail, chemin réseau ou disque), ou None si non cliquable."""\n'
         '    import re\n'
         '    if re.match(r"(?i)^(https?|ftps?)://|^mailto:", url):\n'
         '        return url\n'
         '    if url.startswith("\\\\\\\\") or re.match(r"^[A-Za-z]:[\\\\/]", url):\n'
         '        return "external:" + url\n'
         '    return None\n\n\n'
         'def _ecrire(writer, nom: str, df: pd.DataFrame, largeurs: dict | None = None,\n'
         '            liens: list[str] | None = None) -> None:'),
        ('    ws.freeze_panes(1, 0)\n',
         '    ws.freeze_panes(1, 0)\n'
         '    if liens:                                   # colonnes de type « lien » : hyperliens cliquables\n'
         '        fmt_lien = wb.add_format({"font_color": "blue", "underline": 1})\n'
         '        for nom_col in liens:\n'
         '            if nom_col not in df.columns:\n'
         '                continue\n'
         '            j = list(df.columns).index(nom_col)\n'
         '            for r, v in enumerate(df[nom_col], start=1):\n'
         '                if pd.isna(v) or not str(v).strip():\n'
         '                    continue\n'
         '                url = str(v).strip()\n'
         '                cible = _url_excel(url)\n'
         '                if cible is None or ws.write_url(r, j, cible, fmt_lien, string=url) != 0:\n'
         '                    ws.write_string(r, j, url)  # non cliquable (ou trop long) : le texte reste visible\n'),
        ('            _ecrire(w, "Tickets", t_tickets, {"Résumé": 70})',
         '            _ecrire(w, "Tickets", t_tickets, {"Résumé": 70},\n'
         '                    [n for c in config.colonnes_perso_actives(cfg) if c["type"] == "lien"\n'
         '                     for n in (c["nom"], f"{c[\'nom\']} (perso)")])'),
    ]),
    ("app.py", [
        ('    if t == "case":\n        return st.column_config.CheckboxColumn(col["nom"])\n',
         '    if t == "case":\n        return st.column_config.CheckboxColumn(col["nom"])\n'
         '    if t == "lien":\n'
         '        return st.column_config.LinkColumn(\n'
         '            col["nom"], width="small", display_text="Ouvrir",\n'
         '            help="Double-cliquez pour coller ou modifier l\'adresse ; cliquez sur « Ouvrir » pour l\'ouvrir.")\n'),
        ('    if liens:\n        st.caption(" · ".join(liens))\n',
         '    if liens:\n        st.caption(" · ".join(liens))\n'
         '    for col_lien in config.colonnes_perso_actives(cfg):          # colonnes de type « lien » : boutons cliquables\n'
         '        if col_lien["type"] != "lien":\n'
         '            continue\n'
         '        url = t.get(f"perso_{col_lien[\'id\']}")\n'
         '        if _nul(url) or not str(url).strip():\n'
         '            continue\n'
         '        url = str(url).strip()\n'
         '        if url.lower().startswith(("http://", "https://", "mailto:")):\n'
         '            st.link_button(f"{col_lien[\'nom\']} : ouvrir", url)\n'
         '        else:\n'
         '            st.caption(f"{col_lien[\'nom\']} : {url}")\n'),
        ('help="texte, liste (choix), date, nombre, case à cocher"',
         'help="texte, liste (choix), date, nombre, case à cocher, lien (adresse web)"'),
    ]),
]


def lire(chemin: Path) -> tuple[str, str]:
    brut = chemin.read_bytes()
    bom = "\ufeff" if brut.startswith(b"\xef\xbb\xbf") else ""
    texte = brut.decode("utf-8-sig")
    return texte, bom


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verifier", action="store_true", help="simule sans rien modifier")
    args = ap.parse_args()

    # 1. Préparation en mémoire : aucune écriture tant que tout n'est pas validé
    resultats: dict[Path, tuple[str, str, str]] = {}      # chemin -> (original, nouveau, bom)
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
            resultats[chemin] = (original, texte.replace("\n", "\r\n") if crlf else texte, bom)

    if erreurs:
        print("\nERREUR - aucune modification n'a été faite :")
        for e in erreurs:
            print("  -", e)
        return 1
    if not resultats:
        print("\nRien à faire : le type « lien » est déjà installé.")
        return 0
    if args.verifier:
        print("\nVérification OK : la modification peut être appliquée (rien n'a été écrit).")
        return 0

    # 2. Vérification de syntaxe sur des copies temporaires
    with tempfile.TemporaryDirectory() as tmp:
        for chemin, (_, nouveau, bom) in resultats.items():
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
        for chemin, (original, nouveau, bom) in resultats.items():
            sauvegarde = chemin.with_name(chemin.name + ".avant_lien")
            if not sauvegarde.exists():
                shutil.copy2(chemin, sauvegarde)
            chemin.write_bytes((bom + nouveau).encode("utf-8"))
            ecrits.append(chemin)
            print(f"  OK {chemin.relative_to(RACINE)} (sauvegarde : {sauvegarde.name})")
    except OSError as e:
        print(f"\nERREUR d'écriture ({e}) : restauration des fichiers d'origine.")
        for chemin in ecrits:
            sauvegarde = chemin.with_name(chemin.name + ".avant_lien")
            if sauvegarde.exists():
                shutil.copy2(sauvegarde, chemin)
        return 1

    print("\nTerminé. Relancez l'application (fermez puis rouvrez l'icône ou la fenêtre noire).")
    print("Nouveau type disponible : Paramètres > Ajouter la colonne > Type « lien ».")
    return 0


if __name__ == "__main__":
    sys.exit(main())
