@echo off
rem Lance le suivi des tickets en arriere-plan, avec une icone a cote de l'horloge (aucune fenetre noire).
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Environnement Python introuvable. Lancez d'abord install.ps1 puis install_tray.ps1 ^(voir LISEZMOI_ICONE.md^).
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0tray.py"
