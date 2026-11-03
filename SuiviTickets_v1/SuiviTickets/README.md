# Suivi des tickets (Jira) - application locale

Tableau de bord personnel : import des exports CSV Jira, colonnes de suivi personnelles, to-do list par ticket,
chrono / temps passé et statistiques. Tout est stocké **sur votre poste** (un fichier SQLite). Un export Excel
peut être déposé dans OneDrive pour une consultation depuis Office 365.

## 1. Contenu du dossier

| Élément | Rôle |
|---|---|
| `app.py` | Interface (Streamlit) |
| `suivi/` | Code : `importer.py` (import CSV), `db.py` (base), `stats.py`, `export_excel.py`, `actions.py`, `config.py` |
| `import_cli.py` | Import en ligne de commande (tâche planifiée) |
| `config.json` | Réglages : dossiers, colonnes personnelles, priorités, détection de l'application |
| `depot/` | **Dossier de dépôt** des exports CSV Jira |
| `data/` | Base SQLite `suivi_tickets.db` (vos données) |
| `backups/` | Sauvegardes automatiques de la base |
| `exports/` | Export Excel `Suivi_Tickets.xlsx` |
| `logs/` | Journal d'exécution `suivi_tickets.log` |
| `tests/` | Tests automatiques (pytest) |
| `install.ps1` / `lancer.bat` | Installation / lancement |

## 2. Installation (une seule fois)

**Prérequis :** Windows, Python 3.10 ou plus récent (ou un Python portable), accès à PyPI (ou proxy configuré). Aucun droit administrateur.

1. Dézippez le dossier où vous voulez (ex. `C:\Outils\SuiviTickets`). Évitez un dossier protégé (`Program Files`).
2. Ouvrez PowerShell dans ce dossier :
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\install.ps1 -Raccourci
   ```
   Avec un Python portable : `.\install.ps1 -PythonExe D:\Outils\python\python.exe`
3. `-ExecutionPolicy Bypass` ne s'applique qu'à cette commande. Si votre poste bloque les scripts PowerShell, créez l'environnement à la main :
   ```bat
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

## 3. Utilisation au quotidien

1. Exportez vos tickets depuis Jira (CSV) et **déposez le fichier dans `depot/`**.
2. Double-cliquez sur `lancer.bat` (ou le raccourci) : l'application s'ouvre sur `http://localhost:8501` et importe le dépôt automatiquement.
3. Pour un nouvel export en cours de journée : déposez-le puis onglet **Import / Export > Importer maintenant** (ou chargez-le directement depuis cet onglet).

### Règles d'import
- La **clé du ticket** (`SUP-xxxxx`) est l'identifiant unique.
- Seuls les champs Jira sont mis à jour (résumé, état, priorité Jira, dates, liens...). **Vos priorités, actions, tâches et temps ne sont jamais écrasés.**
- Un ticket **absent** du nouvel export est marqué « Absent » (jamais supprimé) ; s'il revient, il redevient actif. Vérifiez que le filtre de votre export Jira reste toujours le même.
- Un même fichier (même contenu) n'est jamais importé deux fois. Après import, le fichier est déplacé dans `depot/traites/` (`archiver_apres_import`), ou dans `depot/erreurs/` s'il est invalide.
- Chaque changement d'état, de priorité Jira, d'assigné ou d'échéance est historisé (détail d'un ticket > Historique Jira).
- Une sauvegarde de la base est faite avant chaque import contenant un nouveau fichier.

## 4. Les onglets

- **Tickets** : filtres, tri, tableau modifiable. Colonnes personnelles par défaut : *Priorité perso*, *Action en cours*, *Action à faire*, *Application* (détectée automatiquement à partir du résumé : NAIA, AX, EDI). Modifiez les cellules puis **Enregistrer les modifications**. Sous le tableau : détail d'un ticket (tâches, temps, historique).
- **To-do list** : toutes les tâches (liées à un ticket ou libres), filtres par statut / échéance / ticket. Ajout de plusieurs tâches d'un coup (une par ligne). Passer une tâche à « Fait » arrête son chrono.
- **Temps** : saisie manuelle, totaux jour / semaine / mois, temps par ticket et par tâche, modification et suppression des saisies.
- **Statistiques** : tickets par état / priorité / type / application / demandeur, ancienneté, créés vs sortis par mois, heures par semaine / application / ticket / tâche, tickets en retard ou sans mise à jour.
- **Import / Export** : dépôt, historique des imports, export Excel.
- **Paramètres** : ajout / masquage de colonnes, sauvegardes, emplacements.

### Chrono
Barre latérale : choisissez une tâche (ou un ticket) puis **Démarrer le chrono**. **Un seul chrono à la fois** : en démarrer un autre arrête le précédent. Le chrono survit à la fermeture du navigateur (il est enregistré dans la base) ; pensez à l'arrêter avant de quitter.

## 5. Faire évoluer l'application

