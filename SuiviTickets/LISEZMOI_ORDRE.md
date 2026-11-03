# Ordre des colonnes mémorisé (tableau Tickets)

**Pourquoi l'ordre ne restait pas :** faire glisser un en-tête de colonne avec la souris ne change que l'affichage du navigateur. Il est perdu à chaque enregistrement ou rechargement de la page. Ce correctif enregistre l'ordre dans `config.json`.

## Installation (sans droits administrateur, ~2 minutes)
1. Fermez l'application (icône > Quitter, ou fermez la fenêtre noire).
2. Dézippez dans le dossier qui **contient** `SuiviTickets` :
   ```powershell
   Expand-Archive -Path .\SuiviTickets_ordre.zip -DestinationPath C:\Users\thomas.bonhomme\Documents -Force
   ```
3. Simulez, puis appliquez :
   ```powershell
   cd C:\Users\thomas.bonhomme\Documents\SuiviTickets
   .venv\Scripts\python.exe ajouter_ordre_colonnes.py --verifier
   .venv\Scripts\python.exe ajouter_ordre_colonnes.py
   ```
4. Relancez l'application.

Le script modifie `app.py` et `suivi\config.py`. Si l'un d'eux ne correspond pas à la version attendue, **rien n'est modifié** et il vous l'indique. Chaque fichier modifié est sauvegardé à côté sous le nom `<fichier>.avant_ordre`. Votre base de données n'est pas touchée. Le script peut être relancé sans risque.

**Pour annuler :** fermez l'application et recopiez chaque fichier `.avant_ordre` sur son original (sans l'extension `.avant_ordre`). Vous pouvez aussi supprimer la ligne `ordre_colonnes_tickets` de `config.json` pour revenir à l'ordre par défaut.

## Utilisation
Onglet **Paramètres > Ordre des colonnes du tableau Tickets** :
1. choisissez la colonne (par exemple « Lien ticket ») ;
2. indiquez sa position (2 = deuxième colonne) ;
3. cliquez sur **Déplacer la colonne**. L'ordre est enregistré et conservé après chaque enregistrement ou redémarrage.

« Remettre l'ordre par défaut » annule vos réglages.

## À savoir
- Une colonne ajoutée plus tard apparaît à la fin du tableau : déplacez-la ensuite.
- Une colonne masquée (Paramètres > Colonnes personnelles) disparaît de l'ordre ; à sa réactivation, elle revient à la fin.
- Si vous renommez une colonne, elle est considérée comme nouvelle et passe à la fin.
- Le glisser-déposer reste possible dans le tableau pour regarder autrement, mais n'est pas mémorisé.
- L'export Excel garde son propre ordre de colonnes.

## Tests
`.venv\Scripts\python.exe -m pytest -q tests\test_ordre_colonnes.py` (données fictives, votre base n'est pas touchée).
