@echo off
rem Lance le suivi des tickets (http://localhost:8501). Fermez cette fenetre pour arreter l'application.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Environnement Python introuvable. Lancez d'abord install.ps1 ^(voir README.md^).
    pause
    exit /b 1
)
start "" /b cmd /c "timeout /t 4 /nobreak >nul & start http://localhost:8501"
".venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501
if errorlevel 1 pause
