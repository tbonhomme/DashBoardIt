# Icône à côté de l'horloge (sans fenêtre noire)

Ce complément remplace la fenêtre noire de `lancer.bat` par une icône dans la zone de notification de Windows.
Vos données, `config.json` et le code existant ne sont pas modifiés.

## Installation (sans droits administrateur)
1. Fermez l'application si elle tourne (fenêtre noire).
2. Dézippez dans le dossier de l'application, par exemple :
   ```powershell
   Expand-Archive -Path .\SuiviTickets_icone.zip -DestinationPath C:\Users\thomas.bonhomme\Documents -Force
   ```
   Seul `requirements.txt` est remplacé (2 composants ajoutés).
3. Dans PowerShell, dans le dossier de l'application :
   ```powershell
   cd C:\Users\thomas.bonhomme\Documents\SuiviTickets
   powershell -ExecutionPolicy Bypass -File .\install_tray.ps1
   ```
   Option : ajoutez `-Demarrage` pour lancer l'application automatiquement à l'ouverture de votre session.
4. Si PowerShell est bloqué : `.venv\Scripts\python.exe -m pip install -r requirements.txt`, puis double-clic sur `lancer_tray.bat`.

## Utilisation
- Double-clic sur le raccourci **Suivi des tickets** (ou `lancer_tray.bat`) : l'icône apparaît et le navigateur s'ouvre.
- Windows 11 range souvent l'icône sous la flèche « ^ » : faites-la glisser vers la barre pour la garder visible.
- **Clic gauche** : ouvre l'application. **Clic droit** : menu.

| Entrée du menu | Effet |
|---|---|
| Ouvrir le suivi des tickets | Ouvre `http://localhost:8501` |
| Chrono : ... / Arrêter le chrono | Affiche le chrono en cours et l'arrête (puis F5 dans la page) |
| Importer le dépôt maintenant | Importe les CSV du dossier de dépôt, avec une notification |
| Ouvrir le dossier de dépôt / de l'application / le journal | Raccourcis Explorateur |
| Quitter | Arrête le serveur. Si un chrono tourne : l'arrêter, le laisser tourner ou annuler |

La pastille rouge sur l'icône indique qu'un chrono tourne. L'infobulle (survol) affiche le ticket et la durée.

## Dépannage
| Symptôme | Piste |
|---|---|
| Rien ne s'affiche | Journaux : `logs\streamlit.log` (serveur) et `logs\suivi_tickets.log` (icône) |
| « Le port 8501 est déjà utilisé » | L'ancienne fenêtre noire (`lancer.bat`) tourne encore : fermez-la |
| L'icône ne répond plus | Double-clic sur `arreter_tout.bat` (arrête uniquement les processus du dossier `.venv`) |
| Le serveur redémarre en boucle | Après 3 tentatives, l'icône le signale et s'arrête ; consultez `logs\streamlit.log` |

`lancer.bat` reste disponible (avec fenêtre noire) en secours.

## Désactiver le lancement automatique
Appuyez sur `Windows + R`, tapez `shell:startup`, supprimez le raccourci « Suivi des tickets ».

## Tests
`.venv\Scripts\python.exe -m pytest -q tests\test_serveur.py` (données fictives, votre base n'est pas touchée).
