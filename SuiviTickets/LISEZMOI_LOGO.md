# Logo centré en haut de l'application

Affiche le logo Cérèsia au milieu de la page, au-dessus des onglets.

## Installation (sans droits administrateur)
1. Fermez l'application (icône > Quitter, ou fermez la fenêtre noire).
2. Dézippez dans le dossier qui **contient** `SuiviTickets` :
   ```powershell
   cd C:\Users\thomas.bonhomme\Documents
   Expand-Archive -Path .\SuiviTickets_logo.zip -DestinationPath . -Force
   ```
3. Simulez, puis appliquez :
   ```powershell
   cd SuiviTickets
   .venv\Scripts\python.exe ajouter_logo.py --verifier
   .venv\Scripts\python.exe ajouter_logo.py
   ```
4. Relancez l'application, puis `Ctrl + F5` dans le navigateur.

Seul `app.py` est modifié, avec une sauvegarde `app.py.avant_logo`. Si le fichier ne correspond pas à la version attendue, rien n'est modifié. Votre base et `config.json` ne sont pas touchés. Le script peut être relancé sans risque.

**Pour annuler :** fermez l'application et recopiez `app.py.avant_logo` sur `app.py`.

## Changer le logo ou sa taille
- **Autre logo :** remplacez `assets\logo.png` (PNG, fond blanc ou transparent), puis `Ctrl + F5`. Sans ce fichier, aucun logo n'est affiché.
- **Taille :** le logo occupe la colonne centrale, soit 1/5 de la largeur de la page. Pour l'agrandir, dans `app.py`, changez `st.columns([2, 1, 2])` en `st.columns([1, 1, 1])` (1/3 de la largeur) ou `st.columns([3, 2, 3])`.
