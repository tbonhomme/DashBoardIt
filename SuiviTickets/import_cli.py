"""Import en ligne de commande (utilisable depuis le Planificateur de tâches Windows).

Exemples :
    .venv\\Scripts\\python.exe import_cli.py
    .venv\\Scripts\\python.exe import_cli.py --export
Code de sortie : 0 = OK (ou rien à importer), 1 = au moins une erreur.
"""
from __future__ import annotations

import argparse
import sys

from suivi import config, db, export_excel, importer
from suivi.utils import logger


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Importe les CSV Jira du dossier de dépôt.")
    p.add_argument("--config", help="Chemin de config.json (défaut : celui du dossier de l'application)")
    p.add_argument("--export", action="store_true", help="Régénère aussi le fichier Excel après l'import")
    args = p.parse_args(argv)

    try:
        cfg = config.charger(args.config)
    except config.ConfigError as e:
        print(f"ERREUR configuration : {e}", file=sys.stderr)
        return 1
    db.initialiser(cfg)
    resultats = importer.importer_depot(cfg)
    code = 0
    if not resultats:
        print("Aucun fichier CSV à importer dans", config.chemin(cfg, "dossier_depot"))
    for r in resultats:
        print(f"[{r['statut'].upper()}] {r['fichier']} : {r.get('message', '')}")
        for a in r.get("avertissements", []):
            print("   Avertissement :", a)
        if r["statut"] == "erreur":
            code = 1
    if args.export or (cfg.get("export_auto_apres_import") and any(r["statut"] == "ok" for r in resultats)):
        try:
            print("Export Excel :", export_excel.exporter_excel(cfg))
        except Exception as e:  # noqa: BLE001
            logger(cfg).error("Export Excel en erreur : %s", e)
            print(f"ERREUR export Excel : {e}", file=sys.stderr)
            code = 1
    return code


if __name__ == "__main__":
    sys.exit(main())