**Ajouter une colonne :** onglet Paramètres > « Ajouter la colonne » (types : texte, liste, date, nombre, case à cocher), ou en éditant `config.json` :
```json
{"id": "commentaire", "nom": "Commentaire", "type": "texte", "actif": true}
```
Aucune migration de base n'est nécessaire : les données perso sont stockées en JSON par ticket. La colonne apparaît dans le tableau, les filtres (type liste), la recherche (type texte) et l'export Excel. Décocher « actif » la masque sans perdre ses données.

**Autres réglages (`config.json`) :** `ordre_priorite_jira`, `etats_clos`, `jours_sans_maj_alerte`, `detection_application` (expressions régulières), `jira_base_url` (lien « Ouvrir dans Jira »), `mapping_jira` (si un en-tête de l'export Jira change, ex. `{"etat": "Statut"}`).
Un fichier `config.json` invalide est signalé par un message clair ; supprimez-le pour régénérer les valeurs par défaut.

## 6. Accès depuis Office 365 (optionnel)

L'application tourne en local. Pour consulter les données depuis votre compte Office 365 :
1. Dans `config.json`, mettez `dossier_export` sur un dossier **OneDrive** synchronisé, par exemple `"C:/Users/vous/OneDrive - Société/Suivi"`.
2. Onglet Import / Export > **Générer l'export Excel** (ou `export_auto_apres_import: true`).
3. Ouvrez `Suivi_Tickets.xlsx` depuis Office 365 / Excel en ligne : onglets Tickets, Tâches, Temps, Statistiques (lecture seule en pratique : l'export est régénéré, ne le modifiez pas).

Si Excel a le fichier ouvert, l'export échoue avec un message explicite : fermez-le puis réessayez.

## 7. Import automatique (optionnel)

Planificateur de tâches Windows, sans droits administrateur (s'exécute session ouverte) :
```bat
schtasks /Create /SC DAILY /ST 08:00 /TN "SuiviTickets-Import" /TR "\"C:\Outils\SuiviTickets\.venv\Scripts\python.exe\" \"C:\Outils\SuiviTickets\import_cli.py\" --export"
```
Test sans risque : lancez la même commande dans une invite de commandes ; code de sortie 0 = OK, 1 = erreur (voir `logs/suivi_tickets.log`).

## 8. Utiliser l'application sur un autre PC

- **Changement de poste :** copiez tout le dossier (la base est dans `data/`), puis lancez `install.ps1` sur le nouveau poste. Les chemins relatifs de `config.json` suivent le dossier ; seuls les chemins absolus (ex. OneDrive) sont à adapter.
- **Deux PC en alternance :** placez le dossier dans OneDrive, **fermez l'application (et la fenêtre noire) avant de changer de PC**, et attendez la fin de la synchronisation. Ne l'ouvrez jamais sur les deux PC en même temps : risque de conflit ou de corruption de la base. `mode_journal` est réglé sur `DELETE` (pas de fichiers annexes `-wal`/`-shm`), ce qui est compatible OneDrive. Excluez `.venv` de la synchronisation et réinstallez-le sur chaque PC (`install.ps1`).

## 9. Sauvegarde et restauration

- Sauvegarde automatique : au premier lancement de chaque jour et avant chaque import (20 conservées, réglable : `nb_sauvegardes_conservees`). Sauvegarde manuelle : onglet Paramètres.
- **Restaurer :** fermez l'application, renommez `data/suivi_tickets.db` (par précaution), copiez une sauvegarde de `backups/` vers `data/suivi_tickets.db`, relancez.
- Pensez à sauvegarder le dossier `data/` et `config.json` dans votre sauvegarde habituelle.

## 10. Tests et dépannage

```bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
```
Les tests utilisent des données fictives dans un dossier temporaire : ils ne touchent pas à votre base.

| Symptôme | Piste |
|---|---|
| « Colonne Clé de ticket introuvable » | En-têtes de l'export modifiés : adapter `mapping_jira`. Le fichier est déplacé dans `depot/erreurs/` |
| Dates vides ou avertissement « date illisible » | Format de date Jira différent ; formats gérés : `jj/mm/aaaa hh:mm`, `aaaa-mm-jj`, etc. |
| Beaucoup de tickets « Absents » | Le filtre de l'export Jira a changé ; réimportez un export complet, les tickets réapparaissent |
| Page inaccessible | Vérifiez que la fenêtre de `lancer.bat` est ouverte ; port 8501 occupé : fermez l'ancienne instance |
| `database is locked` | Application ouverte deux fois, ou base sur un dossier synchronisé en cours d'écriture |
| Erreur d'export Excel | Fichier ouvert dans Excel : fermez-le |

Journal détaillé : `logs/suivi_tickets.log`.

## 11. Limites connues
- Le « temps passé » est enregistré par l'heure du poste ; un changement d'heure pendant un chrono peut fausser cette durée d'une heure (corrigeable dans l'onglet Temps).
- Les tickets clos ne sont détectés que par leur disparition de l'export (ou un état listé dans `etats_clos`).
- Pas de multi-utilisateur : une seule personne à la fois sur la base.
