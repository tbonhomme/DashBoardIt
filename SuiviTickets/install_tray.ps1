<#
.SYNOPSIS
  Ajoute l'icone a cote de l'horloge (plus de fenetre noire) a l'application Suivi des tickets.

.DESCRIPTION
  - Installe 2 composants dans le .venv existant (pystray, pillow). Aucun droit administrateur.
  - Cree un raccourci "Suivi des tickets" sur le Bureau qui lance l'application sans fenetre.
  - Avec -Demarrage : cree aussi un raccourci dans le dossier Demarrage de votre profil
    (l'application se lance a l'ouverture de session, sans ouvrir le navigateur).
  - Ne modifie ni le registre, ni les variables d'environnement, ni vos donnees.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install_tray.ps1
  powershell -ExecutionPolicy Bypass -File .\install_tray.ps1 -Demarrage
#>
[CmdletBinding()]
param(
    [switch]$Demarrage
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Fail($msg) { Write-Host "ERREUR : $msg" -ForegroundColor Red; exit 1 }

$py  = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$pyw = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
$tray = Join-Path $PSScriptRoot 'tray.py'
$ico  = Join-Path $PSScriptRoot 'assets\suivi.ico'

if (-not (Test-Path $py) -or -not (Test-Path $pyw)) { Fail "Environnement .venv introuvable. Lancez d'abord install.ps1." }
if (-not (Test-Path $tray)) { Fail "tray.py introuvable : le contenu de l'archive n'a pas ete copie dans ce dossier." }

Write-Host "Installation des composants de l'icone (pystray, pillow)..."
& $py -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail 'Installation en echec (reseau / proxy ?).' }

& $py -c "import pystray, PIL; print('Composants OK')"
if ($LASTEXITCODE -ne 0) { Fail 'Verification des composants en echec.' }

function New-Raccourci($dossier, $arguments) {
    $lnk = Join-Path $dossier 'Suivi des tickets.lnk'
    $sh = New-Object -ComObject WScript.Shell
    $s = $sh.CreateShortcut($lnk)
    $s.TargetPath = $pyw
    $s.Arguments = $arguments
    $s.WorkingDirectory = $PSScriptRoot
    $s.IconLocation = "$ico,0"
    $s.Description = 'Suivi des tickets'
    $s.Save()
    return $lnk
}

$bureau = [Environment]::GetFolderPath('Desktop')
$lnk = New-Raccourci $bureau ('"' + $tray + '"')
Write-Host "Raccourci cree : $lnk"

if ($Demarrage) {
    $demarrage = [Environment]::GetFolderPath('Startup')
    $lnk2 = New-Raccourci $demarrage ('"' + $tray + '" --sans-navigateur')
    Write-Host "Lancement automatique a l'ouverture de session : $lnk2"
}

Write-Host ''
Write-Host "Termine. Fermez toute fenetre noire ouverte avec lancer.bat, puis double-cliquez sur le raccourci 'Suivi des tickets'." -ForegroundColor Green
