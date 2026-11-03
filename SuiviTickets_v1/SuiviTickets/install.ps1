<#
.SYNOPSIS
  Installe l'application "Suivi des tickets" (environnement Python local + dossiers + raccourci optionnel).

.DESCRIPTION
  - Cree un environnement virtuel .venv dans le dossier de l'application (aucun droit administrateur requis).
  - Installe les dependances de requirements.txt (acces a PyPI necessaire, ou proxy configure).
  - Cree les dossiers de travail et, avec -Raccourci, un raccourci sur le Bureau.
  - Ne modifie ni le registre, ni les variables d'environnement, ni le profil utilisateur.

.PARAMETER PythonExe
  Chemin d'un python.exe a utiliser (ex. Python portable : D:\Outils\python\python.exe).
  Par defaut : le lanceur "py -3" puis "python" du PATH.

.PARAMETER Raccourci
  Cree un raccourci "Suivi des tickets" sur le Bureau.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install.ps1 -Raccourci
#>
[CmdletBinding()]
param(
    [string]$PythonExe,
    [switch]$Raccourci
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Fail($msg) { Write-Host "ERREUR : $msg" -ForegroundColor Red; exit 1 }

# 1. Trouver Python (>= 3.10)
$python = $null
if ($PythonExe) {
    if (-not (Test-Path $PythonExe)) { Fail "Python introuvable : $PythonExe" }
    $python = @($PythonExe)
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $python = @('py', '-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = @('python')
} else {
    Fail "Python n'est pas installe. Installez Python 3.10+ (ou utilisez -PythonExe avec un Python portable)."
}
$exe  = $python[0]
$args0 = @(); if ($python.Count -gt 1) { $args0 = $python[1..($python.Count - 1)] }

$version = & $exe @args0 -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$version -lt [version]'3.10') { Fail "Python $version detecte : version 3.10 minimum requise." }
Write-Host "Python $version detecte."

# 2. Environnement virtuel
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    Write-Host 'Creation de l''environnement virtuel (.venv)...'
    & $exe @args0 -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail 'Creation du venv impossible.' }
}

# 3. Dependances
Write-Host 'Installation des dependances...'
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail 'Installation des dependances en echec (reseau / proxy ?).' }

# 4. Dossiers de travail
foreach ($d in 'depot', 'data', 'backups', 'exports', 'logs') { New-Item -ItemType Directory -Force -Path $d | Out-Null }

# 5. Verification
& .\.venv\Scripts\python.exe -c "import streamlit, pandas, plotly, xlsxwriter; print('Dependances OK')"
if ($LASTEXITCODE -ne 0) { Fail 'Verification des dependances en echec.' }

# 6. Raccourci (optionnel)
if ($Raccourci) {
    $bureau = [Environment]::GetFolderPath('Desktop')
    $lnk = Join-Path $bureau 'Suivi des tickets.lnk'
    $sh = New-Object -ComObject WScript.Shell
    $s = $sh.CreateShortcut($lnk)
    $s.TargetPath = Join-Path $PSScriptRoot 'lancer.bat'
    $s.WorkingDirectory = $PSScriptRoot
    $s.Save()
    Write-Host "Raccourci cree : $lnk"
}

Write-Host ''
Write-Host 'Installation terminee. Deposez un export CSV Jira dans le dossier "depot", puis lancez lancer.bat.' -ForegroundColor Green
