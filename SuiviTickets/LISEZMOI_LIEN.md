# Type de colonne « lien »

Ajoute le type **lien** (adresse web cliquable) à la liste des types de colonnes, à côté de texte, liste, date, nombre et case à cocher.

## Installation (sans droits administrateur, ~2 minutes)
1. Fermez l'application (icône > Quitter, ou fermez la fenêtre noire).
2. Dézippez dans le dossier qui **contient** `SuiviTickets` :
   ```powershell
   Expand-Archive -Path .\SuiviTickets_lien.zip -DestinationPath C:\Users\thomas.bonhomme\Documents -Force
   ```
   Seuls 2 fichiers sont ajoutés : `ajouter_type_lien.py` et `tests\test_lien.py`.
3. Simulez d'abord (ne modifie rien), puis appliquez :
   ```powershell
   cd C:\Users\thomas.bonhomme\Documents\SuiviTickets
   .venv\Scripts\python.exe ajouter_type_lien.py --verifier
   .venv\Scripts\python.exe ajouter_type_lien.py
   ```
4. Relancez l'application.

Le script modifie 4 fichiers (`app.py`, `suivi\config.py`, `suivi\actions.py`, `suivi\export_excel.py`). Si l'un d'eux ne correspond pas à la version attendue, **rien n'est modifié** et il vous l'indique. Chaque fichier modifié est sauvegardé à côté sous le nom `<fichier>.avant_lien`. Votre base de données et `config.json` ne sont pas touchés. Le script peut être relancé sans risque.

**Pour annuler :** fermez l'application et recopiez chaque fichier `.avant_lien` sur son original (en supprimant l'extension `.avant_lien`).

## Utilisation
- **Nouvelle colonne :** onglet Paramètres > Ajouter la colonne > Type **lien**.
- **Colonne existante :** dans `config.json`, changez `"type": "texte"` en `"type": "lien"` pour la colonne voulue, puis rechargez la page. Les valeurs déjà saisies sont conservées.
- **Saisie :** dans l'onglet Tickets, double-cliquez sur la cellule et collez l'adresse, puis « Enregistrer les modifications ». La cellule affiche « Ouvrir ».
- **Détail d'un ticket :** un bouton « <nom de la colonne> : ouvrir » apparaît pour chaque lien renseigné.
- **Export Excel :** les liens deviennent des hyperliens cliquables.

## Règles de saisie
| Vous collez | Enregistré |
|---|---|
| `https://jira.societe.fr/browse/SUP-1` | tel quel |
| `www.societe.fr/page` | `https://www.societe.fr/page` |
| `jira.societe.fr/browse/SUP-1` | `https://jira.societe.fr/browse/SUP-1` |
| `mailto:nom@societe.fr` | tel quel |
| `\\serveur\partage\doc.docx` ou `C:\...\doc.docx` | tel quel |
| `jira.societe.fr` (sans `/`) ou `rapport.docx` | tel quel (non reconnu comme adresse web) |

## Limite à connaître
Les chemins de fichiers (`\\serveur\...`, `C:\...`) sont conservés et cliquables **dans Excel**, mais pas depuis la page web : les navigateurs bloquent l'ouverture de fichiers locaux depuis une page. Les adresses `http(s)` et `mailto:` s'ouvrent normalement.

## Tests
`.venv\Scripts\python.exe -m pytest -q tests\test_lien.py` (données fictives, votre base n'est pas touchée).
