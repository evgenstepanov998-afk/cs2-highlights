# Builds Killcam (app folder) and the installer:
#   .\build.ps1                -> dist\KillcamSetup.exe      (everyone, auto-updates)
#   .\build.ps1 -Channel demo  -> dist\KillcamDemoSetup.exe  (test build: own name, folders, no updates)
# Builds in a short temp path: PyInstaller output hits the 260-char path limit from deep folders.
param([ValidateSet("main", "demo")][string]$Channel = "main")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$name = if ($Channel -eq "demo") { "KillcamDemo" } else { "Killcam" }
$out = Join-Path $env:TEMP "kc"
Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
$channelFile = "$PSScriptRoot\highlights\channel.py"
$channelOrig = Get-Content $channelFile -Raw
try {
  [IO.File]::WriteAllText($channelFile, ($channelOrig -replace 'CHANNEL = "\w+"', "CHANNEL = `"$Channel`""))
  python -m PyInstaller --noconfirm --clean --onedir --windowed --name $name --icon "$PSScriptRoot\assets\killcam.ico" `
    --add-data "$PSScriptRoot\ui;ui" `
    --collect-all demoparser2 --collect-all polars --collect-all polars_runtime_32 `
    --hidden-import pyarrow --hidden-import pyarrow.lib --collect-binaries pyarrow `
    --collect-all webview --collect-all clr_loader --hidden-import clr `
    --hidden-import pycaw.pycaw --hidden-import comtypes.stream --hidden-import zstandard `
    --exclude-module polars.testing --exclude-module webview.platforms.android `
    --distpath "$out\dist" --workpath "$out\build" --specpath $out "$PSScriptRoot\killcam.py"
  if ($LASTEXITCODE) { throw "PyInstaller failed" }
} finally {
  [IO.File]::WriteAllText($channelFile, $channelOrig)  # the source tree always stays "main"
}
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "C:\Program Files (x86)\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
& $iscc /Q "/DAppDir=$out\dist\$name" "/DChannel=$Channel" "/O$PSScriptRoot\dist" installer.iss
if ($LASTEXITCODE) { throw "Inno Setup failed" }
Get-Item "dist\${name}Setup.exe" | ForEach-Object { "{0} - {1:N0} MB" -f $_.Name, ($_.Length / 1MB) }
