# Builds Killcam (app folder) and dist\KillcamSetup.exe (installer).
# Builds in a short temp path: PyInstaller output hits the 260-char path limit from deep folders.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$out = Join-Path $env:TEMP "kc"
Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
python -m PyInstaller --noconfirm --clean --onedir --windowed --name Killcam --icon "$PSScriptRoot\assets\killcam.ico" `
  --add-data "$PSScriptRoot\ui;ui" `
  --collect-all demoparser2 --collect-all polars --collect-all polars_runtime_32 `
  --hidden-import pyarrow --hidden-import pyarrow.lib --collect-binaries pyarrow `
  --collect-all webview --collect-all clr_loader --hidden-import clr `
  --hidden-import pycaw.pycaw --hidden-import comtypes.stream --hidden-import zstandard `
  --exclude-module polars.testing --exclude-module webview.platforms.android `
  --distpath "$out\dist" --workpath "$out\build" --specpath $out "$PSScriptRoot\killcam.py"
if ($LASTEXITCODE) { throw "PyInstaller failed" }
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "C:\Program Files (x86)\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
& $iscc /Q "/DAppDir=$out\dist\Killcam" "/O$PSScriptRoot\dist" installer.iss
if ($LASTEXITCODE) { throw "Inno Setup failed" }
Get-Item dist\KillcamSetup.exe | ForEach-Object { "{0} - {1:N0} MB" -f $_.Name, ($_.Length / 1MB) }
