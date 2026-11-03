@echo off
rem Secours : arrete l'application et son icone si le menu de l'icone ne repond plus.
rem Ne touche qu'aux processus lances depuis le dossier .venv de cette application.
cd /d "%~dp0"
powershell -NoProfile -Command "$racine = (Get-Location).Path + '\.venv\'; Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($racine, [System.StringComparison]::OrdinalIgnoreCase) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo Application arretee.
pause
